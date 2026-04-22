#!/usr/bin/env python3
"""
ED Finder — Cluster Summary Builder
Version: 1.1  (resume-safe, grid-aware, log-dir guard)

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

KEY FIXES in v1.1:
  • Log directory is created automatically (no more FileNotFoundError on start)
  • Removed duplicate "Nothing to do" / "Get a coffee" code blocks
  • Removed duplicate elapsed/rate lines
  • Resume-safe: default mode skips already-computed anchors (cluster_dirty=FALSE)
  • Grid-aware per-anchor query: uses spatial_grid adjacency to limit the neighbour
    scan to 27 cells instead of the full systems table
  • Neighbour rows streamed with fetchmany() instead of fetchall()
  • Progress logged every 60 seconds regardless of chunk boundaries

Usage:
    python3 build_clusters.py                    # build all (resume-safe)
    python3 build_clusters.py --rebuild          # re-compute ALL anchors from scratch
    python3 build_clusters.py --dirty-only       # only rebuild dirty anchors
    python3 build_clusters.py --workers 4        # set worker count
    python3 build_clusters.py --radius 500       # search radius (default 500ly)
    python3 build_clusters.py --min-score 40     # minimum viable score (default 40)
    python3 build_clusters.py --limit 100000     # process N anchors (testing)

Runtime estimate: ~8-24 hours for 73M anchors on i7-8700 with --workers 4
"""

import os
import sys
import math
import time
import logging
import argparse
import multiprocessing as mp

import psycopg2
import psycopg2.extras

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_DSN          = os.getenv('DATABASE_URL', 'postgresql://edfinder:edfinder@localhost:5432/edfinder')
BATCH_SIZE      = int(os.getenv('BATCH_SIZE', '500'))
LOG_LEVEL       = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE        = os.getenv('LOG_FILE', '/tmp/build_clusters.log')   # safe default
DEFAULT_RADIUS  = 500   # LY
MIN_VIABLE      = 40    # minimum score to count as "viable"

# Ensure log directory exists before setting up logging
os.makedirs(os.path.dirname(os.path.abspath(LOG_FILE)), exist_ok=True)

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
) -> tuple:
    """
    Worker process: for each anchor in the batch, find viable systems
    within `radius` LY and aggregate economy coverage.

    FIX v1.1: Uses spatial grid adjacency (3×3×3 cell neighbourhood) to
    limit the neighbour scan instead of querying the whole systems table.
    Without this, each anchor triggers a bounding-box scan of 186M rows.
    With this, each anchor scans at most 27 grid cells × ~1400 systems = ~38k rows.
    """
    conn = psycopg2.connect(db_dsn)
    conn.autocommit = False
    cur = conn.cursor()

    # Load grid parameters from app_meta once per worker
    cur.execute("""
        SELECT key, value FROM app_meta
        WHERE key IN ('grid_cell_size','grid_min_x','grid_min_y','grid_min_z')
    """)
    meta = {r[0]: float(r[1]) for r in cur.fetchall()}
    cell_size = meta.get('grid_cell_size', 500.0)
    gmin_x    = meta.get('grid_min_x', -43214.0)
    gmin_y    = meta.get('grid_min_y', -30360.0)
    gmin_z    = meta.get('grid_min_z', -24405.0)

    processed = 0
    errors = 0
    cluster_batch = []

    eco_col = {
        'Agriculture': 1,
        'Refinery':    2,
        'Industrial':  3,
        'HighTech':    4,
        'Military':    5,
        'Tourism':     6,
    }

    for anchor in anchor_batch:
        anchor_id64, ax, ay, az = anchor[0], anchor[1], anchor[2], anchor[3]

        try:
            # ── Grid-aware neighbour query ────────────────────────────────
            # Compute which cell this anchor sits in
            acx = int(math.floor((ax - gmin_x) / cell_size))
            acy = int(math.floor((ay - gmin_y) / cell_size))
            acz = int(math.floor((az - gmin_z) / cell_size))

            # Build list of adjacent cell IDs (3×3×3 = up to 27 cells)
            adjacent_cell_ids = []
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    for dz in range(-1, 2):
                        cx = acx + dx
                        cy = acy + dy
                        cz = acz + dz
                        # cell_id encoding must match build_grid.py exactly
                        adjacent_cell_ids.append(
                            cx * 100_000_000 + cy * 10_000 + cz
                        )

            # Query only systems in those 27 cells, then filter by exact distance
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
                  AND s.grid_cell_id = ANY(%s)
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
                ax, ay, az,               # distance_ly args
                anchor_id64,              # exclude self
                adjacent_cell_ids,        # grid cell filter (replaces bounding box)
                ax, ay, az, radius,       # exact distance check
                min_score, min_score, min_score,
                min_score, min_score, min_score,
            ))

            # Stream neighbour rows to avoid large fetchall() in dense regions
            counts = {e: 0 for e in eco_col}
            bests  = {e: None for e in eco_col}
            top_id = {e: None for e in eco_col}
            viable_sids: set = set()

            while True:
                chunk = cur.fetchmany(1000)
                if not chunk:
                    break
                for row in chunk:
                    sid = row[7]
                    for eco, col_idx in eco_col.items():
                        eco_score = row[col_idx]
                        if eco_score is not None and eco_score >= min_score:
                            counts[eco] += 1
                            viable_sids.add(sid)
                            if bests[eco] is None or eco_score > bests[eco]:
                                bests[eco]  = eco_score
                                top_id[eco] = sid

            # Compute coverage score and diversity
            coverage     = compute_coverage_score(counts, bests)
            diversity    = sum(1 for c in counts.values() if c > 0)
            total_viable = len(viable_sids)

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

    # Mark anchors as clean — use ANY(%s), correct psycopg2 array syntax
    anchor_ids = [a[0] for a in anchor_batch]
    if anchor_ids:
        cur.execute("""
            UPDATE systems SET cluster_dirty = FALSE
            WHERE id64 = ANY(%s)
        """, (anchor_ids,))
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
        # Tuple layout (24 values, indices 0-23):
        #   0:  system_id64
        #   1-18: 6 economies × (count, best, top_id)
        #   19: total_viable  20: coverage_score  21: economy_diversity
        #   22: search_radius  23: dirty
        [(r[0],
          r[1],  r[2],  r[3],
          r[4],  r[5],  r[6],
          r[7],  r[8],  r[9],
          r[10], r[11], r[12],
          r[13], r[14], r[15],
          r[16], r[17], r[18],
          r[19], r[20], r[21],
          r[22], r[23]) for r in batch],
        template="""(%s,
            %s,%s,%s, %s,%s,%s, %s,%s,%s,
            %s,%s,%s, %s,%s,%s, %s,%s,%s,
            %s,%s,%s, %s,%s, NOW(), NOW())""",
        page_size=BATCH_SIZE,
    )
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description='Build cluster_summary table (v1.1)')
    parser.add_argument('--rebuild',    action='store_true', help='Re-compute ALL anchors from scratch (ignores cluster_dirty)')
    parser.add_argument('--dirty-only', action='store_true', help='Only rebuild dirty anchors')
    parser.add_argument('--workers',    type=int,   default=mp.cpu_count(), help='Worker processes (recommend 4 on i7-8700)')
    parser.add_argument('--radius',     type=float, default=DEFAULT_RADIUS, help='Search radius in LY (default 500)')
    parser.add_argument('--min-score',  type=int,   default=MIN_VIABLE,     help='Minimum viable score (default 40)')
    parser.add_argument('--limit',      type=int,   default=None,           help='Process N anchors (testing)')
    args = parser.parse_args()

    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()

    # ── Prerequisite checks ───────────────────────────────────────────────────
    cur.execute("SELECT value FROM app_meta WHERE key = 'ratings_built'")
    r = cur.fetchone()
    if not r or r[0] != 'true':
        log.error("Ratings not yet built. Run build_ratings.py first.")
        cur.close(); conn.close(); return

    cur.execute("SELECT value FROM app_meta WHERE key = 'grid_built'")
    r = cur.fetchone()
    if not r or r[0] != 'true':
        log.warning("Spatial grid not built — cluster build will be MUCH slower (no grid cell filter).")
        log.warning("Run build_grid.py first for best performance.")

    # ── Diagnostic counts ─────────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM systems WHERE has_body_data = TRUE")
    total_with_bodies = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM cluster_summary")
    already_done = cur.fetchone()[0]

    if args.rebuild:
        mode = "FULL REBUILD — all anchors"
        cur.execute("SELECT COUNT(*) FROM systems WHERE has_body_data = TRUE")
    elif args.dirty_only:
        mode = "dirty anchors only"
        cur.execute("SELECT COUNT(*) FROM systems WHERE has_body_data = TRUE AND cluster_dirty = TRUE")
    else:
        # Default: resume mode — only process anchors not yet in cluster_summary
        mode = "resume mode — unprocessed anchors only"
        cur.execute("""
            SELECT COUNT(*) FROM systems s
            LEFT JOIN cluster_summary cs ON cs.system_id64 = s.id64
            WHERE s.has_body_data = TRUE AND cs.system_id64 IS NULL
        """)

    total = cur.fetchone()[0]
    cur.close()
    conn.close()

    log.info(f"DB diagnostic: {total_with_bodies:,} anchors total, {already_done:,} already computed, {total:,} remaining")
    log.info(f"Mode: {mode}")
    log.info(f"Radius: {args.radius}ly | Min viable score: {args.min_score} | Workers: {args.workers}")

    if total == 0:
        log.info("Nothing to do — cluster_summary is complete!")
        return

    est_hours = total / 1_000_000 * (1.0 / args.workers)
    log.info(f"Estimated time: {est_hours:.1f}h with {args.workers} workers")
    log.info("Starting cluster build — this is the long one. Get a coffee. ☕")

    # ── Stream anchors with server-side cursor ────────────────────────────────
    stream_conn = psycopg2.connect(DB_DSN)
    stream_conn.autocommit = False
    stream_conn.set_session(readonly=True)
    chunk_size = 50_000

    start = time.time()
    total_processed = 0
    total_errors    = 0
    chunks_dispatched = 0
    pending_results   = []
    last_log_time     = time.time()

    with stream_conn.cursor(name='anchors_stream') as stream_cur:
        stream_cur.itersize = chunk_size

        if args.rebuild:
            stream_cur.execute("""
                SELECT id64, x, y, z FROM systems
                WHERE has_body_data = TRUE
                ORDER BY id64
                LIMIT %s
            """, (args.limit or 200_000_000,))
        elif args.dirty_only:
            stream_cur.execute("""
                SELECT id64, x, y, z FROM systems
                WHERE has_body_data = TRUE AND cluster_dirty = TRUE
                ORDER BY id64
                LIMIT %s
            """, (args.limit or 10_000_000,))
        else:
            # Resume mode: LEFT JOIN to find anchors not yet in cluster_summary
            stream_cur.execute("""
                SELECT s.id64, s.x, s.y, s.z
                FROM systems s
                LEFT JOIN cluster_summary cs ON cs.system_id64 = s.id64
                WHERE s.has_body_data = TRUE
                  AND cs.system_id64 IS NULL
                ORDER BY s.id64
                LIMIT %s
            """, (args.limit or 200_000_000,))

        with mp.Pool(processes=args.workers) as pool:
            while True:
                batch = stream_cur.fetchmany(chunk_size)
                if not batch:
                    log.info("Stream exhausted — all anchors dispatched.")
                    break
                chunks_dispatched += 1
                pending_results.append(
                    pool.apply_async(
                        process_anchor_batch,
                        (chunks_dispatched % args.workers, batch, DB_DSN, args.radius, args.min_score)
                    )
                )

                # Drain completed work to bound memory (keep at most workers*2 in-flight)
                while len(pending_results) >= args.workers * 2:
                    done = pending_results.pop(0)
                    p, e = done.get()
                    total_processed += p
                    total_errors    += e
                    # Log progress at most once per 60s to avoid log spam
                    if time.time() - last_log_time >= 60:
                        elapsed = time.time() - start
                        rate    = total_processed / elapsed if elapsed > 0 else 0
                        eta_h   = (total - total_processed) / rate / 3600 if rate > 0 else 0
                        log.info(
                            f"  Progress: {total_processed + already_done:,} / {total_with_bodies:,} "
                            f"({(total_processed + already_done) / total_with_bodies * 100:.1f}%) | "
                            f"speed: {rate:.0f}/s | ETA: {eta_h:.1f}h | errors: {total_errors}"
                        )
                        last_log_time = time.time()

            log.info(f"All {chunks_dispatched} chunks dispatched — waiting for workers to finish...")
            for done in pending_results:
                p, e = done.get()
                total_processed += p
                total_errors    += e

    stream_conn.close()

    elapsed = time.time() - start
    rate    = total_processed / elapsed if elapsed > 0 else 0
    log.info(f"\nCluster build complete!")
    log.info(f"  Anchors processed: {total_processed:,}")
    log.info(f"  Errors:            {total_errors:,}")
    log.info(f"  Total time:        {elapsed/3600:.2f}h")
    log.info(f"  Rate:              {rate:.0f} anchors/sec")

    # Mark clusters as built in app_meta
    conn2 = psycopg2.connect(DB_DSN)
    with conn2.cursor() as cur:
        cur.execute("""
            INSERT INTO app_meta (key, value, updated_at)
            VALUES ('clusters_built', 'true', NOW())
            ON CONFLICT (key) DO UPDATE SET value = 'true', updated_at = NOW()
        """)

        # Sanity check — show top 5 results
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
        if rows:
            log.info("\nTop 5 empire locations:")
            for r in rows:
                log.info(f"  {r[0]:<30} coverage={r[1]:.1f} diversity={r[2]} "
                         f"ag={r[4]} ht={r[5]} ref={r[6]}")

    conn2.commit()
    conn2.close()

    log.info("\nNext step: run sql/002_indexes.sql to build all indexes")
    log.info("  docker exec -it ed-postgres psql -U edfinder -d edfinder -f /path/to/002_indexes.sql")


if __name__ == '__main__':
    main()
