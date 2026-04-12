#!/usr/bin/env python3
"""
ED Finder — Ratings Computer
Version: 1.0

Ports the JavaScript rateSystem() function to Python exactly.
Computes scores for all visited systems and writes to the ratings table.

Features:
  • Parallel processing (multiprocessing — uses all CPU cores)
  • Processes only systems with body data (has_body_data = TRUE)
  • Skips systems already rated unless --rebuild flag passed
  • Batch writes to ratings table
  • Progress reporting

Usage:
    python3 build_ratings.py              # rate all unrated visited systems
    python3 build_ratings.py --rebuild    # re-rate all visited systems
    python3 build_ratings.py --dirty      # only re-rate systems flagged dirty
    python3 build_ratings.py --workers 8  # set worker count (default: CPU count)

Runtime estimate: ~2-4 hours for 70M visited systems on i7-8700
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
DB_DSN     = os.getenv('DATABASE_URL', 'postgresql://edfinder:edfinder@localhost:5432/edfinder')
BATCH_SIZE = int(os.getenv('BATCH_SIZE', '1000'))
LOG_LEVEL  = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE   = os.getenv('LOG_FILE', '/data/logs/build_ratings.log')

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger('build_ratings')

# ---------------------------------------------------------------------------
# Scoring constants — must mirror frontend rateSystem() exactly
# ---------------------------------------------------------------------------

# Economy score weights
ECO_WEIGHTS = {
    'Agriculture': {
        'elw':          40,
        'ww':           20,
        'terraformable': 15,
        'bio':          10,
        'landable':      5,
        'starBonus':    10,
    },
    'Refinery': {
        'rocky':        25,
        'metalRich':    25,
        'hmc':          20,
        'icy':          15,
        'rockyIce':     15,
    },
    'Industrial': {
        'gasGiant':     30,
        'rockyIce':     20,
        'icy':          20,
        'hmc':          15,
        'rocky':        15,
    },
    'HighTech': {
        'elw':          35,
        'ammonia':      25,
        'gasGiant':     20,
        'blackHole':    10,
        'neutron':      10,
    },
    'Military': {
        'gasGiant':     30,
        'landable':     20,
        'rocky':        20,
        'blackHole':    15,
        'neutron':      15,
    },
    'Tourism': {
        'elw':          25,
        'blackHole':    25,
        'neutron':      20,
        'ammonia':      15,
        'ww':           15,
    },
}

# Scoopable star types (bonus for Agriculture — warm star = habitable zone)
SCOOPABLE_STARS = {'G', 'K', 'F', 'A'}

# Economy-suggesting body thresholds
ECO_THRESHOLDS = {
    'Agriculture': {'elw': 1, 'ww': 1},
    'Refinery':    {'rocky': 3, 'metalRich': 1},
    'Industrial':  {'gasGiant': 2, 'rockyIce': 2},
    'HighTech':    {'elw': 1, 'ammonia': 1},
    'Military':    {'gasGiant': 2, 'landable': 3},
    'Tourism':     {'blackHole': 1, 'neutron': 1},
}


def count_bodies(bodies: list) -> dict:
    """Count bodies by type — mirrors frontend countBodyTypes()."""
    counts = {
        'elw': 0, 'ww': 0, 'ammonia': 0, 'gasGiant': 0,
        'rocky': 0, 'metalRich': 0, 'icy': 0, 'rockyIce': 0,
        'hmc': 0, 'landable': 0, 'terraformable': 0,
        'bio': 0, 'geo': 0, 'neutron': 0, 'blackHole': 0,
        'whiteDwarf': 0,
    }
    for b in bodies:
        sub = str(b.get('subtype') or b.get('sub_type') or '').lower()
        if b.get('is_earth_like') or 'earth-like' in sub:
            counts['elw'] += 1
        if b.get('is_water_world') or 'water world' in sub:
            counts['ww'] += 1
        if b.get('is_ammonia_world') or 'ammonia' in sub:
            counts['ammonia'] += 1
        if 'gas giant' in sub or 'gas_giant' in sub:
            counts['gasGiant'] += 1
        if 'rocky body' in sub or sub == 'rocky':
            counts['rocky'] += 1
        if 'metal-rich' in sub or 'metal rich' in sub:
            counts['metalRich'] += 1
        if 'icy body' in sub or sub == 'icy':
            counts['icy'] += 1
        if 'rocky ice' in sub:
            counts['rockyIce'] += 1
        if 'high metal content' in sub:
            counts['hmc'] += 1
        if b.get('is_landable'):
            counts['landable'] += 1
        if b.get('is_terraformable'):
            counts['terraformable'] += 1
        counts['bio'] += int(b.get('bio_signal_count') or 0)
        counts['geo'] += int(b.get('geo_signal_count') or 0)
        if 'neutron' in sub:
            counts['neutron'] += 1
        if 'black hole' in sub:
            counts['blackHole'] += 1
        if 'white dwarf' in sub:
            counts['whiteDwarf'] += 1
    return counts


def score_economy(counts: dict, eco: str, star_type: Optional[str]) -> int:
    """Score a system for a specific economy type (0-100)."""
    weights = ECO_WEIGHTS.get(eco, {})
    raw = 0

    raw += min(counts['elw'],          4) * weights.get('elw',          0)
    raw += min(counts['ww'],           4) * weights.get('ww',           0)
    raw += min(counts['ammonia'],      3) * weights.get('ammonia',       0)
    raw += min(counts['gasGiant'],    15) * weights.get('gasGiant',      0) // max(counts['gasGiant'], 1)  # diminishing returns
    raw += min(counts['rocky'],       10) * weights.get('rocky',         0) // max(min(counts['rocky'], 10), 1)
    raw += min(counts['metalRich'],    8) * weights.get('metalRich',     0) // max(min(counts['metalRich'], 8), 1)
    raw += min(counts['icy'],         10) * weights.get('icy',           0) // max(min(counts['icy'], 10), 1)
    raw += min(counts['rockyIce'],    10) * weights.get('rockyIce',      0) // max(min(counts['rockyIce'], 10), 1)
    raw += min(counts['hmc'],         10) * weights.get('hmc',           0) // max(min(counts['hmc'], 10), 1)
    raw += min(counts['landable'],    20) * weights.get('landable',      0) // max(min(counts['landable'], 20), 1)
    raw += min(counts['terraformable'], 5) * weights.get('terraformable', 0)
    raw += min(counts['bio'],         20) * weights.get('bio',           0) // max(min(counts['bio'], 20), 1)
    raw += min(counts['neutron'],      2) * weights.get('neutron',       0)
    raw += min(counts['blackHole'],    1) * weights.get('blackHole',     0)

    # Star type bonus for Agriculture (warm main star = better habitable zone)
    if eco == 'Agriculture' and star_type:
        if star_type[0].upper() in SCOOPABLE_STARS:
            raw += weights.get('starBonus', 0)

    return min(int(raw), 100)


def rate_system(system_id64: int, bodies: list, main_star_type: Optional[str]) -> dict:
    """
    Compute full rating for a system.
    Returns dict matching the ratings table columns.
    Mirrors frontend rateSystem() exactly.
    """
    counts = count_bodies(bodies)

    scores = {
        'Agriculture': score_economy(counts, 'Agriculture', main_star_type),
        'Refinery':    score_economy(counts, 'Refinery',    main_star_type),
        'Industrial':  score_economy(counts, 'Industrial',  main_star_type),
        'HighTech':    score_economy(counts, 'HighTech',    main_star_type),
        'Military':    score_economy(counts, 'Military',    main_star_type),
        'Tourism':     score_economy(counts, 'Tourism',     main_star_type),
    }

    # Overall score = weighted average (Agriculture + HighTech weighted higher)
    overall = int(
        scores['Agriculture'] * 0.20 +
        scores['Refinery']    * 0.18 +
        scores['Industrial']  * 0.18 +
        scores['HighTech']    * 0.20 +
        scores['Military']    * 0.12 +
        scores['Tourism']     * 0.12
    )

    # Best economy suggestion
    best_eco  = max(scores, key=scores.get)
    best_score = scores[best_eco]
    economy_suggestion = best_eco if best_score >= 20 else None

    # Score breakdown for frontend popover
    breakdown = {
        'economies': scores,
        'bodies': {k: v for k, v in counts.items() if v > 0},
    }

    return {
        'system_id64':      system_id64,
        'score':            overall,
        'score_agriculture': scores['Agriculture'],
        'score_refinery':   scores['Refinery'],
        'score_industrial': scores['Industrial'],
        'score_hightech':   scores['HighTech'],
        'score_military':   scores['Military'],
        'score_tourism':    scores['Tourism'],
        'economy_suggestion': economy_suggestion,
        'elw_count':        counts['elw'],
        'ww_count':         counts['ww'],
        'ammonia_count':    counts['ammonia'],
        'gas_giant_count':  counts['gasGiant'],
        'rocky_count':      counts['rocky'],
        'metal_rich_count': counts['metalRich'],
        'icy_count':        counts['icy'],
        'rocky_ice_count':  counts['rockyIce'],
        'hmc_count':        counts['hmc'],
        'landable_count':   counts['landable'],
        'terraformable_count': counts['terraformable'],
        'bio_signal_total': counts['bio'],
        'geo_signal_total': counts['geo'],
        'neutron_count':    counts['neutron'],
        'black_hole_count': counts['blackHole'],
        'white_dwarf_count': counts['whiteDwarf'],
        'score_breakdown':  breakdown,
    }


# ---------------------------------------------------------------------------
# Worker function (runs in separate process)
# ---------------------------------------------------------------------------
def worker_process(worker_id: int, system_batch: list, db_dsn: str) -> tuple[int, int]:
    """
    Process a batch of systems, fetch their bodies, compute ratings,
    write to DB. Returns (processed_count, error_count).
    """
    conn = psycopg2.connect(db_dsn)
    conn.autocommit = False
    cur = conn.cursor()

    processed = 0
    errors = 0
    rating_batch = []

    for system_id64, main_star_type in system_batch:
        try:
            # Fetch bodies for this system
            cur.execute("""
                SELECT subtype, is_earth_like, is_water_world, is_ammonia_world,
                       is_landable, is_terraformable,
                       bio_signal_count, geo_signal_count
                FROM bodies
                WHERE system_id64 = %s
            """, (system_id64,))

            bodies = [
                {
                    'subtype':           r[0],
                    'is_earth_like':     r[1],
                    'is_water_world':    r[2],
                    'is_ammonia_world':  r[3],
                    'is_landable':       r[4],
                    'is_terraformable':  r[5],
                    'bio_signal_count':  r[6],
                    'geo_signal_count':  r[7],
                }
                for r in cur.fetchall()
            ]

            rating = rate_system(system_id64, bodies, main_star_type)
            rating_batch.append(rating)
            processed += 1

        except Exception as e:
            errors += 1
            continue

        # Write batch
        if len(rating_batch) >= BATCH_SIZE:
            _write_ratings(conn, cur, rating_batch)
            rating_batch = []

    # Write remainder
    if rating_batch:
        _write_ratings(conn, cur, rating_batch)

    # Mark systems as clean
    id64s = [s[0] for s in system_batch]
    if id64s:
        psycopg2.extras.execute_values(cur, """
            UPDATE systems SET rating_dirty = FALSE
            WHERE id64 IN %s
        """, [(tuple(id64s),)])
        conn.commit()

    cur.close()
    conn.close()
    return processed, errors


def _write_ratings(conn, cur, batch: list):
    """Upsert a batch of rating records."""
    import json as _json
    rows = [(
        r['system_id64'],
        r['score'],
        r['score_agriculture'], r['score_refinery'],
        r['score_industrial'],  r['score_hightech'],
        r['score_military'],    r['score_tourism'],
        r['economy_suggestion'],
        r['elw_count'],         r['ww_count'],
        r['ammonia_count'],     r['gas_giant_count'],
        r['rocky_count'],       r['metal_rich_count'],
        r['icy_count'],         r['rocky_ice_count'],
        r['hmc_count'],         r['landable_count'],
        r['terraformable_count'],
        r['bio_signal_total'],  r['geo_signal_total'],
        r['neutron_count'],     r['black_hole_count'],
        r['white_dwarf_count'],
        _json.dumps(r['score_breakdown']),
    ) for r in batch]

    psycopg2.extras.execute_values(cur, """
        INSERT INTO ratings (
            system_id64, score,
            score_agriculture, score_refinery, score_industrial,
            score_hightech, score_military, score_tourism,
            economy_suggestion,
            elw_count, ww_count, ammonia_count, gas_giant_count,
            rocky_count, metal_rich_count, icy_count, rocky_ice_count,
            hmc_count, landable_count, terraformable_count,
            bio_signal_total, geo_signal_total,
            neutron_count, black_hole_count, white_dwarf_count,
            score_breakdown, updated_at
        ) VALUES %s
        ON CONFLICT (system_id64) DO UPDATE SET
            score               = EXCLUDED.score,
            score_agriculture   = EXCLUDED.score_agriculture,
            score_refinery      = EXCLUDED.score_refinery,
            score_industrial    = EXCLUDED.score_industrial,
            score_hightech      = EXCLUDED.score_hightech,
            score_military      = EXCLUDED.score_military,
            score_tourism       = EXCLUDED.score_tourism,
            economy_suggestion  = EXCLUDED.economy_suggestion,
            elw_count           = EXCLUDED.elw_count,
            ww_count            = EXCLUDED.ww_count,
            ammonia_count       = EXCLUDED.ammonia_count,
            gas_giant_count     = EXCLUDED.gas_giant_count,
            rocky_count         = EXCLUDED.rocky_count,
            metal_rich_count    = EXCLUDED.metal_rich_count,
            icy_count           = EXCLUDED.icy_count,
            rocky_ice_count     = EXCLUDED.rocky_ice_count,
            hmc_count           = EXCLUDED.hmc_count,
            landable_count      = EXCLUDED.landable_count,
            terraformable_count = EXCLUDED.terraformable_count,
            bio_signal_total    = EXCLUDED.bio_signal_total,
            geo_signal_total    = EXCLUDED.geo_signal_total,
            neutron_count       = EXCLUDED.neutron_count,
            black_hole_count    = EXCLUDED.black_hole_count,
            white_dwarf_count   = EXCLUDED.white_dwarf_count,
            score_breakdown     = EXCLUDED.score_breakdown,
            updated_at          = NOW()
        """,
        [(r + (psycopg2.extras.Json(None),))[:26] + (rows[i][-1],)
         for i, r in enumerate(rows)],
        template="(%s,%s,%s,%s,%s,%s,%s,%s,%s::economy_type,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())",
        page_size=BATCH_SIZE,
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='Build pre-computed ratings')
    parser.add_argument('--rebuild',  action='store_true', help='Re-rate all systems, not just unrated')
    parser.add_argument('--dirty',    action='store_true', help='Only re-rate dirty systems')
    parser.add_argument('--workers',  type=int, default=mp.cpu_count(), help='Worker processes')
    parser.add_argument('--limit',    type=int, default=None, help='Process at most N systems (testing)')
    args = parser.parse_args()

    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()

    # Build list of systems to rate
    if args.dirty:
        log.info("Loading dirty systems ...")
        cur.execute("""
            SELECT s.id64, s.main_star_type
            FROM systems s
            WHERE s.has_body_data = TRUE
              AND s.rating_dirty  = TRUE
            ORDER BY s.id64
            LIMIT %s
        """, (args.limit or 10_000_000,))
    elif args.rebuild:
        log.info("Loading ALL visited systems for full rebuild ...")
        cur.execute("""
            SELECT s.id64, s.main_star_type
            FROM systems s
            WHERE s.has_body_data = TRUE
            ORDER BY s.id64
            LIMIT %s
        """, (args.limit or 200_000_000,))
    else:
        log.info("Loading unrated visited systems ...")
        cur.execute("""
            SELECT s.id64, s.main_star_type
            FROM systems s
            LEFT JOIN ratings r ON r.system_id64 = s.id64
            WHERE s.has_body_data = TRUE
              AND r.system_id64 IS NULL
            ORDER BY s.id64
            LIMIT %s
        """, (args.limit or 200_000_000,))

    all_systems = cur.fetchall()
    total = len(all_systems)
    cur.close()
    conn.close()

    log.info(f"Systems to rate: {total:,}")
    if total == 0:
        log.info("Nothing to do.")
        return

    # Split into worker chunks
    chunk_size = max(BATCH_SIZE * 10, total // args.workers)
    chunks = [all_systems[i:i+chunk_size] for i in range(0, total, chunk_size)]
    log.info(f"Using {args.workers} workers, {len(chunks)} chunks of ~{chunk_size:,} systems each")

    start = time.time()
    total_processed = 0
    total_errors = 0

    with mp.Pool(processes=args.workers) as pool:
        results = pool.starmap(
            worker_process,
            [(i, chunk, DB_DSN) for i, chunk in enumerate(chunks)]
        )

    for processed, errors in results:
        total_processed += processed
        total_errors += errors

    elapsed = time.time() - start
    rate = total_processed / elapsed if elapsed > 0 else 0
    log.info(f"Ratings complete: {total_processed:,} systems in {elapsed/3600:.2f}h ({rate:.0f}/s)")
    if total_errors:
        log.warning(f"Errors: {total_errors:,}")

    # Mark ratings as built in app_meta
    conn = psycopg2.connect(DB_DSN)
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO app_meta (key, value, updated_at)
            VALUES ('ratings_built', 'true', NOW())
            ON CONFLICT (key) DO UPDATE SET value = 'true', updated_at = NOW()
        """)
    conn.commit()
    conn.close()

    log.info("Next step: python3 build_grid.py")


if __name__ == '__main__':
    main()
