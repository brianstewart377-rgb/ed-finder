#!/usr/bin/env python3
"""
ED Finder — Cluster Summary Builder
Version: 3.3

Strategy:
  • Pure SQL Aggregation per grid cell, parallelised across N workers.
  • No Python iteration over anchors — the DB engine does the spatial JOIN.
  • Each worker picks up one viable grid cell at a time from a shared queue,
    runs the SQL aggregation for that cell, and writes results.
  • Default Quality: Score 65+ (Focuses on Terraformables and ELWs).

Performance:
  • v2.9: 73M Python→DB round-trips  → 3,255 h ETA
  • v3.1: 125K SQL aggregations (1 thread) → 8–14 h ETA
  • v3.2: 125K SQL aggregations (6 threads) → 1.5–3 h ETA
  • v3.3: Adds statement_timeout + anchor-count pre-check to skip pathological
          dense cells (Sol/core) that would otherwise stall for hours.
"""

import os
import sys
import time
import logging
import argparse
import multiprocessing as mp
from multiprocessing import Queue, Value
import ctypes

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
# SQL: Core aggregation query (runs entirely inside PostgreSQL)
# ---------------------------------------------------------------------------
AGGREGATE_SQL = """
WITH viable AS (
    SELECT
        s.id64, s.x, s.y, s.z,
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
    SELECT id64, x, y, z
    FROM systems
    WHERE has_body_data = TRUE
      AND grid_cell_id = %(anchor_cell)s
),
pairs AS (
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
        anchor_id                                                                AS system_id64,
        COUNT(*) FILTER (WHERE score_agriculture >= %(min_score)s)              AS agriculture_count,
        MAX(score_agriculture) FILTER (WHERE score_agriculture >= %(min_score)s) AS agriculture_best,
        COUNT(*) FILTER (WHERE score_refinery    >= %(min_score)s)              AS refinery_count,
        MAX(score_refinery)    FILTER (WHERE score_refinery    >= %(min_score)s) AS refinery_best,
        COUNT(*) FILTER (WHERE score_industrial  >= %(min_score)s)              AS industrial_count,
        MAX(score_industrial)  FILTER (WHERE score_industrial  >= %(min_score)s) AS industrial_best,
        COUNT(*) FILTER (WHERE score_hightech    >= %(min_score)s)              AS hightech_count,
        MAX(score_hightech)    FILTER (WHERE score_hightech    >= %(min_score)s) AS hightech_best,
        COUNT(*) FILTER (WHERE score_military    >= %(min_score)s)              AS military_count,
        MAX(score_military)    FILTER (WHERE score_military    >= %(min_score)s) AS military_best,
        COUNT(*) FILTER (WHERE score_tourism     >= %(min_score)s)              AS tourism_count,
        MAX(score_tourism)     FILTER (WHERE score_tourism     >= %(min_score)s) AS tourism_best,
        COUNT(*)                                                                 AS total_viable
    FROM pairs
    GROUP BY anchor_id
    HAVING COUNT(*) > 0
),
top_ag  AS (SELECT DISTINCT ON (anchor_id) anchor_id, viable_id FROM pairs WHERE score_agriculture >= %(min_score)s ORDER BY anchor_id, score_agriculture DESC),
top_re  AS (SELECT DISTINCT ON (anchor_id) anchor_id, viable_id FROM pairs WHERE score_refinery    >= %(min_score)s ORDER BY anchor_id, score_refinery    DESC),
top_in  AS (SELECT DISTINCT ON (anchor_id) anchor_id, viable_id FROM pairs WHERE score_industrial  >= %(min_score)s ORDER BY anchor_id, score_industrial  DESC),
top_ht  AS (SELECT DISTINCT ON (anchor_id) anchor_id, viable_id FROM pairs WHERE score_hightech    >= %(min_score)s ORDER BY anchor_id, score_hightech    DESC),
top_mi  AS (SELECT DISTINCT ON (anchor_id) anchor_id, viable_id FROM pairs WHERE score_military    >= %(min_score)s ORDER BY anchor_id, score_military    DESC),
top_to  AS (SELECT DISTINCT ON (anchor_id) anchor_id, viable_id FROM pairs WHERE score_tourism     >= %(min_score)s ORDER BY anchor_id, score_tourism     DESC)
SELECT
    agg.system_id64,
    agg.agriculture_count, agg.agriculture_best, top_ag.viable_id AS agriculture_top_id,
    agg.refinery_count,    agg.refinery_best,    top_re.viable_id AS refinery_top_id,
    agg.industrial_count,  agg.industrial_best,  top_in.viable_id AS industrial_top_id,
    agg.hightech_count,    agg.hightech_best,    top_ht.viable_id AS hightech_top_id,
    agg.military_count,    agg.military_best,    top_mi.viable_id AS military_top_id,
    agg.tourism_count,     agg.tourism_best,     top_to.viable_id AS tourism_top_id,
    agg.total_viable
FROM agg
LEFT JOIN top_ag ON top_ag.anchor_id = agg.system_id64
LEFT JOIN top_re ON top_re.anchor_id = agg.system_id64
LEFT JOIN top_in ON top_in.anchor_id = agg.system_id64
LEFT JOIN top_ht ON top_ht.anchor_id = agg.system_id64
LEFT JOIN top_mi ON top_mi.anchor_id = agg.system_id64
LEFT JOIN top_to ON top_to.anchor_id = agg.system_id64
"""

INSERT_SQL = """
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
"""

INSERT_TEMPLATE = """(%s,
    %s,%s,%s, %s,%s,%s, %s,%s,%s,
    %s,%s,%s, %s,%s,%s, %s,%s,%s,
    %s,%s,%s, %s, FALSE, NOW(), NOW())"""

# ---------------------------------------------------------------------------
# Coverage score (Python side)
# ---------------------------------------------------------------------------
def compute_coverage_score(rd: dict) -> float:
    weights = {
        'agriculture': 0.25, 'refinery': 0.20, 'industrial': 0.20,
        'hightech': 0.20, 'military': 0.10, 'tourism': 0.05,
    }
    score = 0.0
    for eco, weight in weights.items():
        best  = rd.get(f'{eco}_best') or 0
        count = rd.get(f'{eco}_count') or 0
        if best > 0:
            count_bonus = min(count / 3.0, 1.0) * 0.1
            score += (best / 100.0 + count_bonus) * weight
    return round(min(score * 100, 100.0), 1)

# ---------------------------------------------------------------------------
# Worker function
# ---------------------------------------------------------------------------
def worker_fn(worker_id: int, cell_queue: Queue, done_counter, db_url: str,
              radius: float, min_score: int, dirty_only: bool,
              cell_timeout: int = 120, max_anchors: int = 50000):
    """
    Pull grid cells from the queue and process each one with a SQL aggregation.
    """
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = False
        cur = conn.cursor()
        # Set per-statement timeout to avoid stalling on dense cells
        cur.execute(f"SET statement_timeout = '{cell_timeout}s'")
        conn.commit()
    except Exception as e:
        print(f"[W{worker_id}] DB connect failed: {e}", flush=True)
        return

    while True:
        try:
            anchor_cell = cell_queue.get(timeout=5)
        except Exception:
            break  # Queue empty

        if anchor_cell is None:
            break  # Sentinel

        # Build 27-cell neighbourhood
        vcz = anchor_cell % 10000
        rem = anchor_cell // 10000
        vcy = rem % 10000
        vcx = rem // 10000
        search_cells = [
            (vcx + dx) * 100_000_000 + (vcy + dy) * 10_000 + (vcz + dz)
            for dx in range(-1, 2)
            for dy in range(-1, 2)
            for dz in range(-1, 2)
        ]

        params = {
            'anchor_cell':  anchor_cell,
            'search_cells': search_cells,
            'radius':       radius,
            'min_score':    min_score,
        }

        # Pre-check: skip cells with too many anchors (they would stall the DB)
        try:
            cur.execute(
                "SELECT COUNT(*) FROM systems WHERE has_body_data = TRUE AND grid_cell_id = %s",
                (anchor_cell,)
            )
            anchor_count = cur.fetchone()[0]
            if anchor_count > max_anchors:
                print(f"[W{worker_id}] Cell {anchor_cell} has {anchor_count} anchors — skipping (too dense)", flush=True)
                with done_counter.get_lock():
                    done_counter.value += 1
                continue
        except Exception as e:
            print(f"[W{worker_id}] Cell {anchor_cell} count check failed: {e}", flush=True)
            conn.rollback()
            with done_counter.get_lock():
                done_counter.value += 1
            continue

        try:
            cur.execute(AGGREGATE_SQL, params)
            rows = cur.fetchall()
        except Exception as e:
            print(f"[W{worker_id}] Cell {anchor_cell} query error (timeout or other): {e}", flush=True)
            conn.rollback()
            with done_counter.get_lock():
                done_counter.value += 1
            continue

        if rows:
            cols = [d[0] for d in cur.description]
            write_batch = []
            for row in rows:
                rd = dict(zip(cols, row))
                coverage  = compute_coverage_score(rd)
                diversity = sum(1 for eco in ('agriculture','refinery','industrial',
                                              'hightech','military','tourism')
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
                    radius,
                ))

            try:
                psycopg2.extras.execute_values(
                    cur, INSERT_SQL, write_batch,
                    template=INSERT_TEMPLATE, page_size=200
                )
                conn.commit()
            except Exception as e:
                print(f"[W{worker_id}] Cell {anchor_cell} write error: {e}", flush=True)
                conn.rollback()

        if dirty_only:
            try:
                cur.execute(
                    "UPDATE systems SET cluster_dirty = FALSE "
                    "WHERE grid_cell_id = %s AND has_body_data = TRUE",
                    (anchor_cell,)
                )
                conn.commit()
            except Exception:
                conn.rollback()

        with done_counter.get_lock():
            done_counter.value += 1

    cur.close()
    conn.close()

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='Build cluster_summary (v3.3 - Parallel SQL + Timeout)')
    parser.add_argument('--workers',    type=int,   default=6)
    parser.add_argument('--radius',     type=float, default=DEFAULT_RADIUS)
    parser.add_argument('--min-score',  type=int,   default=DEFAULT_SCORE)
    parser.add_argument('--dirty-only', action='store_true',
                        help='Only rebuild clusters for dirty anchors')
    parser.add_argument('--cell-timeout', type=int, default=120,
                        help='Max seconds per cell query before skipping (default: 120)')
    parser.add_argument('--max-anchors', type=int, default=50000,
                        help='Skip cells with more than this many anchors (default: 50000)')
    args = parser.parse_args()

    script_start = time.time()
    startup_banner(log, "Cluster Summary Builder", "3.3 (Parallel SQL + Timeout)")

    try:
        conn = psycopg2.connect(DATABASE_URL)
    except Exception as e:
        log.error(f"FATAL: Cannot connect to database: {e}")
        sys.exit(1)

    cur = conn.cursor()

    # ------------------------------------------------------------------
    # Step 1: Find all viable grid cells
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
    cur.close()
    conn.close()

    if not viable_cells:
        log.warning("No viable systems found. Are ratings built? Exiting.")
        sys.exit(0)

    total_cells = len(viable_cells)
    log.info(f"  Found {fmt_num(total_cells)} viable grid cells.")
    log.info(f"  Launching {args.workers} parallel workers...")

    # ------------------------------------------------------------------
    # Step 2: Fill the work queue
    # ------------------------------------------------------------------
    cell_queue   = Queue()
    done_counter = Value(ctypes.c_int, 0)

    for cell in viable_cells:
        cell_queue.put(cell)
    # Sentinel values to stop workers
    for _ in range(args.workers):
        cell_queue.put(None)

    # ------------------------------------------------------------------
    # Step 3: Start workers
    # ------------------------------------------------------------------
    workers = []
    for wid in range(args.workers):
        p = mp.Process(
            target=worker_fn,
            args=(wid, cell_queue, done_counter, DATABASE_URL,
                  args.radius, args.min_score, args.dirty_only,
                  args.cell_timeout, args.max_anchors),
            daemon=True,
        )
        p.start()
        workers.append(p)

    # ------------------------------------------------------------------
    # Step 4: Progress reporting in main process
    # ------------------------------------------------------------------
    progress = ProgressReporter(log, total=total_cells, label="cells", interval=30)
    last_done = 0

    while any(p.is_alive() for p in workers):
        time.sleep(5)
        current = done_counter.value
        delta = current - last_done
        if delta > 0:
            progress.update(delta)
            last_done = current

    # Final update
    current = done_counter.value
    delta = current - last_done
    if delta > 0:
        progress.update(delta)

    for p in workers:
        p.join()

    # ------------------------------------------------------------------
    # Step 5: Mark build complete
    # ------------------------------------------------------------------
    conn2 = psycopg2.connect(DATABASE_URL)
    cur2  = conn2.cursor()
    cur2.execute("""
        INSERT INTO app_meta (key, value, updated_at)
        VALUES ('clusters_built', 'true', NOW())
        ON CONFLICT (key) DO UPDATE SET value = 'true', updated_at = NOW()
    """)
    # On a full rebuild, clear all cluster_dirty flags so the next incremental
    # run does not re-process everything unnecessarily.
    if not args.dirty_only:
        log.info("Clearing cluster_dirty flags after full rebuild...")
        cur2.execute(
            "UPDATE systems SET cluster_dirty = FALSE WHERE has_body_data = TRUE"
        )
        log.info("cluster_dirty flags cleared.")
    conn2.commit()
    cur2.close()
    conn2.close()

    elapsed = time.time() - script_start
    done_banner(log, "Cluster Build Complete", elapsed, [
        f"Viable cells processed : {fmt_num(total_cells)}",
        f"Workers used           : {args.workers}",
        f"Total time             : {fmt_duration(elapsed)}",
    ])


if __name__ == '__main__':
    main()
