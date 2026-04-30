#!/usr/bin/env python3
"""
ED Finder — Cluster Summary Builder (HIGH PERFORMANCE)
Version: 2.0  (Bottom-Up Strategy)

Speedup Strategy:
  Original (v1.x): For each of 73M anchors, find neighbors within 500ly.
                   73M queries * ~38k rows/query = ~2.7 Trillion row-checks.
                   ETA: 7 months.

  New (v2.0):      1. Identify all "Viable Systems" (score >= 40, population = 0).
                      (Only ~5-10M systems vs 186M total).
                   2. For each viable system, find all "Anchors" (has_body_data = TRUE)
                      within 500ly of IT.
                   3. Increment counts and track best scores for those anchors.
                   4. Batch-write the final aggregates.

  Benefits:        • Only processes regions of space that actually HAVE viable systems.
                   • Skips millions of empty anchors in the void.
                   • Uses a single pass over the viable systems.
                   • ETA: ~4-8 hours.
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
def _make_direct_dsn(url: str) -> str:
    direct = os.getenv('DB_DSN_DIRECT', '')
    if direct: return direct
    if ':5433/' in url: url = url.replace(':5433/', ':5432/')
    url = url.replace('@pgbouncer:', '@postgres:')
    return url

DB_DSN          = _make_direct_dsn(os.getenv('DATABASE_URL', 'postgresql://edfinder:edfinder@localhost:5432/edfinder'))
BATCH_SIZE      = 5000  # Larger batches for the bottom-up approach
LOG_LEVEL       = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE        = os.getenv('LOG_FILE', '/tmp/build_clusters.log')
DEFAULT_RADIUS  = 500   # LY
MIN_VIABLE      = 40    # minimum score to count as "viable"

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

def process_viable_batch(worker_id: int, viable_batch: list, db_dsn: str, radius: float):
    """
    Worker: For each viable system, find all anchors within 500ly.
    Returns a mapping: {anchor_id: {eco: (count, best_score, best_id)}}
    """
    conn = psycopg2.connect(db_dsn)
    cur = conn.cursor()

    # Load grid params
    cur.execute("SELECT key, value FROM app_meta WHERE key IN ('grid_cell_size','grid_min_x','grid_min_y','grid_min_z')")
    meta = {r[0]: float(r[1]) for r in cur.fetchall()}
    cell_size = meta.get('grid_cell_size', 500.0)
    gmin_x, gmin_y, gmin_z = meta.get('grid_min_x'), meta.get('grid_min_y'), meta.get('grid_min_z')

    # Local aggregation for this batch
    # { anchor_id: { eco: [count, best_score, best_sid] } }
    local_agg = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))
    # { anchor_id: set(viable_sids) } for total_viable count
    local_viable_sets = defaultdict(set)

    hb = WorkerHeartbeat(worker_id, total=len(viable_batch), label="mapping", interval=60.0)

    for viable in viable_batch:
        sid, vx, vy, vz, eco_sug, s_ag, s_re, s_in, s_ht, s_mi, s_to = viable
        scores = {
            'Agriculture': s_ag, 'Refinery': s_re, 'Industrial': s_in,
            'HighTech': s_ht, 'Military': s_mi, 'Tourism': s_to
        }

        # Grid cells for the search
        vcx = int(math.floor((vx - gmin_x) / cell_size))
        vcy = int(math.floor((vy - gmin_y) / cell_size))
        vcz = int(math.floor((vz - gmin_z) / cell_size))
        adj_cells = []
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                for dz in range(-1, 2):
                    adj_cells.append((vcx+dx) * 100_000_000 + (vcy+dy) * 10_000 + (vcz+dz))

        # Find anchors (has_body_data) in these cells
        cur.execute("""
            SELECT id64 FROM systems
            WHERE has_body_data = TRUE
              AND grid_cell_id = ANY(%s)
              AND in_bounding_box(x, y, z, %s, %s, %s, %s)
              AND distance_ly(x, y, z, %s, %s, %s) <= %s
        """, (adj_cells, vx, vy, vz, radius, vx, vy, vz, radius))
        
        anchors = cur.fetchall()
        for (a_id,) in anchors:
            if a_id == sid: continue # Don't count self if anchor
            local_viable_sets[a_id].add(sid)
            for eco, score in scores.items():
                if score and score >= MIN_VIABLE:
                    stats = local_agg[a_id][eco]
                    stats[0] += 1 # count
                    if score > stats[1]:
                        stats[1] = score
                        stats[2] = sid # best_id

        hb.tick()

    cur.close()
    conn.close()
    
    # Convert sets to counts for serialization
    final_viable_counts = {aid: len(sids) for aid, sids in local_viable_sets.items()}
    return dict(local_agg), final_viable_counts

def main():
    parser = argparse.ArgumentParser(description='Build cluster_summary (v2.0 - HIGH PERFORMANCE)')
    parser.add_argument('--workers', type=int, default=6)
    parser.add_argument('--radius', type=float, default=500.0)
    parser.add_argument('--min-score', type=int, default=40)
    args = parser.parse_args()

    script_start = time.time()
    startup_banner(log, "Cluster Summary Builder", "2.0 (Bottom-Up)")

    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()

    # 1. Get all viable systems
    stage_banner(log, 1, 3, "Identify viable systems")
    cur.execute("""
        SELECT 
            s.id64, s.x, s.y, s.z, r.economy_suggestion,
            r.score_agriculture, r.score_refinery, r.score_industrial,
            r.score_hightech, r.score_military, r.score_tourism
        FROM systems s
        JOIN ratings r ON r.system_id64 = s.id64
        WHERE s.population = 0
          AND (r.score_agriculture >= %s OR r.score_refinery >= %s OR 
               r.score_industrial >= %s OR r.score_hightech >= %s OR 
               r.score_military >= %s OR r.score_tourism >= %s)
    """, [args.min_score]*6)
    
    viable_systems = cur.fetchall()
    log.info(f"  Found {fmt_num(len(viable_systems))} viable systems to map.")

    # 2. Map viable systems to anchors in parallel
    stage_banner(log, 2, 3, "Map viable systems to anchors")
    chunk_size = 2000
    chunks = [viable_systems[i:i + chunk_size] for i in range(0, len(viable_systems), chunk_size)]
    
    # Global aggregation
    # anchor_id -> { eco: [count, best_score, best_sid] }
    global_agg = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))
    global_viable_counts = defaultdict(int)

    with mp.Pool(processes=args.workers) as pool:
        results = []
        for i, chunk in enumerate(chunks):
            results.append(pool.apply_async(process_viable_batch, (i, chunk, DB_DSN, args.radius)))
        
        progress = ProgressReporter(log, total=len(viable_systems), label="mapping", interval=30)
        for r in results:
            batch_agg, batch_viable_counts = r.get()
            # Merge into global
            for aid, ecos in batch_agg.items():
                for eco, stats in ecos.items():
                    g_stats = global_agg[aid][eco]
                    g_stats[0] += stats[0]
                    if stats[1] > g_stats[1]:
                        g_stats[1] = stats[1]
                        g_stats[2] = stats[2]
            for aid, count in batch_viable_counts.items():
                global_viable_counts[aid] += count
            progress.update(chunk_size)

    # 3. Finalize and Write
    stage_banner(log, 3, 3, "Compute coverage and write to DB")
    
    # Clear old summary (Bottom-up requires a clean slate or careful delta)
    log.info("  Clearing cluster_summary table for fresh build...")
    cur.execute("TRUNCATE TABLE cluster_summary")
    conn.commit()

    write_batch = []
    log.info(f"  Finalizing {fmt_num(len(global_agg))} anchor summaries...")
    
    for aid, ecos in global_agg.items():
        counts = {eco: stats[0] for eco, stats in ecos.items()}
        bests = {eco: stats[1] for eco, stats in ecos.items()}
        top_ids = {eco: stats[2] for eco, stats in ecos.items()}
        
        coverage = compute_coverage_score(counts, bests)
        diversity = sum(1 for c in counts.values() if c > 0)
        total_viable = global_viable_counts[aid]

        write_batch.append((
            aid,
            counts.get('Agriculture', 0), bests.get('Agriculture'), top_ids.get('Agriculture'),
            counts.get('Refinery', 0),    bests.get('Refinery'),    top_ids.get('Refinery'),
            counts.get('Industrial', 0),  bests.get('Industrial'),  top_ids.get('Industrial'),
            counts.get('HighTech', 0),    bests.get('HighTech'),    top_ids.get('HighTech'),
            counts.get('Military', 0),    bests.get('Military'),    top_ids.get('Military'),
            counts.get('Tourism', 0),     bests.get('Tourism'),     top_ids.get('Tourism'),
            total_viable, coverage, diversity, args.radius
        ))

        if len(write_batch) >= BATCH_SIZE:
            _bulk_insert(cur, write_batch)
            write_batch = []
            conn.commit()

    if write_batch:
        _bulk_insert(cur, write_batch)
        conn.commit()

    # Finalize meta
    cur.execute("INSERT INTO app_meta (key, value, updated_at) VALUES ('clusters_built', 'true', NOW()) ON CONFLICT (key) DO UPDATE SET value = 'true', updated_at = NOW()")
    cur.execute("UPDATE systems SET cluster_dirty = FALSE")
    conn.commit()
    cur.close()
    conn.close()

    elapsed = time.time() - script_start
    done_banner(log, "High-Speed Cluster Build Complete", elapsed, [
        f"Anchors computed : {fmt_num(len(global_agg))}",
        f"Viable systems mapped: {fmt_num(len(viable_systems))}",
        f"Total time : {fmt_duration(elapsed)}",
    ])

def _bulk_insert(cur, batch):
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
    """, batch, template="""(%s,
        %s,%s,%s, %s,%s,%s, %s,%s,%s,
        %s,%s,%s, %s,%s,%s, %s,%s,%s,
        %s,%s,%s, %s, FALSE, NOW(), NOW())""", page_size=len(batch))

if __name__ == '__main__':
    main()
