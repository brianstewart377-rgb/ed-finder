#!/usr/bin/env python3
"""
ED Finder — Spatial Grid Builder
Version: 1.4  (TCP keepalives, reconnect-on-error, skip assigned cells)

Divides the galaxy into 500ly cubic cells and assigns every system to a cell.

STAGES:
  1. Galaxy bounds  — compute or load from cache (one-time seq scan)
  2. Cell INSERT    — GROUP BY all 186M systems into 500ly cubes
  3. Cell ASSIGN    — UPDATE every system with its grid_cell_id (batched, resume-safe)
  4. Visited count  — count scanned systems per cell
  5. Save meta      — write grid parameters to app_meta

ROOT CAUSE of repeated crashes (fixed in v1.4):
  The Stage 3 loop holds ONE connection open for many hours, issuing 135k
  individual UPDATE statements.  PostgreSQL closes long-idle connections and
  the Docker network drops TCP sessions silently after ~1-2h.

FIXES in v1.4:
  • TCP keepalives (idle=60s, interval=10s, count=6) — prevents silent drops
  • Reconnect-on-error — if UPDATE fails, reconnects and retries once before
    giving up on that cell (doesn't skip 10k cells just because of one drop)
  • Skip already-assigned cells in SQL — uses bounding-box pre-filter AND
    checks grid_cell_id IS NULL so already-done cells are a no-op UPDATE
    (negligible cost, means re-runs truly continue from where they left off)
  • Commit every 200 cells (was 500) — smaller WAL, less lost work on crash
  • Progress every 20s (was 30s) — faster feedback
  • server-side cursor for cell list — avoids fetching all 135k rows into RAM

Usage:
    python3 build_grid.py
    python3 build_grid.py --cell-size 500   # default
"""

import os
import sys
import math
import time
import signal
import logging
import argparse

import psycopg2
import psycopg2.extras
import psycopg2.extensions

from progress import (
    ProgressReporter,
    startup_banner, stage_banner, done_banner, crash_hint,
    fmt_duration, fmt_num, fmt_rate, fmt_pct,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_DSN    = os.getenv('DATABASE_URL', 'postgresql://edfinder:edfinder@localhost:5432/edfinder')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE  = os.getenv('LOG_FILE', '/tmp/build_grid.log')
CELL_SIZE = int(os.getenv('CELL_SIZE', '500'))

os.makedirs(os.path.dirname(os.path.abspath(LOG_FILE)), exist_ok=True)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger('build_grid')

# Graceful shutdown flag
_shutdown = False
def _handle_signal(sig, frame):
    global _shutdown
    log.warning("Interrupt received — finishing current batch then exiting cleanly ...")
    _shutdown = True
signal.signal(signal.SIGINT,  _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _connect(dsn: str) -> psycopg2.extensions.connection:
    """
    Open a PostgreSQL connection with TCP keepalives enabled.

    keepalives_idle=60   — send first keepalive probe after 60s of silence
    keepalives_interval=10 — resend probe every 10s if no reply
    keepalives_count=6   — declare connection dead after 6 missed probes (60s)

    This prevents Docker/NAT from silently dropping connections during the
    long Stage-3 UPDATE loop.
    """
    conn = psycopg2.connect(
        dsn,
        keepalives=1,
        keepalives_idle=60,
        keepalives_interval=10,
        keepalives_count=6,
    )
    conn.autocommit = False
    return conn


def _connect_with_retry(dsn: str, label: str = "", retries: int = 5,
                         delay: float = 10.0) -> psycopg2.extensions.connection:
    """Connect with exponential back-off retries."""
    for attempt in range(1, retries + 1):
        try:
            return _connect(dsn)
        except Exception as e:
            if attempt == retries:
                log.error(f"FATAL: Cannot connect to database ({label}): {e}")
                raise
            wait = delay * attempt
            log.warning(f"  DB connect failed ({label}, attempt {attempt}/{retries}): {e}")
            log.warning(f"  Retrying in {wait:.0f}s ...")
            time.sleep(wait)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Build spatial grid for fast cluster queries')
    parser.add_argument('--cell-size', type=int, default=CELL_SIZE,
                        help=f'Grid cell size in LY (default: {CELL_SIZE})')
    args = parser.parse_args()
    cell_size = args.cell_size

    script_start = time.time()

    startup_banner(log, "Spatial Grid Builder", "v1.4", [
        ("Cell size",   f"{cell_size} LY"),
        ("Log file",    LOG_FILE),
        ("DB",          DB_DSN.split('@')[-1]),
        ("Keepalives",  "idle=60s, interval=10s, count=6  (prevents TCP drops)"),
        ("Commit freq", "every 200 cells  (~280k systems per commit)"),
    ])

    conn = _connect_with_retry(DB_DSN, label="main")
    cur = conn.cursor()

    # =========================================================================
    # STAGE 1: Galaxy bounds
    # =========================================================================
    stage_banner(log, 1, 5, "Galaxy Bounds")

    cur.execute("""
        SELECT key, value FROM app_meta
        WHERE key IN ('grid_min_x','grid_min_y','grid_min_z',
                      'grid_max_x','grid_max_y','grid_max_z','grid_total_systems')
    """)
    stored = {r[0]: r[1] for r in cur.fetchall()}
    bounds_keys = ('grid_min_x','grid_min_y','grid_min_z',
                   'grid_max_x','grid_max_y','grid_max_z','grid_total_systems')

    if all(k in stored for k in bounds_keys):
        min_x = float(stored['grid_min_x'])
        min_y = float(stored['grid_min_y'])
        min_z = float(stored['grid_min_z'])
        max_x = float(stored['grid_max_x'])
        max_y = float(stored['grid_max_y'])
        max_z = float(stored['grid_max_z'])
        total_systems = int(stored['grid_total_systems'])
        log.info(f"  Loaded from cache (skipping seq scan) ✓")
        log.info(f"  X: [{min_x:.0f}, {max_x:.0f}]  Y: [{min_y:.0f}, {max_y:.0f}]  Z: [{min_z:.0f}, {max_z:.0f}]")
        log.info(f"  Total systems: {fmt_num(total_systems)}")
    else:
        log.info(f"  Running full seq scan on systems table (186M rows) ...")
        log.info(f"  This takes 5-30 minutes without coord indexes. Only needed once.")
        t0 = time.time()
        cur.execute("""
            SELECT MIN(x), MAX(x), MIN(y), MAX(y), MIN(z), MAX(z), COUNT(*)
            FROM systems
        """)
        row = cur.fetchone()
        log.info(f"  Seq scan completed in {fmt_duration(time.time()-t0)}")
        min_x, max_x = row[0] - cell_size, row[1] + cell_size
        min_y, max_y = row[2] - cell_size, row[3] + cell_size
        min_z, max_z = row[4] - cell_size, row[5] + cell_size
        total_systems = row[6]
        log.info(f"  X: [{min_x:.0f}, {max_x:.0f}]  Y: [{min_y:.0f}, {max_y:.0f}]  Z: [{min_z:.0f}, {max_z:.0f}]")
        log.info(f"  Total systems: {fmt_num(total_systems)}")
        cur.execute("""
            INSERT INTO app_meta (key, value, updated_at) VALUES
                ('grid_min_x', %s, NOW()), ('grid_max_x', %s, NOW()),
                ('grid_min_y', %s, NOW()), ('grid_max_y', %s, NOW()),
                ('grid_min_z', %s, NOW()), ('grid_max_z', %s, NOW()),
                ('grid_total_systems', %s, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
        """, (str(min_x), str(max_x), str(min_y), str(max_y),
              str(min_z), str(max_z), str(total_systems)))
        conn.commit()
        log.info(f"  Bounds cached in app_meta — future runs skip this stage ✓")

    x_cells = math.ceil((max_x - min_x) / cell_size)
    y_cells = math.ceil((max_y - min_y) / cell_size)
    z_cells = math.ceil((max_z - min_z) / cell_size)
    log.info(f"  Grid dimensions: {x_cells} x {y_cells} x {z_cells} = {fmt_num(x_cells*y_cells*z_cells)} max cells")

    if _shutdown:
        log.warning("Shutdown requested. Exiting after Stage 1.")
        sys.exit(0)

    # =========================================================================
    # STAGE 2: Populate spatial_grid
    # =========================================================================
    cur.execute("SELECT COUNT(*) FROM spatial_grid")
    existing_cells = cur.fetchone()[0]

    if existing_cells > 0:
        cell_count = existing_cells
        stage_banner(log, 2, 5, "Populate spatial_grid", resumed=True)
        log.info(f"  Already have {fmt_num(cell_count)} cells — skipping INSERT ✓")
    else:
        stage_banner(log, 2, 5, "Populate spatial_grid")
        log.info(f"  GROUP BY all {fmt_num(total_systems)} systems into {cell_size}ly cubes ...")
        log.info(f"  This query takes 5-15 minutes (parallel seq scan + group) ...")
        crash_hint(log, "from Stage 2 (cells will be created on next run)")
        t0 = time.time()
        cur.execute(f"""
            INSERT INTO spatial_grid (cell_id, cell_x, cell_y, cell_z,
                                       min_x, max_x, min_y, max_y, min_z, max_z,
                                       system_count)
            WITH cells AS (
                SELECT
                    floor((x - {min_x}) / {cell_size})::bigint AS cx,
                    floor((y - {min_y}) / {cell_size})::bigint AS cy,
                    floor((z - {min_z}) / {cell_size})::bigint AS cz,
                    COUNT(*) AS cnt
                FROM systems
                GROUP BY
                    floor((x - {min_x}) / {cell_size}),
                    floor((y - {min_y}) / {cell_size}),
                    floor((z - {min_z}) / {cell_size})
            )
            SELECT
                (cx * 100000000 + cy * 10000 + cz) AS cell_id,
                cx::smallint, cy::smallint, cz::smallint,
                cx * {cell_size} + {min_x},
                cx * {cell_size} + {min_x} + {cell_size},
                cy * {cell_size} + {min_y},
                cy * {cell_size} + {min_y} + {cell_size},
                cz * {cell_size} + {min_z},
                cz * {cell_size} + {min_z} + {cell_size},
                cnt
            FROM cells
            ON CONFLICT (cell_x, cell_y, cell_z) DO UPDATE SET
                system_count = EXCLUDED.system_count
        """)
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM spatial_grid")
        cell_count = cur.fetchone()[0]
        log.info(f"  Created {fmt_num(cell_count)} occupied grid cells in {fmt_duration(time.time()-t0)} ✓")

    if _shutdown:
        log.warning("Shutdown requested. Exiting after Stage 2.")
        sys.exit(0)

    # =========================================================================
    # STAGE 3: Assign grid_cell_id to every system
    # =========================================================================
    # Count how many are already done
    cur.execute("SELECT COUNT(*) FROM systems WHERE grid_cell_id IS NOT NULL")
    already_assigned = cur.fetchone()[0]
    resumed = already_assigned > 0

    if already_assigned >= total_systems:
        stage_banner(log, 3, 5, "Assign grid_cell_id", resumed=True)
        log.info(f"  All {fmt_num(total_systems)} systems already assigned — skipping ✓")
    else:
        stage_banner(log, 3, 5, "Assign grid_cell_id", resumed=resumed)
        log.info(f"  Total systems    : {fmt_num(total_systems)}")
        log.info(f"  Already assigned : {fmt_num(already_assigned)}  ({fmt_pct(already_assigned, total_systems)})")
        log.info(f"  Remaining        : {fmt_num(total_systems - already_assigned)}")
        log.info(f"  Strategy         : one UPDATE per grid cell, commit every 200 cells")
        log.info(f"  Keepalives       : enabled (prevents TCP timeout crashes)")
        crash_hint(log, "from the last committed cell automatically")

        # Check if coord index exists
        cur.execute("""
            SELECT COUNT(*) FROM pg_indexes
            WHERE tablename = 'systems' AND indexname = 'idx_sys_coords'
        """)
        has_idx = cur.fetchone()[0] > 0
        if has_idx:
            log.info(f"  idx_sys_coords   : EXISTS ✓  (each cell UPDATE uses index scan, not seq scan)")
        else:
            log.warning(f"  idx_sys_coords   : MISSING — each UPDATE is a full seq scan, will be very slow")
            log.warning(f"  Fix: CREATE INDEX CONCURRENTLY idx_sys_coords ON systems(x,y,z);")

        # How many cells still have unassigned systems?
        # We'll discover this as we go — the UPDATE WHERE grid_cell_id IS NULL skips done cells.

        ASSIGN_BATCH = 200   # commit every 200 cells (~280k systems per commit)
        progress = ProgressReporter(log, cell_count, "cell-assign", interval=20, heartbeat=90)
        assigned_cells   = 0
        skipped_cells    = 0   # cells where all systems already assigned
        total_rows_updated = 0

        # Use a server-side cursor so we don't pull all 135k cell rows into RAM at once.
        # We need a SEPARATE connection for the streaming read cursor because psycopg2
        # doesn't support mixing server-side cursors with DML on the same connection.
        read_conn = _connect_with_retry(DB_DSN, label="cell-reader")
        read_conn.set_session(readonly=True)

        with read_conn.cursor(name='cell_stream') as cell_cur:
            cell_cur.itersize = 2000   # fetch 2000 cells at a time from server
            cell_cur.execute("""
                SELECT cell_id, cell_x, cell_y, cell_z,
                       min_x, max_x, min_y, max_y, min_z, max_z
                FROM spatial_grid
                ORDER BY cell_id
            """)

            # Use a dedicated write connection for the UPDATEs so we can reconnect
            # if the write connection drops without losing the read cursor position.
            write_conn = _connect_with_retry(DB_DSN, label="cell-writer")
            write_cur  = write_conn.cursor()

            try:
                while True:
                    if _shutdown:
                        log.warning(f"  Shutdown mid-assignment — committing and exiting.")
                        write_conn.commit()
                        break

                    # Fetch next batch of cells from server-side cursor
                    cell_rows = cell_cur.fetchmany(2000)
                    if not cell_rows:
                        log.info(f"  All {fmt_num(cell_count)} cells processed ✓")
                        break

                    for cell in cell_rows:
                        if _shutdown:
                            break

                        cell_id, cx, cy, cz, bx0, bx1, by0, by1, bz0, bz1 = cell

                        # The WHERE includes grid_cell_id IS NULL — so already-assigned
                        # systems are skipped automatically (they're a no-op at DB level).
                        # This makes re-runs truly resume without re-doing finished work.
                        for attempt in range(2):
                            try:
                                write_cur.execute("""
                                    UPDATE systems
                                    SET grid_cell_id = %s
                                    WHERE x >= %s AND x < %s
                                      AND y >= %s AND y < %s
                                      AND z >= %s AND z < %s
                                      AND grid_cell_id IS NULL
                                """, (cell_id, bx0, bx1, by0, by1, bz0, bz1))
                                rows_updated = write_cur.rowcount
                                total_rows_updated += rows_updated
                                if rows_updated == 0:
                                    skipped_cells += 1
                                break   # success
                            except psycopg2.OperationalError as e:
                                if attempt == 0:
                                    log.warning(f"  DB connection lost on cell {cell_id} — reconnecting ...")
                                    try:
                                        write_cur.close()
                                        write_conn.close()
                                    except Exception:
                                        pass
                                    time.sleep(5)
                                    write_conn = _connect_with_retry(DB_DSN, label="cell-writer-retry")
                                    write_cur  = write_conn.cursor()
                                    log.info(f"  Reconnected ✓ — retrying cell {cell_id}")
                                else:
                                    log.error(f"  Skipping cell {cell_id} after retry: {e}")
                                    skipped_cells += 1

                        assigned_cells += 1

                        # Commit every ASSIGN_BATCH cells
                        if assigned_cells % ASSIGN_BATCH == 0:
                            write_conn.commit()
                            progress.update(ASSIGN_BATCH)

                # Final commit for remainder
                write_conn.commit()
                remainder = assigned_cells % ASSIGN_BATCH
                if remainder:
                    progress.update(remainder)

            finally:
                progress.finish()
                write_cur.close()
                write_conn.close()

        read_conn.close()

        # Reconnect main conn (may have timed out during long Stage 3)
        try:
            cur.close()
            conn.close()
        except Exception:
            pass
        conn = _connect_with_retry(DB_DSN, label="post-stage3")
        cur  = conn.cursor()

        # Verify assignment completeness
        cur.execute("SELECT COUNT(*) FROM systems WHERE grid_cell_id IS NULL")
        unassigned = cur.fetchone()[0]
        if unassigned > 0:
            log.warning(f"  {fmt_num(unassigned)} systems still have no grid cell")
            log.warning(f"  Re-run this script to continue — it will resume automatically")
        else:
            log.info(f"  All {fmt_num(total_systems)} systems assigned ✓")

        log.info(f"  Cells processed    : {fmt_num(assigned_cells)}")
        log.info(f"  Cells already done : {fmt_num(skipped_cells)}")
        log.info(f"  Rows updated       : {fmt_num(total_rows_updated)}")

    if _shutdown:
        log.warning("Shutdown requested. Exiting after Stage 3.")
        sys.exit(0)

    # =========================================================================
    # STAGE 4: Update visited_count per cell
    # =========================================================================
    stage_banner(log, 4, 5, "Update visited_count")
    log.info(f"  Aggregating {fmt_num(total_systems)} systems by grid_cell_id ...")
    log.info(f"  (Reads 73M scanned systems, writes to {fmt_num(cell_count)} cells — safe single query)")
    t0 = time.time()
    cur.execute("""
        UPDATE spatial_grid g
        SET visited_count = v.cnt
        FROM (
            SELECT grid_cell_id, COUNT(*) AS cnt
            FROM systems
            WHERE has_body_data = TRUE AND grid_cell_id IS NOT NULL
            GROUP BY grid_cell_id
        ) v
        WHERE g.cell_id = v.grid_cell_id
    """)
    conn.commit()
    log.info(f"  Visited counts updated in {fmt_duration(time.time()-t0)} ✓")

    # =========================================================================
    # STAGE 5: Save parameters to app_meta
    # =========================================================================
    stage_banner(log, 5, 5, "Save parameters to app_meta")
    cur.execute("""
        INSERT INTO app_meta (key, value, updated_at)
        VALUES ('grid_cell_size', %s, NOW()),
               ('grid_min_x',    %s, NOW()),
               ('grid_min_y',    %s, NOW()),
               ('grid_min_z',    %s, NOW()),
               ('grid_built',    'true', NOW())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
    """, (str(cell_size), str(min_x), str(min_y), str(min_z)))
    conn.commit()
    log.info(f"  grid_built = true ✓")

    # Distribution stats
    cur.execute("""
        SELECT MIN(system_count), MAX(system_count),
               AVG(system_count)::int,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY system_count)::int AS median
        FROM spatial_grid WHERE system_count > 0
    """)
    r = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM spatial_grid WHERE visited_count > 0")
    visited_cells = cur.fetchone()[0]

    cur.close()
    conn.close()

    total_elapsed = time.time() - script_start
    done_banner(log, "Spatial Grid Complete", total_elapsed, [
        f"Cells created   : {fmt_num(cell_count)}",
        f"Cells with scans: {fmt_num(visited_cells)}",
        f"Systems assigned: {fmt_num(total_systems)}",
        f"Systems per cell: min={r[0]}  max={r[1]}  avg={r[2]}  median={r[3]}",
    ])
    log.info("Next step: python3 build_clusters.py --workers 4")


if __name__ == '__main__':
    main()
