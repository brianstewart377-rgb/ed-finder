#!/usr/bin/env python3
"""
ED:Finder — Phase 1 Local DB Import: systems.json.gz
=====================================================
Streams the Spansh systems dump into a local SQLite database.

Schema stored in: /data/galaxy.db  (separate from the cache edfinder.db)

Usage:
    python3 import_systems.py [--db /data/galaxy.db] [--file /data/systems.json.gz]
    python3 import_systems.py --download          # fetch from Spansh first

Performance targets (Pi 5, NVMe):
    ~180 M systems → ~36 GB SQLite → ~25–45 min import

Columns imported from systems.json.gz per the Spansh schema:
    id64, name, coords.x/y/z, mainStar, updateTime, needsPermit
"""
from __future__ import annotations

import argparse
import gzip
import json
import logging
import os
import sqlite3
import sys
import time
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

# ── Config ────────────────────────────────────────────────────────────────────
SPANSH_SYSTEMS_URL  = "https://downloads.spansh.co.uk/systems.json.gz"
SPANSH_1DAY_URL     = "https://downloads.spansh.co.uk/galaxy_1day.json.gz"
DEFAULT_DB          = "/data/galaxy.db"
DEFAULT_FILE        = "/data/systems.json.gz"
BATCH_SIZE          = 5000      # rows per SQLite transaction
LOG_EVERY           = 500_000   # print progress every N systems

logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger("import_systems")


# ── SQLite helpers ────────────────────────────────────────────────────────────
def open_db(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    # Optimised for bulk import on NVMe
    conn.executescript("""
        PRAGMA journal_mode    = WAL;
        PRAGMA synchronous     = NORMAL;
        PRAGMA cache_size      = -65536;   -- 64 MB
        PRAGMA mmap_size       = 536870912; -- 512 MB
        PRAGMA temp_store      = MEMORY;
        PRAGMA page_size       = 8192;
    """)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist (idempotent)."""
    conn.executescript("""
        -- Core systems table (from systems.json.gz)
        CREATE TABLE IF NOT EXISTS systems (
            id64          INTEGER PRIMARY KEY,
            name          TEXT    NOT NULL,
            x             REAL    NOT NULL,
            y             REAL    NOT NULL,
            z             REAL    NOT NULL,
            main_star     TEXT,
            needs_permit  INTEGER NOT NULL DEFAULT 0,
            updated_at    TEXT,           -- ISO timestamp from dump
            imported_at   REAL    NOT NULL DEFAULT 0
        );

        -- Spatial index helper: bucketed grid for fast radius searches
        -- Cells are 25 LY cubes: cell = CAST(coord / 25 AS INTEGER)
        CREATE TABLE IF NOT EXISTS spatial_grid (
            cx  INTEGER NOT NULL,
            cy  INTEGER NOT NULL,
            cz  INTEGER NOT NULL,
            id64 INTEGER NOT NULL REFERENCES systems(id64) ON DELETE CASCADE,
            PRIMARY KEY (cx, cy, cz, id64)
        );

        -- Bodies table (populated from galaxy.json.gz, Phase 2)
        CREATE TABLE IF NOT EXISTS bodies (
            id64          INTEGER PRIMARY KEY,
            system_id64   INTEGER NOT NULL REFERENCES systems(id64) ON DELETE CASCADE,
            name          TEXT,
            type          TEXT,
            subtype       TEXT,
            distance_to_arrival REAL,
            is_main_star  INTEGER DEFAULT 0,
            is_landable   INTEGER DEFAULT 0,
            is_tidal_lock INTEGER DEFAULT 0,  -- rotationalPeriodTidallyLocked from Spansh dump
            has_signals   INTEGER DEFAULT 0,
            has_rings     INTEGER DEFAULT 0,
            ring_types    TEXT,           -- JSON array
            atmosphere    TEXT,
            volcanism     TEXT,
            terraform_state TEXT,
            mass          REAL,
            radius        REAL,
            surface_temp  REAL,
            surface_gravity REAL,
            estimated_mapping_value  INTEGER DEFAULT 0,
            estimated_scan_value     INTEGER DEFAULT 0,
            data          TEXT           -- full JSON blob from Spansh
        );

        -- Colonisation status table (updated by EDDN listener)
        CREATE TABLE IF NOT EXISTS colonisation (
            id64          INTEGER PRIMARY KEY REFERENCES systems(id64) ON DELETE CASCADE,
            population    INTEGER DEFAULT 0,
            is_colonised  INTEGER DEFAULT 0,
            is_being_colonised INTEGER DEFAULT 0,
            controlling_faction TEXT,
            state         TEXT,
            government    TEXT,
            allegiance    TEXT,
            economy       TEXT,
            eddn_updated  REAL,           -- unix timestamp of last EDDN update
            spansh_updated REAL           -- unix timestamp of last Spansh pull
        );

        -- Stations table (populated from galaxy.json.gz / galaxy_stations.json.gz)
        CREATE TABLE IF NOT EXISTS stations (
            id            INTEGER PRIMARY KEY,
            system_id64   INTEGER NOT NULL REFERENCES systems(id64) ON DELETE CASCADE,
            name          TEXT,
            type          TEXT,
            distance_to_arrival REAL,
            has_shipyard  INTEGER DEFAULT 0,
            has_outfitting INTEGER DEFAULT 0,
            has_market    INTEGER DEFAULT 0,
            economies     TEXT,           -- JSON array
            updated_at    TEXT
        );

        -- Import progress tracker
        CREATE TABLE IF NOT EXISTS import_meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        -- Indexes (created after bulk import for speed)
        -- Run CREATE_INDEXES after initial import completes.
    """)
    conn.commit()
    log.info("Schema initialised at %s", conn)


def create_indexes(conn: sqlite3.Connection) -> None:
    """Create indexes after bulk import (much faster than building during insert)."""
    log.info("Creating indexes (this may take 5–15 minutes on first run)…")
    t0 = time.time()
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_sys_name        ON systems(name);
        CREATE INDEX IF NOT EXISTS idx_sys_x           ON systems(x);
        CREATE INDEX IF NOT EXISTS idx_sys_y           ON systems(y);
        CREATE INDEX IF NOT EXISTS idx_sys_z           ON systems(z);
        CREATE INDEX IF NOT EXISTS idx_sys_star        ON systems(main_star);
        CREATE INDEX IF NOT EXISTS idx_spatial         ON spatial_grid(cx, cy, cz);
        CREATE INDEX IF NOT EXISTS idx_bodies_system   ON bodies(system_id64);
        CREATE INDEX IF NOT EXISTS idx_bodies_type     ON bodies(type);
        CREATE INDEX IF NOT EXISTS idx_bodies_landable ON bodies(is_landable);
        CREATE INDEX IF NOT EXISTS idx_bodies_tidal    ON bodies(is_tidal_lock);
        CREATE INDEX IF NOT EXISTS idx_bodies_signals  ON bodies(has_signals);
        CREATE INDEX IF NOT EXISTS idx_col_pop         ON colonisation(population);
        CREATE INDEX IF NOT EXISTS idx_col_colonised   ON colonisation(is_colonised);
        CREATE INDEX IF NOT EXISTS idx_stations_system ON stations(system_id64);
    """)
    conn.commit()
    log.info("Indexes created in %.1f s", time.time() - t0)


def meta_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO import_meta (key, value) VALUES (?,?)", (key, value)
    )
    conn.commit()


def meta_get(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute(
        "SELECT value FROM import_meta WHERE key=?", (key,)
    ).fetchone()
    return row[0] if row else default


# ── Streaming JSON parser ─────────────────────────────────────────────────────
def stream_systems_gz(path: str) -> Iterator[dict]:
    """
    Stream systems from a gzip'd JSON file.

    Spansh systems.json.gz is a JSON *array* of objects — one giant array.
    We stream it line-by-line; each line after the first '[' is either an
    object (trim trailing comma) or the closing ']'.
    """
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line in ("[", "]"):
                continue
            # Strip trailing comma (array format)
            if line.endswith(","):
                line = line[:-1]
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def stream_galaxy_gz(path: str) -> Iterator[dict]:
    """
    Stream systems from galaxy.json.gz (same format but each object has
    a 'bodies' array nested inside).
    """
    yield from stream_systems_gz(path)


# ── Import logic ──────────────────────────────────────────────────────────────
def import_systems(db_path: str, file_path: str, resume: bool = True) -> None:
    """
    Stream-import systems.json.gz into the galaxy.db.

    If resume=True, skips systems already present (INSERT OR IGNORE).
    This makes the import restartable after a crash or power cut.
    """
    conn = open_db(db_path)
    init_schema(conn)

    start_count = conn.execute("SELECT COUNT(*) FROM systems").fetchone()[0]
    log.info("Starting systems import. DB already has %d systems.", start_count)
    log.info("Source file: %s", file_path)

    now = time.time()
    batch: list[tuple] = []
    total = 0
    inserted = 0
    t_start = time.time()
    t_last_log = t_start

    try:
        for sys in stream_systems_gz(file_path):
            coords = sys.get("coords", {})
            x = coords.get("x", 0.0)
            y = coords.get("y", 0.0)
            z = coords.get("z", 0.0)

            batch.append((
                sys["id64"],
                sys.get("name", ""),
                x, y, z,
                sys.get("mainStar"),
                1 if sys.get("needsPermit") else 0,
                sys.get("updateTime"),
                now,
            ))

            total += 1

            if len(batch) >= BATCH_SIZE:
                n = _flush_systems(conn, batch)
                inserted += n
                batch.clear()

                if total % LOG_EVERY < BATCH_SIZE:
                    elapsed = time.time() - t_start
                    rate = total / elapsed if elapsed > 0 else 0
                    eta_s = (180_000_000 - total) / rate if rate > 0 else 0
                    log.info(
                        "Progress: %d systems (%.0f/s) | inserted %d | ETA %.0f min",
                        total, rate, inserted, eta_s / 60,
                    )
                    meta_set(conn, "import_progress", str(total))

        # Final flush
        if batch:
            n = _flush_systems(conn, batch)
            inserted += n

    except KeyboardInterrupt:
        log.warning("Import interrupted at %d systems. Safe to resume.", total)
        meta_set(conn, "import_progress", str(total))
        conn.close()
        return

    elapsed = time.time() - t_start
    log.info("Systems import complete: %d scanned, %d inserted in %.1f min",
             total, inserted, elapsed / 60)
    meta_set(conn, "systems_import_done", datetime.now(timezone.utc).isoformat())
    meta_set(conn, "systems_total", str(total))

    log.info("Building spatial grid…")
    _build_spatial_grid(conn)

    log.info("Creating indexes…")
    create_indexes(conn)

    conn.execute("PRAGMA optimize")
    conn.close()
    log.info("All done. Galaxy DB ready at %s", db_path)


def _flush_systems(conn: sqlite3.Connection, batch: list) -> int:
    """INSERT OR IGNORE a batch of systems; return number actually inserted."""
    cur = conn.executemany(
        """INSERT OR IGNORE INTO systems
           (id64, name, x, y, z, main_star, needs_permit, updated_at, imported_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        batch,
    )
    conn.commit()
    return cur.rowcount


def _build_spatial_grid(conn: sqlite3.Connection) -> None:
    """
    Populate the spatial_grid table from the systems table.
    Uses 25 LY cells so a 100 LY radius search checks at most ~8³ = 512 cells.
    Run AFTER all systems are inserted.
    """
    CELL = 25
    count = conn.execute("SELECT COUNT(*) FROM systems").fetchone()[0]
    log.info("Building spatial grid for %d systems…", count)
    t0 = time.time()

    conn.execute("DELETE FROM spatial_grid")  # idempotent rebuild
    conn.execute("""
        INSERT OR IGNORE INTO spatial_grid (cx, cy, cz, id64)
        SELECT
            CAST(x / ? AS INTEGER),
            CAST(y / ? AS INTEGER),
            CAST(z / ? AS INTEGER),
            id64
        FROM systems
    """, (CELL, CELL, CELL))
    conn.commit()
    sg_count = conn.execute("SELECT COUNT(*) FROM spatial_grid").fetchone()[0]
    log.info("Spatial grid: %d entries in %.1f s", sg_count, time.time() - t0)


# ── Galaxy import (Phase 2) ───────────────────────────────────────────────────
def import_galaxy(db_path: str, file_path: str) -> None:
    """
    Import galaxy.json.gz — same as systems but also extracts body data.
    Adds rows to: systems (upsert), bodies, colonisation.
    """
    conn = open_db(db_path)
    init_schema(conn)

    log.info("Starting galaxy import (full body data). File: %s", file_path)
    now = time.time()

    sys_batch:  list = []
    body_batch: list = []
    col_batch:  list = []
    total = 0
    t_start = time.time()

    try:
        for sys in stream_galaxy_gz(file_path):
            coords = sys.get("coords", {})
            x = coords.get("x", 0.0)
            y = coords.get("y", 0.0)
            z = coords.get("z", 0.0)

            sys_batch.append((
                sys["id64"],
                sys.get("name", ""),
                x, y, z,
                sys.get("mainStar") or _main_star_from_bodies(sys.get("bodies", [])),
                1 if sys.get("knowsPermit") else 0,
                sys.get("date"),
                now,
            ))

            # Colonisation status
            pop = int(sys.get("population", 0) or 0)
            is_col = 1 if pop > 0 else 0
            col_batch.append((
                sys["id64"],
                pop,
                is_col,
                0,  # is_being_colonised — not in dump, updated by EDDN
                sys.get("controllingFaction", {}).get("name") if isinstance(sys.get("controllingFaction"), dict) else sys.get("controllingFaction"),
                sys.get("state"),
                sys.get("government"),
                sys.get("allegiance"),
                sys.get("primaryEconomy"),
                None,
                now,
            ))

            # Bodies
            for body in sys.get("bodies", []):
                body_batch.append(_body_row(sys["id64"], body))

            total += 1

            if len(sys_batch) >= BATCH_SIZE:
                _flush_galaxy_batch(conn, sys_batch, body_batch, col_batch)
                sys_batch.clear()
                body_batch.clear()
                col_batch.clear()

                if total % LOG_EVERY < BATCH_SIZE:
                    elapsed = time.time() - t_start
                    rate = total / elapsed if elapsed > 0 else 0
                    log.info("Galaxy progress: %d systems (%.0f/s)", total, rate)
                    meta_set(conn, "galaxy_import_progress", str(total))

        # Final flush
        if sys_batch:
            _flush_galaxy_batch(conn, sys_batch, body_batch, col_batch)

    except KeyboardInterrupt:
        log.warning("Galaxy import interrupted at %d systems. Safe to resume.", total)
        conn.close()
        return

    elapsed = time.time() - t_start
    log.info("Galaxy import complete: %d systems in %.1f min", total, elapsed / 60)
    meta_set(conn, "galaxy_import_done", datetime.now(timezone.utc).isoformat())

    log.info("Rebuilding spatial grid and indexes…")
    _build_spatial_grid(conn)
    create_indexes(conn)
    conn.execute("PRAGMA optimize")
    conn.close()
    log.info("Galaxy DB ready at %s", db_path)


def _flush_galaxy_batch(conn, sys_batch, body_batch, col_batch) -> None:
    conn.executemany(
        """INSERT OR REPLACE INTO systems
           (id64, name, x, y, z, main_star, needs_permit, updated_at, imported_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        sys_batch,
    )
    if body_batch:
        conn.executemany(
            """INSERT OR REPLACE INTO bodies
               (id64, system_id64, name, type, subtype, distance_to_arrival,
                is_main_star, is_landable, is_tidal_lock,
                has_signals, has_rings, ring_types,
                atmosphere, volcanism, terraform_state, mass, radius,
                surface_temp, surface_gravity,
                estimated_mapping_value, estimated_scan_value, data)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            body_batch,
        )
    if col_batch:
        conn.executemany(
            """INSERT OR REPLACE INTO colonisation
               (id64, population, is_colonised, is_being_colonised,
                controlling_faction, state, government, allegiance, economy,
                eddn_updated, spansh_updated)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            col_batch,
        )
    conn.commit()


def _main_star_from_bodies(bodies: list) -> str | None:
    """Extract mainStar type from bodies list when not at top level."""
    for b in bodies:
        if b.get("isMainStar") or b.get("is_main_star"):
            return b.get("type") or b.get("subType")
    return None


def _body_row(system_id64: int, body: dict) -> tuple:
    """Convert a Spansh body dict to a row tuple for the bodies table."""
    rings = body.get("rings", []) or []
    ring_types = json.dumps([r.get("type") for r in rings]) if rings else None
    has_sigs = 1 if (body.get("signals") or body.get("has_signals")) else 0
    # Spansh galaxy dump: camelCase 'rotationalPeriodTidallyLocked' (bool)
    # API search endpoint: snake_case 'is_rotational_period_tidally_locked' (bool)
    is_tidal = 1 if (
        body.get("rotationalPeriodTidallyLocked") or
        body.get("is_rotational_period_tidally_locked")
    ) else 0

    return (
        body.get("id64") or body.get("id"),
        system_id64,
        body.get("name"),
        body.get("type"),
        body.get("subType") or body.get("subtype"),
        body.get("distanceToArrival"),
        1 if body.get("isMainStar") else 0,
        1 if body.get("isLandable") else 0,
        is_tidal,                                  # NEW: is_tidal_lock column
        has_sigs,
        1 if rings else 0,
        ring_types,
        body.get("atmosphereType") or body.get("atmosphere"),
        body.get("volcanismType") or body.get("volcanism"),
        body.get("terraformingState") or body.get("terraform_state"),
        body.get("solarMasses") or body.get("mass"),
        body.get("radius"),
        body.get("surfaceTemperature") or body.get("surface_temp"),
        body.get("surfaceGravity") or body.get("surface_gravity"),
        body.get("estimatedMappingValue") or body.get("estimated_mapping_value", 0),
        body.get("estimatedScanValue") or body.get("estimated_scan_value", 0),
        json.dumps(body),
    )


# ── Delta import (nightly galaxy_1day.json.gz) ───────────────────────────────
def import_delta(db_path: str, file_path: str) -> None:
    """
    Apply a Spansh 1-day or 1-month delta dump to update existing records.
    Same format as galaxy.json.gz — upserts systems, bodies, colonisation.
    """
    log.info("Applying delta update from %s", file_path)
    import_galaxy(db_path, file_path)   # Same logic; INSERT OR REPLACE handles upserts


# ── Download helpers ──────────────────────────────────────────────────────────
def download_file(url: str, dest: str) -> None:
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    log.info("Downloading %s → %s", url, dest)
    tmp = dest + ".tmp"

    def _progress(block_num, block_size, total_size):
        downloaded = block_num * block_size
        if total_size > 0:
            pct = min(downloaded / total_size * 100, 100)
            if block_num % 5000 == 0:
                log.info("  %.1f%% (%.1f GB / %.1f GB)",
                         pct, downloaded / 1e9, total_size / 1e9)

    urllib.request.urlretrieve(url, tmp, _progress)
    os.rename(tmp, dest)
    log.info("Download complete: %s (%.2f GB)", dest, os.path.getsize(dest) / 1e9)


# ── CLI ───────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="ED:Finder local galaxy DB importer")
    parser.add_argument("--db",       default=DEFAULT_DB,   help="Galaxy SQLite DB path")
    parser.add_argument("--file",     default=DEFAULT_FILE, help="Input .json.gz file")
    parser.add_argument("--galaxy",   action="store_true",  help="Import full galaxy.json.gz (with bodies)")
    parser.add_argument("--delta",    action="store_true",  help="Apply delta (1-day) update")
    parser.add_argument("--download", action="store_true",  help="Download the dump first")
    parser.add_argument("--url",      default=None,         help="Override download URL")
    parser.add_argument("--index-only", action="store_true", help="Only rebuild indexes (skip import)")
    args = parser.parse_args()

    if args.index_only:
        conn = open_db(args.db)
        create_indexes(conn)
        conn.close()
        return

    if args.download:
        if args.galaxy:
            url = args.url or "https://downloads.spansh.co.uk/galaxy.json.gz"
            dest = args.file if args.file != DEFAULT_FILE else "/data/galaxy.json.gz"
        elif args.delta:
            url = args.url or SPANSH_1DAY_URL
            dest = args.file if args.file != DEFAULT_FILE else "/data/galaxy_1day.json.gz"
        else:
            url = args.url or SPANSH_SYSTEMS_URL
            dest = args.file
        download_file(url, dest)
        if args.file == DEFAULT_FILE and not args.galaxy and not args.delta:
            args.file = DEFAULT_FILE

    if args.galaxy:
        file_path = args.file if args.file != DEFAULT_FILE else "/data/galaxy.json.gz"
        import_galaxy(args.db, file_path)
    elif args.delta:
        file_path = args.file if args.file != DEFAULT_FILE else "/data/galaxy_1day.json.gz"
        import_delta(args.db, file_path)
    else:
        import_systems(args.db, args.file)


if __name__ == "__main__":
    main()
