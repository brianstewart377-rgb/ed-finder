#!/usr/bin/env python3
"""
ED Finder — Spansh Dump Importer  (PostgreSQL / psycopg2 COPY edition)
Version: 2.0

Why psycopg2 COPY instead of INSERT ... ON CONFLICT:
  • COPY is the fastest possible PostgreSQL bulk-load method — it bypasses the
    SQL parser, planner, and most of the rewrite rules.
  • Uses a StringIO/BytesIO pipe fed directly to PostgreSQL's COPY protocol.
  • On a Hetzner AX41 (i7-8700, 128 GB RAM, NVMe RAID-5) with indexes dropped:
      INSERT ... ON CONFLICT:  ~250 kB/s  (~4-5 days for 110 GB)
      COPY + upsert merge:     ~5-15 MB/s (~2-8 hours for 110 GB)
  • Strategy: COPY into a temp table, then INSERT ... ON CONFLICT from temp
    into the real table.  This gives us both speed AND upsert semantics.

Server:   Hetzner AX41-SSD — i7-8700 (6C/12T), 128 GB RAM, 3×1 TB NVMe RAID-5
Database: PostgreSQL 16

Usage:
    python3 import_spansh.py --all                   # import all dumps
    python3 import_spansh.py --file galaxy.json.gz   # import one file
    python3 import_spansh.py --all --resume          # resume from checkpoint
    python3 import_spansh.py --download-only         # download files then exit
    python3 import_spansh.py --download --all        # download then import
    python3 import_spansh.py --status                # show import progress

Spansh dump URLs (current as of 2025):
    https://downloads.spansh.co.uk/galaxy.json.gz           (~102 GB)
    https://downloads.spansh.co.uk/galaxy_populated.json.gz (~3.6 GB)
    https://downloads.spansh.co.uk/galaxy_stations.json.gz  (~3.6 GB)
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
DB_DSN          = os.getenv('DATABASE_URL',
                    'postgresql://edfinder:edfinder@localhost:5432/edfinder')
DUMP_DIR        = Path(os.getenv('DUMP_DIR', '/data/dumps'))
BATCH_SIZE      = int(os.getenv('BATCH_SIZE', '50000'))   # much larger for COPY
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

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
def get_conn() -> psycopg2.extensions.connection:
    conn = psycopg2.connect(DB_DSN)
    conn.autocommit = False
    # Use server-side cursors for large result sets
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


def save_checkpoint(conn, dump_file: str, offset: int, rows: int):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE import_meta
            SET last_checkpoint = %s,
                rows_processed  = %s,
                bytes_processed = %s,
                updated_at      = NOW()
            WHERE dump_file = %s
        """, (offset, rows, offset, dump_file))
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
# COPY helper — the core speed improvement
# ---------------------------------------------------------------------------
def copy_records(conn, table: str, columns: List[str], rows: List[Tuple]) -> int:
    """
    Bulk-insert rows into `table` using PostgreSQL COPY protocol via a
    StringIO pipe.  This is ~20-50x faster than executemany() for large batches.

    Returns number of rows inserted.
    """
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
                # Escape special COPY characters
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
    col_list = ', '.join(columns)
    with conn.cursor() as cur:
        cur.copy_from(buf, table, columns=columns, null='\\N')
    conn.commit()
    return len(rows)


def upsert_via_temp(conn, target_table: str, columns: List[str],
                    rows: List[Tuple], conflict_col: str,
                    update_cols: Optional[List[str]] = None) -> int:
    """
    COPY rows into a temp table then INSERT ... ON CONFLICT DO UPDATE into
    the real table.  Gives us COPY speed + upsert semantics.

    conflict_col: the PRIMARY KEY / UNIQUE column to conflict on.
    update_cols:  columns to update on conflict (defaults to all non-PK cols).
    """
    if not rows:
        return 0

    if update_cols is None:
        update_cols = [c for c in columns if c != conflict_col]

    temp = f"_tmp_{target_table}"
    col_list   = ', '.join(columns)
    set_clause = ', '.join(f"{c} = EXCLUDED.{c}" for c in update_cols)

    with conn.cursor() as cur:
        # Create temp table mirroring target (no constraints, no indexes — fast)
        cur.execute(f"""
            CREATE TEMP TABLE IF NOT EXISTS {temp}
            (LIKE {target_table} INCLUDING DEFAULTS)
            ON COMMIT DELETE ROWS
        """)
        conn.commit()

        # COPY into temp
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

        # Upsert from temp → real table
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
    # Normalise common variants
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
    """Convert any timestamp value to an ISO8601 string PostgreSQL can accept.
    Handles: Unix epoch int/float, ISO8601 strings, other strings (passed through).
    """
    if not v:
        return None
    try:
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(v, tz=timezone.utc).isoformat()
        # Validate/normalise ISO8601 strings so COPY doesn't fail on bad formats
        s = str(v).strip()
        try:
            dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
            return dt.isoformat()
        except ValueError:
            pass
        # Pass through anything else and let PostgreSQL complain if it's wrong
        return s
    except Exception:
        return None


def parse_bool(v) -> Optional[bool]:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    return str(v).lower() in ('true', '1', 'yes')


# ---------------------------------------------------------------------------
# Signal count helpers — Spansh uses multiple inconsistent shapes:
#   dict count:  {"genuses": 3, "geology": 1}
#   dict list:   {"genuses": ["$genus_name1;", ...], "geology": [...]}
#   list:        [{"type": "Biology", "count": 3}, {"type": "Geology", "count": 1}]
# ---------------------------------------------------------------------------
def _to_signal_count(val) -> int:
    """Convert any signal value shape to an integer count."""
    if val is None:
        return 0
    if isinstance(val, list):
        return len(val)          # list of genus names — count = length
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

    Uses COPY-via-temp for bulk loads:
      - Systems batch: 50,000 rows → COPY to temp → upsert to systems
      - Bodies batch:  50,000 rows → COPY to temp → upsert to bodies
      - Stations batch: 50,000 rows → COPY to temp → upsert to stations

    Performance target: 5-15 MB/s on Hetzner AX41 with indexes dropped.
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
        'main_star_type', 'main_star_subtype', 'main_star_is_scoopable',
        'has_body_data', 'body_count', 'data_quality',
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
    last_save   = time.time()

    def flush_systems():
        if sys_batch:
            upsert_via_temp(conn, 'systems', SYS_COLS, sys_batch, 'id64')
            sys_batch.clear()

    def flush_bodies():
        # Always flush systems first — bodies have a FK on system_id64
        flush_systems()
        if body_batch:
            upsert_via_temp(conn, 'bodies', BODY_COLS, body_batch, 'id')
            body_batch.clear()

    def flush_stations():
        # Always flush systems first — stations have a FK on system_id64
        flush_systems()
        if sta_batch:
            upsert_via_temp(conn, 'stations', STA_COLS, sta_batch, 'id')
            sta_batch.clear()

    with gzip.open(dump_path, 'rb') as f:
        if resume_offset > 0:
            log.info(f"Seeking to resume offset {resume_offset:,} ...")
            f.seek(resume_offset)

        pbar = tqdm(
            total=file_size,
            initial=resume_offset,
            unit='B', unit_scale=True, unit_divisor=1024,
            desc=dump_path.name,
        )

        _skip_count = 0  # count of individual bad records skipped

        try:
            for sys_obj in ijson.items(f, 'item'):
                id64 = sys_obj.get('id64')
                if not id64:
                    continue

                now_iso = datetime.now(timezone.utc).isoformat()

                # ── Determine main star from nested bodies ─────────────────
                bodies_raw = sys_obj.get('bodies', []) or []
                main_star_type      = None
                main_star_subtype   = None
                main_star_scoopable = None
                has_body_data = len(bodies_raw) > 0

                for b in bodies_raw:
                    # Spansh schema uses 'mainStar' (not 'isMainStar')
                    if b.get('mainStar') or b.get('isMainStar') or b.get('is_main_star'):
                        sc = b.get('spectralClass') or b.get('spectral_class') or ''
                        main_star_type    = sc[:1] if sc else None
                        main_star_subtype = sc[1:] if len(sc) > 1 else None
                        main_star_scoopable = main_star_type in SCOOPABLE_STARS if main_star_type else None
                        break

                # ── Systems row ───────────────────────────────────────────
                controlling  = None
                factions_raw = sys_obj.get('factions', []) or []
                for fac in factions_raw:
                    if fac.get('isControlling') or fac.get('is_controlling'):
                        controlling = fac.get('name')
                        break
                if not controlling:
                    controlling = sys_obj.get('controllingFaction') or sys_obj.get('controlling_faction')

                try:
                    coords = sys_obj.get('coords') or {}
                    coords = coords if isinstance(coords, dict) else {}
                    sys_batch.append((
                        id64,
                        sys_obj.get('name', ''),
                        float(coords.get('x') or sys_obj.get('x') or 0),
                        float(coords.get('y') or sys_obj.get('y') or 0),
                        float(coords.get('z') or sys_obj.get('z') or 0),
                        norm_economy(sys_obj.get('primaryEconomy') or sys_obj.get('primary_economy')),
                        norm_economy(sys_obj.get('secondaryEconomy') or sys_obj.get('secondary_economy')),
                        int(sys_obj.get('population') or 0),
                        bool(sys_obj.get('isColonised') or sys_obj.get('is_colonised', False)),
                        bool(sys_obj.get('isBeingColonised') or sys_obj.get('is_being_colonised', False)),
                        controlling,
                        norm_security(sys_obj.get('security')),
                        norm_allegiance(sys_obj.get('allegiance')),
                        norm_government(sys_obj.get('government')),
                        main_star_type,
                        main_star_subtype,
                        main_star_scoopable,
                        has_body_data,
                        len(bodies_raw),
                        2 if has_body_data else 0,
                        parse_ts(sys_obj.get('date') or sys_obj.get('first_discovered_at')),
                        now_iso,
                        True,   # rating_dirty
                        True,   # cluster_dirty
                    ))
                except Exception as _e:
                    _skip_count += 1
                    log.debug(f"Skipping system id64={id64} ({sys_obj.get('name','')}): {_e}")
                    continue

                # ── Bodies rows ───────────────────────────────────────────
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

                        # Spansh galaxy.json schema: subType-based world flags
                        # (no isEarthLike/isWaterWorld/isAmmoniaWorld boolean fields in dump)
                        sub_type = b.get('subType') or b.get('subtype') or ''
                        is_main_star = bool(
                            b.get('mainStar') or          # official Spansh schema key
                            b.get('isMainStar') or         # legacy/API key
                            b.get('is_main_star', False)   # snake_case fallback
                        )
                        is_earth_like  = (sub_type == 'Earth-like world') or bool(b.get('isEarthLike') or b.get('is_earth_like', False))
                        is_water_world = (sub_type == 'Water world') or bool(b.get('isWaterWorld') or b.get('is_water_world', False))
                        is_ammonia     = (sub_type == 'Ammonia world') or bool(b.get('isAmmoniaWorld') or b.get('is_ammonia_world', False))

                        # terraformable: check terraformingState field value
                        tf_state = b.get('terraformingState') or b.get('terraforming_state') or ''
                        is_terraformable = (
                            tf_state == 'Terraformable' or
                            bool(b.get('isTerraformingCandidate') or b.get('is_terraformable', False))
                        )

                        # mass column = Earth masses for planets, solar masses for stars.
                        # Deliberately do NOT fall through to solarMasses here; that
                        # goes into the dedicated stellar_mass column below.
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
                            # radius is always in km in Spansh dumps.
                            # solarRadius is in solar radii (~695,700 km) — completely
                            # different unit, so we never mix them.
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
                            sc if sc else None,   # full spectral class — no truncation
                            b.get('luminosity'),
                            stellar_mass,
                            (sc[:1] in SCOOPABLE_STARS) if sc else None,
                            b.get('estimatedMappingValue') or b.get('estimated_mapping_value'),
                            b.get('estimatedScanValue') or b.get('estimated_scan_value'),
                            parse_ts(b.get('updateTime') or b.get('updated_at')),
                            now_iso,
                        ))
                    except Exception as _e:
                        _skip_count += 1
                        log.debug(f"Skipping body id={bid} in system {id64}: {_e}")
                        continue

                # ── Stations rows ─────────────────────────────────────────
                stations_raw = sys_obj.get('stations', []) or []
                for s in stations_raw:
                    sid = s.get('id') or s.get('marketId') or s.get('market_id')
                    if not sid:
                        continue
                    try:
                        # Spansh schema uses 'services' array (not 'otherServices')
                        # Values like "Market", "Shipyard", "Outfitting", "Refuel", etc.
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
                        # market/shipyard/outfitting: present as nested objects in schema,
                        # OR as boolean flags (hasMarket), OR via services list
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
                        _skip_count += 1
                        log.debug(f"Skipping station id={sid} in system {id64}: {_e}")
                        continue

                total_rows += 1

                # Flush when batches are full — ORDER MATTERS: systems before bodies/stations
                # (bodies and stations have FK on system_id64 → parent must exist first)
                if len(sys_batch) >= BATCH_SIZE:
                    flush_systems()
                if len(body_batch) >= BATCH_SIZE:
                    flush_bodies()   # internally calls flush_systems() first
                if len(sta_batch) >= BATCH_SIZE:
                    flush_stations()  # internally calls flush_systems() first

                # Checkpoint every 60 seconds
                if time.time() - last_save > 60:
                    flush_systems()
                    flush_bodies()
                    flush_stations()
                    try:
                        save_checkpoint(conn, dump_path.name, f.tell(), total_rows)
                    except Exception:
                        pass
                    last_save = time.time()
                    pbar.update(f.tell() - pbar.n - resume_offset)

        except KeyboardInterrupt:
            log.info("Interrupted — saving checkpoint ...")
            flush_systems()
            flush_bodies()
            flush_stations()
            save_checkpoint(conn, dump_path.name, f.tell(), total_rows)
            log.info(f"Checkpoint saved at {f.tell():,} bytes, {total_rows:,} systems "
                     f"({_skip_count:,} records skipped)")
            sys.exit(0)

        # Final flush
        flush_systems()
        flush_bodies()
        flush_stations()
        pbar.close()

    if _skip_count:
        log.warning(f"Skipped {_skip_count:,} malformed records during galaxy import")
    mark_complete(conn, dump_path.name, total_rows)
    log.info(f"galaxy.json.gz complete: {total_rows:,} systems imported")
    return total_rows


# ---------------------------------------------------------------------------
# IMPORTER 2 — galaxy_populated.json.gz  (faction/economy enrichment)
# ---------------------------------------------------------------------------
def import_populated(conn, dump_path: Path, resume_offset: int = 0) -> int:
    """
    Enrich populated systems with faction, economy, security, government data.
    Also upserts factions and system_factions tables.
    """
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
    fac_batch  = []   # (name, allegiance, government)
    sf_batch   = []   # (system_id64, faction_name, influence, state, is_controlling)
    total_rows = 0
    last_save  = time.time()

    def flush_sys():
        if not sys_batch:
            return
        upsert_via_temp(conn, 'systems', SYS_ENRICH_COLS, sys_batch, 'id64',
                        update_cols=[c for c in SYS_ENRICH_COLS if c != 'id64'])
        sys_batch.clear()

    def flush_system_factions():
        """
        Upsert system_factions rows.  We resolve faction name -> id by joining
        against the factions table that was just flushed by flush_factions().
        Rows whose faction name does not exist yet are silently skipped.
        """
        if not sf_batch:
            return
        # sf_batch rows: (system_id64, faction_name, influence, state, is_controlling)
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
        # Deduplicate by name — same faction can appear in multiple systems
        # in the same batch; ON CONFLICT cannot affect the same row twice
        seen: dict = {}
        for name, alleg, gov in fac_batch:
            seen[name] = (name, alleg, gov)
        deduped = list(seen.values())
        # Upsert factions — use explicit cursor so it's properly closed
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

    with gzip.open(dump_path, 'rb') as f:
        if resume_offset > 0:
            f.seek(resume_offset)

        pbar = tqdm(
            total=file_size, initial=resume_offset,
            unit='B', unit_scale=True, unit_divisor=1024,
            desc=dump_path.name,
        )

        try:
            for sys_obj in ijson.items(f, 'item'):
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
                        # Queue system_factions row (resolved to faction id in flush)
                        sf_batch.append((
                            id64,
                            fname,
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
                        True,   # is_colonised — all populated systems are colonised
                        now_iso,
                        True,   # rating_dirty
                        True,   # cluster_dirty
                    ))
                except Exception as _e:
                    log.debug(f"Skipping populated system id64={id64}: {_e}")
                    continue

                total_rows += 1

                if len(sys_batch) >= BATCH_SIZE:
                    flush_sys()
                if len(fac_batch) >= BATCH_SIZE:
                    flush_factions()
                    flush_system_factions()  # must come after factions are in DB
                if len(sf_batch) >= BATCH_SIZE:
                    flush_factions()         # ensure faction rows exist first
                    flush_system_factions()

                if time.time() - last_save > 60:
                    flush_sys()
                    flush_factions()
                    flush_system_factions()
                    try:
                        save_checkpoint(conn, dump_path.name, f.tell(), total_rows)
                    except Exception:
                        pass
                    last_save = time.time()
                    pbar.update(f.tell() - pbar.n - resume_offset)

        except KeyboardInterrupt:
            log.info("Interrupted — saving checkpoint ...")
            flush_sys()
            flush_factions()
            flush_system_factions()
            save_checkpoint(conn, dump_path.name, f.tell(), total_rows)
            sys.exit(0)

        flush_sys()
        flush_factions()
        flush_system_factions()
        pbar.close()

    mark_complete(conn, dump_path.name, total_rows)
    log.info(f"galaxy_populated.json.gz complete: {total_rows:,} systems enriched")
    return total_rows


# ---------------------------------------------------------------------------
# IMPORTER 3 — galaxy_stations.json.gz  (station refresh)
# ---------------------------------------------------------------------------
def import_stations(conn, dump_path: Path, resume_offset: int = 0) -> int:
    """
    Re-import all stations with latest market/service/economy state.
    galaxy_stations.json.gz is a flat list of station objects (not nested).
    """
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
    last_save  = time.time()

    def flush():
        if sta_batch:
            upsert_via_temp(conn, 'stations', STA_COLS, sta_batch, 'id')
            sta_batch.clear()

    with gzip.open(dump_path, 'rb') as f:
        if resume_offset > 0:
            f.seek(resume_offset)

        pbar = tqdm(
            total=file_size, initial=resume_offset,
            unit='B', unit_scale=True, unit_divisor=1024,
            desc=dump_path.name,
        )

        _skip_count = 0
        try:
            for s in ijson.items(f, 'item'):
                sid      = s.get('id') or s.get('marketId') or s.get('market_id')
                sys_id64 = s.get('systemId64') or s.get('system_id64')
                if not sid or not sys_id64:
                    continue

                now_iso  = datetime.now(timezone.utc).isoformat()
                try:
                    # Spansh schema uses 'services' array (values: "Market", "Shipyard", etc.)
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
                    _skip_count += 1
                    log.debug(f"Skipping station id={sid} in system {sys_id64}: {_e}")
                    continue

                total_rows += 1

                if len(sta_batch) >= BATCH_SIZE:
                    flush()

                if time.time() - last_save > 60:
                    flush()
                    try:
                        save_checkpoint(conn, dump_path.name, f.tell(), total_rows)
                    except Exception:
                        pass
                    last_save = time.time()
                    pbar.update(f.tell() - pbar.n - resume_offset)

        except KeyboardInterrupt:
            log.info("Interrupted — saving checkpoint ...")
            flush()
            save_checkpoint(conn, dump_path.name, f.tell(), total_rows)
            sys.exit(0)

        flush()
        pbar.close()

    if _skip_count:
        log.warning(f"Skipped {_skip_count:,} malformed station records")
    mark_complete(conn, dump_path.name, total_rows)
    log.info(f"galaxy_stations.json.gz complete: {total_rows:,} stations imported")
    return total_rows


# ---------------------------------------------------------------------------
# IMPORTER 4 — systems delta files (1day / 1week / 1month)
# ---------------------------------------------------------------------------
def import_systems_delta(conn, dump_path: Path, resume_offset: int = 0) -> int:
    """
    Import a Spansh systems delta file (flat list of system objects).
    Used for nightly updates — much smaller than galaxy.json.gz.
    """
    log.info(f"Importing systems delta from {dump_path.name} ...")
    set_import_optimisations(conn)

    file_size = dump_path.stat().st_size
    mark_running(conn, dump_path.name, file_size)

    SYS_COLS = [
        'id64', 'name', 'x', 'y', 'z',
        'primary_economy', 'secondary_economy',
        'population', 'security', 'allegiance', 'government',
        'controlling_faction', 'updated_at',
        'rating_dirty', 'cluster_dirty',
    ]

    sys_batch  = []
    total_rows = 0
    last_save  = time.time()

    def flush():
        if sys_batch:
            upsert_via_temp(conn, 'systems', SYS_COLS, sys_batch, 'id64',
                            update_cols=[c for c in SYS_COLS if c != 'id64'])
            sys_batch.clear()

    with gzip.open(dump_path, 'rb') as f:
        if resume_offset > 0:
            f.seek(resume_offset)

        pbar = tqdm(
            total=file_size, initial=resume_offset,
            unit='B', unit_scale=True, unit_divisor=1024,
            desc=dump_path.name,
        )

        try:
            for sys_obj in ijson.items(f, 'item'):
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
                        save_checkpoint(conn, dump_path.name, f.tell(), total_rows)
                    except Exception:
                        pass
                    last_save = time.time()
                    pbar.update(f.tell() - pbar.n - resume_offset)

        except KeyboardInterrupt:
            flush()
            save_checkpoint(conn, dump_path.name, f.tell(), total_rows)
            sys.exit(0)

        flush()
        pbar.close()

    mark_complete(conn, dump_path.name, total_rows)
    log.info(f"{dump_path.name} complete: {total_rows:,} systems updated")
    return total_rows


# ---------------------------------------------------------------------------
# Download helpers (aria2c → wget → curl → urllib fallback chain)
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
    """
    Download Spansh dump files using the fastest available method.
    Priority: aria2c (16-conn parallel) → wget → curl → urllib.

    On Hetzner 1 Gbps: aria2c downloads 110 GB in ~15 minutes.
    urllib (single-stream) would take ~25 minutes but is the fallback.

    ALWAYS download before importing — streaming directly into PostgreSQL
    is bottlenecked by insert speed (~250 kB/s), not network speed.
    """
    import urllib.request
    DUMP_DIR.mkdir(parents=True, exist_ok=True)

    for fname in files:
        dest = DUMP_DIR / fname
        if dest.exists():
            log.info(f"Already exists: {fname} ({dest.stat().st_size / 1e9:.1f} GB) — skipping")
            continue

        url = f"{SPANSH_BASE}/{fname}"
        log.info(f"Downloading {url}")
        log.info(f"  → {dest}")
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
                   bytes_total,
                   CASE WHEN bytes_total > 0
                       THEN round(bytes_processed::numeric / bytes_total * 100, 1)
                       ELSE 0 END AS pct,
                   started_at, completed_at, error_message
            FROM import_meta ORDER BY id
        """)
        rows = cur.fetchall()

    print(f"\n{'File':<35} {'Status':<10} {'Rows':>12} {'Progress':>10} {'Started':<22}")
    print("-" * 95)
    for r in rows:
        fname, status, rows_proc, bytes_proc, bytes_total, pct, started, completed, err = r
        started_str = started.strftime('%Y-%m-%d %H:%M') if started else 'not started'
        pct_str = f"{pct}%" if pct else "0%"
        print(f"{fname:<35} {str(status):<10} {(rows_proc or 0):>12,} {pct_str:>10} {started_str:<22}")
        if err:
            print(f"  ERROR: {err[:80]}")
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
# Probe helper — print actual JSON keys from the first few records
# Usage: python3 import_spansh.py --probe galaxy.json.gz
# ---------------------------------------------------------------------------
def _probe_dump(fname: str, n_systems: int = 2):
    """
    Dry-run validator: scan up to 50,000 systems, collecting stats on what
    the importer would actually write to the DB.  No DB connection needed.
    Reports:
      - Counts of ELW / WW / ammonia / terraformable / landable / bio / geo
      - Sample of interesting bodies with their extracted values
      - Station service detection sample
    """
    dump_path = DUMP_DIR / fname
    if not dump_path.exists():
        print(f"ERROR: {dump_path} not found. Set DUMP_DIR or use --dump-dir.")
        return

    MAX_SCAN = 50_000
    print(f"\n=== Dry-run validation of {fname} (scanning up to {MAX_SCAN:,} systems) ===\n")

    # Counters
    stats = {
        'systems': 0, 'bodies': 0, 'stars': 0, 'planets': 0, 'stations': 0,
        'main_star_found': 0, 'main_star_missed': 0,
        'landable': 0, 'elw': 0, 'ww': 0, 'ammonia': 0,
        'terraformable': 0, 'bio': 0, 'geo': 0,
        'has_market': 0, 'has_shipyard': 0, 'has_outfitting': 0,
        'sta_via_services': 0, 'sta_via_object': 0, 'sta_via_bool': 0,
    }

    # Samples of interesting finds to print
    samples = {
        'elw': [], 'ww': [], 'ammonia': [], 'terraformable': [],
        'station': [], 'bio': [],
    }
    MAX_SAMPLES = 3

    all_body_keys: set = set()
    all_sta_keys: set  = set()
    all_subtypes: dict = {}  # subType → count

    with gzip.open(dump_path, 'rb') as f:
        for sys_obj in ijson.items(f, 'item'):
            if stats['systems'] >= MAX_SCAN:
                break
            stats['systems'] += 1
            now_iso = datetime.now(timezone.utc).isoformat()

            bodies_raw   = sys_obj.get('bodies') or []
            stations_raw = sys_obj.get('stations') or []

            # ── Main star detection ──────────────────────────────────────
            found_main = False
            for b in bodies_raw:
                if b.get('mainStar') or b.get('isMainStar') or b.get('is_main_star'):
                    found_main = True
                    break
            if found_main:
                stats['main_star_found'] += 1
            elif bodies_raw:
                stats['main_star_missed'] += 1

            # ── Bodies ──────────────────────────────────────────────────
            for b in bodies_raw:
                stats['bodies'] += 1
                all_body_keys.update(b.keys())
                btype = b.get('type', 'Unknown')
                if btype == 'Star':
                    stats['stars'] += 1
                elif btype == 'Planet':
                    stats['planets'] += 1

                sub_type = b.get('subType') or b.get('subtype') or ''
                all_subtypes[sub_type] = all_subtypes.get(sub_type, 0) + 1

                # Derived flags — exactly as the importer does
                is_elw   = (sub_type == 'Earth-like world')
                is_ww    = (sub_type == 'Water world')
                is_amm   = (sub_type == 'Ammonia world')
                tf_state = b.get('terraformingState') or b.get('terraforming_state') or ''
                is_tf    = (tf_state == 'Terraformable') or bool(b.get('isTerraformingCandidate'))
                is_land  = bool(b.get('isLandable') or b.get('is_landable', False))
                bio      = _parse_bio_signals(b)
                geo      = _parse_geo_signals(b)

                if is_land:  stats['landable']      += 1
                if is_elw:   stats['elw']            += 1
                if is_ww:    stats['ww']             += 1
                if is_amm:   stats['ammonia']        += 1
                if is_tf:    stats['terraformable']  += 1
                if bio > 0:  stats['bio']            += 1
                if geo > 0:  stats['geo']            += 1

                sname = sys_obj.get('name', '?')
                if is_elw and len(samples['elw']) < MAX_SAMPLES:
                    samples['elw'].append(f"  ELW: {b.get('name')} in {sname} | subType={sub_type!r} | landable={is_land} | scan={b.get('estimatedScanValue')}")
                if is_ww and len(samples['ww']) < MAX_SAMPLES:
                    samples['ww'].append(f"  WW:  {b.get('name')} in {sname} | subType={sub_type!r} | landable={is_land}")
                if is_amm and len(samples['ammonia']) < MAX_SAMPLES:
                    samples['ammonia'].append(f"  AMM: {b.get('name')} in {sname} | subType={sub_type!r}")
                if is_tf and len(samples['terraformable']) < MAX_SAMPLES:
                    samples['terraformable'].append(f"  TF:  {b.get('name')} in {sname} | subType={sub_type!r} | terraformingState={tf_state!r}")
                if bio > 0 and len(samples['bio']) < MAX_SAMPLES:
                    samples['bio'].append(f"  BIO: {b.get('name')} in {sname} | bio={bio} | geo={geo}")

            # ── Stations ────────────────────────────────────────────────
            for s in stations_raw:
                stats['stations'] += 1
                all_sta_keys.update(s.keys())

                svcs = (s.get('services') or s.get('otherServices') or s.get('other_services') or [])
                svcs_lower = {str(x).lower() for x in svcs}

                has_mkt  = (s.get('market') is not None or 'market' in svcs_lower or bool(s.get('hasMarket')))
                has_shy  = (s.get('shipyard') is not None or 'shipyard' in svcs_lower or bool(s.get('hasShipyard')))
                has_out  = (s.get('outfitting') is not None or 'outfitting' in svcs_lower or bool(s.get('hasOutfitting')))

                if has_mkt: stats['has_market']    += 1
                if has_shy: stats['has_shipyard']  += 1
                if has_out: stats['has_outfitting'] += 1

                # Track how detection happened
                if svcs:            stats['sta_via_services'] += 1
                elif s.get('market') is not None: stats['sta_via_object'] += 1
                elif s.get('hasMarket'): stats['sta_via_bool'] += 1

                if len(samples['station']) < MAX_SAMPLES:
                    samples['station'].append(
                        f"  STA: {s.get('name')!r} | services={svcs[:4]} | "
                        f"market={has_mkt} shipyard={has_shy} outfitting={has_out}"
                    )

    # ── Print results ────────────────────────────────────────────────────
    print(f"Scanned {stats['systems']:,} systems | {stats['bodies']:,} bodies | {stats['stations']:,} stations\n")

    print("── Body flag extraction results ──")
    print(f"  Main star found:    {stats['main_star_found']:>8,}  (missed: {stats['main_star_missed']:,})")
    print(f"  Stars:              {stats['stars']:>8,}")
    print(f"  Planets:            {stats['planets']:>8,}")
    print(f"  Landable:           {stats['landable']:>8,}")
    print(f"  Earth-like world:   {stats['elw']:>8,}")
    print(f"  Water world:        {stats['ww']:>8,}")
    print(f"  Ammonia world:      {stats['ammonia']:>8,}")
    print(f"  Terraformable:      {stats['terraformable']:>8,}")
    print(f"  Bio signals:        {stats['bio']:>8,}")
    print(f"  Geo signals:        {stats['geo']:>8,}")

    print(f"\n── Station service detection ──")
    print(f"  Total stations:     {stats['stations']:>8,}")
    print(f"  Has market:         {stats['has_market']:>8,}")
    print(f"  Has shipyard:       {stats['has_shipyard']:>8,}")
    print(f"  Has outfitting:     {stats['has_outfitting']:>8,}")
    print(f"  Detected via services array: {stats['sta_via_services']:,}")
    print(f"  Detected via market object:  {stats['sta_via_object']:,}")
    print(f"  Detected via hasMarket bool: {stats['sta_via_bool']:,}")

    print(f"\n── Samples ──")
    for key, label in [('elw','ELW'), ('ww','Water worlds'), ('ammonia','Ammonia worlds'),
                       ('terraformable','Terraformable'), ('bio','Bio signals'), ('station','Stations')]:
        if samples[key]:
            print(f"\n{label}:")
            for s in samples[key]:
                print(s)
        else:
            print(f"\n{label}: none found in {MAX_SCAN:,} systems")

    print(f"\n── Top 20 subTypes seen ──")
    for st, cnt in sorted(all_subtypes.items(), key=lambda x: -x[1])[:20]:
        print(f"  {cnt:>8,}  {st!r}")

    print(f"\n── All body keys seen ──\n{sorted(all_body_keys)}")
    print(f"\n── All station keys seen ──\n{sorted(all_sta_keys)}")


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------
def main():
    global DUMP_DIR, BATCH_SIZE

    parser = argparse.ArgumentParser(
        description='ED Finder — Spansh dump importer (PostgreSQL COPY edition)'
    )
    parser.add_argument('--all',           action='store_true', help='Import all dumps in order')
    parser.add_argument('--file',          type=str,            help='Import a specific dump file')
    parser.add_argument('--resume',        action='store_true', help='Resume from last checkpoint')
    parser.add_argument('--download',      action='store_true', help='Download dumps before importing')
    parser.add_argument('--download-only', action='store_true', help='Download dumps then exit (recommended first step)')
    parser.add_argument('--status',        action='store_true', help='Show import status')
    parser.add_argument('--probe',         type=str,            help='Print field keys from first 3 systems in dump file (for debugging)')
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

    if args.probe:
        _probe_dump(args.probe)
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

    # Pre-load import_meta status so we can skip completed files
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

        # Skip files that are already complete (unless --resume is explicitly set)
        current_status = _get_status(fname)
        if current_status == 'complete' and not args.resume:
            log.info(f"⏭  {fname}: already complete — skipping (use --resume to re-run)")
            continue

        resume_offset = get_checkpoint(conn, fname) if args.resume else 0
        if resume_offset > 0:
            log.info(f"Resuming {fname} from byte {resume_offset:,}")

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
    log.info("Next steps:")
    log.info("  python3 build_ratings.py   — compute scores for all systems")
    log.info("  python3 build_grid.py      — build spatial grid")
    log.info("  python3 build_clusters.py  — build cluster summary (long)")


if __name__ == '__main__':
    main()
