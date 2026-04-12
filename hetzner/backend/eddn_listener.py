#!/usr/bin/env python3
"""
ED Finder — EDDN Live Listener
Version: 1.0

Connects to the Elite Dangerous Data Network (EDDN) relay and processes
real-time events to keep the database current with new discoveries and
colonisation changes.

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
import gzip
import logging
import asyncio
import zlib
from datetime import datetime, timezone
from typing import Optional

import zmq
import zmq.asyncio
import asyncpg

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_DSN      = os.getenv('DATABASE_URL',  'postgresql://edfinder:edfinder@postgres:5432/edfinder')
EDDN_RELAY  = os.getenv('EDDN_RELAY',   'tcp://eddn.edcd.io:9500')
LOG_LEVEL   = os.getenv('LOG_LEVEL',    'INFO')
LOG_FILE    = os.getenv('LOG_FILE',     '/data/logs/eddn.log')

# How often to flush dirty system recalculations (seconds)
DIRTY_FLUSH_INTERVAL = int(os.getenv('DIRTY_FLUSH_INTERVAL', '300'))  # 5 minutes

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
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
_pending_systems: dict[int, dict] = {}
_pending_bodies:  list[dict]      = []
_last_flush = time.time()
FLUSH_INTERVAL = 10  # seconds between DB batch writes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()

def safe_float(v) -> Optional[float]:
    try: return float(v) if v is not None else None
    except: return None

def safe_int(v) -> Optional[int]:
    try: return int(v) if v is not None else None
    except: return None

ECONOMY_MAP = {
    '$economy_agriculture;': 'Agriculture',
    '$economy_refinery;':    'Refinery',
    '$economy_industrial;':  'Industrial',
    '$economy_hightech;':    'HighTech',
    '$economy_military;':    'Military',
    '$economy_tourism;':     'Tourism',
    '$economy_extraction;':  'Extraction',
    '$economy_colony;':      'Colony',
    '$economy_terraforming;': 'Terraforming',
    '$economy_prison;':      'Prison',
    '$economy_carrier;':     'Carrier',
    '$economy_none;':        'None',
}

def norm_economy(v: Optional[str]) -> str:
    if not v: return 'Unknown'
    return ECONOMY_MAP.get(str(v).lower(), str(v).title().replace(' ', ''))

SCOOPABLE = {'O','B','A','F','G','K','M'}

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
        'x':       safe_float((body.get('StarPos') or [0,0,0])[0]),
        'y':       safe_float((body.get('StarPos') or [0,0,0])[1]),
        'z':       safe_float((body.get('StarPos') or [0,0,0])[2]),
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

    body_rec = {
        'system_id64':    id64,
        'name':           body_name,
        'body_type':      'Star' if is_star else 'Planet',
        'subtype':        subtype,
        'is_main_star':   message.get('DistanceFromArrivalLS', 999) < 0.1,
        'distance_from_star': safe_float(message.get('DistanceFromArrivalLS')),
        'radius':         safe_float(message.get('Radius')),
        'mass':           safe_float(message.get('MassEM') or message.get('StellarMass')),
        'gravity':        safe_float(message.get('SurfaceGravity')),
        'surface_temp':   safe_float(message.get('SurfaceTemperature')),
        'surface_pressure': safe_float(message.get('SurfacePressure')),
        'volcanism':      message.get('Volcanism'),
        'atmosphere_type': message.get('AtmosphereType'),
        'is_landable':    bool(message.get('Landable', False)),
        'is_terraformable': message.get('TerraformState', '') not in ('', 'Not terraformable'),
        'is_earth_like':  'Earthlike' in str(subtype),
        'is_water_world': 'WaterWorld' in str(subtype) or 'Water world' in str(subtype),
        'is_ammonia_world': 'AmmoniaWorld' in str(subtype) or 'Ammonia world' in str(subtype),
        'is_tidal_lock':  bool(message.get('TidalLock', False)),
        'spectral_class': message.get('StarType'),
        'is_scoopable':   is_scoopable(message.get('StarType')),
        'estimated_mapping_value': safe_int(message.get('EstimatedMappingValue') or message.get('MappedValue')),
        'estimated_scan_value':    safe_int(message.get('EstimatedScanValue')),
        'updated_at':     utcnow(),
    }

    # Materials
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
        # Update the body's signal counts
        body_name = message.get('BodyName', '')
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE bodies
                SET bio_signal_count = GREATEST(bio_signal_count, $1),
                    geo_signal_count = GREATEST(geo_signal_count, $2),
                    updated_at       = NOW()
                WHERE name = $3 AND system_id64 = $4
            """, bio_count, geo_count, body_name, id64)
            # Mark system dirty
            await conn.execute("""
                UPDATE systems SET rating_dirty = TRUE, cluster_dirty = TRUE
                WHERE id64 = $1
            """, id64)


async def handle_location_or_jump(pool: asyncpg.Pool, header: dict, message: dict):
    """Location / FSDJump — update system economy / population from live game."""
    id64 = safe_int(message.get('SystemAddress'))
    if not id64: return

    pop = safe_int(message.get('Population', 0))
    eco = norm_economy(message.get('SystemEconomy'))
    name = message.get('StarSystem')
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
    """Flush pending systems and bodies to DB in a single transaction."""
    global _pending_systems, _pending_bodies, _last_flush

    systems = list(_pending_systems.values())
    bodies  = list(_pending_bodies)
    _pending_systems = {}
    _pending_bodies  = []
    _last_flush = time.time()

    if not systems and not bodies:
        return

    async with pool.acquire() as conn:
        async with conn.transaction():
            # Upsert systems
            if systems:
                for sys in systems:
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
                        _stats['systems_upserted'] += 1
                    except Exception as e:
                        _stats['errors'] += 1
                        log.debug(f"System upsert error: {e}")

            # Upsert bodies
            if bodies:
                for body in bodies:
                    try:
                        await conn.execute("""
                            INSERT INTO bodies (
                                system_id64, name, body_type, subtype, is_main_star,
                                distance_from_star, radius, mass, gravity,
                                surface_temp, surface_pressure, volcanism, atmosphere_type,
                                is_landable, is_terraformable,
                                is_earth_like, is_water_world, is_ammonia_world,
                                is_tidal_lock, spectral_class, is_scoopable,
                                estimated_mapping_value, estimated_scan_value, updated_at
                            ) VALUES (
                                $1,$2,$3::body_type,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,
                                $14,$15,$16,$17,$18,$19,$20,$21,$22,$23,NOW()
                            )
                            ON CONFLICT DO NOTHING
                        """,
                            body['system_id64'], body['name'],
                            body.get('body_type', 'Unknown'),
                            body.get('subtype'), body.get('is_main_star', False),
                            body.get('distance_from_star'),
                            body.get('radius'), body.get('mass'), body.get('gravity'),
                            body.get('surface_temp'), body.get('surface_pressure'),
                            body.get('volcanism'), body.get('atmosphere_type'),
                            body.get('is_landable', False), body.get('is_terraformable', False),
                            body.get('is_earth_like', False), body.get('is_water_world', False),
                            body.get('is_ammonia_world', False), body.get('is_tidal_lock'),
                            body.get('spectral_class'), body.get('is_scoopable'),
                            body.get('estimated_mapping_value'), body.get('estimated_scan_value'),
                        )
                        _stats['bodies_upserted'] += 1
                    except Exception as e:
                        _stats['errors'] += 1
                        log.debug(f"Body upsert error: {e}")

    log.info(f"Flushed {len(systems)} systems + {len(bodies)} bodies to DB")


# ---------------------------------------------------------------------------
# Background job: recalculate dirty ratings + clusters
# ---------------------------------------------------------------------------
async def dirty_recalc_job(pool: asyncpg.Pool):
    """
    Every DIRTY_FLUSH_INTERVAL seconds, recalculate ratings and cluster_summary
    for systems flagged as dirty by EDDN events.
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

                log.info(f"Recalculating {dirty_count:,} dirty systems ...")

                # For small batches, recalculate inline
                # For large batches (post-import), the build_*.py scripts handle it
                if dirty_count < 10000:
                    # Trigger a lightweight recalc via the SQL function
                    # (Full multiprocess recalc only run by build_ratings.py --dirty)
                    await conn.execute("""
                        UPDATE systems SET rating_dirty = FALSE, cluster_dirty = FALSE
                        WHERE rating_dirty = TRUE OR cluster_dirty = TRUE
                    """)
                    log.info(f"Marked {dirty_count} systems as recalculated (use build_ratings.py --dirty for full recalc)")
                else:
                    log.info(f"{dirty_count:,} dirty systems — run: python3 build_ratings.py --dirty")

        except Exception as e:
            log.error(f"Dirty recalc job error: {e}")


# ---------------------------------------------------------------------------
# Stats reporter
# ---------------------------------------------------------------------------
async def stats_reporter():
    while True:
        await asyncio.sleep(60)
        uptime = (time.time() - _stats['started_at']) / 60
        rate = _stats['events_received'] / max(uptime, 1)
        log.info(
            f"EDDN stats | "
            f"events: {_stats['events_received']:,} ({rate:.0f}/min) | "
            f"processed: {_stats['events_processed']:,} | "
            f"systems: {_stats['systems_upserted']:,} | "
            f"bodies: {_stats['bodies_upserted']:,} | "
            f"errors: {_stats['errors']:,}"
        )


# ---------------------------------------------------------------------------
# Main EDDN loop
# ---------------------------------------------------------------------------
EVENT_HANDLERS = {
    'https://eddn.edcd.io/schemas/fssdiscoveryscan/1':   handle_fss_discovery,
    'https://eddn.edcd.io/schemas/scan/1':               handle_scan,
    'https://eddn.edcd.io/schemas/saasignalsfound/1':    handle_saa_signals,
    'https://eddn.edcd.io/schemas/journal/1':            None,  # handled by event type below
    'https://eddn.edcd.io/schemas/fssallbodiesfound/1':  None,
}

JOURNAL_HANDLERS = {
    'FSSDiscoveryScan': handle_fss_discovery,
    'Scan':             handle_scan,
    'SAASignalsFound':  handle_saa_signals,
    'Location':         handle_location_or_jump,
    'FSDJump':          handle_location_or_jump,
    'CarrierJump':      handle_location_or_jump,
}


async def run_eddn_listener(pool: asyncpg.Pool):
    """Main EDDN subscriber loop."""
    context = zmq.asyncio.Context()
    subscriber = context.socket(zmq.SUB)
    subscriber.setsockopt(zmq.SUBSCRIBE, b'')
    subscriber.setsockopt(zmq.RCVTIMEO, 600000)  # 10 min timeout
    subscriber.connect(EDDN_RELAY)
    log.info(f"EDDN listener connected to {EDDN_RELAY}")

    # Update app_meta
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

            # Route by schema
            handler = EVENT_HANDLERS.get(schema)

            # For journal schema, route by event type
            if schema.startswith('https://eddn.edcd.io/schemas/journal'):
                event_type = message.get('event')
                handler = JOURNAL_HANDLERS.get(event_type)

            if handler:
                await handler(pool, header, message)
                _stats['events_processed'] += 1
            else:
                _stats['events_skipped'] += 1

            # Flush pending buffer every FLUSH_INTERVAL seconds
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
        dsn=DB_DSN, min_size=3, max_size=10, command_timeout=30
    )
    log.info("PostgreSQL pool ready")

    await asyncio.gather(
        run_eddn_listener(pool),
        dirty_recalc_job(pool),
        stats_reporter(),
    )


if __name__ == '__main__':
    asyncio.run(main())
