#!/usr/bin/env python3
"""
ED Finder — Cluster Summary Builder
Version: 3.1

Strategy:
  • Pure SQL Aggregation: The entire computation runs inside PostgreSQL.
  • No Python iteration over anchors — the DB engine does the spatial JOIN.
  • For each anchor (body-data system), finds all viable systems within 500 ly
    using the grid_cell_id index, then aggregates per economy type.
  • Processes in batches of grid cells to keep memory and transaction size bounded.
  • Default Quality: Score 65+ (Focuses on Terraformables and ELWs).

Why this is fast:
  • The old approach: 73M Python→DB round-trips (6/s = 3,255 hours).
  • This approach: ~125K grid-cell batches processed entirely inside the DB.
    Each batch is a single SQL statement using existing indexes.
    Expected ETA: 2-8 hours total.
"""

import os
import sys
import math
import time
import logging
import argparse

import psycopg2
import psycopg2.extras

from progress import (
    ProgressReporter,
    startup_banner, done_banner,
    fmt_num, fmt_duration,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATABASE_URL   = os.getenv('DATABASE_URL', 'postgresql://edfinder:edfinder@postgres:5432/edfinder')
LOG_LEVEL      = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE       = os.getenv('LOG_FILE', '/tmp/build_clusters.log')
DEFAULT_RADIUS = 500   # LY
DEFAULT_SCORE  = 65    # Focus on high-quality systems (Terraformables/ELWs)

os.makedirs(os.path.dirname(os.path.abspath(LOG_FILE)), exist_ok=True)
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger('build_clusters')

# ---------------------------------------------------------------------------
# SQL: Core aggregation query
# ---------------------------------------------------------------------------
# For a given set of anchor grid cells, this query:
#   1. Finds all anchors (body-data, unpopulated) in those cells.
#   2. For each anchor, finds viable systems within radius using the grid index.
#   3. Aggregates counts, best scores, and top system IDs per economy type.
#   4. Computes total_viable and economy_diversity.
#
# The coverage_score is computed in Python after the fact (it needs the
# weighted formula), but everything else is done in SQL.
#
# Note: distance_ly and in_bounding_box are SQL functions already defined
# in the database (003_functions.sql).

AGGREGATE_SQL = """
WITH viable AS (
    -- All viable systems (score >= threshold) in the search area
    SELECT
        s.id64, s.x, s.y, s.z, s.grid_cell_id,
        r.score_agriculture, r.score_refinery, r.score_industrial,
        r.score_hightech, r.score_military, r.score_tourism
    FROM systems s
    JOIN ratings r ON r.system_id64 = s.id64
    WHERE s.grid_cell_id = ANY(%(search_cells)s)
      AND (r.score_agriculture >= %(min_score)s OR r.score_refinery >= %(min_score)s OR
           r.score_industrial  >= %(min_score)s OR r.score_hightech  >= %(min_score)s OR
           r.score_military    >= %(min_score)s OR r.score_tourism   >= %(min_score)s)
),
anchors AS (
    -- All potential cluster centres in the anchor cells
    SELECT id64, x, y, z, grid_cell_id
    FROM systems
    WHERE has_body_data = TRUE
      AND grid_cell_id = ANY(%(anchor_cells)s)
),
pairs AS (
    -- Cross-join anchors with viable systems that are within radius
    SELECT
        a.id64  AS anchor_id,
        v.id64  AS viable_id,
        v.score_agriculture,
        v.score_refinery,
        v.score_industrial,
        v.score_hightech,
        v.score_military,
        v.score_tourism
    FROM anchors a
    JOIN viable v ON v.id64 <> a.id64
                  AND in_bounding_box(v.x, v.y, v.z, a.x, a.y, a.z, %(radius)s)
                  AND distance_ly(v.x, v.y, v.z, a.x, a.y, a.z) <= %(radius)s
),
agg AS (
    SELECT
        anchor_id                                                           AS system_id64,
        COUNT(*) FILTER (WHERE score_agriculture >= %(min_score)s)         AS agriculture_count,
        MAX(score_agriculture) FILTER (WHERE score_agriculture >= %(min_score)s) AS agriculture_best,
        COUNT(*) FILTER (WHERE score_refinery    >= %(min_score)s)         AS refinery_count,
        MAX(score_refinery)    FILTER (WHERE score_refinery    >= %(min_score)s) AS refinery_best,
        COUNT(*) FILTER (WHERE score_industrial  >= %(min_score)s)         AS industrial_count,
        MAX(score_industrial)  FILTER (WHERE score_industrial  >= %(min_score)s) AS industrial_best,
        COUNT(*) FILTER (WHERE score_hightech    >= %(min_score)s)         AS hightech_count,
        MAX(score_hightech)    FILTER (WHERE score_hightech    >= %(min_score)s) AS hightech_best,
        COUNT(*) FILTER (WHERE score_military    >= %(min_score)s)         AS military_count,
        MAX(score_military)    FILTER (WHERE score_military    >= %(min_score)s) AS military_best,
        COUNT(*) FILTER (WHERE score_tourism     >= %(min_score)s)         AS tourism_count,
        MAX(score_tourism)     FILTER (WHERE score_tourism     >= %(min_score)s) AS tourism_best,
        COUNT(*)                                                            AS total_viable
    FROM pairs
    GROUP BY anchor_id
    HAVING COUNT(*) > 0
),
top_ids AS (
    -- For each anchor+economy, find the system_id64 with the best score
    SELECT DISTINCT ON (anchor_id, economy)
        anchor_id,
        economy,
        viable_id AS top_id
    FROM (
        SELECT anchor_id, viable_id, 'Agriculture' AS economy, score_agriculture AS sc FROM pairs WHERE score_agriculture >= %(min_score)s
        UNION ALL
        SELECT anchor_id, viable_id, 'Refinery',   score_refinery   FROM pairs WHERE score_refinery   >= %(min_score)s
        UNION ALL
        SELECT anchor_id, viable_id, 'Industrial',  score_industrial  FROM pairs WHERE score_industrial  >= %(min_score)s
        UNION ALL
        SELECT anchor_id, viable_id, 'HighTech',    score_hightech    FROM pairs WHERE score_hightech    >= %(min_score)s
        UNION ALL
        SELECT anchor_id, viable_id, 'Military',    score_military    FROM pairs WHERE score_military    >= %(min_score)s
        UNION ALL
        SELECT anchor_id, viable_id, 'Tourism',     score_tourism     FROM pairs WHERE score_tourism     >= %(min_score)s
    ) sub
    ORDER BY anchor_id, economy, sc DESC
)
SELECT
    agg.system_id64,
    agg.agriculture_count,  agg.agriculture_best,
        (SELECT top_id FROM top_ids WHERE anchor_id = agg.system_id64 AND economy = 'Agriculture' LIMIT 1) AS agriculture_top_id,
    agg.refinery_count,     agg.refinery_best,
        (SELECT top_id FROM top_ids WHERE anchor_id = agg.system_id64 AND economy = 'Refinery'    LIMIT 1) AS refinery_top_id,
    agg.industrial_count,   agg.industrial_best,
        (SELECT top_id FROM top_ids WHERE anchor_id = agg.system_id64 AND economy = 'Industrial'  LIMIT 1) AS industrial_top_id,
    agg.hightech_count,     agg.hightech_best,
        (SELECT top_id FROM top_ids WHERE anchor_id = agg.system_id64 AND economy = 'HighTech'    LIMIT 1) AS hightech_top_id,
    agg.military_count,     agg.military_best,
        (SELECT top_id FROM top_ids WHERE anchor_id = agg.system_id64 AND economy = 'Military'    LIMIT 1) AS military_top_id,
    agg.tourism_count,      agg.tourism_best,
        (SELECT top_id FROM top_ids WHERE anchor_id = agg.system_id64 AND economy = 'Tourism'     LIMIT 1) AS tourism_top_id,
    agg.total_viable
FROM agg
"""

# ---------------------------------------------------------------------------
# Coverage score (Python side — same formula as before)
# ---------------------------------------------------------------------------
def compute_coverage_score(row: dict) -> float:
    weights = {
        'Agriculture': 0.25, 'Refinery': 0.20, 'Industrial': 0.20,
        'HighTech': 0.20, 'Military': 0.10, 'Tourism': 0.05,
    }
    score = 0.0
    for eco, weight in weights.items():
        best  = row.get(f'{eco.lower()}_best') or 0
        count = row.get(f'{eco.lower()}_count') or 0
        if best > 0:
            count_bonus = min(count / 3.0, 1.0) * 0.1
            score += (best / 100.0 + count_bonus) * weight
    return round(min(score * 100, 100.0), 1)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='Build cluster_summary (v3.1 - Pure SQL)')
    parser.add_argument('--radius',    type=float, default=DEFAULT_RADIUS)
    parser.add_argument('--min-score', type=int,   default=DEFAULT_SCORE)
    parser.add_argument('--dirty-only', action='store_true',
                        help='Only rebuild clusters for dirty anchors')
    args = parser.parse_args()

    script_start = time.time()
    startup_banner(log, "Cluster Summary Builder", "3.1 (Pure SQL)")

    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
    except Exception as e:
        log.error(f"FATAL: Cannot connect to database: {e}")
        sys.exit(1)

    cur = conn.cursor()

    # ------------------------------------------------------------------
    # Step 1: Load grid metadata
    # ------------------------------------------------------------------
    cur.execute("SELECT key, value FROM app_meta WHERE key IN ('grid_cell_size','grid_min_x','grid_min_y','grid_min_z')")
    meta = {r[0]: float(r[1]) for r in cur.fetchall()}
    cell_size = meta.get('grid_cell_size', 500.0)
    gmin_x    = meta.get('grid_min_x', 0.0)
    gmin_y    = meta.get('grid_min_y', 0.0)
    gmin_z    = meta.get('grid_min_z', 0.0)
    log.info(f"  Grid: cell_size={cell_size} ly, origin=({gmin_x}, {gmin_y}, {gmin_z})")

    # ------------------------------------------------------------------
    # Step 2: Find all grid cells that contain at least one viable system
    # ------------------------------------------------------------------
    log.info("  Finding viable grid cells...")
    if args.dirty_only:
        cur.execute("""
            SELECT DISTINCT s.grid_cell_id
            FROM systems s
            JOIN ratings r ON r.system_id64 = s.id64
            WHERE s.cluster_dirty = TRUE
              AND (r.score_agriculture >= %s OR r.score_refinery >= %s OR
                   r.score_industrial  >= %s OR r.score_hightech  >= %s OR
                   r.score_military    >= %s OR r.score_tourism   >= %s)
        """, (args.min_score,) * 6)
    else:
        cur.execute("""
            SELECT DISTINCT s.grid_cell_id
            FROM systems s
            JOIN ratings r ON r.system_id64 = s.id64
            WHERE (r.score_agriculture >= %s OR r.score_refinery >= %s OR
                   r.score_industrial  >= %s OR r.score_hightech  >= %s OR
                   r.score_military    >= %s OR r.score_tourism   >= %s)
        """, (args.min_score,) * 6)

    viable_cells = [row[0] for row in cur.fetchall()]
    if not viable_cells:
        log.warning("No viable systems found. Are ratings built? Exiting.")
        sys.exit(0)
    log.info(f"  Found {fmt_num(len(viable_cells))} viable grid cells.")

    # ------------------------------------------------------------------
    # Step 3: Process one viable cell at a time
    #
    # For each viable cell C, the search area is C and its 26 neighbours.
    # We only look for anchors in C itself (not the neighbours), to avoid
    # double-counting. Viable systems from all 27 cells are included in
    # the neighbour search.
    #
    # This gives us ~125K batches, each running a fast SQL aggregation.
    # ------------------------------------------------------------------
    total_cells    = len(viable_cells)
    total_written  = 0
    progress       = ProgressReporter(log, total=total_cells, label="cells", interval=30)

    for idx, anchor_cell in enumerate(viable_cells):
        # Compute the 27-cell neighbourhood (anchor cell + 26 neighbours)
        vcz = anchor_cell % 10000
        rem = anchor_cell // 10000
        vcy = rem % 10000
        vcx = rem // 10000

        search_cells = []
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                for dz in range(-1, 2):
                    search_cells.append(
                        (vcx + dx) * 100_000_000 + (vcy + dy) * 10_000 + (vcz + dz)
                    )

        params = {
            'anchor_cells': [anchor_cell],
            'search_cells': search_cells,
            'radius':       args.radius,
            'min_score':    args.min_score,
        }

        try:
            cur.execute(AGGREGATE_SQL, params)
            rows = cur.fetchall()
        except Exception as e:
            log.warning(f"  Cell {anchor_cell} query failed: {e} — skipping")
            conn.rollback()
            progress.update(1)
            continue

        if rows:
            cols = [d[0] for d in cur.description]
            write_batch = []
            for row in rows:
                rd = dict(zip(cols, row))
                coverage  = compute_coverage_score(rd)
                diversity = sum(1 for eco in ('agriculture','refinery','industrial','hightech','military','tourism')
                                if (rd.get(f'{eco}_count') or 0) > 0)
                write_batch.append((
                    rd['system_id64'],
                    rd['agriculture_count'], rd['agriculture_best'], rd['agriculture_top_id'],
                    rd['refinery_count'],    rd['refinery_best'],    rd['refinery_top_id'],
                    rd['industrial_count'],  rd['industrial_best'],  rd['industrial_top_id'],
                    rd['hightech_count'],    rd['hightech_best'],    rd['hightech_top_id'],
                    rd['military_count'],    rd['military_best'],    rd['military_top_id'],
                    rd['tourism_count'],     rd['tourism_best'],     rd['tourism_top_id'],
                    rd['total_viable'],      coverage,               diversity,
                    args.radius,
                ))

            psycopg2.extras.execute_values(cur, """
                INSERT INTO cluster_summary (
                    system_id64,
                    agriculture_count, agriculture_best, agriculture_top_id,
                    refinery_count,    refinery_best,    refinery_top_id,
                    industrial_count,  industrial_best,  industrial_top_id,
                    hightech_count,    hightech_best,    hightech_top_id,
                    military_count,    military_best,    military_top_id,
                    tourism_count,     tourism_best,     tourism_top_id,
                    total_viable, coverage_score, economy_diversity,
                    search_radius, dirty, computed_at, updated_at
                ) VALUES %s
                ON CONFLICT (system_id64) DO UPDATE SET
                    agriculture_count  = EXCLUDED.agriculture_count,
                    agriculture_best   = EXCLUDED.agriculture_best,
                    agriculture_top_id = EXCLUDED.agriculture_top_id,
                    refinery_count     = EXCLUDED.refinery_count,
                    refinery_best      = EXCLUDED.refinery_best,
                    refinery_top_id    = EXCLUDED.refinery_top_id,
                    industrial_count   = EXCLUDED.industrial_count,
                    industrial_best    = EXCLUDED.industrial_best,
                    industrial_top_id  = EXCLUDED.industrial_top_id,
                    hightech_count     = EXCLUDED.hightech_count,
                    hightech_best      = EXCLUDED.hightech_best,
                    hightech_top_id    = EXCLUDED.hightech_top_id,
                    military_count     = EXCLUDED.military_count,
                    military_best      = EXCLUDED.military_best,
                    military_top_id    = EXCLUDED.military_top_id,
                    tourism_count      = EXCLUDED.tourism_count,
                    tourism_best       = EXCLUDED.tourism_best,
                    tourism_top_id     = EXCLUDED.tourism_top_id,
                    total_viable       = EXCLUDED.total_viable,
                    coverage_score     = EXCLUDED.coverage_score,
                    economy_diversity  = EXCLUDED.economy_diversity,
                    dirty              = FALSE,
                    updated_at         = NOW()
            """, write_batch, template="""(%s,
                %s,%s,%s, %s,%s,%s, %s,%s,%s,
                %s,%s,%s, %s,%s,%s, %s,%s,%s,
                %s,%s,%s, %s, FALSE, NOW(), NOW())""", page_size=200)

            conn.commit()
            total_written += len(write_batch)

        # Clear dirty flags for anchors in this cell
        if args.dirty_only:
            cur.execute(
                "UPDATE systems SET cluster_dirty = FALSE WHERE grid_cell_id = %s AND has_body_data = TRUE",
                (anchor_cell,)
            )
            conn.commit()

        progress.update(1)

    # ------------------------------------------------------------------
    # Step 4: Mark build complete
    # ------------------------------------------------------------------
    cur.execute("""
        INSERT INTO app_meta (key, value, updated_at)
        VALUES ('clusters_built', 'true', NOW())
        ON CONFLICT (key) DO UPDATE SET value = 'true', updated_at = NOW()
    """)
    conn.commit()

    elapsed = time.time() - script_start
    done_banner(log, "Cluster Build Complete", elapsed, [
        f"Viable cells processed : {fmt_num(total_cells)}",
        f"Cluster rows written   : {fmt_num(total_written)}",
        f"Total time             : {fmt_duration(elapsed)}",
    ])

    cur.close()
    conn.close()


if __name__ == '__main__':
    main()
