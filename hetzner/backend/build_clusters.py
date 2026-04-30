#!/usr/bin/env python3
"""
ED Finder — Cluster Summary Builder (STABILIZED & OPTIMIZED)
Version: 2.9

Strategy:
  • Hybrid Approach: Iterates through "Anchors" (systems with data) but uses 
    a high-speed spatial pre-filter to skip the empty void.
  • Performance: Uses server-side cursors and parallel workers.
  • Stability: Low memory footprint. Processes in small chunks to prevent crashes.
  • Default Quality: Score 65+ (Focuses on Terraformables and ELWs).
"""

import os
import sys
import math
import time
import logging
import argparse
import multiprocessing as mp
from collections import defaultdict

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
# Version 2.9: Use the DATABASE_URL exactly as provided in the environment.
# This is the same URL that the API uses successfully.
DATABASE_URL    = os.getenv('DATABASE_URL', 'postgresql://edfinder:edfinder@postgres:5432/edfinder')
BATCH_SIZE      = 1000
LOG_LEVEL       = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE        = os.getenv('LOG_FILE', '/tmp/build_clusters.log')
DEFAULT_RADIUS  = 500   # LY
DEFAULT_SCORE   = 65    # Focus on high-quality systems (Terraformables/ELWs)

os.makedirs(os.path.dirname(os.path.abspath(LOG_FILE)), exist_ok=True)
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger('build_clusters')

# ---------------------------------------------------------------------------
# Logic
# ---------------------------------------------------------------------------

def compute_coverage_score(counts: dict, bests: dict) -> float:
    weights = {
        'Agriculture': 0.25, 'Refinery': 0.20, 'Industrial': 0.20,
        'HighTech': 0.20, 'Military': 0.10, 'Tourism': 0.05,
    }
    score = 0.0
    for eco, weight in weights.items():
        best = bests.get(eco)
        count = counts.get(eco, 0)
        if best is not None:
            count_bonus = min(count / 3.0, 1.0) * 0.1
            score += (best / 100.0 + count_bonus) * weight
    return round(min(score * 100, 100.0), 1)

def process_anchor_batch(worker_id: int, anchor_batch: list, db_url: str, radius: float, min_score: int):
    """
    Worker: For each anchor, find neighbors within 500ly that meet the score threshold.
    """
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
    except Exception as e:
        print(f"Worker {worker_id} failed to connect: {e}")
        return []

    # Load grid params
    cur.execute("SELECT key, value FROM app_meta WHERE key IN ('grid_cell_size','grid_min_x','grid_min_y','grid_min_z')")
    meta = {r[0]: float(r[1]) for r in cur.fetchall()}
    cell_size = meta.get('grid_cell_size', 500.0)
    gmin_x, gmin_y, gmin_z = meta.get('grid_min_x'), meta.get('grid_min_y'), meta.get('grid_min_z')

    results = []
    hb = WorkerHeartbeat(worker_id, total=len(anchor_batch), label="clusters", interval=60.0)

    for anchor in anchor_batch:
        aid, ax, ay, az = anchor

        # Grid cells for the search
        vcx = int(math.floor((ax - gmin_x) / cell_size))
        vcy = int(math.floor((ay - gmin_y) / cell_size))
        vcz = int(math.floor((az - gmin_z) / cell_size))
        adj_cells = []
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                for dz in range(-1, 2):
                    adj_cells.append((vcx+dx) * 100_000_000 + (vcy+dy) * 10_000 + (vcz+dz))

        # Query for viable neighbors within radius
        cur.execute("""
            SELECT 
                r.score_agriculture, r.score_refinery, r.score_industrial,
                r.score_hightech, r.score_military, r.score_tourism,
                s.id64
            FROM systems s
            JOIN ratings r ON r.system_id64 = s.id64
            WHERE s.population = 0
              AND s.grid_cell_id = ANY(%s)
              AND in_bounding_box(s.x, s.y, s.z, %s, %s, %s, %s)
              AND distance_ly(s.x, s.y, s.z, %s, %s, %s) <= %s
              AND (r.score_agriculture >= %s OR r.score_refinery >= %s OR 
                   r.score_industrial >= %s OR r.score_hightech >= %s OR 
                   r.score_military >= %s OR r.score_tourism >= %s)
        """, (adj_cells, ax, ay, az, radius, ax, ay, az, radius, min_score, min_score, min_score, min_score, min_score, min_score))
        
        neighbors = cur.fetchall()
        
        if neighbors:
            counts = defaultdict(int)
            bests = defaultdict(int)
            top_ids = defaultdict(int)
            total_viable = 0
            
            for s_ag, s_re, s_in, s_ht, s_mi, s_to, sid in neighbors:
                if sid == aid: continue
                total_viable += 1
                scores = {
                    'Agriculture': s_ag, 'Refinery': s_re, 'Industrial': s_in,
                    'HighTech': s_ht, 'Military': s_mi, 'Tourism': s_to
                }
                for eco, score in scores.items():
                    if score >= min_score:
                        counts[eco] += 1
                        if score > bests[eco]:
                            bests[eco] = score
                            top_ids[eco] = sid
            
            if total_viable > 0:
                coverage = compute_coverage_score(counts, bests)
                diversity = sum(1 for c in counts.values() if c > 0)
                
                results.append((
                    aid,
                    counts.get('Agriculture', 0), bests.get('Agriculture'), top_ids.get('Agriculture'),
                    counts.get('Refinery', 0),    bests.get('Refinery'),    top_ids.get('Refinery'),
                    counts.get('Industrial', 0),  bests.get('Industrial'),  top_ids.get('Industrial'),
                    counts.get('HighTech', 0),    bests.get('HighTech'),    top_ids.get('HighTech'),
                    counts.get('Military', 0),    bests.get('Military'),    top_ids.get('Military'),
                    counts.get('Tourism', 0),     bests.get('Tourism'),     top_ids.get('Tourism'),
                    total_viable, coverage, diversity, radius
                ))

        hb.tick()

    cur.close()
    conn.close()
    return results

def main():
    parser = argparse.ArgumentParser(description='Build cluster_summary (v2.9 - STABILIZED)')
    parser.add_argument('--workers', type=int, default=6)
    parser.add_argument('--radius', type=float, default=500.0)
    parser.add_argument('--min-score', type=int, default=DEFAULT_SCORE)
    parser.add_argument('--dirty-only', action='store_true', help='Only rebuild clusters for dirty anchors')
    args = parser.parse_args()

    script_start = time.time()
    startup_banner(log, "Cluster Summary Builder", "2.9 (Stabilized)")

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor(name='anchor_cursor')
    except Exception as e:
        log.error(f"FATAL: Main process failed to connect to database: {e}")
        sys.exit(1)

    # 1. Identify anchors to process
    if args.dirty_only:
        log.info("  Mode: Incremental (Dirty Anchors Only)")
        cur.execute("SELECT COUNT(*) FROM systems WHERE cluster_dirty = TRUE AND has_body_data = TRUE")
        total_anchors = cur.fetchone()[0]
        cur.execute("SELECT id64, x, y, z FROM systems WHERE cluster_dirty = TRUE AND has_body_data = TRUE")
    else:
        log.info("  Mode: Full Rebuild (All Anchors)")
        cur.execute("SELECT COUNT(*) FROM systems WHERE has_body_data = TRUE")
        total_anchors = cur.fetchone()[0]
        cur.execute("SELECT id64, x, y, z FROM systems WHERE has_body_data = TRUE")
    
    log.info(f"  Processing {fmt_num(total_anchors)} anchors...")

    # 2. Parallel Processing
    with mp.Pool(processes=args.workers) as pool:
        progress = ProgressReporter(log, total=total_anchors, label="anchors", interval=30)
        
        while True:
            batch = cur.fetchmany(BATCH_SIZE * args.workers)
            if not batch: break
            
            # Split batch for workers
            sub_batches = [batch[i:i + BATCH_SIZE] for i in range(0, len(batch), BATCH_SIZE)]
            
            worker_results = []
            for i, sub in enumerate(sub_batches):
                worker_results.append(pool.apply_async(process_anchor_batch, (i, sub, DATABASE_URL, args.radius, args.min_score)))
            
            # Write results
            write_batch = []
            processed_ids = []
            for r in worker_results:
                res = r.get()
                write_batch.extend(res)
            
            # We also need the IDs of all anchors in the batch to clear their dirty flags
            processed_ids = [a[0] for a in batch]
            
            if write_batch:
                _write_to_db(write_batch)
            
            # Clear dirty flags
            _clear_dirty_flags(processed_ids)
            
            progress.update(len(batch))

    # Finalize meta
    cur_meta = conn.cursor()
    cur_meta.execute("INSERT INTO app_meta (key, value, updated_at) VALUES ('clusters_built', 'true', NOW()) ON CONFLICT (key) DO UPDATE SET value = 'true', updated_at = NOW()")
    conn.commit()
    
    elapsed = time.time() - script_start
    done_banner(log, "Stabilized Cluster Build Complete", elapsed, [
        f"Anchors processed : {fmt_num(total_anchors)}",
        f"Total time        : {fmt_duration(elapsed)}",
    ])

def _write_to_db(batch):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
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
            agriculture_count = EXCLUDED.agriculture_count,
            agriculture_best  = EXCLUDED.agriculture_best,
            agriculture_top_id = EXCLUDED.agriculture_top_id,
            refinery_count    = EXCLUDED.refinery_count,
            refinery_best     = EXCLUDED.refinery_best,
            refinery_top_id   = EXCLUDED.refinery_top_id,
            industrial_count  = EXCLUDED.industrial_count,
            industrial_best   = EXCLUDED.industrial_best,
            industrial_top_id = EXCLUDED.industrial_top_id,
            hightech_count    = EXCLUDED.hightech_count,
            hightech_best     = EXCLUDED.hightech_best,
            hightech_top_id   = EXCLUDED.hightech_top_id,
            military_count    = EXCLUDED.military_count,
            military_best     = EXCLUDED.military_best,
            military_top_id   = EXCLUDED.military_top_id,
            tourism_count     = EXCLUDED.tourism_count,
            tourism_best      = EXCLUDED.tourism_best,
            tourism_top_id    = EXCLUDED.tourism_top_id,
            total_viable      = EXCLUDED.total_viable,
            coverage_score    = EXCLUDED.coverage_score,
            economy_diversity = EXCLUDED.economy_diversity,
            dirty             = FALSE,
            updated_at        = NOW()
    """, batch, template="""(%s,
        %s,%s,%s, %s,%s,%s, %s,%s,%s,
        %s,%s,%s, %s,%s,%s, %s,%s,%s,
        %s,%s,%s, %s, FALSE, NOW(), NOW())""", page_size=100)
    conn.commit()
    cur.close()
    conn.close()

def _clear_dirty_flags(ids):
    if not ids: return
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("UPDATE systems SET cluster_dirty = FALSE WHERE id64 = ANY(%s)", (ids,))
    conn.commit()
    cur.close()
    conn.close()

if __name__ == '__main__':
    main()
