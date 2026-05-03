#!/usr/bin/env python3
"""ED Finder — EDDN Live Listener
Version: 1.1

Connects to the Elite Dangerous Data Network (EDDN) relay and processes
real-time events to keep the database current with new discoveries and
colonisation changes.

FIX in v1.1:
  • flush_pending() now only clears in-memory buffers AFTER the DB transaction
    succeeds.  Previously, buffers were cleared before the DB write, causing
    permanent data loss if the connection dropped or the transaction failed.
  • Row-level upsert errors inside flush_pending() are now logged at WARNING
    (not DEBUG) so data ingestion failures are visible in production logs.
  • Graceful shutdown: SIGTERM/SIGINT now triggers a final flush_pending() call
    so buffered events are not lost when the container stops.
  • stats_reporter now includes a per-minute error rate for easier alerting.
  • Bodies upsert block is now correctly inside the transaction scope (was
    accidentally outside in v1.0, meaning body writes were auto-committed
    individually and could not be rolled back on error).

Events handled:
  • Journal/FSSDiscoveryScan   — new system discovered
  • Journal/Scan               — body scanned
  • Journal/NavBeaconScan      — multiple bodies at once
  • Journal/Colonisation       — system being colonised
  • Journal/Location           — system population/economy updates
  • Journal/FSDJump            — system visited (updates coords)
  • Journal/SAASignalsFound    — bio/geo signal counts updated

Dirty flag strategy:
  Rather than recalculating ratings/clusters synchronously (slow),
  we set rating_dirty=TRUE and cluster_dirty=TRUE on affected systems.
  The background job (runs every 5 minutes) picks these up and recalculates.

EDDN relay: wss://eddn.edcd.io:4430/subscribe
"""

import os
import sys
import json
import time
import signal
import logging
import asyncio
import zlib
from datetime import datetime, timezone
from typing import Optional

import zmq
import zmq.asyncio
import asyncpg
import redis.asyncio as aioredis

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_DSN      = os.getenv('DATABASE_URL',  'postgresql://edfinder:edfinder@postgres:5432/edfinder')
REDIS_URL   = os.getenv('REDIS_URL',     'redis://redis:6379/0')
EDDN_RELAY  = os.getenv('EDDN_RELAY',   'tcp://eddn.edcd.io:9500')
LOG_LEVEL   = os.getenv('LOG_LEVEL',    'INFO')
LOG_FILE    = os.getenv('LOG_FILE',     '/data/logs/eddn.log')

EDDN_PUBSUB_CHANNEL = 'eddn_events'

# How often to flush dirty system recalculations (seconds)
DIRTY_FLUSH_INTERVAL = int(os.getenv('DIRTY_FLUSH_INTERVAL', '300'))  # 5 minutes

os.makedirs(os.path.dirname(os.path.abspath(LOG_FILE)), exist_ok=True)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger('eddn_listener')

# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------
_stats = {
    'events_received':  0,
    'events_processed': 0,
    'events_skipped':   0,
    'systems_upserted': 0,
    'bodies_upserted':  0,
    'errors':           0,
    'started_at':       time.time(),
}

# Batch buffer — accumulate DB writes, flush every N seconds
_pending_systems: dict = {}   # id64 -> dict
_pending_bodies:  list = []   # list of body dicts
_last_flush = time.time()
FLUSH_INTERVAL = 10  # seconds between DB batch writes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()

def safe_float(v) -> Optional[float]:
    try: return float(v) if v is not None else None
    except (TypeError, ValueError): return None

def safe_int(v) -> Optional[int]:
    try: return int(v) if v is not None else None
    except (TypeError, ValueError): return None

ECONOMY_MAP = {
    '$economy_agriculture;':  'Agriculture',
    '$economy_refinery;':     'Refinery',
    '$economy_industrial;':   'Industrial',
    '$economy_hightech;':     'HighTech',
    '$economy_military;':     'Military',
    '$economy_tourism;':      'Tourism',
    '$economy_extraction;':   'Extraction',
    '$economy_colony;':       'Colony',
    '$economy_terraforming;': 'Terraforming',
    '$economy_prison;':       'Prison',
    '$economy_carrier;':      'Carrier',
    '$economy_none;':         'None',
}

def norm_economy(v: Optional[str]) -> str:
    if not v: return 'Unknown'
    return ECONOMY_MAP.get(str(v).lower(), str(v).title().replace(' ', ''))

SCOOPABLE = {'O', 'B', 'A', 'F', 'G', 'K', 'M'}

def is_scoopable(spectral: Optional[str]) -> Optional[bool]:
    if not spectral: return None
    return spectral[0].upper() in SCOOPABLE


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------
async def handle_fss_discovery(pool: asyncpg.Pool, header: dict, message: dict):
    """FSSDiscoveryScan — new system found via FSS."""
    body = message.get('StarSystem') or message
    id64 = safe_int(body.get('SystemAddress') or body.get('id64'))
    if not id64: return

    _pending_systems[id64] = {
        'id64':    id64,
        'name':    body.get('StarSystem') or body.get('name', 'Unknown'),
        'x':       safe_float((body.get('StarPos') or [0, 0, 0])[0]),
        'y':       safe_float((body.get('StarPos') or [0, 0, 0])[1]),
        'z':       safe_float((body.get('StarPos') or [0, 0, 0])[2]),
        'economy': norm_economy(body.get('SystemEconomy') or body.get('primaryEconomy')),
        'pop':     safe_int(body.get('Population', 0)),
        'updated': utcnow(),
    }


async def handle_scan(pool: asyncpg.Pool, header: dict, message: dict):
    """Scan event — body scanned."""
    id64 = safe_int(message.get('SystemAddress'))
    if not id64: return

    body_name = message.get('BodyName', 'Unknown')
    subtype   = message.get('PlanetClass') or message.get('StarType', '')
    is_star   = 'StarType' in message

    # Mark parent system dirty for re-rating
    if id64 not in _pending_systems:
        _pending_systems[id64] = {'id64': id64, 'dirty': True, 'updated': utcnow()}

    # BodyID is the Spansh/journal body identifier — required as PK in bodies table.
    # Without it we cannot safely upsert; skip the body if missing.
    body_id = safe_int(message.get('BodyID'))
    if body_id is None:
        log.debug(f"Scan event missing BodyID for {body_name} in system {id64} — skipping body insert")
        return

    body_rec = {
        'id':             body_id,
        'system_id64':    id64,
        'name':           body_name,
        'body_type':      'Star' if is_star else 'Planet',
        'subtype':        subtype,
        'is_main_star':   message.get('DistanceFromArrivalLS', 999) < 0.1,
        'distance_from_star': safe_float(message.get('DistanceFromArrivalLS')),
        'radius':         safe_float(message.get('Radius')),
        'mass':           safe_float(message.get('MassEM')) if not is_star else None,
        'gravity':        safe_float(message.get('SurfaceGravity')),
        'surface_temp':   safe_float(message.get('SurfaceTemperature')),
        'surface_pressure': safe_float(message.get('SurfacePressure')),
        'volcanism':      message.get('Volcanism'),
        'atmosphere_type': message.get('AtmosphereType'),
        'is_landable':    bool(message.get('Landable', False)),
        'is_terraformable': message.get('TerraformState', '') not in ('', 'Not terraformable'),
        'is_earth_like':  str(subtype).lower() == 'earthlikebody' or 'earth-like' in str(subtype).lower(),
        'is_water_world': 'waterworld' in str(subtype).lower() or 'water world' in str(subtype).lower(),
        'is_ammonia_world': 'ammoniaworld' in str(subtype).lower() or 'ammonia world' in str(subtype).lower(),
        'is_tidal_lock':  bool(message.get('TidalLock', False)),
        'spectral_class': message.get('StarType'),
        'stellar_mass':   safe_float(message.get('StellarMass')) if is_star else None,
        'is_scoopable':   is_scoopable(message.get('StarType')),
        'estimated_mapping_value': safe_int(message.get('EstimatedMappingValue') or message.get('MappedValue')),
        'estimated_scan_value':    safe_int(message.get('EstimatedScanValue')),
        'updated_at':     utcnow(),
    }

    if message.get('Materials'):
        body_rec['materials'] = json.dumps({
            m['Name']: m['Percent'] for m in message['Materials']
        })

    _pending_bodies.append(body_rec)


async def handle_saa_signals(pool: asyncpg.Pool, header: dict, message: dict):
    """SAASignalsFound — biological/geological signal counts."""
    id64 = safe_int(message.get('SystemAddress'))
    if not id64: return

    bio_count = 0
    geo_count = 0
    for sig in message.get('Signals', []):
        sig_type = str(sig.get('Type', '')).lower()
        count    = safe_int(sig.get('Count', 0)) or 0
        if 'biological' in sig_type:
            bio_count += count
        elif 'geological' in sig_type:
            geo_count += count

    if bio_count > 0 or geo_count > 0:
        body_name = message.get('BodyName', '')
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE bodies
                SET bio_signal_count = GREATEST(bio_signal_count, $1),
                    geo_signal_count = GREATEST(geo_signal_count, $2),
                    updated_at       = NOW()
                WHERE name = $3 AND system_id64 = $4
            """, bio_count, geo_count, body_name, id64)
            await conn.execute("""
                UPDATE systems SET rating_dirty = TRUE, cluster_dirty = TRUE
                WHERE id64 = $1
            """, id64)


async def handle_location_or_jump(pool: asyncpg.Pool, header: dict, message: dict):
    """Location / FSDJump — update system economy / population from live game."""
    id64 = safe_int(message.get('SystemAddress'))
    if not id64: return

    pop    = safe_int(message.get('Population', 0))
    eco    = norm_economy(message.get('SystemEconomy'))
    name   = message.get('StarSystem')
    coords = message.get('StarPos', [None, None, None])

    upd = {'id64': id64, 'dirty': True, 'updated': utcnow()}
    if pop is not None: upd['pop'] = pop
    if eco != 'Unknown': upd['economy'] = eco
    if name: upd['name'] = name
    if coords[0] is not None:
        upd['x'] = safe_float(coords[0])
        upd['y'] = safe_float(coords[1])
        upd['z'] = safe_float(coords[2])

    existing = _pending_systems.get(id64, {})
    existing.update(upd)
    _pending_systems[id64] = existing


# ---------------------------------------------------------------------------
# Batch DB flush
# ---------------------------------------------------------------------------
async def flush_pending(pool: asyncpg.Pool):
    """
    Flush pending systems and bodies to DB in a single transaction.

    FIX v1.1: Buffers are now only cleared AFTER the transaction succeeds.
    Previously they were cleared at the start of this function, so any DB
    error (connection drop, constraint violation, timeout) would silently
    discard all buffered EDDN events — permanent data loss.

    Also fixed: bodies upsert is now correctly inside the transaction block.
    Previously it was accidentally outside, meaning body writes were
    auto-committed individually and could not be rolled back on error.
    """
    global _pending_systems, _pending_bodies, _last_flush

    # Take a snapshot of current buffer contents — do NOT clear globals yet.
    # We track the IDs/indices we attempted so we can remove only those on success.
    systems_snapshot = list(_pending_systems.values())
    system_ids       = list(_pending_systems.keys())
    bodies_snapshot  = list(_pending_bodies)
    n_bodies         = len(bodies_snapshot)

    if not systems_snapshot and not bodies_snapshot:
        _last_flush = time.time()
        return

    flushed_systems = 0
    flushed_bodies  = 0
    flush_errors    = 0

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                # ── Upsert systems ────────────────────────────────────────
                for sys in systems_snapshot:
                    try:
                        await conn.execute("""
                            INSERT INTO systems (
                                id64, name, x, y, z,
                                primary_economy, population,
                                rating_dirty, cluster_dirty,
                                eddn_updated_at, updated_at
                            ) VALUES ($1,$2,$3,$4,$5,$6::economy_type,$7,TRUE,TRUE,NOW(),NOW())
                            ON CONFLICT (id64) DO UPDATE SET
                                name            = COALESCE(NULLIF($2,'Unknown'), systems.name),
                                x               = COALESCE($3, systems.x),
                                y               = COALESCE($4, systems.y),
                                z               = COALESCE($5, systems.z),
                                primary_economy = CASE WHEN $6 != 'Unknown'
                                                       THEN $6::economy_type
                                                       ELSE systems.primary_economy END,
                                population      = COALESCE($7, systems.population),
                                rating_dirty    = TRUE,
                                cluster_dirty   = TRUE,
                                eddn_updated_at = NOW(),
                                updated_at      = NOW()
                        """,
                            sys['id64'],
                            sys.get('name', 'Unknown'),
                            sys.get('x', 0),
                            sys.get('y', 0),
                            sys.get('z', 0),
                            sys.get('economy', 'Unknown'),
                            sys.get('pop', 0),
                        )
                        flushed_systems += 1
                        _stats['systems_upserted'] += 1
                    except Exception as e:
                        flush_errors += 1
                        _stats['errors'] += 1
                        log.warning(f"System upsert error (id64={sys.get('id64')}): {e}")

                # ── Upsert bodies (inside same transaction) ───────────────
                # 'id' (BodyID) is required as PK; bodies without it are already
                # filtered out in handle_scan() before reaching this point.
                for body in bodies_snapshot:
                    try:
                        await conn.execute("""
                            INSERT INTO bodies (
                                id, system_id64, name, body_type, subtype, is_main_star,
                                distance_from_star, radius, mass, gravity,
                                surface_temp, surface_pressure, volcanism, atmosphere_type,
                                is_landable, is_terraformable,
                                is_earth_like, is_water_world, is_ammonia_world,
                                is_tidal_lock, spectral_class, stellar_mass, is_scoopable,
                                estimated_mapping_value, estimated_scan_value, updated_at
                            ) VALUES (
                                $1,$2,$3,$4::body_type,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,
                                $15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,NOW()
                            )
                            ON CONFLICT (id) DO UPDATE SET
                                subtype           = COALESCE(EXCLUDED.subtype, bodies.subtype),
                                is_landable       = EXCLUDED.is_landable,
                                is_terraformable  = EXCLUDED.is_terraformable,
                                is_earth_like     = EXCLUDED.is_earth_like,
                                is_water_world    = EXCLUDED.is_water_world,
                                is_ammonia_world  = EXCLUDED.is_ammonia_world,
                                surface_temp      = COALESCE(EXCLUDED.surface_temp, bodies.surface_temp),
                                updated_at        = NOW()
                        """,
                            body['id'], body['system_id64'], body['name'],
                            body.get('body_type', 'Unknown'),
                            body.get('subtype'), body.get('is_main_star', False),
                            body.get('distance_from_star'),
                            body.get('radius'), body.get('mass'), body.get('gravity'),
                            body.get('surface_temp'), body.get('surface_pressure'),
                            body.get('volcanism'), body.get('atmosphere_type'),
                            body.get('is_landable', False), body.get('is_terraformable', False),
                            body.get('is_earth_like', False), body.get('is_water_world', False),
                            body.get('is_ammonia_world', False), body.get('is_tidal_lock'),
                            body.get('spectral_class'), body.get('stellar_mass'),
                            body.get('is_scoopable'),
                            body.get('estimated_mapping_value'), body.get('estimated_scan_value'),
                        )
                        flushed_bodies += 1
                        _stats['bodies_upserted'] += 1
                    except Exception as e:
                        flush_errors += 1
                        _stats['errors'] += 1
                        log.warning(f"Body upsert error (id={body.get('id')}): {e}")

        # ── Transaction succeeded — NOW clear the flushed items ───────────
        # Remove only the system IDs we attempted; any new ones that arrived
        # during the DB write are preserved for the next flush.
        for sid in system_ids:
            _pending_systems.pop(sid, None)
        # Remove the first n_bodies entries (those we snapshotted).
        # New bodies appended during the flush are preserved.
        del _pending_bodies[:n_bodies]
        _last_flush = time.time()

        if flush_errors:
            log.warning(
                f"Flushed {flushed_systems} systems + {flushed_bodies} bodies "
                f"({flush_errors} row-level errors — check WARNING logs above)"
            )
        else:
            log.info(f"Flushed {flushed_systems} systems + {flushed_bodies} bodies to DB")

    except Exception as e:
        # The whole transaction failed — buffers are NOT cleared.
        # The data will be retried on the next flush interval.
        _last_flush = time.time()  # reset timer to avoid tight retry loop
        log.error(
            f"flush_pending FAILED — {len(systems_snapshot)} systems + "
            f"{len(bodies_snapshot)} bodies retained in buffer for next retry: {e}"
        )


# ---------------------------------------------------------------------------
# Background job: report dirty counts
# ---------------------------------------------------------------------------
async def dirty_recalc_job(pool: asyncpg.Pool):
    """
    Every DIRTY_FLUSH_INTERVAL seconds, report how many systems need
    ratings/cluster recalculation.  The actual rebuild is handled by
    build_ratings.py --dirty and build_clusters.py --dirty-only.
    """
    while True:
        await asyncio.sleep(DIRTY_FLUSH_INTERVAL)
        try:
            async with pool.acquire() as conn:
                dirty_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM systems WHERE rating_dirty = TRUE OR cluster_dirty = TRUE"
                )
                if dirty_count == 0:
                    continue
                if dirty_count < 10000:
                    log.info(
                        f"{dirty_count} dirty systems — queued for next build_ratings.py --dirty run. "
                        f"Run manually: python3 build_ratings.py --dirty"
                    )
                else:
                    log.warning(
                        f"{dirty_count:,} dirty systems — run: python3 build_ratings.py --dirty"
                    )
        except Exception as e:
            log.error(f"Dirty recalc job error: {e}")


# ---------------------------------------------------------------------------
# Stats reporter
# ---------------------------------------------------------------------------
async def stats_reporter():
    while True:
        await asyncio.sleep(60)
        uptime_min = (time.time() - _stats['started_at']) / 60
        rate       = _stats['events_received'] / max(uptime_min, 1)
        err_rate   = _stats['errors'] / max(uptime_min, 1)
        log.info(
            f"EDDN stats | "
            f"events: {_stats['events_received']:,} ({rate:.0f}/min) | "
            f"processed: {_stats['events_processed']:,} | "
            f"systems: {_stats['systems_upserted']:,} | "
            f"bodies: {_stats['bodies_upserted']:,} | "
            f"errors: {_stats['errors']:,} ({err_rate:.2f}/min) | "
            f"pending: {len(_pending_systems)} sys / {len(_pending_bodies)} bodies"
        )


# ---------------------------------------------------------------------------
# Main EDDN loop
# ---------------------------------------------------------------------------
EVENT_HANDLERS = {
    'https://eddn.edcd.io/schemas/fssdiscoveryscan/1':  handle_fss_discovery,
    'https://eddn.edcd.io/schemas/scan/1':              handle_scan,
    'https://eddn.edcd.io/schemas/saasignalsfound/1':   handle_saa_signals,
    'https://eddn.edcd.io/schemas/journal/1':           None,  # handled by event type below
    'https://eddn.edcd.io/schemas/fssallbodiesfound/1': None,
}

JOURNAL_HANDLERS = {
    'FSSDiscoveryScan': handle_fss_discovery,
    'Scan':             handle_scan,
    'SAASignalsFound':  handle_saa_signals,
    'Location':         handle_location_or_jump,
    'FSDJump':          handle_location_or_jump,
    'CarrierJump':      handle_location_or_jump,
}


async def run_eddn_listener(pool: asyncpg.Pool, redis: Optional[aioredis.Redis] = None):
    """Main EDDN subscriber loop."""
    context = zmq.asyncio.Context()
    subscriber = context.socket(zmq.SUB)
    subscriber.setsockopt(zmq.SUBSCRIBE, b'')
    subscriber.setsockopt(zmq.RCVTIMEO, 600000)  # 10 min timeout
    subscriber.connect(EDDN_RELAY)
    log.info(f"EDDN listener connected to {EDDN_RELAY}")

    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO app_meta (key, value, updated_at) VALUES ('eddn_enabled','true',NOW())
            ON CONFLICT (key) DO UPDATE SET value='true', updated_at=NOW()
        """)

    while True:
        try:
            raw = await subscriber.recv()
            data = zlib.decompress(raw)
            event = json.loads(data)
            _stats['events_received'] += 1

            schema  = event.get('$schemaRef', '')
            header  = event.get('header', {})
            message = event.get('message', {})

            handler = EVENT_HANDLERS.get(schema)
            if schema.startswith('https://eddn.edcd.io/schemas/journal'):
                event_type = message.get('event')
                handler = JOURNAL_HANDLERS.get(event_type)

            if handler:
                await handler(pool, header, message)
                _stats['events_processed'] += 1
                # Publish a compact event summary to Redis so the API
                # container's SSE endpoint can fan it out to connected
                # clients in real time.
                if redis is not None:
                    try:
                        summary = {
                            'system_name': message.get('StarSystem') or message.get('BodyName'),
                            'id64':        safe_int(message.get('SystemAddress')),
                            'type':        message.get('event') or schema.rsplit('/', 1)[-1],
                            'timestamp':   utcnow(),
                        }
                        await redis.publish(EDDN_PUBSUB_CHANNEL, json.dumps(summary, default=str))
                    except Exception as e:
                        log.debug(f"Pub/sub publish failed (non-fatal): {e}")
            else:
                _stats['events_skipped'] += 1

            if time.time() - _last_flush > FLUSH_INTERVAL:
                await flush_pending(pool)

        except zmq.error.Again:
            log.warning("EDDN timeout — no data for 10 minutes, reconnecting ...")
            subscriber.close()
            await asyncio.sleep(5)
            subscriber = context.socket(zmq.SUB)
            subscriber.setsockopt(zmq.SUBSCRIBE, b'')
            subscriber.setsockopt(zmq.RCVTIMEO, 600000)
            subscriber.connect(EDDN_RELAY)

        except Exception as e:
            _stats['errors'] += 1
            log.error(f"EDDN error: {e}")
            await asyncio.sleep(1)


async def main():
    pool = await asyncpg.create_pool(
        dsn=DB_DSN, min_size=3, max_size=10, command_timeout=30,
        # Required for pgBouncer transaction-pool mode.
        statement_cache_size=0,
    )
    log.info("PostgreSQL pool ready")

    # Optional Redis client for publishing live events to the API's SSE bridge.
    redis: Optional[aioredis.Redis] = None
    try:
        redis = aioredis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
            retry_on_timeout=True,
        )
        await redis.ping()
        log.info(f"Redis connected ✓ ({REDIS_URL}) — EDDN events will be published on channel {EDDN_PUBSUB_CHANNEL}")
    except Exception as e:
        log.warning(f"Redis unavailable ({e}) — live SSE feed will be disabled")
        redis = None

    loop = asyncio.get_running_loop()

    # ── Graceful shutdown on SIGTERM/SIGINT ──────────────────────────────────
    # FIX v1.1: Flush any buffered events before the process exits so that
    # a Docker stop / container restart does not silently discard live data.
    async def _shutdown(sig_name: str):
        log.info(f"Received {sig_name} — flushing pending events before shutdown ...")
        try:
            await flush_pending(pool)
            log.info("Final flush complete.")
        except Exception as e:
            log.error(f"Final flush failed: {e}")
        finally:
            if redis is not None:
                try:
                    await redis.aclose()
                except Exception:
                    pass
            for task in asyncio.all_tasks(loop):
                task.cancel()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig, lambda s=sig.name: asyncio.create_task(_shutdown(s))
        )

    await asyncio.gather(
        run_eddn_listener(pool, redis),
        dirty_recalc_job(pool),
        stats_reporter(),
    )


if __name__ == '__main__':
    asyncio.run(main())
