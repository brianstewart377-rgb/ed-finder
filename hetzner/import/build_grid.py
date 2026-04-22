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
LOG_FILE    = os.getenv('LOG_FILE', '/tmp/build_grid.log')
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


def _encode_cell_id(cell_x: int, cell_y: int, cell_z: int) -> int:
    """
    Encode (cell_x, cell_y, cell_z) indices into a single collision-free BIGINT.

    Strides:  z up to 10 000,  y up to 10 000.
    Formula:  cell_x * 100_000_000  +  cell_y * 10_000  +  cell_z

    Supports any galaxy with fewer than 10 000 cells on the y or z axis,
    which covers cell sizes down to ~12 LY.  The result always fits in a
    PostgreSQL BIGINT (< 2^63) for realistic galaxy extents.

    This mirrors the SQL expression in main() exactly so the test suite can
    verify collision-freedom without a database connection.
    """
    return cell_x * 100_000_000 + cell_y * 10_000 + cell_z


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
    # Step 1: Compute galaxy bounds
    # ---------------------------------------------------------------------------
    # Check if bounds were already stored from a previous run
    cur.execute("SELECT key, value FROM app_meta WHERE key IN ('grid_min_x','grid_min_y','grid_min_z','grid_max_x','grid_max_y','grid_max_z','grid_total_systems')")
    stored = {r[0]: r[1] for r in cur.fetchall()}

    if all(k in stored for k in ('grid_min_x','grid_min_y','grid_min_z','grid_max_x','grid_max_y','grid_max_z','grid_total_systems')):
        min_x = float(stored['grid_min_x'])
        min_y = float(stored['grid_min_y'])
        min_z = float(stored['grid_min_z'])
        max_x = float(stored['grid_max_x'])
        max_y = float(stored['grid_max_y'])
        max_z = float(stored['grid_max_z'])
        total_systems = int(stored['grid_total_systems'])
        log.info(f"Galaxy bounds (from app_meta): X[{min_x:.0f}, {max_x:.0f}] Y[{min_y:.0f}, {max_y:.0f}] Z[{min_z:.0f}, {max_z:.0f}]")
        log.info(f"Total systems: {total_systems:,}")
    else:
        log.info("Computing galaxy bounds (full seq scan — only needed once) ...")
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
        # Cache bounds in app_meta so resume skips the seq scan
        cur.execute("""
            INSERT INTO app_meta (key, value, updated_at) VALUES
                ('grid_min_x', %s, NOW()), ('grid_max_x', %s, NOW()),
                ('grid_min_y', %s, NOW()), ('grid_max_y', %s, NOW()),
                ('grid_min_z', %s, NOW()), ('grid_max_z', %s, NOW()),
                ('grid_total_systems', %s, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
        """, (str(min_x), str(max_x), str(min_y), str(max_y), str(min_z), str(max_z), str(total_systems)))
        conn.commit()

    import math
    x_cells = math.ceil((max_x - min_x) / cell_size)
    y_cells = math.ceil((max_y - min_y) / cell_size)
    z_cells = math.ceil((max_z - min_z) / cell_size)
    max_cells = x_cells * y_cells * z_cells
    log.info(f"Grid dimensions: {x_cells} × {y_cells} × {z_cells} = {max_cells:,} max cells")

    # ---------------------------------------------------------------------------
    # Step 2: Populate spatial_grid table with actual occupied cells
    # ---------------------------------------------------------------------------
    # Resume-safe: if spatial_grid already has the right number of cells from a
    # previous (crashed) run, skip the expensive GROUP BY scan and go straight
    # to Step 3 (system assignment).
    cur.execute("SELECT COUNT(*) FROM spatial_grid")
    existing_cells = cur.fetchone()[0]

    if existing_cells > 0:
        log.info(f"spatial_grid already has {existing_cells:,} cells — skipping Step 2 (resume mode)")
        cell_count = existing_cells
    else:
        log.info("Identifying occupied grid cells ...")
        # cell_id encoding: use large enough multipliers so no two distinct
        # (cell_x, cell_y, cell_z) triples can hash to the same integer.
        # Use a CTE so we GROUP BY the real floor() expressions (not SELECT
        # aliases, which PostgreSQL does not allow in GROUP BY).
        cur.execute(f"""
            INSERT INTO spatial_grid (cell_id, cell_x, cell_y, cell_z,
                                       min_x, max_x, min_y, max_y, min_z, max_z,
                                       system_count)
            WITH cells AS (
                SELECT
                    floor((x - {min_x}) / {cell_size})::bigint  AS cx,
                    floor((y - {min_y}) / {cell_size})::bigint  AS cy,
                    floor((z - {min_z}) / {cell_size})::bigint  AS cz,
                    COUNT(*) AS cnt
                FROM systems
                GROUP BY
                    floor((x - {min_x}) / {cell_size}),
                    floor((y - {min_y}) / {cell_size}),
                    floor((z - {min_z}) / {cell_size})
            )
            SELECT
                (cx * 100000000 + cy * 10000 + cz)  AS cell_id,
                cx::smallint                          AS cell_x,
                cy::smallint                          AS cell_y,
                cz::smallint                          AS cell_z,
                cx * {cell_size} + {min_x}            AS min_x,
                cx * {cell_size} + {min_x} + {cell_size} AS max_x,
                cy * {cell_size} + {min_y}            AS min_y,
                cy * {cell_size} + {min_y} + {cell_size} AS max_y,
                cz * {cell_size} + {min_z}            AS min_z,
                cz * {cell_size} + {min_z} + {cell_size} AS max_z,
                cnt                                   AS system_count
            FROM cells
            ON CONFLICT (cell_x, cell_y, cell_z) DO UPDATE SET
                system_count = EXCLUDED.system_count
        """)
        conn.commit()

        cur.execute("SELECT COUNT(*) FROM spatial_grid")
        cell_count = cur.fetchone()[0]
        log.info(f"Created {cell_count:,} occupied grid cells")

    # ---------------------------------------------------------------------------
    # Step 3: Assign grid_cell_id to every system — in per-cell batches
    # ---------------------------------------------------------------------------
    # A single UPDATE JOIN across 186M rows exhausts PostgreSQL's WAL / work_mem
    # and causes the server to close the connection.
    # Fix: iterate over each of the 135k grid cells and UPDATE only the systems
    # in that cell's bounding box.  Each batch touches ~1,400 rows on average
    # (186M / 135k cells) — well within safe transaction size.
    # Check how many systems already have grid_cell_id set (resume safety)
    cur.execute("SELECT COUNT(*) FROM systems WHERE grid_cell_id IS NOT NULL")
    already_assigned = cur.fetchone()[0]
    if already_assigned == total_systems:
        log.info(f"All {total_systems:,} systems already have grid_cell_id — skipping Step 3 (resume mode)")
    else:
        log.info(f"Assigning grid cells to systems in per-cell batches ({cell_count:,} cells) ...")
        if already_assigned > 0:
            log.info(f"  Resuming: {already_assigned:,} already assigned, continuing from where we left off ...")

    # Fetch all cells once — 135k rows is tiny
    cur.execute("""
        SELECT cell_id, cell_x, cell_y, cell_z, min_x, max_x, min_y, max_y, min_z, max_z
        FROM spatial_grid
        ORDER BY cell_id
    """)
    all_cells = cur.fetchall()

    ASSIGN_BATCH = 500          # commit every N cells (~700k systems per commit)
    assigned_cells = 0
    last_log = time.time()

    for i, cell in enumerate(all_cells):
        if already_assigned == total_systems:
            break   # all done — skip loop entirely
        cell_id, cx, cy, cz, bx0, bx1, by0, by1, bz0, bz1 = cell
        cur.execute("""
            UPDATE systems
            SET grid_cell_id = %s
            WHERE x >= %s AND x < %s
              AND y >= %s AND y < %s
              AND z >= %s AND z < %s
        """, (cell_id, bx0, bx1, by0, by1, bz0, bz1))
        assigned_cells += 1

        if assigned_cells % ASSIGN_BATCH == 0:
            conn.commit()
            if time.time() - last_log >= 30:
                pct = assigned_cells / cell_count * 100
                log.info(f"  Grid assignment: {assigned_cells:,} / {cell_count:,} cells ({pct:.1f}%) ...")
                last_log = time.time()

    conn.commit()   # final commit for remainder
    log.info(f"  Grid assignment complete: {assigned_cells:,} cells processed")

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
    # This aggregates 73M rows but only writes to 135k cells — safe as one query
    # since the result set (spatial_grid) is small even if the scan is large.
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
    log.info("Visited counts updated ✓")

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
