#!/usr/bin/env python3
"""
ED Finder — Cluster Summary Builder
Version: 1.3  (disable RI triggers on dirty-flag UPDATE — same fix as build_grid v2.3)

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
  Reduces per-anchor work from 186M comparisons to ~38k comparisons

KEY FIXES in v1.1:
  • Log directory created automatically (no more FileNotFoundError on Docker start)
  • Removed duplicate code blocks
  • Resume-safe: default mode skips already-computed anchors
  • Grid-aware per-anchor query: uses spatial_grid adjacency (27 cells) not full scan
  • Neighbour rows streamed with fetchmany() instead of fetchall()
  • Progress logged every 60 seconds

NEW in v1.2:
  • startup_banner with full config summary
  • stage_banner headers and crash_hint for each long operation
  • Per-worker WorkerHeartbeat (60s interval) — visible in Docker logs
  • done_banner with top-5 coverage table
  • Safe log path default (/tmp/build_clusters.log)
  • Explicit "WARNING: spatial grid missing" block with estimated slow-path time

FIX in v1.3:
  • `UPDATE systems SET cluster_dirty = FALSE` fired 17 RI triggers per row
    (8 child FKs × 2 triggers + 1 custom = 17) even though only cluster_dirty
    changes — ~2.5 billion spurious trigger evaluations across 73M anchors.
  • Fix: SET session_replication_role = replica before the dirty-flag UPDATE
    (session-scoped, reverts automatically, safe: id64/FK columns not touched).

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

from progress import (
    ProgressReporter, WorkerHeartbeat,
    startup_banner, stage_banner, done_banner, crash_hint,
    fmt_num, fmt_duration, fmt_rate, fmt_pct,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_DSN          = os.getenv('DATABASE_URL', 'postgresql://edfinder:edfinder@localhost:5432/edfinder')
BATCH_SIZE      = int(os.getenv('BATCH_SIZE', '500'))
LOG_LEVEL       = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE        = os.getenv('LOG_FILE', '/tmp/build_clusters.log')   # safe Docker default
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

    v1.2: WorkerHeartbeat prints progress every 60s so Docker logs show
    the worker is alive (not silently crashed or hung).
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

    hb = WorkerHeartbeat(worker_id, total=len(anchor_batch),
                         label="clusters", interval=60.0)

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
                ax, ay, az,
                anchor_id64,
                adjacent_cell_ids,
                ax, ay, az, radius,
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

        hb.tick(processed, errors)

        # Write batch when full
        if len(cluster_batch) >= BATCH_SIZE:
            _write_clusters(conn, cur, cluster_batch)
            cluster_batch = []

    # Write remainder
    if cluster_batch:
        _write_clusters(conn, cur, cluster_batch)

    # Mark anchors as clean.
    # FIX v1.3: disable RI triggers for this session so the UPDATE doesn't fire
    # 17 referential-integrity triggers per row (8 FK child tables × 2 triggers
    # each + 1 custom trigger = 17).  Only cluster_dirty is being changed — not
    # id64 (the FK column) — so RI integrity is fully maintained.
    # session_replication_role = replica reverts automatically on disconnect.
    anchor_ids = [a[0] for a in anchor_batch]
    if anchor_ids:
        try:
            cur.execute("SET session_replication_role = replica")
            log.debug(f"Worker {worker_id}: RI triggers disabled for dirty-flag UPDATE")
        except Exception as e:
            log.warning(f"Worker {worker_id}: could not disable RI triggers: {e} — continuing anyway")
        cur.execute("""
            UPDATE systems SET cluster_dirty = FALSE
            WHERE id64 = ANY(%s)
        """, (anchor_ids,))
        conn.commit()
        # session_replication_role reverts to 'origin' on next transaction /
        # disconnect automatically — no explicit reset needed.

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
          r[22], r[23]) for r in batch],
        template="""(%s,
            %s,%s,%s, %s,%s,%s, %s,%s,%s,
            %s,%s,%s, %s,%s,%s, %s,%s,%s,
            %s,%s,%s, %s,%s, NOW(), NOW())""",
        page_size=BATCH_SIZE,
    )
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description='Build cluster_summary table (v1.2)')
    parser.add_argument('--rebuild',    action='store_true',
                        help='Re-compute ALL anchors from scratch (ignores cluster_dirty)')
    parser.add_argument('--dirty-only', action='store_true',
                        help='Only rebuild dirty anchors')
    parser.add_argument('--workers',    type=int,   default=mp.cpu_count(),
                        help='Worker processes (recommend 4 on i7-8700)')
    parser.add_argument('--radius',     type=float, default=DEFAULT_RADIUS,
                        help='Search radius in LY (default 500)')
    parser.add_argument('--min-score',  type=int,   default=MIN_VIABLE,
                        help='Minimum viable score (default 40)')
    parser.add_argument('--limit',      type=int,   default=None,
                        help='Process N anchors (testing)')
    args = parser.parse_args()

    script_start = time.time()

    # ── Startup banner ────────────────────────────────────────────────────
    mode_label = ("REBUILD ALL" if args.rebuild
                  else ("DIRTY ONLY" if args.dirty_only
                        else "RESUME (unprocessed only)"))
    startup_banner(log, "Cluster Summary Builder", "v1.2", [
        ("Mode",       mode_label),
        ("Radius",     f"{args.radius}ly"),
        ("Min score",  str(args.min_score)),
        ("Workers",    str(args.workers)),
        ("Batch size", str(BATCH_SIZE)),
        ("Log file",   LOG_FILE),
        ("DB",         DB_DSN.split('@')[-1]),
    ])

    # ── Prerequisite checks ───────────────────────────────────────────────
    stage_banner(log, 1, 3, "Prerequisite checks")
    try:
        conn = psycopg2.connect(DB_DSN)
    except Exception as e:
        log.error(f"FATAL: Cannot connect to database: {e}")
        sys.exit(1)

    cur = conn.cursor()

    cur.execute("SELECT value FROM app_meta WHERE key = 'ratings_built'")
    r = cur.fetchone()
    if not r or r[0] != 'true':
        log.error("  ✗ Ratings not yet built.")
        log.error("    Run: python3 build_ratings.py")
        log.error("    Or set the flag manually if ratings are complete:")
        log.error("    INSERT INTO app_meta (key,value,updated_at)")
        log.error("      VALUES ('ratings_built','true',NOW())")
        log.error("      ON CONFLICT (key) DO UPDATE SET value='true', updated_at=NOW();")
        cur.close(); conn.close()
        sys.exit(1)
    log.info("  ✓ ratings_built = true")

    cur.execute("SELECT value FROM app_meta WHERE key = 'grid_built'")
    r = cur.fetchone()
    grid_built = r and r[0] == 'true'
    if not grid_built:
        log.warning("  ⚠  Spatial grid NOT built (grid_built != true)")
        log.warning("     Each anchor will scan the FULL systems table (~186M rows)")
        log.warning("     This will be EXTREMELY slow — estimated 8-12 WEEKS vs 8-24 hours")
        log.warning("     Run build_grid.py first, then re-run build_clusters.py")
        log.warning("     Continuing anyway — Ctrl+C to abort")
        time.sleep(5)   # Give the operator time to read and cancel
    else:
        log.info("  ✓ grid_built = true  (spatial grid will limit neighbour scan to ~38k rows/anchor)")

    # ── Diagnostic counts ─────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM systems WHERE has_body_data = TRUE")
    total_with_bodies = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM cluster_summary")
    already_done = cur.fetchone()[0]

    log.info(f"  Total anchors (has_body_data) : {fmt_num(total_with_bodies)}")
    log.info(f"  Already in cluster_summary    : {fmt_num(already_done)}")

    if args.rebuild:
        cur.execute("SELECT COUNT(*) FROM systems WHERE has_body_data = TRUE")
    elif args.dirty_only:
        cur.execute("SELECT COUNT(*) FROM systems WHERE has_body_data = TRUE AND cluster_dirty = TRUE")
    else:
        cur.execute("""
            SELECT COUNT(*) FROM systems s
            LEFT JOIN cluster_summary cs ON cs.system_id64 = s.id64
            WHERE s.has_body_data = TRUE AND cs.system_id64 IS NULL
        """)

    total = cur.fetchone()[0]
    cur.close()
    conn.close()

    log.info(f"  To process this run           : {fmt_num(total)}")

    if total == 0:
        log.info("")
        log.info("  ✓ Nothing to do — cluster_summary is complete!")
        log.info("    Use --rebuild to force re-compute everything.")
        return

    est_hours = total / 1_000_000 / max(args.workers, 1)
    log.info(f"  Estimated time : {est_hours:.1f}h at ~1M anchors/hour/worker")
    log.info(f"  Workers emit heartbeat every 60s — silence > 5 min = crashed worker")

    # ── Stream and dispatch ────────────────────────────────────────────────
    stage_banner(log, 2, 3, "Stream & compute clusters")
    crash_hint(log, "automatically from the last computed anchor")
    log.info("  This is the long one. Get a coffee (or several). ☕☕")

    stream_conn = psycopg2.connect(DB_DSN)
    stream_conn.autocommit = False
    stream_conn.set_session(readonly=True)
    chunk_size = 50_000

    total_processed = 0
    total_errors    = 0
    chunks_dispatched = 0
    pending_results   = []
    progress = ProgressReporter(log, total=total, label="clusters",
                                interval=60, heartbeat=180)

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
                    log.info("  Stream exhausted — all anchors dispatched.")
                    break

                chunks_dispatched += 1
                pending_results.append(
                    pool.apply_async(
                        process_anchor_batch,
                        (chunks_dispatched % args.workers, batch, DB_DSN,
                         args.radius, args.min_score)
                    )
                )

                # Drain completed work to bound memory
                while len(pending_results) >= args.workers * 2:
                    done = pending_results.pop(0)
                    p, e = done.get()
                    total_processed += p
                    total_errors    += e
                    progress.update(p, errors=e)

            log.info(f"  All {chunks_dispatched} chunks dispatched — draining worker pool...")
            for done in pending_results:
                p, e = done.get()
                total_processed += p
                total_errors    += e
                progress.update(p, errors=e)

    stream_conn.close()

    # ── Finalise ──────────────────────────────────────────────────────────
    stage_banner(log, 3, 3, "Finalise — write app_meta & sanity check")

    conn2 = psycopg2.connect(DB_DSN)
    with conn2.cursor() as cur:
        cur.execute("""
            INSERT INTO app_meta (key, value, updated_at)
            VALUES ('clusters_built', 'true', NOW())
            ON CONFLICT (key) DO UPDATE SET value = 'true', updated_at = NOW()
        """)
        conn2.commit()
        log.info("  clusters_built = true  ✓")

        # Sanity check — show top 5 results
        cur.execute("""
            SELECT s.name, cs.coverage_score, cs.economy_diversity,
                   cs.total_viable, cs.agriculture_count,
                   cs.hightech_count, cs.refinery_count
            FROM cluster_summary cs
            JOIN systems s ON s.id64 = cs.system_id64
            WHERE cs.coverage_score IS NOT NULL
            ORDER BY cs.coverage_score DESC
            LIMIT 5
        """)
        rows = cur.fetchall()

    conn2.close()

    elapsed = time.time() - script_start

    done_banner(log, "Cluster Summary Complete", elapsed, [
        f"Anchors processed : {fmt_num(total_processed)}",
        f"Total in table    : {fmt_num(already_done + total_processed)}",
        f"Errors            : {fmt_num(total_errors)}",
        f"Speed             : {fmt_rate(total_processed, elapsed)}",
    ])

    if rows:
        log.info("  Top 5 empire locations:")
        log.info(f"  {'System':<30} {'coverage':>8} {'div':>4} {'viable':>7} {'ag':>5} {'ht':>5} {'ref':>5}")
        log.info(f"  {'─'*30} {'─'*8} {'─'*4} {'─'*7} {'─'*5} {'─'*5} {'─'*5}")
        for r in rows:
            log.info(
                f"  {str(r[0]):<30} {r[1]:>8.1f} {r[2]:>4} {r[3]:>7,}"
                f" {r[4]:>5} {r[5]:>5} {r[6]:>5}"
            )

    log.info("")
    log.info("Next step: run sql/002_indexes.sql to build all search indexes")
    log.info("  docker exec -it ed-postgres psql -U edfinder -d edfinder \\")
    log.info("    -f /path/to/hetzner/sql/002_indexes.sql")


if __name__ == '__main__':
    main()
