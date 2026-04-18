#!/usr/bin/env python3
"""
ED Finder — Spatial Grid Builder
Version: 1.0

Divides the galaxy into 500ly cubic cells and assigns every system to a cell.
This is the key that makes cluster_summary build fast regardless of scale.

Instead of checking 70M systems against 70M systems (O(n²) = 4.9 × 10¹⁵ ops),
we only check systems within the same + adjacent cells (27 cells max).

Galaxy bounds (Elite Dangerous):
  X: -49985 to  65025 LY   (~115,000 LY wide)
  Y:  -6140 to   6050 LY   (~12,200 LY tall)
  Z: -24720 to  65420 LY   (~90,140 LY deep)

With 500ly cells:
  X cells: 230, Y cells: 25, Z cells: 181
  Total cells: ~1,040,500 (but most are empty)
  Expected occupied cells: ~50,000-100,000

Usage:
    python3 build_grid.py
    python3 build_grid.py --cell-size 500   # default
    python3 build_grid.py --cell-size 250   # finer grid (more cells, faster cluster search)
"""

import os
import sys
import time
import logging
import argparse

import psycopg2
import psycopg2.extras

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_DSN      = os.getenv('DATABASE_URL', 'postgresql://edfinder:edfinder@localhost:5432/edfinder')
BATCH_SIZE  = int(os.getenv('BATCH_SIZE', '10000'))
LOG_LEVEL   = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE    = os.getenv('LOG_FILE', '/data/logs/build_grid.log')
CELL_SIZE   = int(os.getenv('CELL_SIZE', '500'))  # LY per grid cell

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger('build_grid')


def main():
    parser = argparse.ArgumentParser(description='Build spatial grid for fast cluster queries')
    parser.add_argument('--cell-size', type=int, default=CELL_SIZE,
                        help=f'Grid cell size in LY (default: {CELL_SIZE})')
    args = parser.parse_args()
    cell_size = args.cell_size

    conn = psycopg2.connect(DB_DSN)
    conn.autocommit = False
    cur = conn.cursor()

    start = time.time()
    log.info(f"Building spatial grid with {cell_size}ly cells ...")

    # ---------------------------------------------------------------------------
    # Step 1: Compute galaxy bounds from actual system coordinates
    # ---------------------------------------------------------------------------
    log.info("Computing galaxy bounds ...")
    cur.execute("""
        SELECT
            MIN(x), MAX(x),
            MIN(y), MAX(y),
            MIN(z), MAX(z),
            COUNT(*)
        FROM systems
    """)
    row = cur.fetchone()
    min_x, max_x = row[0] - cell_size, row[1] + cell_size
    min_y, max_y = row[2] - cell_size, row[3] + cell_size
    min_z, max_z = row[4] - cell_size, row[5] + cell_size
    total_systems = row[6]

    log.info(f"Galaxy bounds: X[{min_x:.0f}, {max_x:.0f}] Y[{min_y:.0f}, {max_y:.0f}] Z[{min_z:.0f}, {max_z:.0f}]")
    log.info(f"Total systems: {total_systems:,}")

    import math
    x_cells = math.ceil((max_x - min_x) / cell_size)
    y_cells = math.ceil((max_y - min_y) / cell_size)
    z_cells = math.ceil((max_z - min_z) / cell_size)
    max_cells = x_cells * y_cells * z_cells
    log.info(f"Grid dimensions: {x_cells} × {y_cells} × {z_cells} = {max_cells:,} max cells")

    # ---------------------------------------------------------------------------
    # Step 2: Populate spatial_grid table with actual occupied cells
    # ---------------------------------------------------------------------------
    log.info("Identifying occupied grid cells ...")
    cur.execute("TRUNCATE TABLE spatial_grid CASCADE")

    # cell_id encoding: use large enough multipliers so no two distinct
    # (cell_x, cell_y, cell_z) triples can hash to the same integer.
    # ED galaxy max extent with cell_size=500: x~230, y~25, z~181 cells.
    # Worst case with cell_size=50: x~2300, y~250, z~1810 cells.
    # Using multipliers 100000 * 100000 overflows INT; use BIGINT instead.
    # Formula: cell_x * Y_STRIDE * Z_STRIDE + cell_y * Z_STRIDE + cell_z
    # where strides are based on actual max cell counts + margin.
    cur.execute(f"""
        INSERT INTO spatial_grid (cell_id, cell_x, cell_y, cell_z,
                                   min_x, max_x, min_y, max_y, min_z, max_z,
                                   system_count)
        SELECT
            -- Collision-free encoding using safe strides.
            -- We cast to BIGINT before multiplying to avoid INT overflow.
            -- Strides: z up to 10000, y up to 10000.  Supports cell_size >= 12 LY.
            (floor((x - {min_x}) / {cell_size})::bigint * 100000000 +
             floor((y - {min_y}) / {cell_size})::bigint * 10000 +
             floor((z - {min_z}) / {cell_size})::bigint) AS cell_id,
            floor((x - {min_x}) / {cell_size})::smallint AS cell_x,
            floor((y - {min_y}) / {cell_size})::smallint AS cell_y,
            floor((z - {min_z}) / {cell_size})::smallint AS cell_z,
            floor((x - {min_x}) / {cell_size}) * {cell_size} + {min_x} AS min_x,
            floor((x - {min_x}) / {cell_size}) * {cell_size} + {min_x} + {cell_size} AS max_x,
            floor((y - {min_y}) / {cell_size}) * {cell_size} + {min_y} AS min_y,
            floor((y - {min_y}) / {cell_size}) * {cell_size} + {min_y} + {cell_size} AS max_y,
            floor((z - {min_z}) / {cell_size}) * {cell_size} + {min_z} AS min_z,
            floor((z - {min_z}) / {cell_size}) * {cell_size} + {min_z} + {cell_size} AS max_z,
            COUNT(*) AS system_count
        FROM systems
        GROUP BY cell_x, cell_y, cell_z, min_x, max_x, min_y, max_y, min_z, max_z
        ON CONFLICT (cell_x, cell_y, cell_z) DO UPDATE SET
            system_count = EXCLUDED.system_count
    """)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM spatial_grid")
    cell_count = cur.fetchone()[0]
    log.info(f"Created {cell_count:,} occupied grid cells")

    # ---------------------------------------------------------------------------
    # Step 3: Assign grid_cell_id to every system
    # ---------------------------------------------------------------------------
    log.info("Assigning grid cells to systems ...")
    cur.execute(f"""
        UPDATE systems s
        SET grid_cell_id = g.cell_id
        FROM spatial_grid g
        WHERE g.cell_x = floor((s.x - {min_x}) / {cell_size})::smallint
          AND g.cell_y = floor((s.y - {min_y}) / {cell_size})::smallint
          AND g.cell_z = floor((s.z - {min_z}) / {cell_size})::smallint
    """)
    conn.commit()

    # Verify assignment
    cur.execute("SELECT COUNT(*) FROM systems WHERE grid_cell_id IS NULL")
    unassigned = cur.fetchone()[0]
    if unassigned > 0:
        log.warning(f"{unassigned:,} systems could not be assigned to a grid cell")
    else:
        log.info("All systems assigned to grid cells ✓")

    # ---------------------------------------------------------------------------
    # Step 4: Update visited_count in spatial_grid
    # ---------------------------------------------------------------------------
    log.info("Updating visited counts per cell ...")
    cur.execute("""
        UPDATE spatial_grid g
        SET visited_count = v.cnt
        FROM (
            SELECT grid_cell_id, COUNT(*) AS cnt
            FROM systems
            WHERE has_body_data = TRUE
              AND grid_cell_id IS NOT NULL
            GROUP BY grid_cell_id
        ) v
        WHERE g.cell_id = v.grid_cell_id
    """)
    conn.commit()

    # ---------------------------------------------------------------------------
    # Step 5: Store cell_size in app_meta for cluster builder to use
    # ---------------------------------------------------------------------------
    cur.execute("""
        INSERT INTO app_meta (key, value, updated_at)
        VALUES ('grid_cell_size', %s, NOW()),
               ('grid_min_x', %s, NOW()),
               ('grid_min_y', %s, NOW()),
               ('grid_min_z', %s, NOW()),
               ('grid_built', 'true', NOW())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
    """, (str(cell_size), str(min_x), str(min_y), str(min_z)))
    conn.commit()

    elapsed = time.time() - start
    log.info(f"Spatial grid built in {elapsed/60:.1f} minutes")
    log.info(f"  Cells: {cell_count:,}")
    log.info(f"  Systems assigned: {total_systems:,}")

    # Show distribution stats
    cur.execute("""
        SELECT
            MIN(system_count), MAX(system_count),
            AVG(system_count)::int,
            percentile_cont(0.5) WITHIN GROUP (ORDER BY system_count)::int AS median
        FROM spatial_grid
        WHERE system_count > 0
    """)
    r = cur.fetchone()
    log.info(f"  Systems per cell: min={r[0]}, max={r[1]}, avg={r[2]}, median={r[3]}")

    cur.close()
    conn.close()
    log.info("Next step: python3 build_clusters.py")


if __name__ == '__main__':
    main()
