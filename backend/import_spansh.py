#!/usr/bin/env python3
"""
ED Finder — Spansh Dump Importer  (PostgreSQL / psycopg2 COPY edition)
Version: 3.0  (galaxy region lookup + structured error logging)

NEW in v3.0:
  • galaxy_region_id populated for every system during import using the
    klightspeed/EliteDangerousRegionMap algorithm (RegionMapData.py).
    Each system gets a SMALLINT (1-42) identifying its named ED codex region
    (Inner Orion Spur, Formorian Frontier, Galactic Centre, etc.).
    The lookup is pure integer arithmetic — zero DB overhead per row.
  • Structured error logging: per-record failures are written to the
    import_errors table so you can query exactly which systems/bodies/stations
    failed and why, without grepping 500MB log files.
  • errors_encountered counter tracked in import_meta so the API can surface
    import health in real-time.
  • needs_permit field populated from Spansh data (defaults FALSE if absent).

FIX in v2.5:
  • Progress bar desync on resume fixed (tqdm initialised after fast-forward).
  • import_stations: stations missing 'id' or 'systemId64' now counted/logged.

FIX in v2.4:
  • _make_direct_dsn() added: automatically rewrites DATABASE_URL to bypass
    pgBouncer (port 5433 → 5432, @pgbouncer: → @postgres:).

Why psycopg2 COPY instead of INSERT ... ON CONFLICT:
  • COPY is the fastest possible PostgreSQL bulk-load method.
  • Strategy: COPY into a temp table, then INSERT ... ON CONFLICT from temp
    into the real table. This gives us both speed AND upsert semantics.

Server:   Hetzner AX41-SSD — i7-8700 (6C/12T), 128 GB RAM, 3×1 TB NVMe RAID-5
Database: PostgreSQL 16

Usage:
    python3 import_spansh.py --all                   # import all dumps
    python3 import_spansh.py --file galaxy.json.gz   # import one file
    python3 import_spansh.py --all --resume          # resume from checkpoint
    python3 import_spansh.py --download-only         # download files then exit
    python3 import_spansh.py --download --all        # download then import
    python3 import_spansh.py --status                # show import progress
    python3 import_spansh.py --errors                # show recent import errors
"""

import os
import sys
import gzip
import json
import time
import logging
import argparse
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Iterator, Any, List, Tuple

import decimal
import ijson
import psycopg2
import psycopg2.extras
import psycopg2.extensions
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Galaxy Region Lookup (klightspeed/EliteDangerousRegionMap)
# ---------------------------------------------------------------------------
try:
    from RegionMapData import regions as _REGION_NAMES, regionmap as _REGION_MAP
    _REGION_X0 = -49985
    _REGION_Z0 = -24105

    def find_galaxy_region(x: float, z: float) -> Optional[int]:
        """
        Return the galaxy region id (1-42) for a system at (x, z).
        Y coordinate is not used — regions are defined in the XZ plane.
        Returns None if the coordinates are outside the region map.
        """
        px = int((x - _REGION_X0) * 83 / 4096)
        pz = int((z - _REGION_Z0) * 83 / 4096)
        if px < 0 or pz < 0 or pz >= len(_REGION_MAP):
            return None
        row = _REGION_MAP[pz]
        rx = 0
        pv = 0
        for rl, pv in row:
            if px < rx + rl:
                break
            rx += rl
        else:
            pv = 0
        return int(pv) if pv else None

    _REGION_LOOKUP_AVAILABLE = True
except ImportError:
    _REGION_LOOKUP_AVAILABLE = False
    def find_galaxy_region(x: float, z: float) -> Optional[int]:
        return None


def _json_dumps(obj) -> Optional[str]:
    """json.dumps that converts Decimal → float (ijson returns Decimal for numbers)."""
    if obj is None:
        return None
    def _default(o):
        if isinstance(o, decimal.Decimal):
            return float(o)
        raise TypeError(f"Not serializable: {type(o)}")
    return json.dumps(obj, default=_default)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _make_direct_dsn(url: str) -> str:
    """
    Ensure the DSN points directly at postgres (port 5432), not pgBouncer (5433).
    pgBouncer transaction-pool mode is incompatible with COPY and long-running
    import transactions — it can silently drop connections mid-import.
    """
    direct = os.getenv('DB_DSN_DIRECT', '')
    if direct:
        return direct
    if ':5433/' in url:
        url = url.replace(':5433/', ':5432/')
    url = url.replace('@pgbouncer:', '@postgres:')
    return url

DB_DSN          = _make_direct_dsn(os.getenv('DATABASE_URL',
                    'postgresql://edfinder:edfinder@localhost:5432/edfinder'))
DUMP_DIR        = Path(os.getenv('DUMP_DIR', '/data/dumps'))
BATCH_SIZE      = int(os.getenv('BATCH_SIZE', '50000'))
LOG_LEVEL       = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE        = os.getenv('LOG_FILE', '/data/logs/import.log')

SPANSH_BASE     = 'https://downloads.spansh.co.uk'

DUMP_FILES      = [
    'galaxy.json.gz',
    'galaxy_populated.json.gz',
    'galaxy_stations.json.gz',
]

DELTA_FILES     = [
    'systems_1day.json.gz',
    'systems_1week.json.gz',
    'systems_1month.json.gz',
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format='%(asctime)s,%(msecs)03d [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
    ]
)
log = logging.getLogger('import_spansh')

if _REGION_LOOKUP_AVAILABLE:
    log.info("Galaxy region lookup: ENABLED (42 named ED codex regions)")
else:
    log.warning("Galaxy region lookup: DISABLED (RegionMapData.py not found)")

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
def get_conn() -> psycopg2.extensions.connection:
    conn = psycopg2.connect(DB_DSN)
    conn.autocommit = False
    return conn


def set_import_optimisations(conn):
    """Apply session-level settings for maximum bulk-load speed."""
    with conn.cursor() as cur:
        cur.execute("SET synchronous_commit = off")
        cur.execute("SET work_mem = '256MB'")
        cur.execute("SET maintenance_work_mem = '4GB'")
    conn.commit()
    log.info("Import optimisations applied (synchronous_commit=off, work_mem=256MB)")


# ---------------------------------------------------------------------------
# Structured error logging
# ---------------------------------------------------------------------------
_error_batch: List[Tuple] = []
_error_batch_size = 500

def log_import_error(conn, dump_file: str, record_id: Optional[int],
                     record_type: str, exc: Exception,
                     raw_snippet: Optional[str] = None):
    """
    Queue a structured error record. Flushed in batches to import_errors table.
    This replaces grepping log files — query import_errors directly to diagnose failures.
    """
    _error_batch.append((
        dump_file,
        record_id,
        record_type,
        type(exc).__name__,
        str(exc)[:500],
        raw_snippet[:500] if raw_snippet else None,
    ))
    if len(_error_batch) >= _error_batch_size:
        flush_error_batch(conn, dump_file)


def flush_error_batch(conn, dump_file: str):
    """Write accumulated error records to the import_errors table."""
    if not _error_batch:
        return
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO import_errors
                    (dump_file, record_id, record_type, error_class, error_message, raw_snippet)
                VALUES %s
                """,
                _error_batch
            )
        conn.commit()
    except Exception as e:
        log.warning(f"Failed to write error batch to import_errors: {e}")
    finally:
        _error_batch.clear()


def increment_error_count(conn, dump_file: str, count: int = 1):
    """Increment the errors_encountered counter in import_meta."""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE import_meta
                SET errors_encountered = errors_encountered + %s,
                    updated_at = NOW()
                WHERE dump_file = %s
            """, (count, dump_file))
        conn.commit()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------
def get_checkpoint(conn, dump_file: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT last_checkpoint FROM import_meta WHERE dump_file = %s",
            (dump_file,)
        )
        row = cur.fetchone()
        return row[0] if row else 0


def save_checkpoint(conn, dump_file: str, offset: int, rows: int, bytes_pos: int = 0):
    """Save checkpoint to import_meta table."""
    with conn.cursor() as cur:
        if bytes_pos > 0:
            cur.execute("""
                UPDATE import_meta
                SET last_checkpoint = %s,
                    rows_processed  = %s,
                    bytes_processed = %s,
                    updated_at      = NOW()
                WHERE dump_file = %s
            """, (rows, rows, bytes_pos, dump_file))
        else:
            cur.execute("""
                UPDATE import_meta
                SET last_checkpoint = %s,
                    rows_processed  = %s,
                    updated_at      = NOW()
                WHERE dump_file = %s
            """, (rows, rows, dump_file))
    conn.commit()


def mark_running(conn, dump_file: str, total_bytes: int):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE import_meta
            SET status      = 'running',
                started_at  = COALESCE(started_at, NOW()),
                bytes_total = %s,
                updated_at  = NOW()
            WHERE dump_file = %s
        """, (total_bytes, dump_file))
    conn.commit()


def mark_complete(conn, dump_file: str, rows: int):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE import_meta
            SET status          = 'complete',
                completed_at    = NOW(),
                rows_processed  = %s,
                updated_at      = NOW()
            WHERE dump_file = %s
        """, (rows, dump_file))
    conn.commit()


def mark_failed(conn, dump_file: str, error: str):
    try:
        conn.rollback()
    except Exception:
        pass
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE import_meta
                SET status        = 'failed',
                    error_message = %s,
                    updated_at    = NOW()
                WHERE dump_file = %s
            """, (error[:500], dump_file))
        conn.commit()
    except Exception as e:
        log.error(f"mark_failed itself failed: {e}")


# ---------------------------------------------------------------------------
# COPY helper
# ---------------------------------------------------------------------------
def copy_records(conn, table: str, columns: List[str], rows: List[Tuple]) -> int:
    if not rows:
        return 0
    buf = io.StringIO()
    for row in rows:
        line_parts = []
        for val in row:
            if val is None:
                line_parts.append('\\N')
            elif isinstance(val, bool):
                line_parts.append('t' if val else 'f')
            elif isinstance(val, str):
                escaped = (val
                    .replace('\\', '\\\\')
                    .replace('\n', '\\n')
                    .replace('\r', '\\r')
                    .replace('\t', '\\t'))
                line_parts.append(escaped)
            else:
                line_parts.append(str(val))
        buf.write('\t'.join(line_parts) + '\n')
    buf.seek(0)
    with conn.cursor() as cur:
        cur.copy_from(buf, table, columns=columns, null='\\N')
    conn.commit()
    return len(rows)


def upsert_via_temp(conn, target_table: str, columns: List[str],
                    rows: List[Tuple], conflict_col: str,
                    update_cols: Optional[List[str]] = None) -> int:
    if not rows:
        return 0
    if update_cols is None:
        update_cols = [c for c in columns if c != conflict_col]
    temp = f"_tmp_{target_table}"
    col_list   = ', '.join(columns)
    set_clause = ', '.join(f"{c} = EXCLUDED.{c}" for c in update_cols)
    with conn.cursor() as cur:
        cur.execute(f"""
            CREATE TEMP TABLE IF NOT EXISTS {temp}
            (LIKE {target_table} INCLUDING DEFAULTS)
            ON COMMIT DELETE ROWS
        """)
        conn.commit()
        buf = io.StringIO()
        for row in rows:
            parts = []
            for val in row:
                if val is None:
                    parts.append('\\N')
                elif isinstance(val, bool):
                    parts.append('t' if val else 'f')
                elif isinstance(val, str):
                    escaped = (val
                        .replace('\\', '\\\\')
                        .replace('\n', '\\n')
                        .replace('\r', '\\r')
                        .replace('\t', '\\t'))
                    parts.append(escaped)
                else:
                    parts.append(str(val))
            buf.write('\t'.join(parts) + '\n')
        buf.seek(0)
        cur.copy_from(buf, temp, columns=columns, null='\\N')
        cur.execute(f"""
            INSERT INTO {target_table} ({col_list})
            SELECT {col_list} FROM {temp}
            ON CONFLICT ({conflict_col}) DO UPDATE
            SET {set_clause}
        """)
        count = cur.rowcount
    conn.commit()
    return count


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------
VALID_ECONOMIES = {
    'Agriculture', 'Refinery', 'Industrial', 'HighTech',
    'Military', 'Tourism', 'Extraction', 'Colony',
    'Terraforming', 'Prison', 'Damaged', 'Rescue',
    'Repair', 'Carrier', 'None', 'Unknown'
}
VALID_SECURITY   = {'High', 'Medium', 'Low', 'Anarchy', 'Lawless', 'Unknown'}
VALID_ALLEGIANCE = {
    'Federation', 'Empire', 'Alliance', 'Independent',
    'Thargoid', 'Guardian', 'PilotsFederation', 'None', 'Unknown'
}
VALID_GOVERNMENT = {
    'Democracy', 'Dictatorship', 'Feudal', 'Patronage',
    'Corporate', 'Cooperative', 'Theocracy', 'Anarchy',
    'Communism', 'Confederacy', 'None', 'Unknown'
}
VALID_STATION_TYPES = {
    'Coriolis', 'Orbis', 'Ocellus', 'Outpost',
    'PlanetaryPort', 'PlanetaryOutpost', 'MegaShip',
    'AsteroidBase', 'FleetCarrier', 'Unknown'
}
SCOOPABLE_STARS = {'O', 'B', 'A', 'F', 'G', 'K', 'M'}


def norm_economy(v) -> str:
    if not v:
        return 'Unknown'
    v = str(v).strip().replace(' ', '').replace('$economy_', '').replace(';', '')
    mapping = {
        'hightech': 'HighTech', 'high_tech': 'HighTech',
        'agriculture': 'Agriculture', 'agri': 'Agriculture',
        'refinery': 'Refinery', 'industrial': 'Industrial',
        'military': 'Military', 'tourism': 'Tourism',
        'extraction': 'Extraction', 'colony': 'Colony',
        'terraforming': 'Terraforming', 'prison': 'Prison',
        'damaged': 'Damaged', 'rescue': 'Rescue',
        'repair': 'Repair', 'carrier': 'Carrier',
        'none': 'None', 'unknown': 'Unknown', '': 'Unknown',
    }
    normalised = mapping.get(v.lower(), v)
    return normalised if normalised in VALID_ECONOMIES else 'Unknown'


def norm_security(v) -> str:
    if not v:
        return 'Unknown'
    v = str(v).strip().replace('$GAlAXY_MAP_INFO_state_', '').replace(';', '')
    mapping = {
        'high': 'High', 'medium': 'Medium', 'low': 'Low',
        'anarchy': 'Anarchy', 'lawless': 'Lawless', 'unknown': 'Unknown',
    }
    return mapping.get(v.lower(), 'Unknown')


def norm_allegiance(v) -> str:
    if not v:
        return 'Unknown'
    mapping = {
        'federation': 'Federation', 'empire': 'Empire',
        'alliance': 'Alliance', 'independent': 'Independent',
        'thargoid': 'Thargoid', 'guardian': 'Guardian',
        'pilotsfederation': 'PilotsFederation',
        'none': 'None', 'unknown': 'Unknown',
    }
    return mapping.get(str(v).lower().replace(' ', ''), 'Unknown')


def norm_government(v) -> str:
    if not v:
        return 'Unknown'
    mapping = {
        'democracy': 'Democracy', 'dictatorship': 'Dictatorship',
        'feudal': 'Feudal', 'patronage': 'Patronage',
        'corporate': 'Corporate', 'cooperative': 'Cooperative',
        'theocracy': 'Theocracy', 'anarchy': 'Anarchy',
        'communism': 'Communism', 'confederacy': 'Confederacy',
        'none': 'None', 'unknown': 'Unknown',
    }
    return mapping.get(str(v).lower().replace(' ', '').replace('$government_', '').replace(';', ''), 'Unknown')


def norm_station_type(v) -> str:
    if not v:
        return 'Unknown'
    mapping = {
        'coriolis': 'Coriolis', 'orbis': 'Orbis', 'ocellus': 'Ocellus',
        'outpost': 'Outpost', 'planetaryport': 'PlanetaryPort',
        'planetaryoutpost': 'PlanetaryOutpost', 'megaship': 'MegaShip',
        'asteroidbase': 'AsteroidBase', 'fleetcarrier': 'FleetCarrier',
        'surfacestation': 'PlanetaryPort', 'craterport': 'PlanetaryPort',
        'crateroutpost': 'PlanetaryOutpost',
        'unknown': 'Unknown',
    }
    return mapping.get(str(v).lower().replace(' ', '').replace('-', ''), 'Unknown')


def parse_ts(v) -> Optional[str]:
    if not v:
        return None
    try:
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(v, tz=timezone.utc).isoformat()
        s = str(v).strip()
        try:
            dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
            return dt.isoformat()
        except ValueError:
            pass
        return s
    except Exception:
        return None


def parse_bool(v) -> Optional[bool]:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    return str(v).lower() in ('true', '1', 'yes')


def _to_signal_count(val) -> int:
    if val is None:
        return 0
    if isinstance(val, list):
        return len(val)
    try:
        return int(val or 0)
    except (TypeError, ValueError):
        return 0


def _parse_bio_signals(b: dict) -> int:
    sig = b.get('signals')
    if sig is None:
        return _to_signal_count(b.get('bio_signal_count'))
    if isinstance(sig, dict):
        return _to_signal_count(sig.get('genuses'))
    if isinstance(sig, list):
        for s in sig:
            if isinstance(s, dict) and str(s.get('type', '')).lower() in ('biology', 'biological'):
                return _to_signal_count(s.get('count'))
        return 0
    return 0


def _parse_geo_signals(b: dict) -> int:
    sig = b.get('signals')
    if sig is None:
        return _to_signal_count(b.get('geo_signal_count'))
    if isinstance(sig, dict):
        return _to_signal_count(sig.get('geology'))
    if isinstance(sig, list):
        for s in sig:
            if isinstance(s, dict) and str(s.get('type', '')).lower() in ('geology', 'geological'):
                return _to_signal_count(s.get('count'))
        return 0
    return 0


# ---------------------------------------------------------------------------
# IMPORTER 1 — galaxy.json.gz  (systems + bodies + stations, all-in-one)
# ---------------------------------------------------------------------------
def import_galaxy(conn, dump_path: Path, resume_offset: int = 0) -> int:
    """
    Parse galaxy.json.gz and upsert systems, bodies, and stations.
    v3.0: galaxy_region_id populated for every system via findRegion().
    v3.0: Structured errors written to import_errors table.
    """
    log.info(f"Importing systems+bodies+stations from {dump_path.name} ...")
    set_import_optimisations(conn)

    file_size = dump_path.stat().st_size
    mark_running(conn, dump_path.name, file_size)

    SYS_COLS = [
        'id64', 'name', 'x', 'y', 'z',
        'primary_economy', 'secondary_economy',
        'population', 'is_colonised', 'is_being_colonised',
        'controlling_faction',
        'security', 'allegiance', 'government',
        'needs_permit',
        'main_star_type', 'main_star_subtype', 'main_star_is_scoopable',
        'has_body_data', 'body_count', 'data_quality',
        'galaxy_region_id',
        'first_discovered_at', 'updated_at',
        'rating_dirty', 'cluster_dirty',
    ]

    BODY_COLS = [
        'id', 'system_id64', 'name',
        'body_type', 'subtype', 'is_main_star',
        'distance_from_star', 'orbital_period',
        'radius', 'mass', 'gravity', 'surface_temp', 'surface_pressure',
        'atmosphere_type', 'atmosphere_composition',
        'volcanism', 'materials',
        'terraforming_state', 'is_terraformable', 'is_landable',
        'is_water_world', 'is_earth_like', 'is_ammonia_world',
        'bio_signal_count', 'geo_signal_count',
        'spectral_class', 'luminosity', 'stellar_mass',
        'is_scoopable',
        'estimated_mapping_value', 'estimated_scan_value',
        'first_discovered_at', 'updated_at',
    ]

    STA_COLS = [
        'id', 'system_id64', 'name', 'station_type',
        'distance_from_star', 'body_name',
        'landing_pad_size',
        'has_market', 'has_shipyard', 'has_outfitting',
        'has_refuel', 'has_repair', 'has_rearm',
        'has_black_market', 'has_material_trader',
        'has_technology_broker', 'has_interstellar_factors',
        'has_universal_cartographics', 'has_search_rescue',
        'primary_economy', 'secondary_economy',
        'controlling_faction', 'allegiance', 'government',
        'updated_at',
    ]

    sys_batch   = []
    body_batch  = []
    sta_batch   = []
    total_rows  = 0
    skip_count  = 0
    last_save   = time.time()

    def flush_systems():
        if sys_batch:
            upsert_via_temp(conn, 'systems', SYS_COLS, sys_batch, 'id64')
            sys_batch.clear()

    def flush_bodies():
        flush_systems()
        if body_batch:
            upsert_via_temp(conn, 'bodies', BODY_COLS, body_batch, 'id')
            body_batch.clear()

    def flush_stations():
        flush_systems()
        if sta_batch:
            upsert_via_temp(conn, 'stations', STA_COLS, sta_batch, 'id')
            sta_batch.clear()

    with open(dump_path, 'rb') as f_raw, gzip.open(f_raw, 'rb') as f:
        if resume_offset > 0:
            log.info(f"Resuming from row {resume_offset:,} — fast-forwarding stream ...")
            _item_iter = ijson.items(f, 'item')
            for _i, _ in enumerate(_item_iter, 1):
                if _i % 500_000 == 0:
                    log.info(f"  fast-forward: {_i:,} / {resume_offset:,} rows skipped ...")
                if _i >= resume_offset:
                    break
            log.info(f"Fast-forward complete — continuing import from row {resume_offset:,}")
            items_iter = _item_iter
        else:
            items_iter = ijson.items(f, 'item')

        pbar = tqdm(
            total=file_size,
            initial=f_raw.tell(),
            unit='B', unit_scale=True, unit_divisor=1024,
            desc=dump_path.name,
        )

        try:
            for sys_obj in items_iter:
                id64 = sys_obj.get('id64')
                if not id64:
                    continue

                now_iso = datetime.now(timezone.utc).isoformat()

                # ── Main star detection ────────────────────────────────────
                bodies_raw = sys_obj.get('bodies', []) or []
                main_star_type      = None
                main_star_subtype   = None
                main_star_scoopable = None
                has_body_data = len(bodies_raw) > 0

                for b in bodies_raw:
                    if b.get('mainStar') or b.get('isMainStar') or b.get('is_main_star'):
                        sc = b.get('spectralClass') or b.get('spectral_class') or ''
                        main_star_type    = sc[:1] if sc else None
                        main_star_subtype = sc[1:] if len(sc) > 1 else None
                        main_star_scoopable = main_star_type in SCOOPABLE_STARS if main_star_type else None
                        break

                # ── Galaxy region lookup ───────────────────────────────────
                try:
                    coords = sys_obj.get('coords') or {}
                    coords = coords if isinstance(coords, dict) else {}
                    sx = float(coords.get('x') or sys_obj.get('x') or 0)
                    sy = float(coords.get('y') or sys_obj.get('y') or 0)
                    sz = float(coords.get('z') or sys_obj.get('z') or 0)
                    region_id = find_galaxy_region(sx, sz)
                except Exception:
                    sx, sy, sz = 0.0, 0.0, 0.0
                    region_id = None

                # ── Controlling faction ────────────────────────────────────
                controlling  = None
                factions_raw = sys_obj.get('factions', []) or []
                for fac in factions_raw:
                    if fac.get('isControlling') or fac.get('is_controlling'):
                        controlling = fac.get('name')
                        break
                if not controlling:
                    controlling = sys_obj.get('controllingFaction') or sys_obj.get('controlling_faction')

                # ── Systems row ────────────────────────────────────────────
                try:
                    needs_permit = bool(
                        sys_obj.get('needsPermit') or
                        sys_obj.get('needs_permit', False)
                    )
                    sys_batch.append((
                        id64,
                        sys_obj.get('name', ''),
                        sx, sy, sz,
                        norm_economy(sys_obj.get('primaryEconomy') or sys_obj.get('primary_economy')),
                        norm_economy(sys_obj.get('secondaryEconomy') or sys_obj.get('secondary_economy')),
                        int(sys_obj.get('population') or 0),
                        bool(sys_obj.get('isColonised') or sys_obj.get('is_colonised', False)),
                        bool(sys_obj.get('isBeingColonised') or sys_obj.get('is_being_colonised', False)),
                        controlling,
                        norm_security(sys_obj.get('security')),
                        norm_allegiance(sys_obj.get('allegiance')),
                        norm_government(sys_obj.get('government')),
                        needs_permit,
                        main_star_type,
                        main_star_subtype,
                        main_star_scoopable,
                        has_body_data,
                        len(bodies_raw),
                        2 if has_body_data else 0,
                        region_id,
                        parse_ts(sys_obj.get('date') or sys_obj.get('first_discovered_at')),
                        now_iso,
                        True,   # rating_dirty
                        True,   # cluster_dirty
                    ))
                except Exception as _e:
                    skip_count += 1
                    log.debug(f"Skipping system id64={id64}: {_e}")
                    log_import_error(conn, dump_path.name, id64, 'system', _e)
                    continue

                # ── Bodies rows ────────────────────────────────────────────
                for b in bodies_raw:
                    bid = b.get('id64') or b.get('id') or b.get('bodyId')
                    if not bid:
                        continue
                    try:
                        btype_raw = b.get('type', 'Unknown')
                        btype = 'Star' if btype_raw == 'Star' else \
                                'Planet' if btype_raw == 'Planet' else \
                                'Unknown'
                        sc = b.get('spectralClass') or b.get('spectral_class') or ''
                        atm_comp = b.get('atmosphereComposition') or b.get('atmosphere_composition')
                        mats     = b.get('materials')
                        sub_type = b.get('subType') or b.get('subtype') or ''
                        is_main_star = bool(
                            b.get('mainStar') or
                            b.get('isMainStar') or
                            b.get('is_main_star', False)
                        )
                        is_earth_like  = (sub_type == 'Earth-like world') or bool(b.get('isEarthLike') or b.get('is_earth_like', False))
                        is_water_world = (sub_type == 'Water world') or bool(b.get('isWaterWorld') or b.get('is_water_world', False))
                        is_ammonia     = (sub_type == 'Ammonia world') or bool(b.get('isAmmoniaWorld') or b.get('is_ammonia_world', False))
                        tf_state = b.get('terraformingState') or b.get('terraforming_state') or ''
                        is_terraformable = (
                            tf_state == 'Terraformable' or
                            bool(b.get('isTerraformingCandidate') or b.get('is_terraformable', False))
                        )
                        mass = b.get('earthMasses') or b.get('mass')
                        stellar_mass = b.get('solarMasses') or b.get('stellar_mass')

                        body_batch.append((
                            bid, id64,
                            b.get('name', ''),
                            btype,
                            sub_type or None,
                            is_main_star,
                            b.get('distanceToArrival') or b.get('distance_from_star'),
                            b.get('orbitalPeriod') or b.get('orbital_period'),
                            b.get('radius'),
                            mass,
                            b.get('gravity'),
                            b.get('surfaceTemperature') or b.get('surface_temp'),
                            b.get('surfacePressure') or b.get('surface_pressure'),
                            b.get('atmosphereType') or b.get('atmosphere_type'),
                            _json_dumps(atm_comp),
                            b.get('volcanismType') or b.get('volcanism'),
                            _json_dumps(mats),
                            tf_state or None,
                            is_terraformable,
                            bool(b.get('isLandable') or b.get('is_landable', False)),
                            is_water_world,
                            is_earth_like,
                            is_ammonia,
                            _parse_bio_signals(b),
                            _parse_geo_signals(b),
                            sc if sc else None,
                            b.get('luminosity'),
                            stellar_mass,
                            (sc[:1] in SCOOPABLE_STARS) if sc else None,
                            b.get('estimatedMappingValue') or b.get('estimated_mapping_value'),
                            b.get('estimatedScanValue') or b.get('estimated_scan_value'),
                            parse_ts(b.get('updateTime') or b.get('updated_at')),
                            now_iso,
                        ))
                    except Exception as _e:
                        skip_count += 1
                        log.debug(f"Skipping body id={bid} in system {id64}: {_e}")
                        log_import_error(conn, dump_path.name, bid, 'body', _e)
                        continue

                # ── Stations rows ──────────────────────────────────────────
                stations_raw = sys_obj.get('stations', []) or []
                for s in stations_raw:
                    sid = s.get('id') or s.get('marketId') or s.get('market_id')
                    if not sid:
                        skip_count += 1
                        log.debug(f"Skipping station with no id in system {id64}")
                        continue
                    try:
                        svcs = (s.get('services') or
                                s.get('otherServices') or
                                s.get('other_services') or [])
                        svcs_lower = {str(x).lower() for x in svcs}
                        landing_pads = s.get('landingPads') or {}
                        if not isinstance(landing_pads, dict):
                            landing_pads = {}
                        pad_size = ('L' if landing_pads.get('large') else
                                    'M' if landing_pads.get('medium') else
                                    s.get('landing_pad_size'))
                        has_market    = (s.get('market') is not None or
                                         'market' in svcs_lower or
                                         bool(s.get('hasMarket') or s.get('has_market', False)))
                        has_shipyard  = (s.get('shipyard') is not None or
                                         'shipyard' in svcs_lower or
                                         bool(s.get('hasShipyard') or s.get('has_shipyard', False)))
                        has_outfitting= (s.get('outfitting') is not None or
                                         'outfitting' in svcs_lower or
                                         bool(s.get('hasOutfitting') or s.get('has_outfitting', False)))
                        sta_batch.append((
                            sid, id64,
                            s.get('name', ''),
                            norm_station_type(s.get('type') or s.get('station_type')),
                            s.get('distanceToArrival') or s.get('distance_from_star'),
                            s.get('body') or s.get('body_name'),
                            pad_size,
                            has_market,
                            has_shipyard,
                            has_outfitting,
                            'refuel' in svcs_lower or bool(s.get('has_refuel', False)),
                            'repair' in svcs_lower or bool(s.get('has_repair', False)),
                            'restock' in svcs_lower or 'rearm' in svcs_lower or bool(s.get('has_rearm', False)),
                            'black market' in svcs_lower or bool(s.get('has_black_market', False)),
                            'material trader' in svcs_lower or bool(s.get('has_material_trader', False)),
                            'technology broker' in svcs_lower or bool(s.get('has_technology_broker', False)),
                            'interstellar factors contact' in svcs_lower or 'interstellar factors' in svcs_lower or bool(s.get('has_interstellar_factors', False)),
                            'universal cartographics' in svcs_lower or bool(s.get('has_universal_cartographics', False)),
                            'search and rescue' in svcs_lower or bool(s.get('has_search_rescue', False)),
                            norm_economy(s.get('primaryEconomy') or s.get('primary_economy')),
                            norm_economy(s.get('secondaryEconomy') or s.get('secondary_economy')),
                            s.get('controllingFaction') or s.get('controlling_faction'),
                            norm_allegiance(s.get('allegiance')),
                            norm_government(s.get('government')),
                            parse_ts(s.get('updateTime') or s.get('updated_at')) or now_iso,
                        ))
                    except Exception as _e:
                        skip_count += 1
                        log.debug(f"Skipping station id={sid} in system {id64}: {_e}")
                        log_import_error(conn, dump_path.name, sid, 'station', _e)
                        continue

                total_rows += 1

                if len(sys_batch) >= BATCH_SIZE:
                    flush_systems()
                if len(body_batch) >= BATCH_SIZE:
                    flush_bodies()
                if len(sta_batch) >= BATCH_SIZE:
                    flush_stations()

                if time.time() - last_save > 60:
                    flush_systems()
                    flush_bodies()
                    flush_stations()
                    flush_error_batch(conn, dump_path.name)
                    if skip_count > 0:
                        increment_error_count(conn, dump_path.name, skip_count)
                        skip_count = 0
                    try:
                        save_checkpoint(conn, dump_path.name, 0, total_rows + resume_offset, f_raw.tell())
                    except Exception:
                        pass
                    last_save = time.time()
                    pbar.n = f_raw.tell()
                    pbar.refresh()

        except KeyboardInterrupt:
            log.info("Interrupted — saving checkpoint ...")
            flush_systems()
            flush_bodies()
            flush_stations()
            flush_error_batch(conn, dump_path.name)
            save_checkpoint(conn, dump_path.name, 0, total_rows + resume_offset, f_raw.tell())
            log.info(f"Checkpoint saved at row {total_rows + resume_offset:,} "
                     f"({skip_count:,} records skipped)")
            sys.exit(0)

        flush_systems()
        flush_bodies()
        flush_stations()
        flush_error_batch(conn, dump_path.name)
        if skip_count > 0:
            increment_error_count(conn, dump_path.name, skip_count)
        pbar.close()

    if skip_count:
        log.warning(f"Skipped {skip_count:,} malformed records during galaxy import")
    mark_complete(conn, dump_path.name, total_rows)
    log.info(f"galaxy.json.gz complete: {total_rows:,} systems imported")
    return total_rows


# ---------------------------------------------------------------------------
# IMPORTER 2 — galaxy_populated.json.gz  (faction/economy enrichment)
# ---------------------------------------------------------------------------
def import_populated(conn, dump_path: Path, resume_offset: int = 0) -> int:
    """Enrich populated systems with faction, economy, security, government data."""
    log.info(f"Importing populated systems from {dump_path.name} ...")
    set_import_optimisations(conn)

    file_size = dump_path.stat().st_size
    mark_running(conn, dump_path.name, file_size)

    SYS_ENRICH_COLS = [
        'id64', 'name', 'x', 'y', 'z',
        'primary_economy', 'secondary_economy',
        'population', 'security', 'allegiance', 'government',
        'controlling_faction', 'is_colonised',
        'updated_at', 'rating_dirty', 'cluster_dirty',
    ]

    sys_batch  = []
    fac_batch  = []
    sf_batch   = []
    total_rows = 0
    skip_count = 0
    last_save  = time.time()

    def flush_sys():
        if not sys_batch:
            return
        upsert_via_temp(conn, 'systems', SYS_ENRICH_COLS, sys_batch, 'id64',
                        update_cols=[c for c in SYS_ENRICH_COLS if c != 'id64'])
        sys_batch.clear()

    def flush_system_factions():
        if not sf_batch:
            return
        with conn.cursor() as _cur:
            for row in sf_batch:
                try:
                    _cur.execute("""
                        INSERT INTO system_factions
                            (system_id64, faction_id, influence, state, is_controlling, updated_at)
                        SELECT %s, f.id, %s, %s, %s, NOW()
                        FROM factions f
                        WHERE f.name = %s
                        ON CONFLICT (system_id64, faction_id) DO UPDATE
                        SET influence      = EXCLUDED.influence,
                            state          = EXCLUDED.state,
                            is_controlling = EXCLUDED.is_controlling,
                            updated_at     = NOW()
                    """, (row[0], row[2], row[3], row[4], row[1]))
                except Exception as _e:
                    log.debug(f"system_factions upsert skipped: {_e}")
        conn.commit()
        sf_batch.clear()

    def flush_factions():
        if not fac_batch:
            return
        seen: dict = {}
        for name, alleg, gov in fac_batch:
            seen[name] = (name, alleg, gov)
        deduped = list(seen.values())
        with conn.cursor() as _cur:
            psycopg2.extras.execute_values(
                _cur,
                """
                INSERT INTO factions (name, allegiance, government)
                VALUES %s
                ON CONFLICT (name) DO UPDATE
                SET allegiance = EXCLUDED.allegiance,
                    government = EXCLUDED.government,
                    updated_at = NOW()
                """,
                deduped
            )
        conn.commit()
        fac_batch.clear()

    with open(dump_path, 'rb') as f_raw, gzip.open(f_raw, 'rb') as f:
        if resume_offset > 0:
            log.info(f"Resuming from row {resume_offset:,} — fast-forwarding stream ...")
            _item_iter = ijson.items(f, 'item')
            for _i, _ in enumerate(_item_iter, 1):
                if _i % 100_000 == 0:
                    log.info(f"  fast-forward: {_i:,} / {resume_offset:,} rows skipped ...")
                if _i >= resume_offset:
                    break
            log.info(f"Fast-forward complete — continuing import from row {resume_offset:,}")
            items_iter = _item_iter
        else:
            items_iter = ijson.items(f, 'item')

        pbar = tqdm(
            total=file_size, initial=f_raw.tell(),
            unit='B', unit_scale=True, unit_divisor=1024,
            desc=dump_path.name,
        )

        try:
            for sys_obj in items_iter:
                id64 = sys_obj.get('id64')
                if not id64:
                    continue

                now_iso = datetime.now(timezone.utc).isoformat()

                controlling = None
                factions_raw = sys_obj.get('factions', []) or []
                for fac in factions_raw:
                    fname = fac.get('name')
                    if fname:
                        falleg = norm_allegiance(fac.get('allegiance'))
                        fgov   = norm_government(fac.get('government'))
                        fac_batch.append((fname, falleg, fgov))
                        is_ctrl = bool(fac.get('isControlling') or fac.get('is_controlling'))
                        if is_ctrl:
                            controlling = fname
                        sf_batch.append((
                            id64, fname,
                            float(fac.get('influence') or 0),
                            fac.get('state'),
                            is_ctrl,
                        ))

                if not controlling:
                    controlling = sys_obj.get('controllingFaction')

                try:
                    sys_batch.append((
                        id64,
                        sys_obj.get('name', ''),
                        float(sys_obj.get('coords', {}).get('x', 0) if isinstance(sys_obj.get('coords'), dict) else sys_obj.get('x', 0)),
                        float(sys_obj.get('coords', {}).get('y', 0) if isinstance(sys_obj.get('coords'), dict) else sys_obj.get('y', 0)),
                        float(sys_obj.get('coords', {}).get('z', 0) if isinstance(sys_obj.get('coords'), dict) else sys_obj.get('z', 0)),
                        norm_economy(sys_obj.get('primaryEconomy') or sys_obj.get('primary_economy')),
                        norm_economy(sys_obj.get('secondaryEconomy') or sys_obj.get('secondary_economy')),
                        int(sys_obj.get('population') or 0),
                        norm_security(sys_obj.get('security')),
                        norm_allegiance(sys_obj.get('allegiance')),
                        norm_government(sys_obj.get('government')),
                        controlling,
                        True,
                        now_iso,
                        True,
                        True,
                    ))
                except Exception as _e:
                    skip_count += 1
                    log.debug(f"Skipping populated system id64={id64}: {_e}")
                    log_import_error(conn, dump_path.name, id64, 'system', _e)
                    continue

                total_rows += 1

                if len(sys_batch) >= BATCH_SIZE:
                    flush_sys()
                if len(fac_batch) >= BATCH_SIZE:
                    flush_factions()
                    flush_system_factions()
                if len(sf_batch) >= BATCH_SIZE:
                    flush_factions()
                    flush_system_factions()

                if time.time() - last_save > 60:
                    flush_sys()
                    flush_factions()
                    flush_system_factions()
                    flush_error_batch(conn, dump_path.name)
                    try:
                        save_checkpoint(conn, dump_path.name, 0, total_rows + resume_offset, f_raw.tell())
                    except Exception:
                        pass
                    last_save = time.time()
                    pbar.n = f_raw.tell()
                    pbar.refresh()

        except KeyboardInterrupt:
            log.info("Interrupted — saving checkpoint ...")
            flush_sys()
            flush_factions()
            flush_system_factions()
            flush_error_batch(conn, dump_path.name)
            save_checkpoint(conn, dump_path.name, 0, total_rows + resume_offset, f_raw.tell())
            sys.exit(0)

        flush_sys()
        flush_factions()
        flush_system_factions()
        flush_error_batch(conn, dump_path.name)
        pbar.close()

    mark_complete(conn, dump_path.name, total_rows)
    log.info(f"galaxy_populated.json.gz complete: {total_rows:,} systems enriched")
    return total_rows


# ---------------------------------------------------------------------------
# IMPORTER 3 — galaxy_stations.json.gz  (station refresh)
# ---------------------------------------------------------------------------
def import_stations(conn, dump_path: Path, resume_offset: int = 0) -> int:
    """Re-import all stations with latest market/service/economy state."""
    log.info(f"Importing stations from {dump_path.name} ...")
    set_import_optimisations(conn)

    file_size = dump_path.stat().st_size
    mark_running(conn, dump_path.name, file_size)

    STA_COLS = [
        'id', 'system_id64', 'name', 'station_type',
        'distance_from_star', 'body_name',
        'landing_pad_size',
        'has_market', 'has_shipyard', 'has_outfitting',
        'has_refuel', 'has_repair', 'has_rearm',
        'has_black_market', 'has_material_trader',
        'has_technology_broker', 'has_interstellar_factors',
        'has_universal_cartographics', 'has_search_rescue',
        'primary_economy', 'secondary_economy',
        'controlling_faction', 'allegiance', 'government',
        'updated_at',
    ]

    sta_batch  = []
    total_rows = 0
    skip_count = 0
    last_save  = time.time()

    def flush():
        if sta_batch:
            upsert_via_temp(conn, 'stations', STA_COLS, sta_batch, 'id')
            sta_batch.clear()

    with open(dump_path, 'rb') as f_raw, gzip.open(f_raw, 'rb') as f:
        if resume_offset > 0:
            log.info(f"Resuming from row {resume_offset:,} — fast-forwarding stream ...")
            _item_iter = ijson.items(f, 'item')
            for _i, _ in enumerate(_item_iter, 1):
                if _i % 100_000 == 0:
                    log.info(f"  fast-forward: {_i:,} / {resume_offset:,} rows skipped ...")
                if _i >= resume_offset:
                    break
            log.info(f"Fast-forward complete — continuing import from row {resume_offset:,}")
            items_iter = _item_iter
        else:
            items_iter = ijson.items(f, 'item')

        pbar = tqdm(
            total=file_size, initial=f_raw.tell(),
            unit='B', unit_scale=True, unit_divisor=1024,
            desc=dump_path.name,
        )

        try:
            for s in items_iter:
                sid      = s.get('id') or s.get('marketId') or s.get('market_id')
                sys_id64 = s.get('systemId64') or s.get('system_id64')
                if not sid or not sys_id64:
                    continue

                now_iso  = datetime.now(timezone.utc).isoformat()
                try:
                    svcs = (s.get('services') or
                            s.get('otherServices') or
                            s.get('other_services') or [])
                    svcs_lower = {str(x).lower() for x in svcs}
                    landing_pads = s.get('landingPads') or {}
                    if not isinstance(landing_pads, dict):
                        landing_pads = {}
                    has_market     = (s.get('market') is not None or 'market' in svcs_lower or bool(s.get('hasMarket') or s.get('has_market', False)))
                    has_shipyard   = (s.get('shipyard') is not None or 'shipyard' in svcs_lower or bool(s.get('hasShipyard') or s.get('has_shipyard', False)))
                    has_outfitting = (s.get('outfitting') is not None or 'outfitting' in svcs_lower or bool(s.get('hasOutfitting') or s.get('has_outfitting', False)))

                    sta_batch.append((
                        sid, sys_id64,
                        s.get('name', ''),
                        norm_station_type(s.get('type') or s.get('stationType') or s.get('station_type')),
                        s.get('distanceToArrival') or s.get('distance_from_star'),
                        s.get('body') or s.get('body_name'),
                        'L' if landing_pads.get('large') else ('M' if landing_pads.get('medium') else s.get('landing_pad_size')),
                        has_market,
                        has_shipyard,
                        has_outfitting,
                        'refuel' in svcs_lower,
                        'repair' in svcs_lower,
                        'restock' in svcs_lower or 'rearm' in svcs_lower,
                        'black market' in svcs_lower,
                        'material trader' in svcs_lower,
                        'technology broker' in svcs_lower,
                        'interstellar factors contact' in svcs_lower or 'interstellar factors' in svcs_lower,
                        'universal cartographics' in svcs_lower,
                        'search and rescue' in svcs_lower,
                        norm_economy(s.get('primaryEconomy') or s.get('primary_economy')),
                        norm_economy(s.get('secondaryEconomy') or s.get('secondary_economy')),
                        s.get('controllingFaction') or s.get('controlling_faction'),
                        norm_allegiance(s.get('allegiance')),
                        norm_government(s.get('government')),
                        parse_ts(s.get('updateTime') or s.get('updated_at')) or now_iso,
                    ))
                except Exception as _e:
                    skip_count += 1
                    log.debug(f"Skipping station id={sid} in system {sys_id64}: {_e}")
                    log_import_error(conn, dump_path.name, sid, 'station', _e)
                    continue

                total_rows += 1

                if len(sta_batch) >= BATCH_SIZE:
                    flush()

                if time.time() - last_save > 60:
                    flush()
                    flush_error_batch(conn, dump_path.name)
                    try:
                        save_checkpoint(conn, dump_path.name, 0, total_rows + resume_offset, f_raw.tell())
                    except Exception:
                        pass
                    last_save = time.time()
                    pbar.n = f_raw.tell()
                    pbar.refresh()

        except KeyboardInterrupt:
            log.info("Interrupted — saving checkpoint ...")
            flush()
            flush_error_batch(conn, dump_path.name)
            save_checkpoint(conn, dump_path.name, 0, total_rows + resume_offset, f_raw.tell())
            sys.exit(0)

        flush()
        flush_error_batch(conn, dump_path.name)
        if skip_count > 0:
            increment_error_count(conn, dump_path.name, skip_count)
        pbar.close()

    if skip_count:
        log.warning(f"Skipped {skip_count:,} malformed station records")
    mark_complete(conn, dump_path.name, total_rows)
    log.info(f"galaxy_stations.json.gz complete: {total_rows:,} stations imported")
    return total_rows


# ---------------------------------------------------------------------------
# IMPORTER 4 — systems delta files (1day / 1week / 1month)
# ---------------------------------------------------------------------------
def import_systems_delta(conn, dump_path: Path, resume_offset: int = 0) -> int:
    """Import a Spansh systems delta file (flat list of system objects)."""
    log.info(f"Importing systems delta from {dump_path.name} ...")
    set_import_optimisations(conn)

    file_size = dump_path.stat().st_size
    mark_running(conn, dump_path.name, file_size)

    SYS_COLS = [
        'id64', 'name', 'x', 'y', 'z',
        'primary_economy', 'secondary_economy',
        'population', 'security', 'allegiance', 'government',
        'controlling_faction', 'galaxy_region_id',
        'updated_at', 'rating_dirty', 'cluster_dirty',
    ]

    sys_batch  = []
    total_rows = 0
    last_save  = time.time()

    def flush():
        if sys_batch:
            upsert_via_temp(conn, 'systems', SYS_COLS, sys_batch, 'id64',
                            update_cols=[c for c in SYS_COLS if c != 'id64'])
            sys_batch.clear()

    with open(dump_path, 'rb') as f_raw, gzip.open(f_raw, 'rb') as f:
        pbar = tqdm(
            total=file_size, initial=0,
            unit='B', unit_scale=True, unit_divisor=1024,
            desc=dump_path.name,
        )

        _rows_skipped = 0
        try:
            for sys_obj in ijson.items(f, 'item'):
                if _rows_skipped < resume_offset:
                    _rows_skipped += 1
                    continue

                id64 = sys_obj.get('id64')
                if not id64:
                    continue

                now_iso = datetime.now(timezone.utc).isoformat()

                controlling = sys_obj.get('controllingFaction') or sys_obj.get('controlling_faction')
                if not controlling:
                    for fac in (sys_obj.get('factions') or []):
                        if fac.get('isControlling'):
                            controlling = fac.get('name')
                            break

                try:
                    coords = sys_obj.get('coords') or {}
                    coords = coords if isinstance(coords, dict) else {}
                    sx = float(coords.get('x') or sys_obj.get('x') or 0)
                    sy = float(coords.get('y') or sys_obj.get('y') or 0)
                    sz = float(coords.get('z') or sys_obj.get('z') or 0)
                    region_id = find_galaxy_region(sx, sz)
                except Exception:
                    sx, sy, sz = 0.0, 0.0, 0.0
                    region_id = None

                sys_batch.append((
                    id64,
                    sys_obj.get('name', ''),
                    sx, sy, sz,
                    norm_economy(sys_obj.get('primaryEconomy') or sys_obj.get('primary_economy')),
                    norm_economy(sys_obj.get('secondaryEconomy') or sys_obj.get('secondary_economy')),
                    int(sys_obj.get('population') or 0),
                    norm_security(sys_obj.get('security')),
                    norm_allegiance(sys_obj.get('allegiance')),
                    norm_government(sys_obj.get('government')),
                    controlling,
                    region_id,
                    now_iso,
                    True,
                    True,
                ))

                total_rows += 1

                if len(sys_batch) >= BATCH_SIZE:
                    flush()

                if time.time() - last_save > 60:
                    flush()
                    try:
                        save_checkpoint(conn, dump_path.name, 0, total_rows + resume_offset, f_raw.tell())
                    except Exception:
                        pass
                    last_save = time.time()
                    pbar.n = f_raw.tell()
                    pbar.refresh()

        except KeyboardInterrupt:
            flush()
            save_checkpoint(conn, dump_path.name, 0, total_rows + resume_offset, f_raw.tell())
            sys.exit(0)

        flush()
        pbar.close()

    mark_complete(conn, dump_path.name, total_rows)
    log.info(f"{dump_path.name} complete: {total_rows:,} systems updated")
    return total_rows


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------
def _download_with_aria2(url: str, dest: Path) -> bool:
    import shutil, subprocess
    if not shutil.which('aria2c'):
        return False
    log.info("  Using aria2c (16 parallel connections) ...")
    cmd = [
        'aria2c', '--continue=true',
        '--split=16', '--max-connection-per-server=16',
        '--min-split-size=10M', '--max-tries=5', '--retry-wait=10',
        '--file-allocation=falloc',
        '--dir', str(dest.parent), '--out', dest.name, url,
    ]
    return subprocess.run(cmd).returncode == 0


def _download_with_wget(url: str, dest: Path) -> bool:
    import shutil, subprocess
    if not shutil.which('wget'):
        return False
    log.info("  Using wget (resumable) ...")
    return subprocess.run(['wget', '--continue', '--show-progress', '-O', str(dest), url]).returncode == 0


def _download_with_curl(url: str, dest: Path) -> bool:
    import shutil, subprocess
    if not shutil.which('curl'):
        return False
    log.info("  Using curl (resumable) ...")
    return subprocess.run(['curl', '-L', '-C', '-', '--progress-bar', '-o', str(dest), url]).returncode == 0


def download_dumps(files: list):
    """Download Spansh dump files using the fastest available method."""
    import urllib.request
    DUMP_DIR.mkdir(parents=True, exist_ok=True)

    for fname in files:
        dest = DUMP_DIR / fname
        if dest.exists():
            log.info(f"Already exists: {fname} ({dest.stat().st_size / 1e9:.1f} GB) — skipping")
            continue

        url = f"{SPANSH_BASE}/{fname}"
        log.info(f"Downloading {url}")
        tmp = dest.with_suffix(dest.suffix + '.tmp')
        ok  = False

        for method in (_download_with_aria2, _download_with_wget, _download_with_curl):
            try:
                if method(url, tmp):
                    tmp.rename(dest)
                    log.info(f"✅ {fname}: {dest.stat().st_size / 1e9:.1f} GB")
                    ok = True
                    break
            except Exception as e:
                log.warning(f"  {method.__name__} failed: {e}")

        if not ok:
            log.warning("  Falling back to urllib ...")
            try:
                def _progress(bc, bs, total):
                    if total > 0:
                        print(f"\r  {fname}: {bc*bs/total*100:.1f}% ({bc*bs/1e9:.1f}/{total/1e9:.1f} GB)",
                              end='', flush=True)
                urllib.request.urlretrieve(url, tmp, reporthook=_progress)
                print()
                tmp.rename(dest)
                log.info(f"✅ {fname}: {dest.stat().st_size / 1e9:.1f} GB")
            except Exception as e:
                log.error(f"❌ Failed to download {fname}: {e}")
                tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Status display
# ---------------------------------------------------------------------------
def show_status(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT dump_file, status, rows_processed, bytes_processed,
                   bytes_total, errors_encountered,
                   CASE WHEN bytes_total > 0
                       THEN round(bytes_processed::numeric / bytes_total * 100, 1)
                       ELSE 0 END AS pct,
                   started_at, completed_at, error_message
            FROM import_meta ORDER BY id
        """)
        rows = cur.fetchall()

    print(f"\n{'File':<35} {'Status':<10} {'Rows':>12} {'Errors':>8} {'Progress':>10} {'Started':<22}")
    print("-" * 105)
    for r in rows:
        fname, status, rows_proc, bytes_proc, bytes_total, errors, pct, started, completed, err = r
        started_str = started.strftime('%Y-%m-%d %H:%M') if started else 'not started'
        pct_str = f"{pct}%" if pct else "0%"
        err_str = f"{errors:,}" if errors else "0"
        print(f"{fname:<35} {str(status):<10} {(rows_proc or 0):>12,} {err_str:>8} {pct_str:>10} {started_str:<22}")
        if err:
            print(f"  LAST ERROR: {err[:80]}")
    print()


def show_errors(conn, limit: int = 50):
    """Show recent structured import errors from the import_errors table."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT dump_file, record_type, record_id, error_class,
                   error_message, occurred_at
            FROM import_errors
            ORDER BY occurred_at DESC
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall()

    if not rows:
        print("\nNo import errors recorded.")
        return

    print(f"\n{'Time':<22} {'File':<30} {'Type':<10} {'ID':>15} {'Error'}")
    print("-" * 110)
    for r in rows:
        dump_file, rec_type, rec_id, err_class, err_msg, occurred = r
        t = occurred.strftime('%Y-%m-%d %H:%M:%S') if occurred else '?'
        rid = str(rec_id) if rec_id else 'N/A'
        print(f"{t:<22} {dump_file:<30} {rec_type:<10} {rid:>15}  [{err_class}] {err_msg[:60]}")
    print()


# ---------------------------------------------------------------------------
# Importer dispatch map
# ---------------------------------------------------------------------------
IMPORTER_MAP = {
    'galaxy.json.gz':           import_galaxy,
    'galaxy_populated.json.gz': import_populated,
    'galaxy_stations.json.gz':  import_stations,
    'systems_1day.json.gz':     import_systems_delta,
    'systems_1week.json.gz':    import_systems_delta,
    'systems_1month.json.gz':   import_systems_delta,
}

IMPORT_ORDER = [
    'galaxy.json.gz',
    'galaxy_populated.json.gz',
    'galaxy_stations.json.gz',
]


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------
def main():
    global DUMP_DIR, BATCH_SIZE

    parser = argparse.ArgumentParser(
        description='ED Finder — Spansh dump importer v3.0 (PostgreSQL COPY + region lookup)'
    )
    parser.add_argument('--all',           action='store_true', help='Import all dumps in order')
    parser.add_argument('--file',          type=str,            help='Import a specific dump file')
    parser.add_argument('--resume',        action='store_true', help='Resume from last checkpoint')
    parser.add_argument('--download',      action='store_true', help='Download dumps before importing')
    parser.add_argument('--download-only', action='store_true', help='Download dumps then exit')
    parser.add_argument('--status',        action='store_true', help='Show import status')
    parser.add_argument('--errors',        action='store_true', help='Show recent import errors from DB')
    parser.add_argument('--probe',         type=str,            help='Print field keys from dump file')
    parser.add_argument('--dump-dir',      type=str,            help=f'Dump directory (default: {DUMP_DIR})')
    parser.add_argument('--batch-size',    type=int,            help=f'Batch size for COPY (default: {BATCH_SIZE})')
    args = parser.parse_args()

    if args.dump_dir:
        DUMP_DIR = Path(args.dump_dir)
    if args.batch_size:
        BATCH_SIZE = args.batch_size

    conn = get_conn()

    if args.status:
        show_status(conn)
        return

    if args.errors:
        show_errors(conn)
        return

    if args.download or getattr(args, 'download_only', False):
        files = [args.file] if args.file else IMPORT_ORDER
        download_dumps(files)

    if getattr(args, 'download_only', False):
        log.info("Download complete. Run with --all (or --file) to import.")
        return

    files_to_import = IMPORT_ORDER if args.all else ([args.file] if args.file else [])
    if not files_to_import:
        parser.print_help()
        return

    def _get_status(fname: str) -> Optional[str]:
        try:
            with conn.cursor() as _cur:
                _cur.execute("SELECT status FROM import_meta WHERE dump_file = %s", (fname,))
                row = _cur.fetchone()
                return str(row[0]) if row else None
        except Exception:
            return None

    total_start = time.time()
    for fname in files_to_import:
        dump_path = DUMP_DIR / fname
        if not dump_path.exists():
            log.error(f"Dump file not found: {dump_path}")
            log.error(f"Run with --download-only first, or place files in {DUMP_DIR}")
            continue

        importer_fn = IMPORTER_MAP.get(fname)
        if not importer_fn:
            log.error(f"No importer for: {fname}")
            continue

        current_status = _get_status(fname)
        if current_status == 'complete' and not args.resume:
            log.info(f"⏭  {fname}: already complete — skipping (use --resume to re-run)")
            continue

        auto_resume = (current_status == 'running') or args.resume
        resume_offset = get_checkpoint(conn, fname) if auto_resume else 0
        if resume_offset > 0:
            log.info(f"Auto-resuming {fname} from row {resume_offset:,} (status was: {current_status})")
        elif auto_resume and resume_offset == 0:
            log.info(f"No checkpoint found for {fname} — starting from beginning")

        start = time.time()
        try:
            rows = importer_fn(conn, dump_path, resume_offset)
            elapsed = time.time() - start
            log.info(f"✅ {fname}: {rows:,} rows in {elapsed/3600:.2f}h")
        except Exception as e:
            log.error(f"❌ {fname} failed: {e}", exc_info=True)
            mark_failed(conn, fname, str(e))

    total_elapsed = time.time() - total_start
    log.info(f"All imports complete in {total_elapsed/3600:.2f} hours")

    # Auto-rebuild indexes if they were dropped for the import
    if args.all or args.file:
        try:
            with conn.cursor() as _cur:
                _cur.execute("SELECT count(*) FROM pg_indexes WHERE tablename = 'systems' AND indexname NOT LIKE '%pkey%'")
                idx_count = _cur.fetchone()[0]
                if idx_count < 5:
                    log.info("--- AUTOMATIC INDEX REBUILD ---")
                    log.info("Indexes are missing (likely dropped for import). Starting rebuild from 002_indexes.sql ...")
                    log.info("This will take 1-3 hours. Do not interrupt.")
                    old_autocommit = conn.autocommit
                    conn.autocommit = True
                    sql_path = Path(__file__).parent.parent / 'sql' / '002_indexes.sql'
                    if sql_path.exists():
                        with open(sql_path, 'r') as sql_f:
                            sql_commands = sql_f.read()
                            _cur.execute(sql_commands)
                        log.info("✅ Indexes rebuilt successfully.")
                    else:
                        log.warning(f"Could not find {sql_path} — please run manually.")
                    conn.autocommit = old_autocommit
                else:
                    log.info(f"Indexes already exist ({idx_count} found) — skipping auto-rebuild.")
        except Exception as e:
            log.error(f"Failed to auto-rebuild indexes: {e}")

    log.info("Next steps (run in this exact order):")
    log.info("  1. python3 build_grid.py      — build 500 LY + 2000 LY spatial grids (~1-2h)")
    log.info("  2. python3 build_ratings.py   — compute economy scores (~3-5h)")
    log.info("  3. python3 build_clusters.py  — build cluster summaries (~2-4h)")


if __name__ == '__main__':
    main()
