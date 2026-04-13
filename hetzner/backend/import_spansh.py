#!/usr/bin/env python3
"""
ED Finder — Spansh Dump Importer
Version: 1.0

Streams all 5 Spansh dump files into PostgreSQL.
Features:
  • Fully resumable — tracks byte offset, restarts mid-file after crash
  • Streaming JSON parser (ijson) — never loads the full file into RAM
  • Batch inserts (configurable batch size, default 5000 rows)
  • Progress reporting every N rows
  • Handles 3 active Spansh dumps (bodies.json.gz and attractions.json.gz were
    removed by Spansh — galaxy.json.gz now contains everything)
  • Downloads dumps from Spansh if not already present

Usage:
    python3 import_spansh.py --all                    # import all dumps
    python3 import_spansh.py --file galaxy.json.gz    # import one file
    python3 import_spansh.py --all --resume           # resume from checkpoint
    python3 import_spansh.py --status                 # show import progress
    python3 import_spansh.py --download               # download all dumps first

Requirements:
    pip install ijson psycopg2-binary aiohttp tqdm

Spansh dump URLs (current as of 2025):
    https://downloads.spansh.co.uk/galaxy.json.gz          (~102 GB, systems+bodies+stations)
    https://downloads.spansh.co.uk/galaxy_populated.json.gz (~3.6 GB, populated systems)
    https://downloads.spansh.co.uk/galaxy_stations.json.gz  (~3.6 GB, enriches stations)

NOTE: bodies.json.gz and attractions.json.gz no longer exist on Spansh.
      galaxy.json.gz is now the single source for all body/station data.
"""

import os
import sys
import gzip
import json
import time
import logging
import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Iterator, Any

import ijson
import psycopg2
import psycopg2.extras
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_DSN      = os.getenv('DATABASE_URL', 'postgresql://edfinder:edfinder@localhost:5432/edfinder')
DUMP_DIR    = Path(os.getenv('DUMP_DIR', '/data/dumps'))
BATCH_SIZE  = int(os.getenv('BATCH_SIZE', '5000'))
LOG_LEVEL   = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE    = os.getenv('LOG_FILE', '/data/logs/import.log')

SPANSH_BASE = 'https://downloads.spansh.co.uk'
# NOTE: bodies.json.gz and attractions.json.gz no longer exist on Spansh.
# galaxy.json.gz now contains systems + bodies + stations all nested.
DUMP_FILES  = [
    'galaxy.json.gz',
    'galaxy_populated.json.gz',
    'galaxy_stations.json.gz',
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger('import_spansh')

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_conn():
    conn = psycopg2.connect(DB_DSN)
    conn.autocommit = False
    return conn

def get_checkpoint(conn, dump_file: str) -> int:
    """Return last saved byte offset for this dump file."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT last_checkpoint FROM import_meta WHERE dump_file = %s",
            (dump_file,)
        )
        row = cur.fetchone()
        return row[0] if row else 0

def save_checkpoint(conn, dump_file: str, offset: int, rows: int):
    """Save progress checkpoint."""
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
        conn.rollback()  # clear any aborted transaction first
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
# Economy / enum normalisation
# ---------------------------------------------------------------------------
ECONOMY_MAP = {
    'agriculture':    'Agriculture',
    'refinery':       'Refinery',
    'industrial':     'Industrial',
    'hightech':       'HighTech',
    'high tech':      'HighTech',
    'military':       'Military',
    'tourism':        'Tourism',
    'extraction':     'Extraction',
    'colony':         'Colony',
    'terraforming':   'Terraforming',
    'prison':         'Prison',
    'damaged':        'Damaged',
    'rescue':         'Rescue',
    'repair':         'Repair',
    'carrier':        'Carrier',
    '$economy_none;': 'None',
    'none':           'None',
    '':               'Unknown',
    None:             'Unknown',
}

SECURITY_MAP = {
    'high':     'High',
    'medium':   'Medium',
    'low':      'Low',
    'anarchy':  'Anarchy',
    'lawless':  'Lawless',
    '$gdpgen_security_state_secure;':  'High',
    '$gdpgen_security_state_medium;':  'Medium',
    '$gdpgen_security_state_low;':     'Low',
    '$gdpgen_security_state_anarchy;': 'Anarchy',
    None: 'Unknown',
}

ALLEGIANCE_MAP = {
    'federation':       'Federation',
    'empire':           'Empire',
    'alliance':         'Alliance',
    'independent':      'Independent',
    'thargoid':         'Thargoid',
    'guardian':         'Guardian',
    'pilotsfederation': 'PilotsFederation',
    'none':             'None',
    None:               'Unknown',
}

GOVERNMENT_MAP = {
    'democracy':    'Democracy',
    'dictatorship': 'Dictatorship',
    'feudal':       'Feudal',
    'patronage':    'Patronage',
    'corporate':    'Corporate',
    'cooperative':  'Cooperative',
    'theocracy':    'Theocracy',
    'anarchy':      'Anarchy',
    'communism':    'Communism',
    'confederacy':  'Confederacy',
    'none':         'None',
    None:           'Unknown',
}

def norm_economy(v):
    return ECONOMY_MAP.get(str(v).lower() if v else None, 'Unknown')

def norm_security(v):
    return SECURITY_MAP.get(str(v).lower() if v else None, 'Unknown')

def norm_allegiance(v):
    return ALLEGIANCE_MAP.get(str(v).lower() if v else None, 'Unknown')

def norm_government(v):
    return GOVERNMENT_MAP.get(str(v).lower() if v else None, 'Unknown')

def safe_float(v) -> Optional[float]:
    """Convert any numeric type (including ijson Decimal) to Python float."""
    try: return float(v) if v is not None else None
    except: return None

def safe_int(v) -> Optional[int]:
    """Convert any numeric type (including ijson Decimal) to Python int."""
    try: return int(v) if v is not None else None
    except: return None

def norm_faction(v) -> Optional[str]:
    """Extract faction name whether v is a dict {'name':...} or a plain string."""
    if v is None:
        return None
    if isinstance(v, dict):
        return v.get('name') or None
    return str(v) or None

def safe_bool(v) -> Optional[bool]:
    if v is None: return None
    if isinstance(v, bool): return v
    return str(v).lower() in ('true', '1', 'yes')

def parse_ts(v) -> Optional[str]:
    if not v: return None
    try:
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(v, tz=timezone.utc).isoformat()
        return str(v)
    except: return None

# ---------------------------------------------------------------------------
# IMPORTER 1: galaxy.json.gz  →  systems + bodies + stations (all-in-one)
# ---------------------------------------------------------------------------
def import_galaxy(conn, dump_path: Path, resume_offset: int = 0) -> int:
    """
    Parse galaxy.json.gz and upsert into systems, bodies, and stations tables.

    As of 2025, Spansh's galaxy.json.gz is the ONLY dump containing body and
    station data (bodies.json.gz and attractions.json.gz have been removed).
    Each system object contains nested 'bodies' and 'stations' arrays.

    Format: array of system objects at top level.
    """
    log.info(f"Importing systems from {dump_path.name} ...")
    total_rows = 0
    batch = []

    SCOOPABLE_STARS = {'O', 'B', 'A', 'F', 'G', 'K', 'M'}

    SYS_INSERT = """
        INSERT INTO systems (
            id64, name, x, y, z,
            primary_economy, secondary_economy,
            population, is_colonised, is_being_colonised,
            controlling_faction,
            security, allegiance, government,
            main_star_type, main_star_subtype, main_star_is_scoopable,
            has_body_data, body_count, data_quality,
            first_discovered_at, updated_at,
            rating_dirty, cluster_dirty
        ) VALUES %s
        ON CONFLICT (id64) DO UPDATE SET
            name                    = EXCLUDED.name,
            x                       = EXCLUDED.x,
            y                       = EXCLUDED.y,
            z                       = EXCLUDED.z,
            primary_economy         = EXCLUDED.primary_economy,
            secondary_economy       = EXCLUDED.secondary_economy,
            population              = EXCLUDED.population,
            is_colonised            = EXCLUDED.is_colonised,
            is_being_colonised      = EXCLUDED.is_being_colonised,
            controlling_faction     = EXCLUDED.controlling_faction,
            security                = EXCLUDED.security,
            allegiance              = EXCLUDED.allegiance,
            government              = EXCLUDED.government,
            main_star_type          = COALESCE(EXCLUDED.main_star_type, systems.main_star_type),
            main_star_subtype       = COALESCE(EXCLUDED.main_star_subtype, systems.main_star_subtype),
            main_star_is_scoopable  = COALESCE(EXCLUDED.main_star_is_scoopable, systems.main_star_is_scoopable),
            has_body_data           = EXCLUDED.has_body_data,
            body_count              = EXCLUDED.body_count,
            updated_at              = EXCLUDED.updated_at,
            rating_dirty            = TRUE,
            cluster_dirty           = TRUE
    """

    BODY_INSERT = """
        INSERT INTO bodies (
            id, system_id64, name,
            body_type, subtype, is_main_star,
            distance_from_star, orbital_period,
            semi_major_axis, orbital_eccentricity,
            orbital_inclination, is_tidal_lock,
            radius, mass, gravity,
            surface_temp, surface_pressure,
            atmosphere_type, atmosphere_composition,
            volcanism, solid_composition, materials,
            terraforming_state, is_terraformable,
            is_landable, is_water_world, is_earth_like, is_ammonia_world,
            bio_signal_count, geo_signal_count,
            spectral_class, luminosity, stellar_mass,
            absolute_magnitude, age_my, is_scoopable,
            estimated_mapping_value, estimated_scan_value,
            first_discovered_at, first_mapped_at, updated_at
        ) VALUES %s
        ON CONFLICT (id) DO UPDATE SET
            subtype                 = EXCLUDED.subtype,
            is_terraformable        = EXCLUDED.is_terraformable,
            terraforming_state      = EXCLUDED.terraforming_state,
            bio_signal_count        = EXCLUDED.bio_signal_count,
            geo_signal_count        = EXCLUDED.geo_signal_count,
            estimated_mapping_value = EXCLUDED.estimated_mapping_value,
            estimated_scan_value    = EXCLUDED.estimated_scan_value,
            updated_at              = EXCLUDED.updated_at
    """

    STATION_TYPE_MAP = {
        'coriolis starport':     'Coriolis',
        'orbis starport':        'Orbis',
        'ocellus starport':      'Ocellus',
        'outpost':               'Outpost',
        'planetary port':        'PlanetaryPort',
        'planetary outpost':     'PlanetaryOutpost',
        'mega ship':             'MegaShip',
        'asteroid base':         'AsteroidBase',
        'fleet carrier':         'FleetCarrier',
    }

    STA_INSERT = """
        INSERT INTO stations (
            id, system_id64, name, station_type,
            distance_from_star, body_name,
            landing_pad_size,
            has_market, has_shipyard, has_outfitting,
            has_refuel, has_repair, has_rearm,
            has_black_market, has_material_trader,
            has_technology_broker, has_interstellar_factors,
            has_universal_cartographics,
            primary_economy, secondary_economy,
            controlling_faction, allegiance, government,
            updated_at
        ) VALUES %s
        ON CONFLICT (id) DO UPDATE SET
            station_type        = EXCLUDED.station_type,
            has_market          = EXCLUDED.has_market,
            has_shipyard        = EXCLUDED.has_shipyard,
            has_outfitting      = EXCLUDED.has_outfitting,
            controlling_faction = EXCLUDED.controlling_faction,
            updated_at          = EXCLUDED.updated_at
    """

    def norm_station_type(v):
        if not v: return 'Unknown'
        return STATION_TYPE_MAP.get(str(v).lower(), 'Unknown')

    def make_body_row(body, sys_id64):
        body_id   = safe_int(body.get('id') or body.get('bodyId'))
        if body_id is None:
            return None
        subtype   = body.get('subType') or body.get('subtype') or body.get('type', '')
        btype_raw = body.get('type', 'Unknown')
        is_star   = 'star' in str(btype_raw).lower()
        is_main   = bool(body.get('isMainStar') or body.get('is_main_star'))
        signals   = body.get('signals') or {}
        bio_sig   = safe_int(signals.get('genuses') or body.get('bio_signal_count', 0)) or 0
        geo_sig   = safe_int(signals.get('geology') or body.get('geo_signal_count', 0)) or 0
        if is_star:
            btype_enum = 'Star'
        elif 'moon' in str(btype_raw).lower():
            btype_enum = 'Moon'
        else:
            btype_enum = 'Planet'
        scoopable = None
        spectral  = body.get('spectralClass') or body.get('spectral_class', '')
        if is_star:
            scoopable = bool(spectral and spectral[0].upper() in SCOOPABLE_STARS)
        return (
            body_id,
            sys_id64,
            str(body.get('name', 'Unknown')),
            btype_enum,
            subtype,
            is_main,
            safe_float(body.get('distanceToArrival') or body.get('distance_from_star')),
            safe_float(body.get('orbitalPeriod') or body.get('orbital_period')),
            safe_float(body.get('semiMajorAxis') or body.get('semi_major_axis')),
            safe_float(body.get('orbitalEccentricity') or body.get('orbital_eccentricity')),
            safe_float(body.get('orbitalInclination') or body.get('orbital_inclination')),
            safe_bool(body.get('isTidallyLocked') or body.get('is_tidal_lock')),
            safe_float(body.get('radius')),
            safe_float(body.get('earthMasses') or body.get('solarMasses') or body.get('mass')),
            safe_float(body.get('gravity')),
            safe_float(body.get('surfaceTemperature') or body.get('surface_temp')),
            safe_float(body.get('surfacePressure') or body.get('surface_pressure')),
            body.get('atmosphereType') or body.get('atmosphere_type'),
            json.dumps(body.get('atmosphereComposition') or body.get('atmosphere_composition')) if (body.get('atmosphereComposition') or body.get('atmosphere_composition')) else None,
            body.get('volcanismType') or body.get('volcanism'),
            json.dumps(body.get('solidComposition') or body.get('solid_composition')) if (body.get('solidComposition') or body.get('solid_composition')) else None,
            json.dumps(body.get('materials')) if body.get('materials') else None,
            body.get('terraformingState') or body.get('terraforming_state'),
            bool((body.get('terraformingState', '') or '') not in ('', 'Not terraformable')),
            bool(body.get('isLandable') or body.get('is_landable', False)),
            bool('water world' in str(subtype).lower()),
            bool('earth-like' in str(subtype).lower() or 'earthlike' in str(subtype).lower()),
            bool('ammonia' in str(subtype).lower()),
            bio_sig,
            geo_sig,
            spectral,
            body.get('luminosity'),
            safe_float(body.get('solarMasses') or body.get('stellar_mass')),
            safe_float(body.get('absoluteMagnitude') or body.get('absolute_magnitude')),
            safe_int(body.get('ageMyrs') or body.get('age_my')),
            scoopable,
            safe_int(body.get('estimatedMappingValue') or body.get('estimated_mapping_value', 500)),
            safe_int(body.get('estimatedScanValue') or body.get('estimated_scan_value', 500)),
            parse_ts(body.get('discovered') or body.get('firstDiscover')),
            parse_ts(body.get('mapped')),
            parse_ts(body.get('updateTime')) or datetime.now(timezone.utc).isoformat(),
        )

    def make_station_row(sta, sys_id64):
        sta_id = safe_int(sta.get('id') or sta.get('marketId'))
        if sta_id is None:
            return None
        services  = set(str(s).lower() for s in (sta.get('services') or []))
        ctrl      = sta.get('controllingFaction') or {}
        ctrl_name = ctrl.get('name') if isinstance(ctrl, dict) else (str(ctrl) if ctrl else None)
        return (
            sta_id, sys_id64,
            str(sta.get('name', 'Unknown')),
            norm_station_type(sta.get('type')),
            safe_float(sta.get('distanceToArrival')),
            sta.get('body', {}).get('name') if isinstance(sta.get('body'), dict) else sta.get('body'),
            'L' if sta.get('landingPads', {}).get('large') else ('M' if sta.get('landingPads', {}).get('medium') else 'S'),
            'market'                  in services,
            'shipyard'                in services,
            'outfitting'              in services,
            'refuel'                  in services,
            'repair'                  in services,
            'rearm'                   in services,
            'black market'            in services,
            'material trader'         in services,
            'technology broker'       in services,
            'interstellar factors'    in services,
            'universal cartographics' in services,
            norm_economy(sta.get('primaryEconomy') or sta.get('economy')),
            norm_economy(sta.get('secondaryEconomy')),
            ctrl_name,
            norm_allegiance(sta.get('allegiance')),
            norm_government(sta.get('government')),
            parse_ts(sta.get('updateTime')) or datetime.now(timezone.utc).isoformat(),
        )

    # Counters
    sys_batch   = []
    body_batch  = []
    sta_batch   = []
    body_rows   = 0
    sta_rows    = 0

    def flush_all():
        nonlocal body_rows, sta_rows
        if not (sys_batch or body_batch or sta_batch):
            return
        # Deduplicate by primary key within each batch to avoid
        # CardinalityViolation when the dump contains duplicate id64 values
        sys_dedup  = list({r[0]: r for r in sys_batch}.values())   # key = id64
        body_dedup = list({r[0]: r for r in body_batch}.values())  # key = body id
        sta_dedup  = list({r[0]: r for r in sta_batch}.values())   # key = station id
        try:
            if sys_dedup:
                psycopg2.extras.execute_values(conn.cursor(), SYS_INSERT, sys_dedup, page_size=BATCH_SIZE)
            if body_dedup:
                psycopg2.extras.execute_values(conn.cursor(), BODY_INSERT, body_dedup, page_size=BATCH_SIZE)
                body_rows += len(body_dedup)
            if sta_dedup:
                psycopg2.extras.execute_values(conn.cursor(), STA_INSERT, sta_dedup, page_size=BATCH_SIZE)
                sta_rows += len(sta_dedup)
            conn.commit()
        except Exception as flush_err:
            conn.rollback()
            log.error(f"flush_all error (batch skipped): {flush_err}")
        sys_batch.clear()
        body_batch.clear()
        sta_batch.clear()

    file_size = dump_path.stat().st_size
    mark_running(conn, dump_path.name, file_size)

    with gzip.open(dump_path, 'rb') as f:
        if resume_offset > 0:
            log.info(f"Resuming from byte offset {resume_offset:,}")
            f.seek(resume_offset)

        parser = ijson.items(f, 'item')
        last_checkpoint = time.time()

        with tqdm(total=file_size, initial=resume_offset, unit='B',
                  unit_scale=True, desc='galaxy.json.gz') as pbar:
            for sys_obj in parser:
                try:
                    sys_id64 = safe_int(sys_obj.get('id64'))
                    if sys_id64 is None:
                        continue

                    bodies_list   = sys_obj.get('bodies') or []
                    stations_list = sys_obj.get('stations') or []

                    # Detect main star from embedded bodies list
                    main_star_type    = sys_obj.get('mainStarType')
                    main_star_sub     = sys_obj.get('mainStarSubtype')
                    main_star_scoop   = None
                    for b in bodies_list:
                        if b.get('isMainStar') or b.get('is_main_star'):
                            sp = b.get('spectralClass') or b.get('spectral_class', '')
                            if sp:
                                main_star_type  = main_star_type or sp
                                main_star_scoop = bool(sp[0].upper() in SCOOPABLE_STARS)
                            break

                    has_bodies = len(bodies_list) > 0

                    sys_batch.append((
                        sys_id64,
                        str(sys_obj.get('name', 'Unknown')),
                        safe_float((sys_obj.get('coords') or {}).get('x', 0)),
                        safe_float((sys_obj.get('coords') or {}).get('y', 0)),
                        safe_float((sys_obj.get('coords') or {}).get('z', 0)),
                        norm_economy(sys_obj.get('primaryEconomy') or sys_obj.get('primary_economy')),
                        norm_economy(sys_obj.get('secondaryEconomy') or sys_obj.get('secondary_economy')),
                        safe_int(sys_obj.get('population', 0)) or 0,
                        bool(sys_obj.get('is_colonised', False)),
                        bool(sys_obj.get('is_being_colonised', False)),
                        norm_faction(sys_obj.get('controllingFaction') or sys_obj.get('controlling_faction')),
                        norm_security(sys_obj.get('security')),
                        norm_allegiance(sys_obj.get('allegiance')),
                        norm_government(sys_obj.get('government')),
                        main_star_type,
                        main_star_sub,
                        main_star_scoop,
                        has_bodies,
                        len(bodies_list),
                        2 if has_bodies else 0,  # data_quality
                        parse_ts(sys_obj.get('date') or sys_obj.get('firstDiscover')),
                        parse_ts(sys_obj.get('date')) or datetime.now(timezone.utc).isoformat(),
                        True,  # rating_dirty
                        True,  # cluster_dirty
                    ))

                    # Bodies nested in this system
                    for b in bodies_list:
                        row = make_body_row(b, sys_id64)
                        if row:
                            body_batch.append(row)

                    # Stations nested in this system
                    for s in stations_list:
                        row = make_station_row(s, sys_id64)
                        if row:
                            sta_batch.append(row)

                except Exception as e:
                    log.warning(f"Skipping malformed system record: {e}")
                    continue

                if len(sys_batch) >= BATCH_SIZE:
                    flush_all()
                    total_rows += BATCH_SIZE
                    pbar.update(BATCH_SIZE * 120)  # approximate bytes per row

                    if time.time() - last_checkpoint > 60:
                        try:
                            save_checkpoint(conn, dump_path.name, f.tell(), total_rows)
                            last_checkpoint = time.time()
                        except Exception:
                            pass

    flush_all()
    total_rows += len(sys_batch)  # any remainder already cleared, count tracked above
    mark_complete(conn, dump_path.name, total_rows)
    log.info(f"Galaxy import complete: {total_rows:,} systems, {body_rows:,} bodies, {sta_rows:,} stations")
    return total_rows


# ---------------------------------------------------------------------------
# IMPORTER 2: bodies.json.gz  →  bodies table + update systems.has_body_data
# ---------------------------------------------------------------------------
def import_bodies(conn, dump_path: Path, resume_offset: int = 0) -> int:
    """
    Parse bodies.json.gz and insert into bodies table.
    Also updates systems.has_body_data, body_count, main_star fields.
    This is the largest dump (~80GB compressed). Takes the most time.
    """
    log.info(f"Importing bodies from {dump_path.name} ...")
    total_rows = 0
    batch = []
    system_updates = {}  # id64 → {has_body_data, body_count, main_star_type, ...}

    INSERT_SQL = """
        INSERT INTO bodies (
            id, system_id64, name,
            body_type, subtype, is_main_star,
            distance_from_star, orbital_period,
            semi_major_axis, orbital_eccentricity,
            orbital_inclination, is_tidal_lock,
            radius, mass, gravity,
            surface_temp, surface_pressure,
            atmosphere_type, atmosphere_composition,
            volcanism, solid_composition, materials,
            terraforming_state, is_terraformable,
            is_landable, is_water_world, is_earth_like, is_ammonia_world,
            bio_signal_count, geo_signal_count,
            spectral_class, luminosity, stellar_mass,
            absolute_magnitude, age_my, is_scoopable,
            estimated_mapping_value, estimated_scan_value,
            first_discovered_at, first_mapped_at, updated_at
        ) VALUES %s
        ON CONFLICT (id) DO UPDATE SET
            subtype                 = EXCLUDED.subtype,
            is_terraformable        = EXCLUDED.is_terraformable,
            terraforming_state      = EXCLUDED.terraforming_state,
            bio_signal_count        = EXCLUDED.bio_signal_count,
            geo_signal_count        = EXCLUDED.geo_signal_count,
            estimated_mapping_value = EXCLUDED.estimated_mapping_value,
            estimated_scan_value    = EXCLUDED.estimated_scan_value,
            updated_at              = EXCLUDED.updated_at
    """

    SCOOPABLE_STARS = {'O', 'B', 'A', 'F', 'G', 'K', 'M'}

    def flush_bodies(batch):
        if not batch: return
        psycopg2.extras.execute_values(conn.cursor(), INSERT_SQL, batch, page_size=BATCH_SIZE)

    def flush_system_updates(updates):
        if not updates: return
        with conn.cursor() as cur:
            for id64, upd in updates.items():
                cur.execute("""
                    UPDATE systems SET
                        has_body_data    = TRUE,
                        body_count       = body_count + %s,
                        main_star_type   = COALESCE(NULLIF(main_star_type,''), %s),
                        main_star_subtype= COALESCE(NULLIF(main_star_subtype,''), %s),
                        main_star_is_scoopable = COALESCE(main_star_is_scoopable, %s),
                        data_quality     = GREATEST(data_quality, 2),
                        rating_dirty     = TRUE,
                        cluster_dirty    = TRUE
                    WHERE id64 = %s
                """, (
                    upd.get('count', 0),
                    upd.get('main_star_type'),
                    upd.get('main_star_subtype'),
                    upd.get('scoopable'),
                    id64
                ))
        conn.commit()

    file_size = dump_path.stat().st_size
    mark_running(conn, dump_path.name, file_size)

    with gzip.open(dump_path, 'rb') as f:
        if resume_offset > 0:
            f.seek(resume_offset)

        parser = ijson.items(f, 'item')
        last_checkpoint = time.time()

        with tqdm(total=file_size, initial=resume_offset, unit='B',
                  unit_scale=True, desc='bodies.json.gz') as pbar:
            for body in parser:
                try:
                    body_id    = safe_int(body.get('id'))
                    system_id  = safe_int(body.get('systemId64') or body.get('system_id64'))
                    if body_id is None or system_id is None:
                        continue

                    subtype    = body.get('subType') or body.get('subtype') or body.get('type', '')
                    btype_raw  = body.get('type', 'Unknown')
                    is_star    = 'star' in str(btype_raw).lower()
                    is_planet  = not is_star
                    is_main    = bool(body.get('isMainStar') or body.get('is_main_star'))

                    # Bio/geo signals
                    signals    = body.get('signals') or {}
                    bio_sig    = safe_int(signals.get('genuses') or body.get('bio_signal_count', 0)) or 0
                    geo_sig    = safe_int(signals.get('geology') or body.get('geo_signal_count', 0)) or 0

                    # Classify body type enum
                    if is_star:
                        btype_enum = 'Star'
                    elif 'moon' in str(btype_raw).lower():
                        btype_enum = 'Moon'
                    else:
                        btype_enum = 'Planet'

                    # Scoopable star check
                    scoopable = None
                    if is_star and is_main:
                        spectral = body.get('spectralClass') or body.get('spectral_class', '')
                        scoopable = bool(spectral and spectral[0].upper() in SCOOPABLE_STARS)

                    row = (
                        body_id,
                        system_id,
                        str(body.get('name', 'Unknown')),
                        btype_enum,
                        subtype,
                        is_main,
                        safe_float(body.get('distanceToArrival') or body.get('distance_from_star')),
                        safe_float(body.get('orbitalPeriod') or body.get('orbital_period')),
                        safe_float(body.get('semiMajorAxis') or body.get('semi_major_axis')),
                        safe_float(body.get('orbitalEccentricity') or body.get('orbital_eccentricity')),
                        safe_float(body.get('orbitalInclination') or body.get('orbital_inclination')),
                        safe_bool(body.get('isTidallyLocked') or body.get('is_tidal_lock')),
                        safe_float(body.get('radius')),
                        safe_float(body.get('earthMasses') or body.get('solarMasses') or body.get('mass')),
                        safe_float(body.get('gravity')),
                        safe_float(body.get('surfaceTemperature') or body.get('surface_temp')),
                        safe_float(body.get('surfacePressure') or body.get('surface_pressure')),
                        body.get('atmosphereType') or body.get('atmosphere_type'),
                        json.dumps(body.get('atmosphereComposition') or body.get('atmosphere_composition')) if body.get('atmosphereComposition') or body.get('atmosphere_composition') else None,
                        body.get('volcanismType') or body.get('volcanism'),
                        json.dumps(body.get('solidComposition') or body.get('solid_composition')) if body.get('solidComposition') or body.get('solid_composition') else None,
                        json.dumps(body.get('materials')) if body.get('materials') else None,
                        body.get('terraformingState') or body.get('terraforming_state'),
                        bool(body.get('terraformingState', '') not in ('', 'Not terraformable', None)
                             or body.get('is_terraformable', False)),
                        bool(body.get('isLandable') or body.get('is_landable', False)),
                        bool('water world' in str(subtype).lower()),
                        bool('earth-like' in str(subtype).lower() or 'earthlike' in str(subtype).lower()),
                        bool('ammonia' in str(subtype).lower()),
                        bio_sig,
                        geo_sig,
                        body.get('spectralClass') or body.get('spectral_class'),
                        body.get('luminosity'),
                        safe_float(body.get('solarMasses') or body.get('stellar_mass')),
                        safe_float(body.get('absoluteMagnitude') or body.get('absolute_magnitude')),
                        safe_int(body.get('age') or body.get('age_my')),
                        scoopable,
                        safe_int(body.get('estimatedMappingValue') or body.get('estimated_mapping_value')),
                        safe_int(body.get('estimatedValue') or body.get('estimated_scan_value')),
                        parse_ts(body.get('discovered') or body.get('first_discovered_at')),
                        parse_ts(body.get('mapped') or body.get('first_mapped_at')),
                        parse_ts(body.get('updateTime') or body.get('updated_at')) or datetime.now(timezone.utc).isoformat(),
                    )
                    batch.append(row)

                    # Track system-level updates
                    upd = system_updates.setdefault(system_id, {'count': 0})
                    upd['count'] += 1
                    if is_main:
                        upd['main_star_type']    = body.get('spectralClass') or body.get('spectral_class')
                        upd['main_star_subtype'] = subtype
                        upd['scoopable']         = scoopable

                except Exception as e:
                    log.warning(f"Skipping malformed body: {e}")
                    continue

                if len(batch) >= BATCH_SIZE:
                    flush_bodies(batch)
                    total_rows += len(batch)
                    batch = []
                    pbar.update(BATCH_SIZE * 300)

                    # Flush system updates every 50k bodies
                    if total_rows % 50000 < BATCH_SIZE:
                        flush_system_updates(system_updates)
                        system_updates = {}

                    if time.time() - last_checkpoint > 60:
                        try:
                            conn.commit()
                            offset = f.tell()
                            save_checkpoint(conn, dump_path.name, offset, total_rows)
                            last_checkpoint = time.time()
                        except Exception: pass

    flush_bodies(batch)
    conn.commit()
    total_rows += len(batch)
    flush_system_updates(system_updates)
    mark_complete(conn, dump_path.name, total_rows)
    log.info(f"Bodies import complete: {total_rows:,} rows")
    return total_rows


# ---------------------------------------------------------------------------
# IMPORTER 3: galaxy_populated.json.gz  →  enrich systems + factions
# ---------------------------------------------------------------------------
def import_populated(conn, dump_path: Path, resume_offset: int = 0) -> int:
    """Enrich populated systems with faction data."""
    log.info(f"Importing populated systems from {dump_path.name} ...")
    total_rows = 0

    file_size = dump_path.stat().st_size
    mark_running(conn, dump_path.name, file_size)

    with gzip.open(dump_path, 'rb') as f:
        if resume_offset > 0:
            f.seek(resume_offset)
        parser = ijson.items(f, 'item')
        last_checkpoint = time.time()
        batch_sys = []
        batch_fac = []

        with tqdm(total=file_size, initial=resume_offset, unit='B',
                  unit_scale=True, desc='galaxy_populated.json.gz') as pbar:
            for sys_obj in parser:
                try:
                    id64 = safe_int(sys_obj.get('id64'))
                    if not id64: continue

                    ctrl = sys_obj.get('controllingFaction') or {}
                    ctrl_name = ctrl.get('name') if isinstance(ctrl, dict) else str(ctrl)

                    batch_sys.append((
                        safe_int(sys_obj.get('population', 0)) or 0,
                        norm_security(sys_obj.get('security')),
                        norm_allegiance(sys_obj.get('allegiance')),
                        norm_government(sys_obj.get('government')),
                        norm_economy(sys_obj.get('primaryEconomy') or sys_obj.get('economy')),
                        norm_economy(sys_obj.get('secondaryEconomy')),
                        ctrl_name,
                        id64,
                    ))

                    # Factions
                    for fac in sys_obj.get('factions', []):
                        if not fac.get('name'): continue
                        batch_fac.append((
                            str(fac['name']),
                            norm_allegiance(fac.get('allegiance')),
                            norm_government(fac.get('government')),
                            id64,
                            safe_float(fac.get('influence', 0)),
                            fac.get('state'),
                            fac.get('name') == ctrl_name,
                        ))

                    total_rows += 1

                    if len(batch_sys) >= BATCH_SIZE:
                        with conn.cursor() as cur:
                            psycopg2.extras.execute_values(cur, """
                                UPDATE systems SET
                                    population          = v.population,
                                    security            = v.security::security_type,
                                    allegiance          = v.allegiance::allegiance_type,
                                    government          = v.government::government_type,
                                    primary_economy     = v.primary_economy::economy_type,
                                    secondary_economy   = v.secondary_economy::economy_type,
                                    controlling_faction = v.ctrl,
                                    is_colonised        = (v.population > 0),
                                    rating_dirty        = TRUE
                                FROM (VALUES %s) AS v(population, security, allegiance,
                                    government, primary_economy, secondary_economy, ctrl, id64)
                                WHERE systems.id64 = v.id64::bigint
                            """, batch_sys)

                            # Upsert factions
                            if batch_fac:
                                psycopg2.extras.execute_values(cur, """
                                    INSERT INTO factions (name, allegiance, government)
                                    VALUES %s
                                    ON CONFLICT (name) DO UPDATE SET
                                        allegiance = EXCLUDED.allegiance,
                                        government = EXCLUDED.government,
                                        updated_at = NOW()
                                """, [(f[0], f[1], f[2]) for f in batch_fac])

                        conn.commit()
                        pbar.update(len(batch_sys) * 200)
                        batch_sys = []
                        batch_fac = []

                        if time.time() - last_checkpoint > 60:
                            save_checkpoint(conn, dump_path.name, f.tell(), total_rows)
                            last_checkpoint = time.time()

                except Exception as e:
                    log.warning(f"Skipping populated record: {e}")
                    continue

        # Flush remainder
        if batch_sys:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(cur, """
                    UPDATE systems SET
                        population          = v.population,
                        security            = v.security::security_type,
                        allegiance          = v.allegiance::allegiance_type,
                        government          = v.government::government_type,
                        primary_economy     = v.primary_economy::economy_type,
                        secondary_economy   = v.secondary_economy::economy_type,
                        controlling_faction = v.ctrl,
                        is_colonised        = (v.population > 0),
                        rating_dirty        = TRUE
                    FROM (VALUES %s) AS v(population, security, allegiance,
                        government, primary_economy, secondary_economy, ctrl, id64)
                    WHERE systems.id64 = v.id64::bigint
                """, batch_sys)
            conn.commit()

    mark_complete(conn, dump_path.name, total_rows)
    log.info(f"Populated import complete: {total_rows:,} rows")
    return total_rows


# ---------------------------------------------------------------------------
# IMPORTER 4: galaxy_stations.json.gz  →  stations table
# ---------------------------------------------------------------------------
def import_stations(conn, dump_path: Path, resume_offset: int = 0) -> int:
    """Import all stations, outposts, carriers."""
    log.info(f"Importing stations from {dump_path.name} ...")
    total_rows = 0
    batch = []

    STATION_TYPE_MAP = {
        'coriolis starport':     'Coriolis',
        'orbis starport':        'Orbis',
        'ocellus starport':      'Ocellus',
        'outpost':               'Outpost',
        'planetary port':        'PlanetaryPort',
        'planetary outpost':     'PlanetaryOutpost',
        'mega ship':             'MegaShip',
        'asteroid base':         'AsteroidBase',
        'fleet carrier':         'FleetCarrier',
    }

    def norm_station_type(v):
        if not v: return 'Unknown'
        return STATION_TYPE_MAP.get(str(v).lower(), 'Unknown')

    INSERT_SQL = """
        INSERT INTO stations (
            id, system_id64, name, station_type,
            distance_from_star, body_name,
            landing_pad_size,
            has_market, has_shipyard, has_outfitting,
            has_refuel, has_repair, has_rearm,
            has_black_market, has_material_trader,
            has_technology_broker, has_interstellar_factors,
            has_universal_cartographics,
            primary_economy, secondary_economy,
            controlling_faction, allegiance, government,
            updated_at
        ) VALUES %s
        ON CONFLICT (id) DO UPDATE SET
            station_type        = EXCLUDED.station_type,
            has_market          = EXCLUDED.has_market,
            has_shipyard        = EXCLUDED.has_shipyard,
            has_outfitting      = EXCLUDED.has_outfitting,
            controlling_faction = EXCLUDED.controlling_faction,
            updated_at          = EXCLUDED.updated_at
    """

    file_size = dump_path.stat().st_size
    mark_running(conn, dump_path.name, file_size)

    with gzip.open(dump_path, 'rb') as f:
        if resume_offset > 0:
            f.seek(resume_offset)
        parser = ijson.items(f, 'item')
        last_checkpoint = time.time()

        with tqdm(total=file_size, initial=resume_offset, unit='B',
                  unit_scale=True, desc='galaxy_stations.json.gz') as pbar:
            for sys_obj in parser:
                try:
                    sys_id64 = safe_int(sys_obj.get('id64'))
                    if not sys_id64: continue

                    for sta in sys_obj.get('stations', []):
                        sta_id = safe_int(sta.get('id'))
                        if not sta_id: continue

                        services = set(str(s).lower() for s in (sta.get('services') or []))
                        ctrl = sta.get('controllingFaction') or {}
                        ctrl_name = ctrl.get('name') if isinstance(ctrl, dict) else str(ctrl) if ctrl else None

                        batch.append((
                            sta_id, sys_id64,
                            str(sta.get('name', 'Unknown')),
                            norm_station_type(sta.get('type')),
                            safe_float(sta.get('distanceToArrival')),
                            sta.get('body', {}).get('name') if isinstance(sta.get('body'), dict) else sta.get('body'),
                            sta.get('landingPads', {}).get('large') and 'L' or
                            sta.get('landingPads', {}).get('medium') and 'M' or 'S',
                            'market' in services,
                            'shipyard' in services,
                            'outfitting' in services,
                            'refuel' in services,
                            'repair' in services,
                            'rearm' in services,
                            'black market' in services,
                            'material trader' in services,
                            'technology broker' in services,
                            'interstellar factors' in services,
                            'universal cartographics' in services,
                            norm_economy(sta.get('primaryEconomy') or sta.get('economy')),
                            norm_economy(sta.get('secondaryEconomy')),
                            ctrl_name,
                            norm_allegiance(sta.get('allegiance')),
                            norm_government(sta.get('government')),
                            parse_ts(sta.get('updateTime')) or datetime.now(timezone.utc).isoformat(),
                        ))
                        total_rows += 1

                    if len(batch) >= BATCH_SIZE:
                        psycopg2.extras.execute_values(conn.cursor(), INSERT_SQL, batch, page_size=BATCH_SIZE)
                        conn.commit()
                        pbar.update(len(batch) * 150)
                        batch = []
                        if time.time() - last_checkpoint > 60:
                            save_checkpoint(conn, dump_path.name, f.tell(), total_rows)
                            last_checkpoint = time.time()

                except Exception as e:
                    log.warning(f"Skipping station record: {e}")
                    continue

    if batch:
        psycopg2.extras.execute_values(conn.cursor(), INSERT_SQL, batch, page_size=BATCH_SIZE)
        conn.commit()

    mark_complete(conn, dump_path.name, total_rows)
    log.info(f"Stations import complete: {total_rows:,} rows")
    return total_rows


# ---------------------------------------------------------------------------
# IMPORTER 5: attractions.json.gz  →  attractions table
# ---------------------------------------------------------------------------
def import_attractions(conn, dump_path: Path, resume_offset: int = 0) -> int:
    """Import all biological, geological, and POI attractions."""
    log.info(f"Importing attractions from {dump_path.name} ...")
    total_rows = 0
    batch = []

    INSERT_SQL = """
        INSERT INTO attractions (
            system_id64, body_name,
            attraction_type, subtype,
            genus, species, variant,
            latitude, longitude,
            estimated_value,
            updated_at
        ) VALUES %s
        ON CONFLICT DO NOTHING
    """

    file_size = dump_path.stat().st_size
    mark_running(conn, dump_path.name, file_size)

    with gzip.open(dump_path, 'rb') as f:
        if resume_offset > 0:
            f.seek(resume_offset)
        parser = ijson.items(f, 'item')
        last_checkpoint = time.time()

        with tqdm(total=file_size, initial=resume_offset, unit='B',
                  unit_scale=True, desc='attractions.json.gz') as pbar:
            for sys_obj in parser:
                try:
                    sys_id64 = safe_int(sys_obj.get('id64'))
                    if not sys_id64: continue

                    for body in sys_obj.get('bodies', []):
                        body_name = body.get('name', '')

                        for signal in body.get('signals', []):
                            sig_type = str(signal.get('type', 'Other'))
                            batch.append((
                                sys_id64, body_name,
                                sig_type,
                                signal.get('subtype') or signal.get('type'),
                                signal.get('genus'),
                                signal.get('species'),
                                signal.get('variant') or signal.get('color'),
                                safe_float(signal.get('latitude')),
                                safe_float(signal.get('longitude')),
                                safe_int(signal.get('value')),
                                datetime.now(timezone.utc).isoformat(),
                            ))
                            total_rows += 1

                    if len(batch) >= BATCH_SIZE:
                        psycopg2.extras.execute_values(conn.cursor(), INSERT_SQL, batch, page_size=BATCH_SIZE)
                        conn.commit()
                        pbar.update(len(batch) * 100)
                        batch = []
                        if time.time() - last_checkpoint > 60:
                            save_checkpoint(conn, dump_path.name, f.tell(), total_rows)
                            last_checkpoint = time.time()

                except Exception as e:
                    log.warning(f"Skipping attraction: {e}")
                    continue

    if batch:
        psycopg2.extras.execute_values(conn.cursor(), INSERT_SQL, batch, page_size=BATCH_SIZE)
        conn.commit()

    mark_complete(conn, dump_path.name, total_rows)
    log.info(f"Attractions import complete: {total_rows:,} rows")
    return total_rows


# ---------------------------------------------------------------------------
# Download helper
# ---------------------------------------------------------------------------
def download_dumps(files: list[str]):
    """Download Spansh dump files if not already present."""
    import urllib.request
    DUMP_DIR.mkdir(parents=True, exist_ok=True)
    for fname in files:
        dest = DUMP_DIR / fname
        if dest.exists():
            log.info(f"Already exists: {fname} ({dest.stat().st_size / 1e9:.1f} GB)")
            continue
        url = f"{SPANSH_BASE}/{fname}"
        log.info(f"Downloading {url} → {dest}")
        try:
            def progress(block_count, block_size, total_size):
                pct = block_count * block_size / total_size * 100 if total_size > 0 else 0
                print(f"\r  {fname}: {pct:.1f}%", end='', flush=True)
            urllib.request.urlretrieve(url, dest, reporthook=progress)
            print()
            log.info(f"Downloaded {fname}: {dest.stat().st_size / 1e9:.1f} GB")
        except Exception as e:
            log.error(f"Failed to download {fname}: {e}")


# ---------------------------------------------------------------------------
# Status display
# ---------------------------------------------------------------------------
def show_status(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT dump_file, status, rows_processed, rows_total,
                   CASE WHEN rows_total > 0
                       THEN round(rows_processed::numeric / rows_total * 100, 1)
                       ELSE 0 END AS pct,
                   started_at, completed_at, error_message
            FROM import_meta ORDER BY id
        """)
        rows = cur.fetchall()

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  ED Finder — Import Status                                   ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    for r in rows:
        status_icon = {'complete': '✅', 'running': '🔄', 'failed': '❌',
                       'pending': '⏳', 'partial': '⚠️'}.get(r[1], '?')
        print(f"║  {status_icon} {r[0]:<35} {r[1]:<10} {r[4]:>5}%  ║")
        if r[7]:
            print(f"║    ⚠ {r[7][:55]:<55} ║")
    print("╚══════════════════════════════════════════════════════════════╝\n")

    # Row counts
    cur = conn.cursor()
    for table in ['systems', 'bodies', 'stations', 'ratings']:
        # attractions table exists in schema but no longer populated (source dump removed by Spansh)
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"  {table:<20} {count:>15,} rows")
        except Exception:
            print(f"  {table:<20} (table not accessible)")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
IMPORTER_MAP = {
    'galaxy.json.gz':            import_galaxy,       # systems + bodies + stations (all-in-one)
    'galaxy_populated.json.gz':  import_populated,    # enriches populated system fields
    'galaxy_stations.json.gz':   import_stations,     # re-imports stations with extra detail
    # bodies.json.gz and attractions.json.gz no longer exist on Spansh
}

# Recommended import order
IMPORT_ORDER = [
    'galaxy.json.gz',           # FIRST: all systems + bodies + stations (102 GB, ~6-18 h)
    'galaxy_populated.json.gz', # enriches faction/economy/security data for populated systems
    'galaxy_stations.json.gz',  # re-imports stations with latest market/service state
]

def main():
    global DUMP_DIR
    parser = argparse.ArgumentParser(
        description='ED Finder — Spansh dump importer'
    )
    parser.add_argument('--all',      action='store_true', help='Import all dumps in order')
    parser.add_argument('--file',     type=str,            help='Import a specific dump file')
    parser.add_argument('--resume',   action='store_true', help='Resume from last checkpoint')
    parser.add_argument('--download', action='store_true', help='Download dump files first')
    parser.add_argument('--status',   action='store_true', help='Show import status')
    parser.add_argument('--dump-dir', type=str,            help=f'Dump directory (default: {DUMP_DIR})')
    args = parser.parse_args()

    if args.dump_dir:
        DUMP_DIR = Path(args.dump_dir)

    conn = get_conn()

    if args.status:
        show_status(conn)
        return

    if args.download:
        files = [args.file] if args.file else IMPORT_ORDER
        download_dumps(files)

    files_to_import = IMPORT_ORDER if args.all else ([args.file] if args.file else [])
    if not files_to_import:
        parser.print_help()
        return

    total_start = time.time()
    for fname in files_to_import:
        dump_path = DUMP_DIR / fname
        if not dump_path.exists():
            log.error(f"Dump file not found: {dump_path}")
            log.error(f"Run with --download first, or place files in {DUMP_DIR}")
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
    log.info(f"\nAll imports complete in {total_elapsed/3600:.2f} hours")
    log.info("Next steps:")
    log.info("  python3 build_ratings.py   — compute scores for all visited systems")
    log.info("  python3 build_grid.py      — build spatial grid")
    log.info("  python3 build_clusters.py  — build cluster_summary table")
    log.info("  psql ... -f 002_indexes.sql — build all indexes")

    conn.close()


if __name__ == '__main__':
    main()
