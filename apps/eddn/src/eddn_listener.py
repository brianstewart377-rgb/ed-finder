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
DB_DSN      = os.environ['DATABASE_URL']  # fail-fast: no insecure 'edfinder:edfinder' fallback
REDIS_URL   = os.getenv('REDIS_URL',     'redis://redis:6379/0')
EDDN_RELAY  = os.getenv('EDDN_RELAY',   'tcp://eddn.edcd.io:9500')
LOG_LEVEL   = os.getenv('LOG_LEVEL',    'INFO')
LOG_FILE    = os.getenv('LOG_FILE',     '/data/logs/eddn.log')
# Set LOG_FORMAT=json to emit each log record as a single-line JSON
# document (required for ingest into Loki / ES / CloudWatch / etc.
# without grok-parsing the human-friendly default).
LOG_FORMAT  = os.getenv('LOG_FORMAT',   'text').lower()
# Bind a Prometheus text-exposition server on this port. Disable by
# setting METRICS_PORT=0. Production prometheus.yml scrapes this.
METRICS_PORT = int(os.getenv('METRICS_PORT', '9091'))

EDDN_PUBSUB_CHANNEL = 'eddn_events'

# How often to flush dirty system recalculations (seconds)
DIRTY_FLUSH_INTERVAL = int(os.getenv('DIRTY_FLUSH_INTERVAL', '300'))  # 5 minutes

os.makedirs(os.path.dirname(os.path.abspath(LOG_FILE)), exist_ok=True)


class _JsonFormatter(logging.Formatter):
    """Single-line JSON formatter, compatible with structured-log shippers.

    Produces the keys: ``ts``, ``level``, ``logger``, ``msg``, plus any
    ``extra={...}`` dict the caller passed. Stack traces are emitted as a
    string under ``exc_info`` so the output stays one record per line.
    """
    _RESERVED = {
        'name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
        'filename', 'module', 'exc_info', 'exc_text', 'stack_info',
        'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
        'thread', 'threadName', 'processName', 'process', 'message',
        'asctime',
    }

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        payload = {
            'ts':     datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            'level':  record.levelname,
            'logger': record.name,
            'msg':    record.getMessage(),
        }
        # Pass-through any caller-supplied extras
        for k, v in record.__dict__.items():
            if k not in self._RESERVED and not k.startswith('_'):
                payload[k] = v
        if record.exc_info:
            payload['exc_info'] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


_handlers = [
    logging.FileHandler(LOG_FILE),
    logging.StreamHandler(sys.stdout),
]
if LOG_FORMAT == 'json':
    for h in _handlers:
        h.setFormatter(_JsonFormatter())
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        handlers=_handlers,
    )
else:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=_handlers,
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
    'rings_upserted':   0,
    'errors':           0,
    'started_at':       time.time(),
}

# Batch buffer — accumulate DB writes, flush every N seconds
_pending_systems: dict = {}   # id64 -> dict
_pending_bodies:  list = []   # list of body dicts
_pending_rings:   list = []   # list of provenance-backed body ring dicts
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
    # Full-name forms (what some emitters send)
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
    # Abbreviated forms (what live Frontier journal events actually emit)
    '$economy_agri;':         'Agriculture',
    '$economy_hitech;':       'HighTech',
    # Live forms that aren't represented in the economy_type enum yet —
    # map them to 'None' so the row inserts cleanly. Add new enum values
    # later if these become important to filter on.
    '$economy_service;':      'None',
    '$economy_repair;':       'Repair',
    '$economy_rescue;':       'Rescue',
    '$economy_damaged;':      'Damaged',
}

# Postgres economy_type enum — used by norm_economy's fallback to drop
# anything we don't recognise rather than poison the transaction with an
# 'invalid input value for enum economy_type' error. Mirror sql/001.
_ECONOMY_ENUM_VALUES = {
    'Agriculture', 'Refinery', 'Industrial', 'HighTech',
    'Military', 'Tourism', 'Extraction', 'Colony',
    'Terraforming', 'Prison', 'Damaged', 'Rescue',
    'Repair', 'Carrier', 'None', 'Unknown',
}

def norm_economy(v: Optional[str]) -> str:
    """Normalise an economy string to a value the economy_type enum accepts.

    Handles three input shapes:
      • Full Frontier journal form: '$Economy_Agri;'    → 'Agriculture'
      • Already-clean enum value:   'HighTech'          → 'HighTech'
      • Plain title-case word:      'Industrial'        → 'Industrial'

    Anything we don't recognise falls back to 'Unknown' rather than the
    raw string — that way one weird payload can't abort the whole batch
    upsert with 'invalid input value for enum economy_type'.
    """
    if not v: return 'Unknown'
    s = str(v).strip().lower()
    # Fast path: explicit map covers all known $economy_*; forms.
    if s in ECONOMY_MAP:
        return ECONOMY_MAP[s]
    # Generic Frontier-form fallback: $economy_<word>; → <Word>
    if s.startswith('$economy_'):
        s = s[len('$economy_'):]
    if s.endswith(';'):
        s = s[:-1]
    # Try title-cased match against the enum (handles 'Industrial', 'Tourism', etc.).
    candidate = s.replace('_', '').title() if '_' in s else s.title()
    if candidate in _ECONOMY_ENUM_VALUES:
        return candidate
    return 'Unknown'

SCOOPABLE = {'O', 'B', 'A', 'F', 'G', 'K', 'M'}

def is_scoopable(spectral: Optional[str]) -> Optional[bool]:
    if not spectral: return None
    return spectral[0].upper() in SCOOPABLE


def normalise_ring_rows(message: dict, *, system_id64: int, body_id: int, body_name: str) -> list[dict]:
    """Normalise Journal/Scan ring rows without treating BodyID as local identity."""
    rings = message.get('Rings')
    if rings is None:
        return []
    if isinstance(rings, dict):
        raw_entries = [rings]
    elif isinstance(rings, list):
        raw_entries = [entry for entry in rings if isinstance(entry, dict)]
    else:
        return []
    rows = []
    for ring in raw_entries:
        ring_name = clean_text(first_present(ring, 'Name', 'name', 'RingName', 'ringName'))
        ring_type = clean_text(first_present(ring, 'Type', 'type'))
        ring_class = clean_text(first_present(ring, 'RingClass', 'ringClass', 'Class', 'class'))
        confidence = 'source_ring_payload' if ring_name or ring_type or ring_class else 'partial_source_ring_payload'
        rows.append({
            'system_id64': system_id64,
            'body_id': None,
            'source_body_id': body_id,
            'body_name': body_name,
            'ring_name': ring_name,
            'ring_type': ring_type,
            'ring_class': ring_class,
            'mass_mt': safe_float(first_present(ring, 'MassMT', 'massMT', 'Mass', 'mass', 'mass_mt')),
            'inner_radius': safe_float(first_present(ring, 'InnerRad', 'innerRad', 'InnerRadius', 'innerRadius', 'inner_radius')),
            'outer_radius': safe_float(first_present(ring, 'OuterRad', 'outerRad', 'OuterRadius', 'outerRadius', 'outer_radius')),
            'source': 'eddn_scan',
            'confidence': confidence,
        })
    return rows


def first_present(record: dict, *keys: str):
    for key in keys:
        if key in record and record[key] is not None:
            return record[key]
    return None


def clean_text(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


async def resolve_ring_rows_to_local_bodies(conn, rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Resolve EDDN ring rows to existing local bodies by exact same-system name."""
    if not rows:
        return [], []

    system_ids = sorted({int(row['system_id64']) for row in rows if row.get('system_id64') is not None})
    body_names = sorted({str(row['body_name']) for row in rows if row.get('body_name')})
    if not system_ids or not body_names:
        return resolve_ring_rows_with_local_bodies(rows, [])

    local_bodies = await conn.fetch("""
        SELECT system_id64, id, name
          FROM bodies
         WHERE system_id64 = ANY($1::bigint[])
           AND name = ANY($2::text[])
    """, system_ids, body_names)
    return resolve_ring_rows_with_local_bodies(rows, local_bodies)


def resolve_ring_rows_with_local_bodies(rows: list[dict], local_bodies) -> tuple[list[dict], list[dict]]:
    local_by_name: dict[tuple[int, str], list[dict]] = {}
    for body in local_bodies:
        system_id64 = body.get('system_id64') if isinstance(body, dict) else body['system_id64']
        body_name = body.get('name') if isinstance(body, dict) else body['name']
        body_id = body.get('id') if isinstance(body, dict) else body['id']
        if system_id64 is None or not body_name or body_id is None:
            continue
        key = (int(system_id64), str(body_name))
        local_by_name.setdefault(key, []).append({
            'system_id64': int(system_id64),
            'id': int(body_id),
            'name': str(body_name),
        })

    resolved: list[dict] = []
    skipped: list[dict] = []
    for row in rows:
        body_name = row.get('body_name')
        if row.get('system_id64') is None or not body_name:
            skipped.append({**row, 'reason': 'missing_system_or_body_name'})
            continue
        matches = local_by_name.get((int(row['system_id64']), str(body_name)), [])
        if len(matches) != 1:
            skipped.append({
                **row,
                'reason': 'local_body_not_found_by_name' if not matches else 'local_body_name_not_unique',
            })
            continue
        match = matches[0]
        resolved.append({
            **row,
            'body_id': match['id'],
            'body_name': match['name'],
        })
    return resolved, skipped


def _star_type_parts(spectral: Optional[str]) -> tuple[str | None, str | None, bool | None]:
    if not spectral:
        return None, None, None
    spectral = str(spectral).strip()
    if not spectral:
        return None, None, None
    star_type = spectral[:1].upper()
    return star_type, spectral[1:] or None, star_type in SCOOPABLE


def _extract_star_pos(value) -> tuple[float | None, float | None, float | None]:
    """Return a complete StarPos triple, or all-null when any axis is missing."""
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None, None, None
    x = safe_float(value[0])
    y = safe_float(value[1])
    z = safe_float(value[2])
    if x is None or y is None or z is None:
        return None, None, None
    return x, y, z


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------
async def handle_fss_discovery(pool: asyncpg.Pool, header: dict, message: dict):
    """FSSDiscoveryScan — new system found via FSS."""
    star_system = message.get('StarSystem')
    body = star_system if isinstance(star_system, dict) else message
    id64 = safe_int(body.get('SystemAddress') or body.get('id64'))
    if not id64: return

    star_pos = body.get('StarPos')
    x, y, z = _extract_star_pos(star_pos)
    _pending_systems[id64] = {
        'id64':    id64,
        'name':    body.get('StarSystem') if isinstance(body.get('StarSystem'), str) else body.get('name', 'Unknown'),
        'x':       x,
        'y':       y,
        'z':       z,
        'economy': norm_economy(body.get('SystemEconomy') or body.get('primaryEconomy')),
        'pop':     safe_int(body.get('Population')),
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
        'is_tidal_lock':  bool(message['TidalLock']) if 'TidalLock' in message else None,
        'spectral_class': message.get('StarType'),
        'stellar_mass':   safe_float(message.get('StellarMass')) if is_star else None,
        'is_scoopable':   is_scoopable(message.get('StarType')),
        'estimated_mapping_value': safe_int(message.get('EstimatedMappingValue') or message.get('MappedValue')),
        'estimated_scan_value':    safe_int(message.get('EstimatedScanValue')),
        'updated_at':     utcnow(),
    }

    _pending_rings.extend(normalise_ring_rows(
        message,
        system_id64=id64,
        body_id=body_id,
        body_name=body_name,
    ))

    if message.get('Materials'):
        body_rec['materials'] = json.dumps({
            m['Name']: m['Percent'] for m in message['Materials']
        })

    if is_star and body_rec.get('is_main_star'):
        star_type, star_subtype, star_scoopable = _star_type_parts(message.get('StarType'))
        if star_type:
            existing = _pending_systems.get(id64, {'id64': id64, 'updated': utcnow()})
            existing.update({
                'main_star_type': star_type,
                'main_star_subtype': star_subtype,
                'main_star_is_scoopable': star_scoopable,
                'updated': utcnow(),
            })
            _pending_systems[id64] = existing

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
            updated_body = await conn.fetchval("""
                UPDATE bodies
                SET bio_signal_count = GREATEST(bio_signal_count, $1),
                    geo_signal_count = GREATEST(geo_signal_count, $2),
                    updated_at       = NOW()
                WHERE name = $3 AND system_id64 = $4
                  AND (bio_signal_count < $1 OR geo_signal_count < $2)
                RETURNING id
            """, bio_count, geo_count, body_name, id64)
            if updated_body:
                await conn.execute("""
                    UPDATE systems
                       SET rating_dirty = TRUE, cluster_dirty = TRUE
                     WHERE id64 = $1
                """, id64)


async def handle_location_or_jump(pool: asyncpg.Pool, header: dict, message: dict):
    """Location / FSDJump — update system economy / population from live game."""
    id64 = safe_int(message.get('SystemAddress'))
    if not id64: return

    pop    = safe_int(message.get('Population'))
    eco    = norm_economy(message.get('SystemEconomy'))
    name   = message.get('StarSystem')
    coords = message.get('StarPos')

    upd = {'id64': id64, 'dirty': True, 'updated': utcnow()}
    if pop is not None: upd['pop'] = pop
    if eco != 'Unknown': upd['economy'] = eco
    if name: upd['name'] = name
    x, y, z = _extract_star_pos(coords)
    if x is not None:
        upd['x'] = x
        upd['y'] = y
        upd['z'] = z

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
    global _pending_systems, _pending_bodies, _pending_rings, _last_flush

    # Take a snapshot of current buffer contents — do NOT clear globals yet.
    # We track the IDs/indices we attempted so we can remove only those on success.
    systems_snapshot = list(_pending_systems.values())
    system_ids       = list(_pending_systems.keys())
    bodies_snapshot  = list(_pending_bodies)
    rings_snapshot   = list(_pending_rings)
    n_bodies         = len(bodies_snapshot)
    n_rings          = len(rings_snapshot)

    if not systems_snapshot and not bodies_snapshot and not rings_snapshot:
        _last_flush = time.time()
        return

    flushed_systems = 0
    flushed_bodies  = 0
    flushed_rings   = 0
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
                                main_star_type, main_star_subtype, main_star_is_scoopable,
                                rating_dirty, cluster_dirty,
                                eddn_updated_at, updated_at
                            ) VALUES (
                                $1,$2,$3,$4,$5,$6::economy_type,COALESCE($7::bigint, 0),
                                $8,$9,$10,
                                TRUE,TRUE,NOW(),NOW()
                            )
                            ON CONFLICT (id64) DO UPDATE SET
                                name            = COALESCE(NULLIF($2,'Unknown'), systems.name),
                                x               = COALESCE($3, systems.x),
                                y               = COALESCE($4, systems.y),
                                z               = COALESCE($5, systems.z),
                                primary_economy = CASE WHEN $6 != 'Unknown'
                                                       THEN $6::economy_type
                                                       ELSE systems.primary_economy END,
                                population      = COALESCE($7::bigint, systems.population),
                                main_star_type  = COALESCE($8, systems.main_star_type),
                                main_star_subtype = COALESCE($9, systems.main_star_subtype),
                                main_star_is_scoopable = COALESCE($10, systems.main_star_is_scoopable),
                                rating_dirty    = TRUE,
                                cluster_dirty   = TRUE,
                                eddn_updated_at = NOW(),
                                updated_at      = NOW()
                            WHERE
                                (NULLIF($2,'Unknown') IS NOT NULL AND systems.name IS DISTINCT FROM NULLIF($2,'Unknown'))
                                OR ($3 IS NOT NULL AND systems.x IS DISTINCT FROM $3)
                                OR ($4 IS NOT NULL AND systems.y IS DISTINCT FROM $4)
                                OR ($5 IS NOT NULL AND systems.z IS DISTINCT FROM $5)
                                OR ($6 != 'Unknown' AND systems.primary_economy IS DISTINCT FROM $6::economy_type)
                                OR ($7 IS NOT NULL AND systems.population IS DISTINCT FROM $7::bigint)
                                OR ($8 IS NOT NULL AND systems.main_star_type IS DISTINCT FROM $8)
                                OR ($9 IS NOT NULL AND systems.main_star_subtype IS DISTINCT FROM $9)
                                OR ($10 IS NOT NULL AND systems.main_star_is_scoopable IS DISTINCT FROM $10)
                        """,
                            sys['id64'],
                            sys.get('name', 'Unknown'),
                            sys.get('x'),
                            sys.get('y'),
                            sys.get('z'),
                            sys.get('economy', 'Unknown'),
                            sys.get('pop'),
                            sys.get('main_star_type'),
                            sys.get('main_star_subtype'),
                            sys.get('main_star_is_scoopable'),
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
                resolved_rings_snapshot = []
                unresolved_rings_snapshot = []
                if rings_snapshot:
                    (
                        resolved_rings_snapshot,
                        unresolved_rings_snapshot,
                    ) = await resolve_ring_rows_to_local_bodies(conn, rings_snapshot)
                    if unresolved_rings_snapshot:
                        log.debug(
                            "Skipped %d unresolved EDDN ring rows without an exact local body match",
                            len(unresolved_rings_snapshot),
                        )

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
                                system_id64       = EXCLUDED.system_id64,
                                name              = COALESCE(NULLIF(EXCLUDED.name, 'Unknown'), bodies.name),
                                body_type         = EXCLUDED.body_type,
                                subtype           = COALESCE(EXCLUDED.subtype, bodies.subtype),
                                is_main_star      = EXCLUDED.is_main_star,
                                distance_from_star = COALESCE(EXCLUDED.distance_from_star, bodies.distance_from_star),
                                radius            = COALESCE(EXCLUDED.radius, bodies.radius),
                                mass              = COALESCE(EXCLUDED.mass, bodies.mass),
                                gravity           = COALESCE(EXCLUDED.gravity, bodies.gravity),
                                is_landable       = EXCLUDED.is_landable,
                                is_terraformable  = EXCLUDED.is_terraformable,
                                is_earth_like     = EXCLUDED.is_earth_like,
                                is_water_world    = EXCLUDED.is_water_world,
                                is_ammonia_world  = EXCLUDED.is_ammonia_world,
                                surface_temp      = COALESCE(EXCLUDED.surface_temp, bodies.surface_temp),
                                surface_pressure  = COALESCE(EXCLUDED.surface_pressure, bodies.surface_pressure),
                                volcanism         = COALESCE(EXCLUDED.volcanism, bodies.volcanism),
                                atmosphere_type   = COALESCE(EXCLUDED.atmosphere_type, bodies.atmosphere_type),
                                is_tidal_lock     = COALESCE(EXCLUDED.is_tidal_lock, bodies.is_tidal_lock),
                                spectral_class    = COALESCE(EXCLUDED.spectral_class, bodies.spectral_class),
                                stellar_mass      = COALESCE(EXCLUDED.stellar_mass, bodies.stellar_mass),
                                is_scoopable      = COALESCE(EXCLUDED.is_scoopable, bodies.is_scoopable),
                                estimated_mapping_value = COALESCE(EXCLUDED.estimated_mapping_value, bodies.estimated_mapping_value),
                                estimated_scan_value = COALESCE(EXCLUDED.estimated_scan_value, bodies.estimated_scan_value),
                                updated_at        = NOW()
                            WHERE
                                bodies.system_id64 IS DISTINCT FROM EXCLUDED.system_id64
                                OR bodies.name IS DISTINCT FROM COALESCE(NULLIF(EXCLUDED.name, 'Unknown'), bodies.name)
                                OR bodies.body_type IS DISTINCT FROM EXCLUDED.body_type
                                OR bodies.subtype IS DISTINCT FROM COALESCE(EXCLUDED.subtype, bodies.subtype)
                                OR bodies.is_main_star IS DISTINCT FROM EXCLUDED.is_main_star
                                OR bodies.distance_from_star IS DISTINCT FROM COALESCE(EXCLUDED.distance_from_star, bodies.distance_from_star)
                                OR bodies.radius IS DISTINCT FROM COALESCE(EXCLUDED.radius, bodies.radius)
                                OR bodies.mass IS DISTINCT FROM COALESCE(EXCLUDED.mass, bodies.mass)
                                OR bodies.gravity IS DISTINCT FROM COALESCE(EXCLUDED.gravity, bodies.gravity)
                                OR bodies.is_landable IS DISTINCT FROM EXCLUDED.is_landable
                                OR bodies.is_terraformable IS DISTINCT FROM EXCLUDED.is_terraformable
                                OR bodies.is_earth_like IS DISTINCT FROM EXCLUDED.is_earth_like
                                OR bodies.is_water_world IS DISTINCT FROM EXCLUDED.is_water_world
                                OR bodies.is_ammonia_world IS DISTINCT FROM EXCLUDED.is_ammonia_world
                                OR bodies.surface_temp IS DISTINCT FROM COALESCE(EXCLUDED.surface_temp, bodies.surface_temp)
                                OR bodies.surface_pressure IS DISTINCT FROM COALESCE(EXCLUDED.surface_pressure, bodies.surface_pressure)
                                OR bodies.volcanism IS DISTINCT FROM COALESCE(EXCLUDED.volcanism, bodies.volcanism)
                                OR bodies.atmosphere_type IS DISTINCT FROM COALESCE(EXCLUDED.atmosphere_type, bodies.atmosphere_type)
                                OR bodies.is_tidal_lock IS DISTINCT FROM COALESCE(EXCLUDED.is_tidal_lock, bodies.is_tidal_lock)
                                OR bodies.spectral_class IS DISTINCT FROM COALESCE(EXCLUDED.spectral_class, bodies.spectral_class)
                                OR bodies.stellar_mass IS DISTINCT FROM COALESCE(EXCLUDED.stellar_mass, bodies.stellar_mass)
                                OR bodies.is_scoopable IS DISTINCT FROM COALESCE(EXCLUDED.is_scoopable, bodies.is_scoopable)
                                OR bodies.estimated_mapping_value IS DISTINCT FROM COALESCE(EXCLUDED.estimated_mapping_value, bodies.estimated_mapping_value)
                                OR bodies.estimated_scan_value IS DISTINCT FROM COALESCE(EXCLUDED.estimated_scan_value, bodies.estimated_scan_value)
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

                # ── Upsert ring facts ───────────────────────────────────
                for ring in resolved_rings_snapshot:
                    try:
                        await conn.execute("""
                            INSERT INTO body_rings (
                                system_id64, body_id, source_body_id, body_name,
                                ring_name, ring_type, ring_class,
                                mass_mt, inner_radius, outer_radius,
                                source, confidence, updated_at
                            ) VALUES (
                                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,NOW()
                            )
                            ON CONFLICT (system_id64, body_id, ring_name, source) DO UPDATE SET
                                source_body_id = COALESCE(EXCLUDED.source_body_id, body_rings.source_body_id),
                                body_name    = COALESCE(EXCLUDED.body_name, body_rings.body_name),
                                ring_type    = COALESCE(EXCLUDED.ring_type, body_rings.ring_type),
                                ring_class   = COALESCE(EXCLUDED.ring_class, body_rings.ring_class),
                                mass_mt      = COALESCE(EXCLUDED.mass_mt, body_rings.mass_mt),
                                inner_radius = COALESCE(EXCLUDED.inner_radius, body_rings.inner_radius),
                                outer_radius = COALESCE(EXCLUDED.outer_radius, body_rings.outer_radius),
                                confidence   = EXCLUDED.confidence,
                                updated_at   = NOW()
                        """,
                            ring.get('system_id64'), ring.get('body_id'), ring.get('source_body_id'), ring.get('body_name'),
                            ring.get('ring_name'), ring.get('ring_type'), ring.get('ring_class'),
                            ring.get('mass_mt'), ring.get('inner_radius'), ring.get('outer_radius'),
                            ring.get('source'), ring.get('confidence'),
                        )
                        flushed_rings += 1
                        _stats['rings_upserted'] += 1
                    except Exception as e:
                        flush_errors += 1
                        _stats['errors'] += 1
                        log.warning(f"Ring upsert error (body_id={ring.get('body_id')}): {e}")

        # ── Transaction succeeded — NOW clear the flushed items ───────────
        # Remove only the system IDs we attempted; any new ones that arrived
        # during the DB write are preserved for the next flush.
        for sid in system_ids:
            _pending_systems.pop(sid, None)
        # Remove the first n_bodies entries (those we snapshotted).
        # New bodies appended during the flush are preserved.
        del _pending_bodies[:n_bodies]
        del _pending_rings[:n_rings]
        _last_flush = time.time()

        if flush_errors:
            log.warning(
                f"Flushed {flushed_systems} systems + {flushed_bodies} bodies + {flushed_rings} rings "
                f"({flush_errors} row-level errors — check WARNING logs above)"
            )
        else:
            log.info(f"Flushed {flushed_systems} systems + {flushed_bodies} bodies + {flushed_rings} rings to DB")

    except Exception as e:
        # The whole transaction failed — buffers are NOT cleared.
        # The data will be retried on the next flush interval.
        _last_flush = time.time()  # reset timer to avoid tight retry loop
        log.error(
            f"flush_pending FAILED — {len(systems_snapshot)} systems + "
            f"{len(bodies_snapshot)} bodies + {len(rings_snapshot)} rings retained in buffer for next retry: {e}"
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
            f"rings: {_stats['rings_upserted']:,} | "
            f"errors: {_stats['errors']:,} ({err_rate:.2f}/min) | "
            f"pending: {len(_pending_systems)} sys / {len(_pending_bodies)} bodies / {len(_pending_rings)} rings"
        )


# ---------------------------------------------------------------------------
# Prometheus metrics endpoint
# ---------------------------------------------------------------------------
def _prometheus_text() -> bytes:
    """Render the EDDN listener's _stats dict in Prometheus text format.

    Stays dependency-free (no prometheus_client) so the EDDN image
    keeps its 70 MB footprint. The metric names mirror the
    Grafana-side queries already wired up by config/grafana/.
    """
    uptime_min = (time.time() - _stats['started_at']) / 60.0
    rate       = _stats['events_received'] / max(uptime_min, 1)
    err_rate   = _stats['errors']          / max(uptime_min, 1)
    lines = [
        '# HELP eddn_events_received_total Events ingested from the EDDN relay',
        '# TYPE eddn_events_received_total counter',
        f'eddn_events_received_total {_stats["events_received"]}',
        '# HELP eddn_events_processed_total Events with a registered handler',
        '# TYPE eddn_events_processed_total counter',
        f'eddn_events_processed_total {_stats["events_processed"]}',
        '# HELP eddn_events_skipped_total Events with no registered handler',
        '# TYPE eddn_events_skipped_total counter',
        f'eddn_events_skipped_total {_stats["events_skipped"]}',
        '# HELP eddn_systems_upserted_total Systems written to the DB',
        '# TYPE eddn_systems_upserted_total counter',
        f'eddn_systems_upserted_total {_stats["systems_upserted"]}',
        '# HELP eddn_bodies_upserted_total Bodies written to the DB',
        '# TYPE eddn_bodies_upserted_total counter',
        f'eddn_bodies_upserted_total {_stats["bodies_upserted"]}',
        '# HELP eddn_rings_upserted_total Ring facts written to the DB',
        '# TYPE eddn_rings_upserted_total counter',
        f'eddn_rings_upserted_total {_stats["rings_upserted"]}',
        '# HELP eddn_errors_total Total errors (ZMQ + DB + decode)',
        '# TYPE eddn_errors_total counter',
        f'eddn_errors_total {_stats["errors"]}',
        '# HELP eddn_pending_systems Systems buffered awaiting next flush',
        '# TYPE eddn_pending_systems gauge',
        f'eddn_pending_systems {len(_pending_systems)}',
        '# HELP eddn_pending_bodies Bodies buffered awaiting next flush',
        '# TYPE eddn_pending_bodies gauge',
        f'eddn_pending_bodies {len(_pending_bodies)}',
        '# HELP eddn_pending_rings Ring facts buffered awaiting next flush',
        '# TYPE eddn_pending_rings gauge',
        f'eddn_pending_rings {len(_pending_rings)}',
        '# HELP eddn_seconds_since_flush Seconds since the last DB flush',
        '# TYPE eddn_seconds_since_flush gauge',
        f'eddn_seconds_since_flush {time.time() - _last_flush:.1f}',
        '# HELP eddn_uptime_seconds Seconds since process start',
        '# TYPE eddn_uptime_seconds gauge',
        f'eddn_uptime_seconds {(time.time() - _stats["started_at"]):.0f}',
        '# HELP eddn_events_per_minute Rolling-average ingest rate',
        '# TYPE eddn_events_per_minute gauge',
        f'eddn_events_per_minute {rate:.2f}',
        '# HELP eddn_errors_per_minute Rolling-average error rate',
        '# TYPE eddn_errors_per_minute gauge',
        f'eddn_errors_per_minute {err_rate:.4f}',
        '',
    ]
    return ('\n'.join(lines)).encode('utf-8')


async def _metrics_handler(reader: asyncio.StreamReader,
                           writer: asyncio.StreamWriter) -> None:
    """Tiny HTTP/1.1 handler — only serves GET /metrics, 404 elsewhere."""
    try:
        request_line = await asyncio.wait_for(reader.readline(), timeout=2.0)
        # Drain headers so the client doesn't see a broken pipe
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=2.0)
            if line in (b'\r\n', b'\n', b''):
                break
        if not request_line.startswith(b'GET '):
            writer.write(b'HTTP/1.1 405 Method Not Allowed\r\n'
                         b'Content-Length: 0\r\nConnection: close\r\n\r\n')
        elif b' /metrics' in request_line or b' /metrics ' in request_line or request_line.startswith(b'GET /metrics'):
            payload = _prometheus_text()
            writer.write(
                b'HTTP/1.1 200 OK\r\n'
                b'Content-Type: text/plain; version=0.0.4\r\n'
                + f'Content-Length: {len(payload)}\r\n'.encode()
                + b'Connection: close\r\n\r\n'
                + payload
            )
        elif request_line.startswith(b'GET /healthz'):
            writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n'
                         b'Connection: close\r\n\r\nok')
        else:
            writer.write(b'HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n'
                         b'Connection: close\r\n\r\n')
        await writer.drain()
    except (asyncio.TimeoutError, ConnectionResetError):
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def metrics_server() -> None:
    """Bind 0.0.0.0:METRICS_PORT and serve /metrics for Prometheus scrape."""
    if METRICS_PORT == 0:
        log.info('metrics_server disabled (METRICS_PORT=0)')
        return
    server = await asyncio.start_server(
        _metrics_handler, host='0.0.0.0', port=METRICS_PORT,
    )
    log.info(
        'metrics_server listening',
        extra={'metrics_port': METRICS_PORT,
               'endpoint':     f'http://0.0.0.0:{METRICS_PORT}/metrics'},
    )
    async with server:
        await server.serve_forever()


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
                # Build a compact summary used by both eddn_log (for the
                # /api/events/recent feed) and Redis pub/sub (for SSE).
                evt_type   = message.get('event') or schema.rsplit('/', 1)[-1]
                evt_id64   = safe_int(message.get('SystemAddress'))
                evt_sysnam = message.get('StarSystem') or message.get('BodyName')
                # Persist to eddn_log so the /api/events/recent feed has
                # data. Fire-and-forget against the pool — the listener
                # mustn't block on this; failures are logged but don't
                # break the pipeline. Old rows are trimmed by a separate
                # rolling-window job (7 days, see the table comment).
                try:
                    await pool.execute(
                        """
                        INSERT INTO eddn_log
                            (event_type, system_id64, system_name, processed)
                        VALUES ($1, $2, $3, TRUE)
                        """,
                        evt_type, evt_id64, evt_sysnam,
                    )
                except Exception as e:
                    log.debug(f"eddn_log insert failed (non-fatal): {e}")
                # Publish a compact event summary to Redis so the API
                # container's SSE endpoint can fan it out to connected
                # clients in real time.
                if redis is not None:
                    try:
                        summary = {
                            'system_name': evt_sysnam,
                            'id64':        evt_id64,
                            'type':        evt_type,
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
        # Mirror the api fix in commit 4fe340a: pass statement_timeout
        # through asyncpg's startup parameters (server_settings) rather
        # than via a session-level SET, because pgBouncer's transaction-
        # pool mode wipes session SETs between transactions but
        # preserves protocol-level startup parameters across the pool.
        # Without this ceiling, a hung body-upsert in flush_pending()
        # against asyncpg's 30 s command_timeout pins a connection,
        # back-pressures the EDDN ingestion loop, and ultimately makes
        # the SSE bridge silent — exactly the failure mode the api
        # commit was originally written to fix. application_name lets
        # us spot eddn-originated queries in pg_stat_activity.
        server_settings={
            'application_name':   'ed_finder_eddn',
            'statement_timeout':  '15000',
        },
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
        metrics_server(),
    )


if __name__ == '__main__':
    asyncio.run(main())
