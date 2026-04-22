#!/usr/bin/env python3
"""
ED Finder — Spatial Grid Builder
Version: 1.3  (rich progress reporting, startup banner, fmt_pct)

Divides the galaxy into 500ly cubic cells and assigns every system to a cell.

STAGES:
  1. Galaxy bounds  — compute or load from cache (one-time seq scan)
  2. Cell INSERT    — GROUP BY all 186M systems into 500ly cubes
  3. Cell ASSIGN    — UPDATE every system with its grid_cell_id (batched, resume-safe)
  4. Visited count  — count scanned systems per cell
  5. Save meta      — write grid parameters to app_meta

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


def _encode_cell_id(cell_x: int, cell_y: int, cell_z: int) -> int:
    return cell_x * 100_000_000 + cell_y * 10_000 + cell_z


def main():
    parser = argparse.ArgumentParser(description='Build spatial grid for fast cluster queries')
    parser.add_argument('--cell-size', type=int, default=CELL_SIZE,
                        help=f'Grid cell size in LY (default: {CELL_SIZE})')
    args = parser.parse_args()
    cell_size = args.cell_size

    script_start = time.time()

    startup_banner(log, "Spatial Grid Builder", "v1.3", [
        ("Cell size", f"{cell_size} LY"),
        ("Log file",  LOG_FILE),
        ("DB",        DB_DSN.split('@')[-1]),
    ])

    try:
        conn = psycopg2.connect(DB_DSN)
    except Exception as e:
        log.error(f"FATAL: Cannot connect to database: {e}")
        sys.exit(1)

    conn.autocommit = False
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
        log.info(f"  Loaded from cache (skipping seq scan)")
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
        log.info(f"  Bounds cached in app_meta — future runs skip this stage")

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
        log.info(f"  Already have {fmt_num(cell_count)} cells — skipping INSERT")
    else:
        stage_banner(log, 2, 5, "Populate spatial_grid")
        log.info(f"  GROUP BY all {fmt_num(total_systems)} systems into {cell_size}ly cubes ...")
        log.info(f"  This query takes 5-15 minutes (parallel seq scan + group) ...")
        crash_hint(log, "from Stage 2")
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
        log.info(f"  Created {fmt_num(cell_count)} occupied grid cells in {fmt_duration(time.time()-t0)}")

    if _shutdown:
        log.warning("Shutdown requested. Exiting after Stage 2.")
        sys.exit(0)

    # =========================================================================
    # STAGE 3: Assign grid_cell_id to every system (batched, resume-safe)
    # =========================================================================
    cur.execute("SELECT COUNT(*) FROM systems WHERE grid_cell_id IS NOT NULL")
    already_assigned = cur.fetchone()[0]
    resumed = already_assigned > 0 and already_assigned < total_systems

    if already_assigned >= total_systems:
        stage_banner(log, 3, 5, "Assign grid_cell_id", resumed=True)
        log.info(f"  All {fmt_num(total_systems)} systems already assigned — skipping")
    else:
        stage_banner(log, 3, 5, "Assign grid_cell_id", resumed=resumed)
        remaining_pct = (total_systems - already_assigned) / total_systems * 100
        log.info(f"  Systems to assign : {fmt_num(total_systems - already_assigned)} ({remaining_pct:.1f}%)")
        log.info(f"  Already assigned  : {fmt_num(already_assigned)}")
        log.info(f"  Method            : {fmt_num(cell_count)} individual cell UPDATEs, {500} cells per commit")
        log.info(f"  Index             : idx_sys_coords must exist for speed (check below)")
        crash_hint(log, "system assignment")

        # Check if coord index exists
        cur.execute("""
            SELECT COUNT(*) FROM pg_indexes
            WHERE tablename = 'systems' AND indexname = 'idx_sys_coords'
        """)
        has_idx = cur.fetchone()[0] > 0
        if has_idx:
            log.info(f"  idx_sys_coords    : EXISTS ✓ (each cell UPDATE will be fast)")
        else:
            log.warning(f"  idx_sys_coords    : MISSING — each UPDATE is a seq scan, will be SLOW")
            log.warning(f"  Run in parallel: CREATE INDEX CONCURRENTLY idx_sys_coords ON systems(x,y,z);")

        cur.execute("""
            SELECT cell_id, cell_x, cell_y, cell_z,
                   min_x, max_x, min_y, max_y, min_z, max_z
            FROM spatial_grid ORDER BY cell_id
        """)
        all_cells = cur.fetchall()

        ASSIGN_BATCH = 500
        progress = ProgressReporter(log, cell_count, "cell-assign", interval=30, heartbeat=120)
        assigned_cells = 0

        for cell in all_cells:
            if _shutdown:
                log.warning(f"Shutdown requested mid-assignment. {fmt_num(assigned_cells)} cells done.")
                conn.commit()
                sys.exit(0)

            if already_assigned >= total_systems:
                break

            cell_id, cx, cy, cz, bx0, bx1, by0, by1, bz0, bz1 = cell
            cur.execute("""
                UPDATE systems SET grid_cell_id = %s
                WHERE x >= %s AND x < %s
                  AND y >= %s AND y < %s
                  AND z >= %s AND z < %s
            """, (cell_id, bx0, bx1, by0, by1, bz0, bz1))
            assigned_cells += 1

            if assigned_cells % ASSIGN_BATCH == 0:
                conn.commit()
                progress.update(ASSIGN_BATCH)

        conn.commit()
        progress.update(assigned_cells % ASSIGN_BATCH)
        progress.finish()

        cur.execute("SELECT COUNT(*) FROM systems WHERE grid_cell_id IS NULL")
        unassigned = cur.fetchone()[0]
        if unassigned > 0:
            log.warning(f"  WARNING: {fmt_num(unassigned)} systems have no grid cell assigned")
            log.warning(f"  These are likely outside the computed galaxy bounds — investigate if > 1000")
        else:
            log.info(f"  All {fmt_num(total_systems)} systems assigned ✓")

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
