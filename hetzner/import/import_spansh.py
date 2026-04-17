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
    if not v:
        return None
    try:
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(v, tz=timezone.utc).isoformat()
        return str(v)
    except Exception:
        return None


def parse_bool(v) -> Optional[bool]:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    return str(v).lower() in ('true', '1', 'yes')


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
        if body_batch:
            upsert_via_temp(conn, 'bodies', BODY_COLS, body_batch, 'id')
            body_batch.clear()

    def flush_stations():
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

        try:
            for sys_obj in ijson.items(f, 'item'):
                id64 = sys_obj.get('id64')
                if not id64:
                    continue

                now_iso = datetime.now(timezone.utc).isoformat()

                # --- Determine main star from nested bodies ---
                bodies_raw = sys_obj.get('bodies', []) or []
                main_star_type     = None
                main_star_subtype  = None
                main_star_scoopable = None
                has_body_data = len(bodies_raw) > 0

                for b in bodies_raw:
                    if b.get('isMainStar') or b.get('is_main_star'):
                        sc = b.get('spectralClass') or b.get('spectral_class') or ''
                        main_star_type    = sc[:1] if sc else None
                        main_star_subtype = sc[1:] if len(sc) > 1 else None
                        main_star_scoopable = main_star_type in SCOOPABLE_STARS if main_star_type else None
                        break

                # --- Systems row ---
                controlling = None
                factions_raw = sys_obj.get('factions', []) or []
                for fac in factions_raw:
                    if fac.get('isControlling') or fac.get('is_controlling'):
                        controlling = fac.get('name')
                        break
                if not controlling:
                    controlling = sys_obj.get('controllingFaction') or sys_obj.get('controlling_faction')

                sys_batch.append((
                    id64,
                    sys_obj.get('name', ''),
                    float(sys_obj.get('coords', {}).get('x', 0) if isinstance(sys_obj.get('coords'), dict) else sys_obj.get('x', 0)),
                    float(sys_obj.get('coords', {}).get('y', 0) if isinstance(sys_obj.get('coords'), dict) else sys_obj.get('y', 0)),
                    float(sys_obj.get('coords', {}).get('z', 0) if isinstance(sys_obj.get('coords'), dict) else sys_obj.get('z', 0)),
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

                # --- Bodies rows ---
                for b in bodies_raw:
                    bid = b.get('id64') or b.get('id') or b.get('bodyId')
                    if not bid:
                        continue
                    btype_raw = b.get('type', 'Unknown')
                    btype = 'Star' if btype_raw == 'Star' else \
                            'Planet' if btype_raw == 'Planet' else \
                            'Unknown'
                    sc = b.get('spectralClass') or b.get('spectral_class') or ''
                    atm_comp = b.get('atmosphereComposition') or b.get('atmosphere_composition')
                    mats     = b.get('materials')
                    body_batch.append((
                        bid, id64,
                        b.get('name', ''),
                        btype,
                        b.get('subType') or b.get('subtype'),
                        bool(b.get('isMainStar') or b.get('is_main_star', False)),
                        b.get('distanceToArrival') or b.get('distance_from_star'),
                        b.get('orbitalPeriod') or b.get('orbital_period'),
                        b.get('radius'),
                        b.get('solarMasses') or b.get('mass') or b.get('earthMasses'),
                        b.get('gravity'),
                        b.get('surfaceTemperature') or b.get('surface_temp'),
                        b.get('surfacePressure') or b.get('surface_pressure'),
                        b.get('atmosphereType') or b.get('atmosphere_type'),
                        _json_dumps(atm_comp),
                        b.get('volcanismType') or b.get('volcanism'),
                        _json_dumps(mats),
                        b.get('terraformingState') or b.get('terraforming_state'),
                        bool(b.get('isTerraformingCandidate') or b.get('is_terraformable', False)),
                        bool(b.get('isLandable') or b.get('is_landable', False)),
                        bool(b.get('isWaterWorld') or b.get('is_water_world', False)),
                        bool(b.get('isEarthLike') or b.get('is_earth_like', False)),
                        bool(b.get('isAmmoniaWorld') or b.get('is_ammonia_world', False)),
                        int(b.get('signals', {}).get('genuses', 0) if isinstance(b.get('signals'), dict) else b.get('bio_signal_count', 0)),
                        int(b.get('signals', {}).get('geology', 0) if isinstance(b.get('signals'), dict) else b.get('geo_signal_count', 0)),
                        sc[:4] if sc else None,
                        b.get('luminosity'),
                        b.get('solarMasses') or b.get('stellar_mass'),
                        (sc[:1] in SCOOPABLE_STARS) if sc else None,
                        b.get('estimatedMappingValue') or b.get('estimated_mapping_value'),
                        b.get('estimatedScanValue') or b.get('estimated_scan_value'),
                        parse_ts(b.get('updateTime') or b.get('updated_at')),
                        now_iso,
                    ))

                # --- Stations rows ---
                stations_raw = sys_obj.get('stations', []) or []
                for s in stations_raw:
                    sid = s.get('id') or s.get('marketId') or s.get('market_id')
                    if not sid:
                        continue
                    svcs = s.get('otherServices') or s.get('other_services') or []
                    svcs_lower = [str(x).lower() for x in svcs]
                    sta_batch.append((
                        sid, id64,
                        s.get('name', ''),
                        norm_station_type(s.get('type') or s.get('station_type')),
                        s.get('distanceToArrival') or s.get('distance_from_star'),
                        s.get('body') or s.get('body_name'),
                        s.get('landingPads', {}).get('large') and 'L' or
                        s.get('landingPads', {}).get('medium') and 'M' or
                        s.get('landing_pad_size'),
                        bool(s.get('hasMarket') or s.get('has_market', False)),
                        bool(s.get('hasShipyard') or s.get('has_shipyard', False)),
                        bool(s.get('hasOutfitting') or s.get('has_outfitting', False)),
                        'refuel' in svcs_lower or bool(s.get('has_refuel', False)),
                        'repair' in svcs_lower or bool(s.get('has_repair', False)),
                        'rearm' in svcs_lower or bool(s.get('has_rearm', False)),
                        'black market' in svcs_lower or bool(s.get('has_black_market', False)),
                        'material trader' in svcs_lower or bool(s.get('has_material_trader', False)),
                        'technology broker' in svcs_lower or bool(s.get('has_technology_broker', False)),
                        'interstellar factors' in svcs_lower or bool(s.get('has_interstellar_factors', False)),
                        'universal cartographics' in svcs_lower or bool(s.get('has_universal_cartographics', False)),
                        'search and rescue' in svcs_lower or bool(s.get('has_search_rescue', False)),
                        norm_economy(s.get('primaryEconomy') or s.get('primary_economy')),
                        norm_economy(s.get('secondaryEconomy') or s.get('secondary_economy')),
                        s.get('controllingFaction') or s.get('controlling_faction'),
                        norm_allegiance(s.get('allegiance')),
                        norm_government(s.get('government')),
                        parse_ts(s.get('updateTime') or s.get('updated_at')) or now_iso,
                    ))

                total_rows += 1

                # Flush when batches are full
                if len(sys_batch) >= BATCH_SIZE:
                    flush_systems()
                if len(body_batch) >= BATCH_SIZE:
                    flush_bodies()
                if len(sta_batch) >= BATCH_SIZE:
                    flush_stations()

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
            log.info(f"Checkpoint saved at {f.tell():,} bytes, {total_rows:,} systems")
            sys.exit(0)

        # Final flush
        flush_systems()
        flush_bodies()
        flush_stations()
        pbar.close()

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
    total_rows = 0
    last_save  = time.time()

    # Pre-load faction name → id map to avoid per-row lookups
    fac_cache: dict = {}

    def flush_sys():
        if not sys_batch:
            return
        upsert_via_temp(conn, 'systems', SYS_ENRICH_COLS, sys_batch, 'id64',
                        update_cols=[c for c in SYS_ENRICH_COLS if c != 'id64'])
        sys_batch.clear()

    def flush_factions():
        if not fac_batch:
            return
        # Upsert factions
        psycopg2.extras.execute_values(
            conn.cursor(),
            """
            INSERT INTO factions (name, allegiance, government)
            VALUES %s
            ON CONFLICT (name) DO UPDATE
            SET allegiance = EXCLUDED.allegiance,
                government = EXCLUDED.government,
                updated_at = NOW()
            """,
            fac_batch
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
                    if fac.get('isControlling'):
                        controlling = fname

                if not controlling:
                    controlling = sys_obj.get('controllingFaction')

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

                total_rows += 1

                if len(sys_batch) >= BATCH_SIZE:
                    flush_sys()
                if len(fac_batch) >= BATCH_SIZE:
                    flush_factions()

                if time.time() - last_save > 60:
                    flush_sys()
                    flush_factions()
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
            save_checkpoint(conn, dump_path.name, f.tell(), total_rows)
            sys.exit(0)

        flush_sys()
        flush_factions()
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

        try:
            for s in ijson.items(f, 'item'):
                sid      = s.get('id') or s.get('marketId') or s.get('market_id')
                sys_id64 = s.get('systemId64') or s.get('system_id64')
                if not sid or not sys_id64:
                    continue

                now_iso  = datetime.now(timezone.utc).isoformat()
                svcs     = s.get('otherServices') or s.get('other_services') or []
                svcs_lower = [str(x).lower() for x in svcs]

                sta_batch.append((
                    sid, sys_id64,
                    s.get('name', ''),
                    norm_station_type(s.get('type') or s.get('stationType') or s.get('station_type')),
                    s.get('distanceToArrival') or s.get('distance_from_star'),
                    s.get('body') or s.get('body_name'),
                    s.get('landingPads', {}).get('large') and 'L' or
                    s.get('landingPads', {}).get('medium') and 'M' or
                    s.get('landing_pad_size'),
                    bool(s.get('hasMarket') or s.get('has_market', False)),
                    bool(s.get('hasShipyard') or s.get('has_shipyard', False)),
                    bool(s.get('hasOutfitting') or s.get('has_outfitting', False)),
                    'refuel' in svcs_lower,
                    'repair' in svcs_lower,
                    'rearm' in svcs_lower,
                    'black market' in svcs_lower,
                    'material trader' in svcs_lower,
                    'technology broker' in svcs_lower,
                    'interstellar factors' in svcs_lower,
                    'universal cartographics' in svcs_lower,
                    'search and rescue' in svcs_lower,
                    norm_economy(s.get('primaryEconomy') or s.get('primary_economy')),
                    norm_economy(s.get('secondaryEconomy') or s.get('secondary_economy')),
                    s.get('controllingFaction') or s.get('controlling_faction'),
                    norm_allegiance(s.get('allegiance')),
                    norm_government(s.get('government')),
                    parse_ts(s.get('updateTime') or s.get('updated_at')) or now_iso,
                ))

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
