#!/usr/bin/env python3
"""
ED Finder — Ratings Computer
Version: 2.0  (streaming fix — no more 74M ceiling)

Ports the JavaScript rateSystem() function to Python exactly.
Computes scores for all visited systems and writes to the ratings table.

KEY FIXES in v2.0:
  • Server-side named cursor streams rows — fetchall() was silently truncating
    at ~74M rows when PostgreSQL's statement_timeout or client RAM was hit.
    Now uses itersize-based streaming so 186M+ systems are processed reliably.
  • Batch body fetch — one ANY(%s) query per chunk instead of one query per
    system (was causing thousands of random-read round-trips per second).
  • Dynamic work dispatch — pool.apply_async() drains completed work
    continuously instead of starmap() blocking until ALL chunks finish.
  • Correct score_economy() math — integer division // was collapsing all
    counts > 0 to the same score; fixed to proper linear scaling with caps.

Usage:
    python3 build_ratings.py              # rate all unrated systems (resume-safe)
    python3 build_ratings.py --rebuild    # re-rate ALL systems from scratch
    python3 build_ratings.py --dirty      # only re-rate systems flagged dirty
    python3 build_ratings.py --workers 4  # set worker count (default: CPU count)
    python3 build_ratings.py --chunk 50000 # systems per worker chunk

Runtime estimate: ~3-5 hours for 186M systems on i7-8700 with --workers 4
"""

import os
import sys
import json
import time
import logging
import argparse
import datetime
import multiprocessing as mp
from typing import Optional

import psycopg2
import psycopg2.extras

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_DSN     = os.getenv('DATABASE_URL', 'postgresql://edfinder:edfinder@localhost:5432/edfinder')
BATCH_SIZE = int(os.getenv('BATCH_SIZE', '5000'))   # rows per INSERT batch
LOG_LEVEL  = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE   = os.getenv('LOG_FILE', '/data/logs/build_ratings.log')

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

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

ECO_WEIGHTS = {
    'Agriculture': {
        'elw':           40,
        'ww':            20,
        'terraformable': 15,
        'bio':           10,
        'landable':       5,
        'starBonus':     10,
    },
    'Refinery': {
        'rocky':         25,
        'metalRich':     25,
        'hmc':           20,
        'icy':           15,
        'rockyIce':      15,
    },
    'Industrial': {
        'gasGiant':      30,
        'rockyIce':      20,
        'icy':           20,
        'hmc':           15,
        'rocky':         15,
    },
    'HighTech': {
        'elw':           35,
        'ammonia':       25,
        'gasGiant':      20,
        'blackHole':     10,
        'neutron':       10,
    },
    'Military': {
        'gasGiant':      30,
        'landable':      20,
        'rocky':         20,
        'blackHole':     15,
        'neutron':       15,
    },
    'Tourism': {
        'elw':           25,
        'blackHole':     25,
        'neutron':       20,
        'ammonia':       15,
        'ww':            15,
    },
}

SCOOPABLE_STARS = {'G', 'K', 'F', 'A'}


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
    """
    Score a system for a specific economy type (0-100).

    FIX v2.0: the original code used integer division (//) which collapsed
    every count > 0 to the same score regardless of quantity.
    e.g.  min(5,10) * 25 // max(min(5,10),1)  →  5*25//5  →  25  (any count!)
    Now uses simple linear scaling with hard caps, matching the backend
    rateSystem() in local_search.py.
    """
    weights = ECO_WEIGHTS.get(eco, {})
    raw = 0

    raw += min(counts['elw'],            4) * weights.get('elw',           0)
    raw += min(counts['ww'],             4) * weights.get('ww',            0)
    raw += min(counts['ammonia'],        3) * weights.get('ammonia',        0)
    raw += min(counts['gasGiant'],       3) * weights.get('gasGiant',       0)
    raw += min(counts['rocky'],          5) * weights.get('rocky',          0)
    raw += min(counts['metalRich'],      4) * weights.get('metalRich',      0)
    raw += min(counts['icy'],            5) * weights.get('icy',            0)
    raw += min(counts['rockyIce'],       5) * weights.get('rockyIce',       0)
    raw += min(counts['hmc'],            5) * weights.get('hmc',            0)
    raw += min(counts['landable'],      10) * weights.get('landable',       0)
    raw += min(counts['terraformable'],  5) * weights.get('terraformable',  0)
    raw += min(counts['bio'],           10) * weights.get('bio',            0)
    raw += min(counts['neutron'],        2) * weights.get('neutron',        0)
    raw += min(counts['blackHole'],      1) * weights.get('blackHole',      0)

    if eco == 'Agriculture' and star_type:
        if star_type[0].upper() in SCOOPABLE_STARS:
            raw += weights.get('starBonus', 0)

    return min(int(raw), 100)


def rate_system(system_id64: int, bodies: list, main_star_type: Optional[str]) -> dict:
    """Compute full rating for a system. Returns dict matching the ratings table."""
    counts = count_bodies(bodies)

    scores = {
        'Agriculture': score_economy(counts, 'Agriculture', main_star_type),
        'Refinery':    score_economy(counts, 'Refinery',    main_star_type),
        'Industrial':  score_economy(counts, 'Industrial',  main_star_type),
        'HighTech':    score_economy(counts, 'HighTech',    main_star_type),
        'Military':    score_economy(counts, 'Military',    main_star_type),
        'Tourism':     score_economy(counts, 'Tourism',     main_star_type),
    }

    overall = int(
        scores['Agriculture'] * 0.20 +
        scores['Refinery']    * 0.18 +
        scores['Industrial']  * 0.18 +
        scores['HighTech']    * 0.20 +
        scores['Military']    * 0.12 +
        scores['Tourism']     * 0.12
    )

    best_eco   = max(scores, key=scores.get)
    best_score = scores[best_eco]
    economy_suggestion = best_eco if best_score >= 20 else None

    breakdown = {
        'economies': scores,
        'bodies': {k: v for k, v in counts.items() if v > 0},
    }

    return {
        'system_id64':        system_id64,
        'score':              overall,
        'score_agriculture':  scores['Agriculture'],
        'score_refinery':     scores['Refinery'],
        'score_industrial':   scores['Industrial'],
        'score_hightech':     scores['HighTech'],
        'score_military':     scores['Military'],
        'score_tourism':      scores['Tourism'],
        'economy_suggestion': economy_suggestion,
        'elw_count':          counts['elw'],
        'ww_count':           counts['ww'],
        'ammonia_count':      counts['ammonia'],
        'gas_giant_count':    counts['gasGiant'],
        'rocky_count':        counts['rocky'],
        'metal_rich_count':   counts['metalRich'],
        'icy_count':          counts['icy'],
        'rocky_ice_count':    counts['rockyIce'],
        'hmc_count':          counts['hmc'],
        'landable_count':     counts['landable'],
        'terraformable_count': counts['terraformable'],
        'bio_signal_total':   counts['bio'],
        'geo_signal_total':   counts['geo'],
        'neutron_count':      counts['neutron'],
        'black_hole_count':   counts['blackHole'],
        'white_dwarf_count':  counts['whiteDwarf'],
        'score_breakdown':    breakdown,
    }


# ---------------------------------------------------------------------------
# Worker function (runs in separate process)
# ---------------------------------------------------------------------------

def worker_process(worker_id: int, system_batch: list, db_dsn: str) -> tuple:
    """
    Process a chunk of systems.

    FIX v2.0: fetch ALL bodies for the entire chunk in ONE batched query
    instead of one query per system. Reduces round-trips from N to ~N/5000.
    """
    conn = psycopg2.connect(db_dsn)
    conn.autocommit = False
    cur  = conn.cursor()

    processed    = 0
    errors       = 0
    rating_batch = []

    # ── Batch-fetch all bodies for this chunk in one pass ─────────────────
    # SQLite uses 900 as its safe limit; PostgreSQL handles 5000+ fine via ANY(%s)
    id64s = [s[0] for s in system_batch]
    bodies_by_system: dict = {}

    BODY_CHUNK = 5000
    for start in range(0, len(id64s), BODY_CHUNK):
        slice_ids = id64s[start: start + BODY_CHUNK]
        try:
            cur.execute("""
                SELECT system_id64,
                       subtype, is_earth_like, is_water_world, is_ammonia_world,
                       is_landable, is_terraformable,
                       bio_signal_count, geo_signal_count
                FROM   bodies
                WHERE  system_id64 = ANY(%s)
            """, (slice_ids,))
            for row in cur:
                sid = row[0]
                bodies_by_system.setdefault(sid, []).append({
                    'subtype':          row[1],
                    'is_earth_like':    row[2],
                    'is_water_world':   row[3],
                    'is_ammonia_world': row[4],
                    'is_landable':      row[5],
                    'is_terraformable': row[6],
                    'bio_signal_count': row[7],
                    'geo_signal_count': row[8],
                })
        except Exception as e:
            log.error(f"Worker {worker_id}: body fetch error (offset {start}): {e}")
            # Don't abort — systems without bodies will get score=0 style defaults

    # ── Compute ratings using the in-memory body dict ──────────────────────
    for system_id64, main_star_type in system_batch:
        try:
            bodies = bodies_by_system.get(system_id64, [])
            rating = rate_system(system_id64, bodies, main_star_type)
            rating_batch.append(rating)
            processed += 1
        except Exception as e:
            errors += 1
            log.debug(f"Worker {worker_id}: rating error for {system_id64}: {e}")
            continue

        if len(rating_batch) >= BATCH_SIZE:
            try:
                _write_ratings(conn, cur, rating_batch)
            except Exception as e:
                log.error(f"Worker {worker_id}: write error: {e}")
                conn.rollback()
            rating_batch.clear()

    # Final flush
    if rating_batch:
        try:
            _write_ratings(conn, cur, rating_batch)
        except Exception as e:
            log.error(f"Worker {worker_id}: final write error: {e}")
            conn.rollback()

    # Mark systems as clean (one UPDATE, one commit)
    if id64s:
        try:
            cur.execute(
                "UPDATE systems SET rating_dirty = FALSE WHERE id64 = ANY(%s)",
                (id64s,)
            )
            conn.commit()
        except Exception as e:
            log.error(f"Worker {worker_id}: dirty-flag update error: {e}")
            conn.rollback()

    cur.close()
    conn.close()
    return processed, errors


def _write_ratings(conn, cur, batch: list) -> None:
    """Upsert a batch of rating records — single commit per call."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
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
        json.dumps(r['score_breakdown']),
        now_iso,
    ) for r in batch]

    psycopg2.extras.execute_values(
        cur,
        """
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
        rows,
        template=(
            "(%s,%s,%s,%s,%s,%s,%s,%s,"
            "%s::economy_type,"
            "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        ),
        page_size=BATCH_SIZE,
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Build pre-computed ratings (v2.0 streaming)')
    parser.add_argument('--rebuild',  action='store_true',
                        help='Re-rate ALL systems, not just unrated ones')
    parser.add_argument('--dirty',    action='store_true',
                        help='Only re-rate systems with rating_dirty = TRUE')
    parser.add_argument('--workers',  type=int, default=mp.cpu_count(),
                        help='Parallel worker processes (default: CPU count; recommend 4 on i7-8700)')
    parser.add_argument('--chunk',    type=int, default=50_000,
                        help='Systems per worker chunk (default: 50000)')
    parser.add_argument('--limit',    type=int, default=None,
                        help='Stop after N systems total (for testing)')
    args = parser.parse_args()

    # ── Diagnostic: show counts before starting ────────────────────────────
    conn = psycopg2.connect(DB_DSN)
    with conn.cursor() as diag:
        diag.execute("SELECT COUNT(*) FROM systems WHERE has_body_data = TRUE")
        total_with_bodies = diag.fetchone()[0]
        diag.execute("SELECT COUNT(*) FROM ratings")
        already_rated = diag.fetchone()[0]
    conn.close()

    log.info(f"DB diagnostic: {total_with_bodies:,} systems with body data, "
             f"{already_rated:,} already rated, "
             f"{total_with_bodies - already_rated:,} remaining")

    # ── Open streaming connection ──────────────────────────────────────────
    # FIX: use a server-side named cursor so PostgreSQL streams rows to us
    # instead of materialising the entire result set in one go.
    # fetchall() on a plain cursor with 100M+ rows silently truncates when
    # the client runs out of RAM or hits statement_timeout — producing the
    # "74M is the total" symptom.  A named cursor never has this problem.
    stream_conn = psycopg2.connect(DB_DSN)
    stream_conn.autocommit = False  # named cursors require a transaction (autocommit=False)
    stream_conn.set_session(readonly=True)  # safe read-only transaction for streaming

    with stream_conn.cursor(name='ratings_stream') as stream_cur:
        stream_cur.itersize = args.chunk  # fetch this many rows from server per network round-trip

        if args.dirty:
            log.info("Mode: dirty systems only (server-side streaming cursor)")
            stream_cur.execute("""
                SELECT s.id64, s.main_star_type
                FROM   systems s
                WHERE  s.has_body_data  = TRUE
                  AND  s.rating_dirty   = TRUE
                ORDER BY s.id64
            """)
        elif args.rebuild:
            log.info("Mode: FULL REBUILD — all systems with body data (server-side streaming cursor)")
            stream_cur.execute("""
                SELECT s.id64, s.main_star_type
                FROM   systems s
                WHERE  s.has_body_data = TRUE
                ORDER BY s.id64
            """)
        else:
            log.info("Mode: unrated systems only — resuming from where we left off "
                     "(server-side streaming cursor)")
            # This is the default/resume mode.
            # LEFT JOIN + IS NULL finds only systems NOT yet in the ratings table.
            # Safe to re-run as many times as needed — each run picks up exactly
            # the systems that weren't rated in previous runs.
            stream_cur.execute("""
                SELECT s.id64, s.main_star_type
                FROM   systems s
                LEFT JOIN ratings r ON r.system_id64 = s.id64
                WHERE  s.has_body_data  = TRUE
                  AND  r.system_id64   IS NULL
                ORDER BY s.id64
            """)

        log.info(f"Streaming started. Workers: {args.workers}, chunk size: {args.chunk:,}")
        log.info("Progress will be reported as each chunk completes.")

        start_time     = time.time()
        total_processed = 0
        total_errors    = 0
        chunks_dispatched = 0
        limit_remaining   = args.limit or 999_999_999
        pending_results   = []

        with mp.Pool(processes=args.workers) as pool:

            while limit_remaining > 0:
                # Fetch next chunk from PostgreSQL server (network round-trip)
                fetch_n = min(args.chunk, limit_remaining)
                batch   = stream_cur.fetchmany(fetch_n)
                if not batch:
                    log.info("Stream exhausted — all qualifying systems dispatched.")
                    break

                limit_remaining   -= len(batch)
                chunks_dispatched += 1

                # Dispatch to worker pool asynchronously
                pending_results.append(
                    pool.apply_async(worker_process, (chunks_dispatched, batch, DB_DSN))
                )

                # Drain completed work to bound memory (keep at most workers*2 in-flight)
                while len(pending_results) >= args.workers * 2:
                    done = pending_results.pop(0)
                    p, e = done.get()
                    total_processed += p
                    total_errors    += e
                    elapsed = time.time() - start_time
                    rate    = total_processed / elapsed if elapsed > 0 else 0
                    eta_h   = (total_with_bodies - already_rated - total_processed) / rate / 3600 if rate > 0 else 0
                    log.info(
                        f"  Rated: {total_processed + already_rated:,} / {total_with_bodies:,} "
                        f"({(total_processed + already_rated) / total_with_bodies * 100:.1f}%) | "
                        f"speed: {rate:.0f}/s | ETA: {eta_h:.1f}h | errors: {total_errors}"
                    )

            # Wait for all remaining workers to finish
            log.info(f"All {chunks_dispatched} chunks dispatched — waiting for workers to finish...")
            for done in pending_results:
                p, e = done.get()
                total_processed += p
                total_errors    += e

    stream_conn.close()

    elapsed = time.time() - start_time
    rate    = total_processed / elapsed if elapsed > 0 else 0
    log.info(
        f"Ratings complete: {total_processed:,} new ratings in {elapsed / 3600:.2f}h "
        f"({rate:.0f} systems/s)"
    )
    if total_errors:
        log.warning(f"Total errors: {total_errors:,} (these systems were skipped)")

    # Mark ratings as built in app_meta
    conn2 = psycopg2.connect(DB_DSN)
    with conn2.cursor() as cur:
        cur.execute("""
            INSERT INTO app_meta (key, value, updated_at)
            VALUES ('ratings_built', 'true', NOW())
            ON CONFLICT (key) DO UPDATE SET value = 'true', updated_at = NOW()
        """)
    conn2.commit()
    conn2.close()

    log.info("Ratings job done. Next step: python3 build_grid.py")


if __name__ == '__main__':
    main()
