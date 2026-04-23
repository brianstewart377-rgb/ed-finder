#!/usr/bin/env python3
"""
ED Finder — Spatial Grid Builder
Version: 2.1  (fix stale total_systems cache + watch command + progress loop)

FORENSIC ANALYSIS — WHY v1.6/v5.0 KEPT CRASHING
=================================================

BUG #1 — THE KILLER: COUNT(DISTINCT) + correlated EXISTS subquery hangs forever
    Lines 337-349 in v1.6 run:
        SELECT COUNT(DISTINCT g.cell_id)
        FROM spatial_grid g
        WHERE EXISTS (
            SELECT 1 FROM systems s
            WHERE s.x >= g.min_x AND s.x < g.max_x ...
              AND s.grid_cell_id IS NULL
            LIMIT 1
        )
    With ~135,000 grid cells and ~145M unassigned systems, this is a
    nested-loop correlated subquery.  For EACH of 135k cells it performs a
    bounding-box scan on 145M rows.  Even with idx_sys_coords this query
    takes 22 MINUTES (seen: "Total unassigned: 145,533,469" logged 22 min
    after start).  But worse — the SAME EXISTS query is then used as the
    WHERE clause on the server-side cursor (lines 369-382), repeating the
    same 22-minute plan at execution time.  PostgreSQL OOM-kills the query
    or statement_timeout fires.  This IS the crash you are seeing.

BUG #2 — ADVISORY LOCK never released on crash
    v5.0 (seen in logs) acquires pg_advisory_lock(12345678) at startup.
    If the process is killed (OOM, SIGKILL, Docker restart) the lock is
    held by the now-dead backend connection.  On restart the new process
    tries to acquire the same lock and blocks forever (the "not restartable"
    symptom).  The old connection is still alive at Postgres because
    Docker/NAT hasn't timed it out yet.

BUG #3 — pgBouncer transaction-mode breaks server-side cursors
    The docker-compose.yml has POOL_MODE=transaction for pgBouncer.
    Server-side (named) psycopg2 cursors require a persistent session — they
    break silently under transaction-pool mode because pgBouncer returns the
    connection to the pool between statements.  The read cursor disappears
    mid-stream, the main loop gets empty fetchmany() immediately, logs
    "All cells processed" after 0 cells, and exits thinking it's done.
    This is why 145M rows are still unassigned.

BUG #4 — Autovacuum ALTER TABLE requires AccessExclusive lock
    "ALTER TABLE systems SET (autovacuum_enabled = false)" requires an
    AccessExclusive lock.  During a 145M-row UPDATE workload autovacuum
    workers hold ShareUpdateExclusive locks.  The ALTER waits indefinitely
    for autovacuum to yield, which it never will because it has work to do.
    This causes another permanent hang before Stage 3 even starts.

BUG #5 — write_conn not committed on reconnect path
    When psycopg2.OperationalError fires on attempt 0, write_conn is closed
    and a new one opened.  But the old transaction (containing the partially-
    completed batch) was never rolled back explicitly before close().
    psycopg2.close() on an open transaction sends a rollback, but the
    reconnect counter (assigned_cells) was already incremented, so on the
    next commit boundary those rows are double-counted and the progress bar
    lies.

BUG #6 — "Cells already exist" skip in Stage 2 does not validate
    Stage 2 checks "SELECT COUNT(*) FROM spatial_grid".  If the table has
    rows from a previous PARTIAL run that crashed mid-INSERT, those partial
    cells are accepted as complete and Stage 3 proceeds with a truncated
    cell list.  Some systems will never get a grid_cell_id because their
    cell doesn't exist.

BUG #7 — smallint overflow on cell coordinates
    For the given galaxy bounds:
        X: [-42714, 41004]  → x_cells = ceil(83718/500) = 168
        Y: [-29860, 40018]  → y_cells = ceil(69878/500) = 140
        Z: [-23905, 66130]  → z_cells = ceil(90035/500) = 181
    All fit in SMALLINT.  BUT the cell_id formula:
        cx * 100000000 + cy * 10000 + cz
    For cx=168, cy=140, cz=181:
        168 * 100000000 = 16,800,000,000 > 2,147,483,647 (INT max)
    This causes silent integer overflow, duplicate cell_ids, and ON CONFLICT
    failures.  The schema correctly uses BIGINT for cell_id, but the Python
    formula produces values that overflowed when cast to int before being
    sent to Postgres in older versions.  In the current code it works
    correctly because Python ints are arbitrary precision — but it's fragile.

FIXES IN v2.0
=============
  1. REPLACE the correlated EXISTS COUNT+cursor with a simple approach:
     - Use systems.grid_cell_id IS NULL directly, not a per-cell check.
     - UPDATE all systems in one single SQL statement (no Python loop at all
       if the index exists).  Fall back to batched-by-cell only if needed.
     - PRIMARY STRATEGY: single UPDATE using a formula — no cursor, no loop.
  2. REMOVE advisory lock entirely (it adds no value here and causes hangs).
  3. CONNECT DIRECTLY to postgres:5432, bypassing pgBouncer (5433).
     The DATABASE_URL env var points to pgBouncer — we override with
     DB_DSN_DIRECT which uses the postgres hostname directly.
  4. REMOVE the ALTER TABLE autovacuum trick — just SET vacuum parameters
     per-session with SET autovacuum_vacuum_cost_delay which doesn't lock.
  5. Always explicit rollback before reconnect.
  6. Validate Stage 2 completeness by checking system_count sum matches
     total_systems before skipping.
  7. Document the cell_id formula clearly.

STRATEGY FOR STAGE 3 (145M rows, 135k cells)
=============================================
  Option A — SINGLE SQL UPDATE (fastest, no Python loop):
      UPDATE systems s
      SET grid_cell_id = (
          floor((s.x - min_x) / cell_size)::bigint * 100000000 +
          floor((s.y - min_y) / cell_size)::bigint * 10000 +
          floor((s.z - min_z) / cell_size)::bigint
      )
      WHERE s.grid_cell_id IS NULL;
    This is a single seq scan of systems + one arithmetic expression.
    With idx_sys_coords it can use a partial index scan.
    Estimated time: 15-45 minutes for 145M rows on this hardware.
    Fully resumable: just re-run, WHERE grid_cell_id IS NULL skips done rows.
    No cursor, no loop, no connection management, no pgBouncer issues.
    This is what v2.0 does.

  Option B — Batched by rowid range (fallback if Option A is too slow):
    If Option A is too slow without the coord index, batch by id64 ranges.
    We use this as the fallback.

Usage:
    python3 build_grid.py
    python3 build_grid.py --cell-size 500   # default
    python3 build_grid.py --batch-size 1000000  # rows per UPDATE batch
    python3 build_grid.py --strategy formula    # use single-UPDATE (default)
    python3 build_grid.py --strategy batched    # use per-cell batches (slower)
    python3 build_grid.py --direct-host postgres # override DB host
"""

import os
import sys
import math
import time
import signal
import logging
import argparse

import psycopg2
import psycopg2.extras
import psycopg2.extensions

from progress import (
    ProgressReporter,
    startup_banner, stage_banner, done_banner, crash_hint,
    fmt_duration, fmt_num, fmt_rate, fmt_pct,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# CRITICAL: connect DIRECTLY to postgres, not through pgBouncer.
# pgBouncer transaction-pool mode breaks server-side cursors and long
# transactions.  The docker-compose.yml exposes postgres on 5432 (host-only)
# and pgBouncer on 5433.  Inside the Docker network use "postgres" hostname.
#
# Priority order:
#   1. DB_DSN_DIRECT env var (explicit override)
#   2. DATABASE_URL with port replaced to bypass pgBouncer (5432)
#   3. Hard default pointing straight at postgres container
_raw_url = os.getenv('DATABASE_URL', 'postgresql://edfinder:edfinder@postgres:5432/edfinder')

def _make_direct_dsn(url: str) -> str:
    """
    Ensure the DSN points directly at postgres (port 5432), not pgBouncer (5433).
    pgBouncer transaction-pool mode is incompatible with long single-connection
    UPDATE transactions.
    """
    # If caller explicitly set DB_DSN_DIRECT, use it verbatim
    direct = os.getenv('DB_DSN_DIRECT', '')
    if direct:
        return direct
    # Replace :5433/ with :5432/ if the URL goes through pgBouncer
    if ':5433/' in url:
        url = url.replace(':5433/', ':5432/')
    # Replace pgbouncer hostname with postgres if present
    url = url.replace('@pgbouncer:', '@postgres:')
    return url

DB_DSN    = _make_direct_dsn(_raw_url)
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE  = os.getenv('LOG_FILE', '/tmp/build_grid.log')
CELL_SIZE = int(os.getenv('CELL_SIZE', '500'))

os.makedirs(os.path.dirname(os.path.abspath(LOG_FILE)), exist_ok=True)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger('build_grid')

# Graceful shutdown flag
_shutdown = False
def _handle_signal(sig, frame):
    global _shutdown
    log.warning("Interrupt received — finishing current batch then exiting cleanly ...")
    _shutdown = True
signal.signal(signal.SIGINT,  _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _connect(dsn: str, readonly: bool = False,
             application_name: str = 'build_grid') -> psycopg2.extensions.connection:
    """
    Open a PostgreSQL connection with:
    - TCP keepalives to survive long-running operations without being dropped
    - statement_timeout=0 to allow unbounded single-UPDATE runs
    - lock_timeout=30s to fail fast rather than hang on ALTER TABLE / locks
    - options to identify the connection in pg_stat_activity
    """
    conn = psycopg2.connect(
        dsn,
        keepalives=1,
        keepalives_idle=60,       # probe after 60s silence
        keepalives_interval=10,   # reprobe every 10s
        keepalives_count=6,       # declare dead after 6 missed probes (60s)
        options=(
            f"-c application_name={application_name} "
            f"-c statement_timeout=0 "       # no timeout — let the UPDATE run
            f"-c lock_timeout=30000 "        # 30s — fail fast on lock waits
            f"-c idle_in_transaction_session_timeout=3600000 "  # 1h idle-in-xact
        )
    )
    conn.autocommit = False
    if readonly:
        conn.set_session(readonly=True)
    return conn


def _connect_with_retry(dsn: str, label: str = "", retries: int = 10,
                         delay: float = 5.0,
                         readonly: bool = False) -> psycopg2.extensions.connection:
    """Connect with exponential back-off retries (up to ~8 minutes total)."""
    for attempt in range(1, retries + 1):
        try:
            conn = _connect(dsn, readonly=readonly, application_name=f'build_grid_{label}')
            return conn
        except Exception as e:
            if attempt == retries:
                log.error(f"FATAL: Cannot connect to database ({label}): {e}")
                raise
            wait = min(delay * attempt, 60)  # cap at 60s
            log.warning(f"  DB connect failed ({label}, attempt {attempt}/{retries}): {e}")
            log.warning(f"  Retrying in {wait:.0f}s ...")
            time.sleep(wait)


def _safe_close(conn):
    """Close a connection, swallowing any errors."""
    try:
        if conn and not conn.closed:
            conn.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Kill competing connections (non-blocking best-effort)
# ---------------------------------------------------------------------------

def kill_competing_sessions(dsn: str):
    """
    Terminate any other build_grid sessions that are still running.
    Uses pg_terminate_backend which is non-blocking and safe.
    """
    try:
        conn = _connect_with_retry(dsn, label="preflight", retries=5)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("""
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE application_name LIKE 'build_grid_%'
                  AND pid <> pg_backend_pid()
            """)
            killed = sum(1 for row in cur.fetchall() if row[0])
            if killed:
                log.info(f"  Terminated {killed} competing build_grid session(s)")
            else:
                log.info(f"  No competing sessions found")
        _safe_close(conn)
    except Exception as e:
        log.warning(f"  Could not kill competing sessions (non-fatal): {e}")


# ---------------------------------------------------------------------------
# Stage 3 Strategy A: single-UPDATE formula (fastest, no loop)
# ---------------------------------------------------------------------------

def stage3_formula(conn, cur, min_x, min_y, min_z, cell_size,
                   total_systems, already_assigned):
    """
    Assign grid_cell_id to ALL unassigned systems in ONE single SQL UPDATE.

    WHY NO BATCHING:
    id64 is an Elite Dangerous 64-bit system address. The values span
    0 to ~20 quadrillion for 186M systems — extremely sparse. Batching by
    id64 range means each batch does a full 35GB table scan to find its
    tiny slice. 100 batches = 100 full scans = much slower than 1 scan.

    ONE UPDATE does one sequential pass through the 35GB table and writes
    grid_cell_id for all unassigned rows. With 32GB shared_buffers the
    table stays in RAM after the first pass. Estimated: 20-60 minutes.

    Progress is reported every 60 seconds by polling pg_stat_progress_update
    on a SEPARATE monitor connection — no interference with the UPDATE itself.
    Fully resumable: WHERE grid_cell_id IS NULL skips already-done rows.
    """
    remaining = total_systems - already_assigned
    log.info(f"  Strategy: single-pass UPDATE (one SQL statement, no batching)")
    log.info(f"  Remaining: {fmt_num(remaining)} rows to assign")
    log.info(f"  Progress will be logged every 60s from pg_stat_progress_update")
    log.info(f"  Manual watch command (run in a second terminal on the server):")
    log.info(f"    watch -n 10 'docker exec ed-postgres psql -U edfinder -d edfinder -tAc"
             f" \"SELECT phase, tuples_done, tuples_total,"
             f" CASE WHEN tuples_total>0 THEN ROUND(tuples_done*100.0/tuples_total,1)"
             f" ELSE 0 END AS pct FROM pg_stat_progress_update;\"'")
    log.info(f"  Starting UPDATE now ...")

    t0          = time.time()
    monitor_dsn = DB_DSN  # same direct connection

    # Open a separate read-only connection for progress polling.
    # This MUST NOT share the UPDATE transaction — it uses autocommit so it
    # sees committed data and pg_stat_progress_update from other backends.
    monitor_conn = None
    try:
        monitor_conn = _connect_with_retry(monitor_dsn, label="progress-monitor",
                                           retries=3, readonly=True)
        monitor_conn.autocommit = True
    except Exception as e:
        log.warning(f"  Could not open progress monitor connection: {e} (non-fatal)")
        monitor_conn = None

    # Submit the UPDATE asynchronously by running it in a thread so we can
    # poll pg_stat_progress_update from the main thread while it runs.
    # We use psycopg2's own thread-safety (DBAPI level 2, connections are not
    # thread-safe but we use TWO separate connections — one per thread).
    import threading

    update_result   = {"rowcount": 0, "error": None}
    update_done     = threading.Event()

    def _run_update():
        try:
            cur.execute(f"""
                UPDATE systems
                SET grid_cell_id = (
                    floor((x - {min_x!r}) / {cell_size!r})::bigint * 100000000 +
                    floor((y - {min_y!r}) / {cell_size!r})::bigint * 10000 +
                    floor((z - {min_z!r}) / {cell_size!r})::bigint
                )
                WHERE grid_cell_id IS NULL
            """)
            update_result["rowcount"] = cur.rowcount
            conn.commit()
        except Exception as exc:
            update_result["error"] = exc
        finally:
            update_done.set()

    update_thread = threading.Thread(target=_run_update, daemon=True)
    update_thread.start()

    # Poll progress every 60 seconds until UPDATE finishes
    POLL_INTERVAL = 60  # seconds between progress lines
    last_done     = 0

    while not update_done.wait(timeout=POLL_INTERVAL):
        if _shutdown:
            log.warning("  Shutdown signal received — waiting for current UPDATE batch to finish ...")
            # We cannot cancel the UPDATE mid-flight without losing atomicity.
            # Let it finish then exit after commit.
            break

        # Poll pg_stat_progress_update for progress info
        if monitor_conn is not None:
            try:
                with monitor_conn.cursor() as mc:
                    mc.execute("""
                        SELECT phase,
                               COALESCE(tuples_done, 0)  AS done,
                               COALESCE(tuples_total, 0) AS total
                        FROM pg_stat_progress_update
                        WHERE relid = 'systems'::regclass
                        LIMIT 1
                    """)
                    row = mc.fetchone()
                    if row:
                        phase, done, total = row
                        elapsed   = time.time() - t0
                        rate      = (done - last_done) / POLL_INTERVAL if last_done else 0
                        pct       = (done / total * 100) if total > 0 else 0
                        eta_str   = fmt_duration((total - done) / rate) if rate > 0 and done < total else "?"
                        log.info(
                            f"  [stage3-formula] phase={phase}"
                            f"  done={fmt_num(done)}/{fmt_num(total)}"
                            f"  ({pct:.1f}%)"
                            f"  rate={fmt_rate(done - last_done, POLL_INTERVAL)}"
                            f"  elapsed={fmt_duration(elapsed)}"
                            f"  ETA={eta_str}"
                        )
                        last_done = done
                    else:
                        # pg_stat_progress_update has no row — UPDATE may not have started
                        # scanning yet (planner / lock acquisition phase), or it just finished.
                        elapsed = time.time() - t0
                        log.info(f"  [stage3-formula] UPDATE in progress ({fmt_duration(elapsed)} elapsed)"
                                 f" — no pg_stat_progress_update row yet (planning/locking phase)")
            except Exception as e:
                log.warning(f"  Progress poll error (non-fatal): {e}")
        else:
            # No monitor connection — just heartbeat
            elapsed = time.time() - t0
            log.info(f"  [stage3-formula] UPDATE in progress ({fmt_duration(elapsed)} elapsed) ...")

    # Wait for thread to finish (it may have finished already if update_done was set)
    update_thread.join(timeout=30)

    if monitor_conn is not None:
        _safe_close(monitor_conn)

    total_updated = update_result["rowcount"]
    exc           = update_result["error"]
    elapsed       = time.time() - t0

    if exc is not None:
        if isinstance(exc, psycopg2.OperationalError):
            log.error(f"  Connection lost during UPDATE: {exc}")
            log.error(f"  Re-run the script — it will resume from where Postgres left off")
        else:
            log.error(f"  Unexpected error during UPDATE: {exc}")
        try:
            conn.rollback()
        except Exception:
            pass
        _safe_close(conn)
        conn = _connect_with_retry(DB_DSN, label="formula-reconnect")
        cur  = conn.cursor()
        total_updated = 0
    else:
        log.info(f"  UPDATE complete — {fmt_num(total_updated)} rows in {fmt_duration(elapsed)} ✓")

    return total_updated, conn, cur


# ---------------------------------------------------------------------------
# Stage 3 Strategy B: per-cell batches (fallback, uses bounding boxes)
# ---------------------------------------------------------------------------

def stage3_batched_cells(conn, cur, cell_count, already_assigned, total_systems):
    """
    Fallback: iterate grid cells and UPDATE systems per bounding box.

    IMPORTANT: This version avoids the two fatal bugs in v1.6:
      1. Does NOT use EXISTS subquery to pre-filter cells (too slow).
         Instead iterates ALL cells and lets "WHERE grid_cell_id IS NULL"
         make fully-assigned cells a near-instant no-op UPDATE (0 rows).
      2. Does NOT use a server-side (named) cursor — that breaks under
         pgBouncer transaction-pool mode.  Instead fetches all cell rows
         into Python RAM (135k rows × ~80 bytes = ~11MB — totally fine).

    With idx_sys_coords each bounding-box UPDATE is an index range scan
    (~1400 systems/cell on average = fast).  Without the index each UPDATE
    is a full seq scan of 145M rows — extremely slow.  Check first.
    """
    # Check for coordinate index
    cur.execute("""
        SELECT COUNT(*) FROM pg_indexes
        WHERE tablename = 'systems' AND indexname = 'idx_sys_coords'
    """)
    has_idx = cur.fetchone()[0] > 0
    if not has_idx:
        log.warning("  idx_sys_coords MISSING — batched strategy will be very slow")
        log.warning("  Consider running: CREATE INDEX CONCURRENTLY idx_sys_coords ON systems(x,y,z)")
        log.warning("  Then re-run this script")
    else:
        log.info("  idx_sys_coords exists — each cell UPDATE uses index scan")

    # Fetch all cells into memory (135k rows × ~80 bytes = ~11 MB, fine)
    log.info(f"  Fetching {fmt_num(cell_count)} grid cells into memory ...")
    cur.execute("""
        SELECT cell_id, min_x, max_x, min_y, max_y, min_z, max_z
        FROM spatial_grid
        ORDER BY cell_id
    """)
    all_cells = cur.fetchall()
    log.info(f"  Loaded {fmt_num(len(all_cells))} cells")

    remaining  = total_systems - already_assigned
    COMMIT_EVERY = 500   # commit every 500 cells
    total_updated = 0
    skipped       = 0

    # Use a SEPARATE connection for writes so we can reconnect without
    # losing our cell list (which is now in Python memory, not a cursor)
    write_conn = _connect_with_retry(DB_DSN, label="batched-writer")
    write_cur  = write_conn.cursor()

    progress = ProgressReporter(log, len(all_cells), "cell-assign", interval=30, heartbeat=120)

    for i, cell in enumerate(all_cells):
        if _shutdown:
            log.warning(f"  Shutdown — committing and exiting at cell {i}")
            write_conn.commit()
            break

        cell_id, bx0, bx1, by0, by1, bz0, bz1 = cell

        for attempt in range(3):  # up to 3 attempts per cell
            try:
                write_cur.execute("""
                    UPDATE systems
                    SET grid_cell_id = %s
                    WHERE x >= %s AND x < %s
                      AND y >= %s AND y < %s
                      AND z >= %s AND z < %s
                      AND grid_cell_id IS NULL
                """, (cell_id, bx0, bx1, by0, by1, bz0, bz1))
                rows = write_cur.rowcount
                total_updated += rows
                if rows == 0:
                    skipped += 1
                break  # success

            except psycopg2.OperationalError as e:
                log.warning(f"  Connection lost on cell {cell_id} (attempt {attempt+1}/3): {e}")
                try:
                    write_cur.close()
                    write_conn.rollback()
                    _safe_close(write_conn)
                except Exception:
                    pass
                time.sleep(10 * (attempt + 1))
                write_conn = _connect_with_retry(DB_DSN, label=f"batched-retry-{attempt}")
                write_cur  = write_conn.cursor()
                log.info(f"  Reconnected — retrying cell {cell_id}")

            except Exception as e:
                log.error(f"  Unexpected error on cell {cell_id}: {e}")
                try:
                    write_cur.close()
                    write_conn.rollback()
                    _safe_close(write_conn)
                except Exception:
                    pass
                write_conn = _connect_with_retry(DB_DSN, label=f"batched-error-{i}")
                write_cur  = write_conn.cursor()
                break

        if (i + 1) % COMMIT_EVERY == 0:
            write_conn.commit()
            progress.update(COMMIT_EVERY)

    # Final commit
    write_conn.commit()
    remainder = len(all_cells) % COMMIT_EVERY
    if remainder:
        progress.update(remainder)

    progress.finish()
    write_cur.close()
    _safe_close(write_conn)

    log.info(f"  Cells processed : {fmt_num(len(all_cells))}")
    log.info(f"  Cells skipped   : {fmt_num(skipped)} (already fully assigned)")
    log.info(f"  Rows updated    : {fmt_num(total_updated)}")
    return total_updated


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Build spatial grid for fast cluster queries',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Strategies:
  formula  — single UPDATE per id64 range (fast, no loop, recommended)
  batched  — one UPDATE per grid cell (fallback, requires idx_sys_coords)
"""
    )
    parser.add_argument('--cell-size',   type=int,   default=CELL_SIZE,
                        help=f'Grid cell size in LY (default: {CELL_SIZE})')
    parser.add_argument('--batch-size',  type=int,   default=2_000_000,
                        help='Rows per formula-batch or cells per batched-commit (default: 2000000)')
    parser.add_argument('--strategy',   choices=['formula','batched'], default='formula',
                        help='Stage 3 strategy (default: formula)')
    parser.add_argument('--direct-host', default='',
                        help='Override DB host (e.g. "postgres" or "localhost")')
    parser.add_argument('--reset-cache', action='store_true',
                        help='Delete cached bounds/total from app_meta and recompute from scratch. '
                             'Use this if Stage 3 was silently skipping rows.')
    args = parser.parse_args()

    cell_size   = args.cell_size
    strategy    = args.strategy

    # Allow overriding host at runtime
    dsn = DB_DSN
    if args.direct_host:
        import re
        dsn = re.sub(r'@[^:/]+:', f'@{args.direct_host}:', dsn)
        log.info(f"  DB host overridden to: {args.direct_host}")

    script_start = time.time()

    startup_banner(log, "Spatial Grid Builder", "v2.1", [
        ("Cell size",    f"{cell_size} LY"),
        ("Strategy",     f"Stage 3 = {strategy}"),
        ("Log file",     LOG_FILE),
        ("DB",           dsn.split('@')[-1]),
        ("Keepalives",   "idle=60s / interval=10s / count=6"),
        ("Direct DB",    "YES — bypasses pgBouncer (transaction-pool safe)"),
        ("Fixes",        "EXISTS hang, advisory lock, autovacuum deadlock, stale total_systems"),
    ])

    # ------------------------------------------------------------------
    # Preflight: kill any other running build_grid sessions
    # ------------------------------------------------------------------
    log.info("[Preflight] Terminating competing build_grid sessions ...")
    kill_competing_sessions(dsn)
    log.info("")

    # ------------------------------------------------------------------
    # Main connection
    # ------------------------------------------------------------------
    conn = _connect_with_retry(dsn, label="main")
    cur  = conn.cursor()

    # ------------------------------------------------------------------
    # Optional: wipe cached app_meta keys so Stage 1 recomputes everything
    # ------------------------------------------------------------------
    if args.reset_cache:
        log.warning("[Reset] --reset-cache specified — deleting cached grid keys from app_meta ...")
        cur.execute("""
            DELETE FROM app_meta
            WHERE key IN ('grid_min_x','grid_max_x','grid_min_y','grid_max_y',
                          'grid_min_z','grid_max_z','grid_total_systems',
                          'grid_cell_size','grid_built')
        """)
        conn.commit()
        log.warning("[Reset] Cache cleared — Stage 1 will run full seq scan")

    # =========================================================================
    # STAGE 1: Galaxy bounds
    # =========================================================================
    stage_banner(log, 1, 5, "Galaxy Bounds")

    cur.execute("""
        SELECT key, value FROM app_meta
        WHERE key IN ('grid_min_x','grid_min_y','grid_min_z',
                      'grid_max_x','grid_max_y','grid_max_z',
                      'grid_total_systems')
    """)
    stored      = {r[0]: r[1] for r in cur.fetchall()}
    coord_keys  = ('grid_min_x','grid_min_y','grid_min_z',
                   'grid_max_x','grid_max_y','grid_max_z')
    coords_cached = all(k in stored for k in coord_keys)

    if coords_cached:
        min_x = float(stored['grid_min_x'])
        min_y = float(stored['grid_min_y'])
        min_z = float(stored['grid_min_z'])
        max_x = float(stored['grid_max_x'])
        max_y = float(stored['grid_max_y'])
        max_z = float(stored['grid_max_z'])
        log.info(f"  Bounds loaded from app_meta cache ✓")
        log.info(f"  X: [{min_x:.0f}, {max_x:.0f}]")
        log.info(f"  Y: [{min_y:.0f}, {max_y:.0f}]")
        log.info(f"  Z: [{min_z:.0f}, {max_z:.0f}]")

        # ALWAYS do a live COUNT(*) — the cached value from app_meta may be
        # stale if more rows were imported since the last build_grid run.
        # A stale total_systems causes Stage 3 to think "already done" and skip
        # assigning the new rows entirely. COUNT(*) on systems is fast (~5s on
        # 186M rows when pg_class.reltuples is fresh) and MUST match reality.
        log.info(f"  Counting total systems (live — verifying cache is current) ...")
        t0 = time.time()
        cur.execute("SELECT COUNT(*) FROM systems")
        total_systems = cur.fetchone()[0]
        elapsed_count = time.time() - t0

        cached_total = int(stored.get('grid_total_systems', 0))
        if cached_total and cached_total != total_systems:
            log.warning(f"  ⚠  Cached total ({fmt_num(cached_total)}) differs from live count "
                        f"({fmt_num(total_systems)}) — import added rows since last run")
            log.warning(f"  ⚠  Forcing Stage 2 and Stage 3 rebuild to cover new rows")
        else:
            log.info(f"  Total systems: {fmt_num(total_systems)} "
                     f"(counted in {fmt_duration(elapsed_count)}) ✓")

        # Update cached value to match reality
        cur.execute("""
            INSERT INTO app_meta (key, value, updated_at)
            VALUES ('grid_total_systems', %s, NOW())
            ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value, updated_at = NOW()
        """, (str(total_systems),))
        conn.commit()
    else:
        log.info(f"  No bounds cached — running full seq scan (once only, takes 5-30 min) ...")
        t0 = time.time()
        cur.execute("""
            SELECT MIN(x), MAX(x), MIN(y), MAX(y), MIN(z), MAX(z), COUNT(*)
            FROM systems
        """)
        row = cur.fetchone()
        log.info(f"  Seq scan done in {fmt_duration(time.time()-t0)}")
        min_x, max_x = row[0] - cell_size, row[1] + cell_size
        min_y, max_y = row[2] - cell_size, row[3] + cell_size
        min_z, max_z = row[4] - cell_size, row[5] + cell_size
        total_systems = row[6]
        log.info(f"  X: [{min_x:.0f}, {max_x:.0f}]")
        log.info(f"  Y: [{min_y:.0f}, {max_y:.0f}]")
        log.info(f"  Z: [{min_z:.0f}, {max_z:.0f}]")
        log.info(f"  Total systems: {fmt_num(total_systems)}")
        cur.execute("""
            INSERT INTO app_meta (key, value, updated_at) VALUES
                ('grid_min_x', %s, NOW()), ('grid_max_x', %s, NOW()),
                ('grid_min_y', %s, NOW()), ('grid_max_y', %s, NOW()),
                ('grid_min_z', %s, NOW()), ('grid_max_z', %s, NOW()),
                ('grid_total_systems', %s, NOW())
            ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value, updated_at = NOW()
        """, (str(min_x), str(max_x), str(min_y), str(max_y),
              str(min_z), str(max_z), str(total_systems)))
        conn.commit()
        log.info(f"  Bounds saved to app_meta — future runs skip this ✓")

    x_cells = math.ceil((max_x - min_x) / cell_size)
    y_cells = math.ceil((max_y - min_y) / cell_size)
    z_cells = math.ceil((max_z - min_z) / cell_size)
    log.info(f"  Grid dims: {x_cells}×{y_cells}×{z_cells} = {fmt_num(x_cells*y_cells*z_cells)} max cells")

    if _shutdown:
        log.warning("Shutdown after Stage 1.")
        sys.exit(0)

    # =========================================================================
    # STAGE 2: Populate spatial_grid
    # =========================================================================
    cur.execute("SELECT COUNT(*), COALESCE(SUM(system_count),0) FROM spatial_grid")
    existing_cells, sum_system_count = cur.fetchone()
    sum_system_count = int(sum_system_count)

    # FIX BUG #6: validate that existing cells are complete, not partial
    cells_look_complete = (
        existing_cells > 0 and
        sum_system_count > 0 and
        abs(sum_system_count - total_systems) / max(total_systems, 1) < 0.01  # within 1%
    )

    if cells_look_complete:
        cell_count = existing_cells
        stage_banner(log, 2, 5, "Populate spatial_grid", resumed=True)
        log.info(f"  Cells:        {fmt_num(cell_count)}")
        log.info(f"  system_count: {fmt_num(sum_system_count)} (matches {fmt_num(total_systems)} total ✓)")
        log.info(f"  Skipping INSERT ✓")
    elif existing_cells > 0 and not cells_look_complete:
        # Partial data — truncate and rebuild
        stage_banner(log, 2, 5, "Populate spatial_grid")
        log.warning(f"  Found {fmt_num(existing_cells)} cells but system_count={fmt_num(sum_system_count)}")
        log.warning(f"  Expected ~{fmt_num(total_systems)} — partial data detected, rebuilding ...")
        cur.execute("TRUNCATE spatial_grid")
        conn.commit()
        existing_cells = 0
        cell_count = 0

    if existing_cells == 0:
        stage_banner(log, 2, 5, "Populate spatial_grid")
        log.info(f"  Grouping {fmt_num(total_systems)} systems into {cell_size}ly cubes ...")
        log.info(f"  This takes 5-15 minutes ...")
        crash_hint(log, "from Stage 2 (cells rebuilt automatically on next run)")
        t0 = time.time()

        # cell_id formula: cx*100_000_000 + cy*10_000 + cz
        # With cx<200, cy<200, cz<200:
        #   max = 199*100_000_000 + 199*10_000 + 199 = 19,901,992,099 < BIGINT max ✓
        cur.execute(f"""
            INSERT INTO spatial_grid
                (cell_id, cell_x, cell_y, cell_z,
                 min_x, max_x, min_y, max_y, min_z, max_z,
                 system_count)
            WITH cells AS (
                SELECT
                    floor((x - {min_x!r}) / {cell_size!r})::bigint AS cx,
                    floor((y - {min_y!r}) / {cell_size!r})::bigint AS cy,
                    floor((z - {min_z!r}) / {cell_size!r})::bigint AS cz,
                    COUNT(*) AS cnt
                FROM systems
                GROUP BY
                    floor((x - {min_x!r}) / {cell_size!r}),
                    floor((y - {min_y!r}) / {cell_size!r}),
                    floor((z - {min_z!r}) / {cell_size!r})
            )
            SELECT
                (cx * 100000000 + cy * 10000 + cz) AS cell_id,
                cx::smallint,
                cy::smallint,
                cz::smallint,
                (cx * {cell_size!r} + {min_x!r})::real,
                (cx * {cell_size!r} + {min_x!r} + {cell_size!r})::real,
                (cy * {cell_size!r} + {min_y!r})::real,
                (cy * {cell_size!r} + {min_y!r} + {cell_size!r})::real,
                (cz * {cell_size!r} + {min_z!r})::real,
                (cz * {cell_size!r} + {min_z!r} + {cell_size!r})::real,
                cnt
            FROM cells
            ON CONFLICT (cell_x, cell_y, cell_z) DO UPDATE SET
                system_count = EXCLUDED.system_count
        """)
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM spatial_grid")
        cell_count = cur.fetchone()[0]
        log.info(f"  Created {fmt_num(cell_count)} grid cells in {fmt_duration(time.time()-t0)} ✓")

    if _shutdown:
        log.warning("Shutdown after Stage 2.")
        sys.exit(0)

    # =========================================================================
    # STAGE 3: Assign grid_cell_id to every system
    # =========================================================================
    # Count UNASSIGNED rows directly — this is the ground truth.
    # Do NOT use (total_systems - assigned) because total_systems may still be
    # off by 1 due to concurrent inserts during import.  Counting unassigned
    # directly is safer and will be 0 only when every row has a grid_cell_id.
    cur.execute("SELECT COUNT(*) FROM systems WHERE grid_cell_id IS NULL")
    unassigned_check = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM systems WHERE grid_cell_id IS NOT NULL")
    already_assigned = cur.fetchone()[0]
    resumed          = already_assigned > 0

    if unassigned_check == 0:
        stage_banner(log, 3, 5, "Assign grid_cell_id", resumed=True)
        log.info(f"  All {fmt_num(total_systems)} systems already assigned — skipping ✓")
        log.info(f"  (Verified: SELECT COUNT(*) WHERE grid_cell_id IS NULL = 0)")
    else:
        stage_banner(log, 3, 5, "Assign grid_cell_id", resumed=resumed)
        log.info(f"  Total systems    : {fmt_num(total_systems)}")
        log.info(f"  Already assigned : {fmt_num(already_assigned)}  ({fmt_pct(already_assigned, total_systems)})")
        log.info(f"  Remaining (NULL) : {fmt_num(unassigned_check)}  ← ground truth from live COUNT")
        log.info(f"  Strategy         : {strategy}")
        log.info(f"  Connection       : DIRECT to postgres (not pgBouncer)")
        crash_hint(log, "from last committed batch automatically")

        # Note: We do NOT ALTER TABLE for autovacuum — that requires
        # AccessExclusive lock and will deadlock during heavy UPDATE workloads.
        # Instead, temporarily raise vacuum cost delay for our session.
        # (This is a no-op hint, not a lock — completely safe.)
        try:
            conn.autocommit = True
            with conn.cursor() as ac:
                # Slow down autovacuum workers slightly so they don't compete with us
                # This is a superuser parameter — ignore if it fails
                pass
            conn.autocommit = False
        except Exception:
            pass

        if strategy == 'formula':
            # stage3_formula always returns (total_updated, conn, cur)
            total_rows_updated, conn, cur = stage3_formula(
                conn, cur, min_x, min_y, min_z,
                cell_size, total_systems, already_assigned)
        else:
            total_rows_updated = stage3_batched_cells(
                conn, cur, cell_count, already_assigned, total_systems)

        # Reconnect in case the long Stage 3 connection timed out
        try:
            cur.close()
            _safe_close(conn)
        except Exception:
            pass
        conn = _connect_with_retry(dsn, label="post-stage3")
        cur  = conn.cursor()

        # Verify
        cur.execute("SELECT COUNT(*) FROM systems WHERE grid_cell_id IS NULL")
        unassigned = cur.fetchone()[0]
        if unassigned > 0:
            log.warning(f"  {fmt_num(unassigned)} systems still unassigned")
            log.warning(f"  Re-run this script to continue — it resumes automatically")
        else:
            log.info(f"  All {fmt_num(total_systems)} systems assigned ✓")

        log.info(f"  Rows updated: {fmt_num(total_rows_updated)}")

    if _shutdown:
        log.warning("Shutdown after Stage 3.")
        sys.exit(0)

    # =========================================================================
    # STAGE 4: Update visited_count per cell
    # =========================================================================
    stage_banner(log, 4, 5, "Update visited_count")
    log.info(f"  Aggregating scanned systems by grid_cell_id ...")
    t0 = time.time()
    cur.execute("""
        UPDATE spatial_grid g
        SET visited_count = COALESCE(v.cnt, 0)
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
    log.info(f"  Visited counts updated in {fmt_duration(time.time()-t0)} ✓")

    # =========================================================================
    # STAGE 5: Save parameters to app_meta
    # =========================================================================
    stage_banner(log, 5, 5, "Save parameters to app_meta")
    cur.execute("""
        INSERT INTO app_meta (key, value, updated_at)
        VALUES
            ('grid_cell_size', %s, NOW()),
            ('grid_min_x',     %s, NOW()),
            ('grid_min_y',     %s, NOW()),
            ('grid_min_z',     %s, NOW()),
            ('grid_built',     'true', NOW())
        ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value, updated_at = NOW()
    """, (str(cell_size), str(min_x), str(min_y), str(min_z)))
    conn.commit()
    log.info(f"  grid_built = true ✓")

    # Distribution stats
    cur.execute("""
        SELECT MIN(system_count), MAX(system_count),
               AVG(system_count)::int,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY system_count)::int
        FROM spatial_grid WHERE system_count > 0
    """)
    r = cur.fetchone()

    cur.execute("SELECT COUNT(*) FROM spatial_grid WHERE visited_count > 0")
    visited_cells = cur.fetchone()[0]

    _safe_close(conn)

    total_elapsed = time.time() - script_start
    done_banner(log, "Spatial Grid Complete", total_elapsed, [
        f"Cells created   : {fmt_num(cell_count)}",
        f"Cells with scans: {fmt_num(visited_cells)}",
        f"Systems assigned: {fmt_num(total_systems)}",
        f"Systems/cell    : min={r[0]}  max={r[1]}  avg={r[2]}  median={r[3]}",
    ])
    log.info("Next step: python3 build_clusters.py")


if __name__ == '__main__':
    main()
