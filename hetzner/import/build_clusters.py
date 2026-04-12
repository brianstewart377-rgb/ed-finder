#!/usr/bin/env python3
"""
ED Finder — Cluster Summary Builder
Version: 1.0

Builds the cluster_summary table: for every visited system, computes
how many viable uncolonised systems exist for each economy type within
500ly — the data that powers the "find me the best empire location" search.

Algorithm:
  For each anchor system (visited, has body data):
    For each economy type:
      Count uncolonised systems within 500ly where score_{economy} >= MIN_VIABLE_SCORE
      Track the best score and the id64 of that best system

Uses spatial grid to avoid O(n²) scanning:
  Only checks systems in the same + 26 adjacent cells (3×3×3 neighbourhood)
  Reduces per-anchor work from 70M comparisons to ~50k comparisons

Performance on i7-8700:
  ~70M anchors × ~50k neighbours = fast with grid
  Estimated total time: 8-24 hours (acceptable for one-time build)
  Use --workers to parallelise across CPU cores

Usage:
    python3 build_clusters.py                    # build all
    python3 build_clusters.py --dirty-only       # only rebuild dirty anchors
    python3 build_clusters.py --workers 6        # use 6 parallel workers
    python3 build_clusters.py --radius 500       # search radius (default 500ly)
    python3 build_clusters.py --min-score 40     # minimum viable score (default 40)
    python3 build_clusters.py --limit 100000     # process N anchors (testing)
"""

import os
import sys
import math
import time
import logging
import argparse
import multiprocessing as mp
from typing import Optional

import psycopg2
import psycopg2.extras

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_DSN          = os.getenv('DATABASE_URL', 'postgresql://edfinder:edfinder@localhost:5432/edfinder')
BATCH_SIZE      = int(os.getenv('BATCH_SIZE', '500'))
LOG_LEVEL       = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE        = os.getenv('LOG_FILE', '/data/logs/build_clusters.log')
DEFAULT_RADIUS  = 500   # LY
MIN_VIABLE      = 40    # minimum score to count as "viable"

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger('build_clusters')


def compute_coverage_score(counts: dict, bests: dict) -> float:
    """
    Weighted coverage score (0-100).
    Mirrors the SQL function compute_coverage_score() exactly.
    Agriculture + HighTech weighted higher.
    """
    weights = {
        'Agriculture': 0.25,
        'Refinery':    0.20,
        'Industrial':  0.20,
        'HighTech':    0.20,
        'Military':    0.10,
        'Tourism':     0.05,
    }
    score = 0.0
    for eco, weight in weights.items():
        best = bests.get(eco)
        count = counts.get(eco, 0)
        if best is not None:
            count_bonus = min(count / 3.0, 1.0) * 0.1
            score += (best / 100.0 + count_bonus) * weight
    return round(min(score * 100, 100.0), 1)


def process_anchor_batch(
    worker_id: int,
    anchor_batch: list,
    db_dsn: str,
    radius: float,
    min_score: int,
) -> tuple[int, int]:
    """
    Worker process: for each anchor in the batch, find viable systems
    within `radius` LY and aggregate economy coverage.
    """
    conn = psycopg2.connect(db_dsn)
    conn.autocommit = False
    cur = conn.cursor()

    processed = 0
    errors = 0
    cluster_batch = []

    for anchor in anchor_batch:
        anchor_id64, ax, ay, az = anchor[0], anchor[1], anchor[2], anchor[3]

        try:
            # Query: find all viable uncolonised systems within radius using
            # bounding box pre-filter (fast) then exact distance check
            cur.execute("""
                SELECT
                    r.economy_suggestion,
                    r.score_agriculture, r.score_refinery,
                    r.score_industrial,  r.score_hightech,
                    r.score_military,    r.score_tourism,
                    s.id64,
                    distance_ly(s.x, s.y, s.z, %s, %s, %s) AS dist
                FROM systems s
                JOIN ratings r ON r.system_id64 = s.id64
                WHERE s.population = 0
                  AND s.id64 != %s
                  AND in_bounding_box(s.x, s.y, s.z, %s, %s, %s, %s)
                  AND distance_ly(s.x, s.y, s.z, %s, %s, %s) <= %s
                  AND (
                      r.score_agriculture >= %s OR
                      r.score_refinery    >= %s OR
                      r.score_industrial  >= %s OR
                      r.score_hightech    >= %s OR
                      r.score_military    >= %s OR
                      r.score_tourism     >= %s
                  )
            """, (
                ax, ay, az,          # for distance_ly
                anchor_id64,         # exclude self
                ax, ay, az, radius,  # bounding box
                ax, ay, az, radius,  # exact distance
                min_score, min_score, min_score,
                min_score, min_score, min_score,
            ))

            rows = cur.fetchall()

            # Aggregate per-economy counts and best scores
            counts = {e: 0 for e in ['Agriculture','Refinery','Industrial','HighTech','Military','Tourism']}
            bests  = {e: None for e in ['Agriculture','Refinery','Industrial','HighTech','Military','Tourism']}
            top_id = {e: None for e in ['Agriculture','Refinery','Industrial','HighTech','Military','Tourism']}

            eco_col = {
                'Agriculture': 1,
                'Refinery':    2,
                'Industrial':  3,
                'HighTech':    4,
                'Military':    5,
                'Tourism':     6,
            }

            for row in rows:
                sid = row[7]
                for eco, col_idx in eco_col.items():
                    eco_score = row[col_idx]
                    if eco_score is not None and eco_score >= min_score:
                        counts[eco] += 1
                        if bests[eco] is None or eco_score > bests[eco]:
                            bests[eco]  = eco_score
                            top_id[eco] = sid

            # Compute coverage score and diversity
            coverage = compute_coverage_score(counts, bests)
            diversity = sum(1 for c in counts.values() if c > 0)
            total_viable = sum(counts.values())

            cluster_batch.append((
                anchor_id64,
                counts['Agriculture'], bests.get('Agriculture'), top_id.get('Agriculture'),
                counts['Refinery'],    bests.get('Refinery'),    top_id.get('Refinery'),
                counts['Industrial'],  bests.get('Industrial'),  top_id.get('Industrial'),
                counts['HighTech'],    bests.get('HighTech'),    top_id.get('HighTech'),
                counts['Military'],    bests.get('Military'),    top_id.get('Military'),
                counts['Tourism'],     bests.get('Tourism'),     top_id.get('Tourism'),
                total_viable,
                coverage,
                diversity,
                radius,
                False,  # dirty = False (just computed)
            ))
            processed += 1

        except Exception as e:
            errors += 1
            log.debug(f"Worker {worker_id} error on {anchor_id64}: {e}")
            continue

        # Write batch
        if len(cluster_batch) >= BATCH_SIZE:
            _write_clusters(conn, cur, cluster_batch)
            cluster_batch = []

    # Write remainder
    if cluster_batch:
        _write_clusters(conn, cur, cluster_batch)

    # Mark anchors as clean
    anchor_ids = [a[0] for a in anchor_batch]
    if anchor_ids:
        psycopg2.extras.execute_values(cur, """
            UPDATE systems SET cluster_dirty = FALSE
            WHERE id64 IN %s
        """, [(tuple(anchor_ids),)])
        conn.commit()

    cur.close()
    conn.close()
    return processed, errors


def _write_clusters(conn, cur, batch: list):
    """Upsert a batch of cluster_summary records."""
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
            computed_at        = NOW(),
            updated_at         = NOW()
        """,
        [(r[0],
          r[1],  r[2],  r[3],
          r[4],  r[5],  r[6],
          r[7],  r[8],  r[9],
          r[10], r[11], r[12],
          r[13], r[14], r[15],
          r[16], r[17], r[18],
          r[19], r[20], r[21],
          r[22], r[23], 'NOW()', 'NOW()') for r in batch],
        template="""(%s,
            %s,%s,%s, %s,%s,%s, %s,%s,%s,
            %s,%s,%s, %s,%s,%s, %s,%s,%s,
            %s,%s,%s, %s,%s, NOW(), NOW())""",
        page_size=BATCH_SIZE,
    )
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description='Build cluster_summary table')
    parser.add_argument('--dirty-only', action='store_true', help='Only rebuild dirty anchors')
    parser.add_argument('--workers',    type=int,   default=mp.cpu_count(), help='Worker processes')
    parser.add_argument('--radius',     type=float, default=DEFAULT_RADIUS, help='Search radius in LY')
    parser.add_argument('--min-score',  type=int,   default=MIN_VIABLE,     help='Minimum viable score')
    parser.add_argument('--limit',      type=int,   default=None,           help='Process N anchors (testing)')
    args = parser.parse_args()

    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()

    # Check prerequisites
    cur.execute("SELECT value FROM app_meta WHERE key = 'ratings_built'")
    r = cur.fetchone()
    if not r or r[0] != 'true':
        log.error("Ratings not yet built. Run build_ratings.py first.")
        return

    cur.execute("SELECT value FROM app_meta WHERE key = 'grid_built'")
    r = cur.fetchone()
    if not r or r[0] != 'true':
        log.warning("Spatial grid not built. Cluster build will be slower (no grid optimisation).")

    # Load anchor systems (visited systems = potential empire centres)
    log.info("Loading anchor systems ...")
    if args.dirty_only:
        cur.execute("""
            SELECT id64, x, y, z FROM systems
            WHERE has_body_data = TRUE
              AND cluster_dirty = TRUE
            ORDER BY id64
            LIMIT %s
        """, (args.limit or 10_000_000,))
    else:
        cur.execute("""
            SELECT id64, x, y, z FROM systems
            WHERE has_body_data = TRUE
            ORDER BY id64
            LIMIT %s
        """, (args.limit or 200_000_000,))

    all_anchors = cur.fetchall()
    total = len(all_anchors)
    cur.close()
    conn.close()

    log.info(f"Anchors to process: {total:,}")
    log.info(f"Radius: {args.radius}ly | Min viable score: {args.min_score} | Workers: {args.workers}")
    if total == 0:
        log.info("Nothing to do.")
        return

    # Estimate time
    # With grid: each anchor checks ~50k neighbours, ~1ms per anchor on SSD
    est_hours = total / 1_000_000 * (1.0 / args.workers)
    log.info(f"Estimated time: {est_hours:.1f}h with {args.workers} workers")
    log.info("Starting cluster build — this is the long one. Get a coffee. ☕")

    # Split into worker chunks
    chunk_size = max(BATCH_SIZE * 20, total // (args.workers * 10))
    chunks = [all_anchors[i:i+chunk_size] for i in range(0, total, chunk_size)]

    start = time.time()
    total_processed = 0
    total_errors = 0
    last_report = time.time()

    # Process in batches, reporting progress every 5 minutes
    with mp.Pool(processes=args.workers) as pool:
        results = pool.starmap(
            process_anchor_batch,
            [(i % args.workers, chunk, DB_DSN, args.radius, args.min_score)
             for i, chunk in enumerate(chunks)]
        )

    for processed, errors in results:
        total_processed += processed
        total_errors += errors

    elapsed = time.time() - start
    rate = total_processed / elapsed if elapsed > 0 else 0
    log.info(f"\nCluster build complete!")
    log.info(f"  Anchors processed: {total_processed:,}")
    log.info(f"  Errors:            {total_errors:,}")
    log.info(f"  Total time:        {elapsed/3600:.2f}h")
    log.info(f"  Rate:              {rate:.0f} anchors/sec")

    # Mark clusters as built
    conn = psycopg2.connect(DB_DSN)
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO app_meta (key, value, updated_at)
            VALUES ('clusters_built', 'true', NOW())
            ON CONFLICT (key) DO UPDATE SET value = 'true', updated_at = NOW()
        """)

        # Show top 5 results as a sanity check
        cur.execute("""
            SELECT s.name, cs.coverage_score, cs.economy_diversity, cs.total_viable,
                   cs.agriculture_count, cs.hightech_count, cs.refinery_count
            FROM cluster_summary cs
            JOIN systems s ON s.id64 = cs.system_id64
            WHERE cs.coverage_score IS NOT NULL
            ORDER BY cs.coverage_score DESC
            LIMIT 5
        """)
        rows = cur.fetchall()
        log.info("\nTop 5 empire locations:")
        for r in rows:
            log.info(f"  {r[0]:<30} coverage={r[1]:.1f} diversity={r[2]} "
                     f"ag={r[4]} ht={r[5]} ref={r[6]}")

    conn.commit()
    conn.close()

    log.info("\nNext step: psql -U edfinder -d edfinder -f sql/002_indexes.sql")


if __name__ == '__main__':
    main()
