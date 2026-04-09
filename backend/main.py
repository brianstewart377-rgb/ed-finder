"""
ED:Finder — Self-Hosted Backend  (v3.16)
FastAPI caching proxy for Spansh API + SQLite persistence
Works on x86 (Hetzner) and ARM64 (Raspberry Pi 5)

Changes in v3.14 (startup/shutdown audit):
  - FIX-S1  Misplaced `from contextlib import contextmanager` moved to imports block
  - FIX-S2  WATCHLIST_CHECK_INTERVAL constant moved to config block (was buried mid-file)
  - FIX-S3  Module docstring updated from v3.3 → v3.14
  - FIX-S4  Duplicate section-header comments removed (App lifecycle ×2, Watchlist ×2)
  - FIX-L1  add_to_watchlist:    raw get_db() → db_conn() context manager (connection leak)
  - FIX-L2  remove_from_watchlist: same
  - FIX-L3  _check_one (watchlist_changes): both branches use db_conn() (connection leak)
  - FIX-L4  cache_cleanup_task:  raw get_db() → db_conn() context manager (connection leak)
  - FIX-L5  api_status:          raw get_db() → db_conn() context manager (connection leak)
  - FIX-L6  cache_stats:         raw get_db() → db_conn() context manager (connection leak)
  - FIX-SH1 lifespan shutdown:   await asyncio.gather(...) before _http.aclose() so
            background tasks fully stop before the HTTP client is torn down
            (previously cancel() was called but never awaited → race on shutdown)
  - FIX-SH2 spansh_get / spansh_post: guard against _http being None with a clear
            RuntimeError instead of silent AttributeError: 'NoneType'

Changes in v3.15 (deep code audit):
  - BUG-B1  api_status: called _http.get() directly, bypassing the None guard
            added in FIX-SH2.  Replaced with spansh_get() so the guard applies
            and errors surface properly instead of crashing with AttributeError.
  - BUG-B2  scheduled_watchlist_check: WATCHLIST_CHECK_INTERVAL=0 (the .env
            documented way to disable watchlist checking) caused asyncio.sleep(0)
            in a tight infinite loop -> 100% CPU.  Now exits early if interval <= 0.
  - BUG-B3  trigger_refresh: asyncio.create_task(_bg()) stored no reference to
            the task.  Python's GC can collect un-referenced tasks mid-run, and
            on shutdown the task continued using _http after aclose().  Task is
            now tracked in a module-level set and cancelled at shutdown.
  - BUG-B4  clear_cache: `if prefix else cache_invalidate_pattern("")` -- both
            branches called cache_invalidate_pattern with the same value; the
            ternary was dead code.  Simplified to always call
            cache_invalidate_pattern(prefix).  SQL `LIKE '%'` still intentionally
            matches all rows when prefix is empty (documented in docstring).
  - BUG-B5  cache_stats: `total` counted ALL rows (including expired ones) while
            `by_prefix` and `expiring_soon` were derived from the same unfiltered
            set.  `expiring_soon` incorrectly flagged already-expired entries
            (negative remaining TTL < 3600 s).  Fixed: both total and the per-
            prefix loop now filter to live rows only (created_at + ttl > now);
            expiring_soon only counts rows whose remaining time is > 0 and < 1 h.
  - BUG-B6  batch_systems: X-Cache-Age header was hardcoded "86400" for a full
            cache hit regardless of actual entry age.  Changed to "0" (unknown
            mixed age) with a comment; proper per-entry age tracking would require
            a separate cache_get_with_age call per id64 which is not worth the
            extra DB round-trips for a header value.
  - BUG-B7  api_status: cache_entries count used SELECT COUNT(*) FROM cache which
            included expired rows, inflating the number reported at /api/status
            vs /api/cache/stats (which correctly filters to live rows only).
            Fixed: now filters WHERE created_at + ttl > now, consistent with
            the cache_stats endpoint.

Changes in v3.16 (performance, observability, resilience):
  - PERF-2  SQLite tuned for Pi 5: cache_size=-32000 (32 MB page cache),
            mmap_size=268435456 (256 MB mmap), temp_store=MEMORY.
            PRAGMA optimize called at startup to refresh query planner stats.
  - PERF-4  uvloop event-loop policy applied at module load (if available) for
            2–3× I/O throughput.  Falls back gracefully if uvloop not installed.
  - OBS-1   StructuredFormatter: all log records emit JSON lines with timestamp,
            level, module, message, and any extra fields (request_id, etc.).
  - OBS-2   /api/metrics endpoint: Prometheus text-format exposing uptime,
            cache hit/miss counters, circuit-breaker state, and request count.
  - OBS-3   RequestIDMiddleware: generates/propagates X-Request-ID header on
            every request; request_id is included in structured log records.
  - RES-1   SpanshCircuitBreaker wraps all spansh_get / spansh_post calls.
            failure_threshold=5, recovery_timeout=60 s.  State: closed →
            open (after 5 failures) → half-open (after 60 s) → closed (on success).
"""
from __future__ import annotations

# ── PERF-4: uvloop — must be set before any asyncio import in __main__ ────────
# We apply the policy here at module load; uvloop is an optional dependency.
try:
    import uvloop
    uvloop.install()          # sets the default event-loop policy globally
    _UVLOOP_ACTIVE = True
except ImportError:
    _UVLOOP_ACTIVE = False    # graceful fallback to default asyncio loop

import asyncio
import hashlib
import json
import logging
import os
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

# ─── Shared HTTP client ───────────────────────────────────────────────────────
_http: Optional[httpx.AsyncClient] = None

# ─── Background task registry ────────────────────────────────────────────────
_background_tasks: set = set()

# ─── Config ──────────────────────────────────────────────────────────────────
LOG_LEVEL   = os.getenv("LOG_LEVEL", "INFO")
DB_PATH     = os.getenv("DB_PATH", "/data/edfinder.db")
SPANSH_BASE = "https://spansh.co.uk/api"

# Cache TTLs (seconds)
TTL_AUTOCOMPLETE = int(os.getenv("TTL_AUTOCOMPLETE", 3600))
TTL_SEARCH       = int(os.getenv("TTL_SEARCH",       86400))
TTL_SYSTEM       = int(os.getenv("TTL_SYSTEM",       86400))
TTL_BODY         = int(os.getenv("TTL_BODY",         86400))

# Daily refresh: comma-separated reference system names
DAILY_SYSTEMS = os.getenv("DAILY_SYSTEMS", "Sol,Colonia")
DAILY_RADII   = [15, 50, 100]   # LY buckets to pre-warm per system

WATCHLIST_CHECK_INTERVAL = int(os.getenv("WATCHLIST_CHECK_HOURS", "6")) * 3600

_raw_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost,http://localhost:80,http://127.0.0.1,http://raspberrypi.local,http://ed-finder.local",
)
ALLOWED_ORIGINS: list[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]

HEADERS = {
    "User-Agent": "ED-Finder-SelfHost/3.16 (github.com/ed-finder)",
    "Accept": "application/json",
}

# ─── OBS-1: Structured JSON logging ──────────────────────────────────────────
class StructuredFormatter(logging.Formatter):
    """Emit one JSON object per log record — compatible with Loki / Grafana."""

    def format(self, record: logging.LogRecord) -> str:
        # Base fields always present
        doc: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level":     record.levelname,
            "module":    record.name,
            "message":   record.getMessage(),
        }
        # Extra fields injected via logger.info("…", extra={"request_id": …})
        for key, val in record.__dict__.items():
            if key.startswith("x_") or key in ("request_id", "duration_ms", "status_code"):
                doc[key] = val
        if record.exc_info:
            doc["exception"] = self.formatException(record.exc_info)
        return json.dumps(doc, default=str)


def _setup_logging(level: str) -> None:
    """Replace the root handler with a StructuredFormatter (JSON lines)."""
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


_setup_logging(LOG_LEVEL)
log = logging.getLogger("ed-finder")

if _UVLOOP_ACTIVE:
    log.info("uvloop event loop active (PERF-4)")
else:
    log.info("uvloop not installed — using default asyncio loop")


# ─── OBS-2: Metrics counters ─────────────────────────────────────────────────
_metrics: dict = {
    "start_time":         time.time(),
    "cache_hits":         0,
    "cache_misses":       0,
    "requests_total":     0,
    "spansh_errors":      0,
    "cb_open_count":      0,   # number of times circuit breaker opened
}


# ─── RES-1: Spansh Circuit Breaker ───────────────────────────────────────────
class SpanshCircuitBreaker:
    """
    Three-state circuit breaker protecting Spansh API calls.

    States:
        closed     — normal operation; failures are counted
        open       — calls fail fast (HTTPException 503) after failure_threshold
                     consecutive failures; resets after recovery_timeout seconds
        half-open  — one probe call allowed; success → closed, failure → open
    """

    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half-open"

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout  = recovery_timeout
        self._state            = self.CLOSED
        self._failure_count    = 0
        self._opened_at: Optional[float] = None

    @property
    def state(self) -> str:
        if self._state == self.OPEN:
            if time.time() - (self._opened_at or 0) >= self.recovery_timeout:
                self._state = self.HALF_OPEN
                log.info("CircuitBreaker → half-open (probing Spansh API)",
                         extra={"x_cb_state": self.HALF_OPEN})
        return self._state

    def record_success(self) -> None:
        if self._state in (self.HALF_OPEN, self.OPEN):
            log.info("CircuitBreaker → closed (Spansh API recovered)",
                     extra={"x_cb_state": self.CLOSED})
        self._state         = self.CLOSED
        self._failure_count = 0
        self._opened_at     = None

    def record_failure(self) -> None:
        self._failure_count += 1
        if self._state == self.HALF_OPEN or self._failure_count >= self.failure_threshold:
            if self._state != self.OPEN:
                _metrics["cb_open_count"] += 1
                log.warning(
                    "CircuitBreaker → open (Spansh API unreachable; %d failures)",
                    self._failure_count,
                    extra={"x_cb_state": self.OPEN,
                           "x_failure_count": self._failure_count},
                )
            self._state     = self.OPEN
            self._opened_at = self._opened_at or time.time()

    def allow_request(self) -> bool:
        return self.state in (self.CLOSED, self.HALF_OPEN)


_circuit_breaker = SpanshCircuitBreaker(failure_threshold=5, recovery_timeout=60.0)


# ─── DB helpers ──────────────────────────────────────────────────────────────
def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # PERF-2: Pi 5 optimised SQLite settings
    conn.execute("PRAGMA journal_mode=WAL")          # concurrent reads during writes
    conn.execute("PRAGMA synchronous=NORMAL")        # fsync only at WAL checkpoints
    conn.execute("PRAGMA cache_size=-32000")         # 32 MB page cache (per connection)
    conn.execute("PRAGMA mmap_size=268435456")       # 256 MB memory-mapped I/O
    conn.execute("PRAGMA temp_store=MEMORY")         # temp tables / sort buffers in RAM
    conn.execute("PRAGMA foreign_keys=ON")           # enforce FK constraints
    return conn


@contextmanager
def db_conn():
    """Context manager that always closes the connection, even on error."""
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with db_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS cache (
                key        TEXT PRIMARY KEY,
                data       TEXT NOT NULL,
                created_at REAL NOT NULL,
                ttl        REAL NOT NULL DEFAULT 86400
            );
            -- Index lets expired-row DELETE and age lookups avoid full scans
            CREATE INDEX IF NOT EXISTS idx_cache_age ON cache(created_at);

            CREATE TABLE IF NOT EXISTS systems (
                id64       INTEGER PRIMARY KEY,
                name       TEXT NOT NULL,
                x          REAL, y REAL, z REAL,
                population INTEGER DEFAULT 0,
                is_colonised INTEGER DEFAULT 0,
                data       TEXT,
                updated_at REAL
            );
            CREATE INDEX IF NOT EXISTS idx_sys_name ON systems(name);

            CREATE TABLE IF NOT EXISTS meta (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS watchlist (
                id64         INTEGER PRIMARY KEY,
                name         TEXT NOT NULL,
                x            REAL, y REAL, z REAL,
                added_at     REAL NOT NULL,
                last_checked REAL,
                is_colonised INTEGER DEFAULT 0,
                population   INTEGER DEFAULT 0,
                last_status  TEXT DEFAULT 'unknown',
                alert_config TEXT DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_watch_name ON watchlist(name);
            -- F10: persistent change log for watchlist (90-day TTL)
            CREATE TABLE IF NOT EXISTS watchlist_changelog (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                id64        INTEGER NOT NULL,
                sys_name    TEXT NOT NULL,
                field       TEXT NOT NULL,
                old_value   TEXT,
                new_value   TEXT,
                detected_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_wlog_id64 ON watchlist_changelog(id64);
            CREATE INDEX IF NOT EXISTS idx_wlog_det  ON watchlist_changelog(detected_at);
            -- G9: per-system user notes
            CREATE TABLE IF NOT EXISTS system_notes (
                id64       INTEGER PRIMARY KEY,
                name       TEXT,
                note       TEXT NOT NULL DEFAULT '',
                updated_at REAL NOT NULL DEFAULT 0
            );
            -- AC-1: persistent autocomplete cache (30-day TTL)
            -- Separate from the general cache table so cache clears don't wipe
            -- system name lookups that took real internet round-trips to build.
            CREATE TABLE IF NOT EXISTS autocomplete_cache (
                query      TEXT PRIMARY KEY,       -- normalised lowercase query string
                results    TEXT NOT NULL,           -- full JSON response from Spansh
                cached_at  REAL NOT NULL            -- unix timestamp
            );
            CREATE INDEX IF NOT EXISTS idx_ac_cached_at ON autocomplete_cache(cached_at);
        """)
        conn.commit()
        # PERF-2: refresh query planner statistics (no-op if stats are fresh)
        conn.execute("PRAGMA optimize")
    log.info("Database initialised at %s", DB_PATH)


def cache_get(key: str) -> Optional[Any]:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT data, created_at, ttl FROM cache WHERE key = ?", (key,)
        ).fetchone()
    if row and (time.time() - row["created_at"] < row["ttl"]):
        _metrics["cache_hits"] += 1
        return json.loads(row["data"])
    _metrics["cache_misses"] += 1
    return None


def cache_get_with_age(key: str) -> tuple[Optional[Any], Optional[float]]:
    """Return (data, age_seconds) or (None, None) on miss/expired."""
    with db_conn() as conn:
        row = conn.execute(
            "SELECT data, created_at, ttl FROM cache WHERE key = ?", (key,)
        ).fetchone()
    if row:
        age = time.time() - row["created_at"]
        if age < row["ttl"]:
            _metrics["cache_hits"] += 1
            return json.loads(row["data"]), age
    _metrics["cache_misses"] += 1
    return None, None


def cache_set(key: str, data: Any, ttl: int = TTL_SEARCH) -> None:
    with db_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO cache (key, data, created_at, ttl) VALUES (?, ?, ?, ?)",
            (key, json.dumps(data), time.time(), ttl),
        )
        conn.commit()


def cache_invalidate_pattern(prefix: str) -> int:
    """Delete all cache rows whose key starts with prefix."""
    with db_conn() as conn:
        cur = conn.execute("DELETE FROM cache WHERE key LIKE ?", (f"{prefix}%",))
        conn.commit()
        return cur.rowcount


def meta_set(key: str, value: str) -> None:
    with db_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
        conn.commit()


def meta_get(key: str, default: str = "") -> str:
    with db_conn() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


# ─── Autocomplete cache helpers (AC-1) ───────────────────────────────────────
TTL_AC_PERSISTENT = 30 * 86400  # 30 days — survives cache clears and reboots

def ac_cache_get(query: str) -> Optional[Any]:
    """Return cached autocomplete result for `query`, or None if missing/expired."""
    key = query.lower().strip()
    with db_conn() as conn:
        row = conn.execute(
            "SELECT results, cached_at FROM autocomplete_cache WHERE query = ?", (key,)
        ).fetchone()
    if not row:
        return None
    age = time.time() - row["cached_at"]
    if age > TTL_AC_PERSISTENT:
        return None   # expired — let it refresh from Spansh
    return json.loads(row["results"])

def ac_cache_set(query: str, data: Any) -> None:
    """Store autocomplete result for `query` in the persistent cache."""
    key = query.lower().strip()
    with db_conn() as conn:
        conn.execute(
            """INSERT INTO autocomplete_cache (query, results, cached_at)
               VALUES (?, ?, ?)
               ON CONFLICT(query) DO UPDATE SET
                   results   = excluded.results,
                   cached_at = excluded.cached_at""",
            (key, json.dumps(data), time.time()),
        )
        conn.commit()


# ─── Spansh HTTP helpers ──────────────────────────────────────────────────────
async def _retry(coro_factory, retries: int = 3, base_delay: float = 1.0) -> Any:
    """Run coro_factory(), retrying up to `retries` times with exponential back-off."""
    for attempt in range(retries):
        try:
            return await coro_factory()
        except (httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException) as exc:
            if attempt == retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            log.warning("Spansh request failed (attempt %d/%d): %s — retrying in %.1fs",
                        attempt + 1, retries, exc, delay)
            await asyncio.sleep(delay)


async def spansh_get(path: str, params: Optional[dict] = None) -> Any:
    """GET from Spansh via persistent client with circuit breaker + retry/back-off."""
    if _http is None:
        raise RuntimeError("HTTP client is not initialised — is the app lifespan running?")
    # RES-1: circuit breaker guard
    if not _circuit_breaker.allow_request():
        _metrics["spansh_errors"] += 1
        raise HTTPException(503, "Spansh API circuit breaker is open — try again in 60 s")

    async def _do():
        r = await _http.get(f"{SPANSH_BASE}/{path}", params=params)
        r.raise_for_status()
        return r.json()

    try:
        result = await _retry(_do)
        _circuit_breaker.record_success()
        return result
    except HTTPException:
        # Circuit-breaker 503 — already counted above; do not double-count
        raise
    except Exception as exc:
        _circuit_breaker.record_failure()
        _metrics["spansh_errors"] += 1
        log.debug("spansh_get error: %s", exc)
        raise


async def spansh_post(path: str, body: dict) -> Any:
    """POST to Spansh via persistent client with circuit breaker + retry/back-off."""
    if _http is None:
        raise RuntimeError("HTTP client is not initialised — is the app lifespan running?")
    # RES-1: circuit breaker guard
    if not _circuit_breaker.allow_request():
        _metrics["spansh_errors"] += 1
        raise HTTPException(503, "Spansh API circuit breaker is open — try again in 60 s")

    async def _do():
        r = await _http.post(f"{SPANSH_BASE}/{path}", json=body)
        r.raise_for_status()
        return r.json()

    try:
        result = await _retry(_do)
        _circuit_breaker.record_success()
        return result
    except HTTPException:
        # Circuit-breaker 503 — already counted above; do not double-count
        raise
    except Exception as exc:
        _circuit_breaker.record_failure()
        _metrics["spansh_errors"] += 1
        log.debug("spansh_post error: %s", exc)
        raise


# ─── Background tasks ─────────────────────────────────────────────────────────
async def _prewarm_one(system_name: str, radius: int) -> None:
    """Fetch and cache systems within `radius` LY of `system_name`."""
    try:
        search_data = await spansh_get("search", {"q": system_name})
        if not search_data.get("results"):
            return
        rec = search_data["results"][0]["record"]
        x, y, z = rec.get("x", 0), rec.get("y", 0), rec.get("z", 0)

        body = {
            "filters": {
                "distance": {"min": 0, "max": radius},
            },
            "reference_coords": {"x": x, "y": y, "z": z},
            "sort": [{"distance": {"direction": "asc"}}],
            "size": 100, "from": 0,
        }
        data = await spansh_post("systems/search", body)
        cache_key = "sys:" + hashlib.md5(
            json.dumps(body, sort_keys=True).encode()
        ).hexdigest()
        cache_set(cache_key, data, ttl=TTL_SEARCH)
        log.info("Pre-warmed %s @%dLY → %d systems", system_name, radius, data.get("count", 0))
    except Exception as exc:
        log.warning("Pre-warm failed for %s @%dLY: %s", system_name, radius, exc)


async def daily_refresh_task() -> None:
    """Run once at startup then every 24 h."""
    while True:
        log.info("Starting daily data refresh…")
        meta_set("last_refresh_start", datetime.now(timezone.utc).isoformat())
        systems = [s.strip() for s in DAILY_SYSTEMS.split(",") if s.strip()]
        for sys_name in systems:
            for radius in DAILY_RADII:
                await _prewarm_one(sys_name, radius)
                await asyncio.sleep(0.5)   # polite to Spansh
        meta_set("last_refresh_end", datetime.now(timezone.utc).isoformat())
        log.info("Daily refresh complete. Sleeping 24 h.")
        await asyncio.sleep(86400)


async def cache_cleanup_task() -> None:
    """Delete expired cache rows once per night to keep the DB lean."""
    await asyncio.sleep(3600)   # first run 1 h after startup
    while True:
        try:
            with db_conn() as conn:
                now = time.time()
                cur = conn.execute(
                    "DELETE FROM cache WHERE created_at + ttl < ?", (now,)
                )
                deleted = cur.rowcount
                conn.commit()
                if deleted > 500:
                    try:
                        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    except Exception:
                        pass  # best-effort; not critical
            if deleted:
                log.info("Cache cleanup: removed %d expired rows", deleted)
            meta_set("last_cache_cleanup", datetime.now(timezone.utc).isoformat())
            # F10: prune watchlist changelog older than 90 days
            with db_conn() as conn:
                cutoff = time.time() - 90 * 86400
                cur2 = conn.execute("DELETE FROM watchlist_changelog WHERE detected_at < ?", (cutoff,))
                conn.commit()
                if cur2.rowcount:
                    log.info("Changelog cleanup: removed %d old rows", cur2.rowcount)
            # AC-1: prune autocomplete cache entries older than 30 days
            with db_conn() as conn:
                ac_cutoff = time.time() - TTL_AC_PERSISTENT
                cur3 = conn.execute(
                    "DELETE FROM autocomplete_cache WHERE cached_at < ?", (ac_cutoff,)
                )
                conn.commit()
                if cur3.rowcount:
                    log.info("Autocomplete cache cleanup: removed %d expired entries", cur3.rowcount)
        except Exception as exc:
            log.warning("Cache cleanup error: %s", exc)
        await asyncio.sleep(86400)


async def scheduled_watchlist_check() -> None:
    """Background task: check watchlist every WATCHLIST_CHECK_HOURS hours."""
    if WATCHLIST_CHECK_INTERVAL <= 0:
        log.info("Watchlist auto-check disabled (WATCHLIST_CHECK_HOURS=0)")
        return
    await asyncio.sleep(300)
    while True:
        try:
            with db_conn() as conn:
                rows = conn.execute("SELECT * FROM watchlist").fetchall()
            if rows:
                log.info("Scheduled watchlist check: %d systems", len(rows))
                sem = asyncio.Semaphore(3)

                async def _chk(row):
                    async with sem:
                        try:
                            data = await spansh_get(f"system/{row['id64']}")
                            rec  = data.get("record", {})
                            nc   = int(bool(rec.get("is_colonised", 0)))
                            np_  = int(rec.get("population", 0))
                            if nc != row["is_colonised"] or np_ != row["population"]:
                                now_ts = time.time()
                                with db_conn() as c2:
                                    c2.execute(
                                        "UPDATE watchlist "
                                        "SET is_colonised=?, population=?, last_checked=?, last_status=? "
                                        "WHERE id64=?",
                                        (nc, np_, now_ts, "changed", row["id64"]),
                                    )
                                    # F10: write changelog rows for each changed field
                                    if nc != row["is_colonised"]:
                                        c2.execute(
                                            "INSERT INTO watchlist_changelog (id64, sys_name, field, old_value, new_value, detected_at) VALUES (?,?,?,?,?,?)",
                                            (row["id64"], row["name"], "is_colonised", str(row["is_colonised"]), str(nc), now_ts)
                                        )
                                    if np_ != row["population"]:
                                        c2.execute(
                                            "INSERT INTO watchlist_changelog (id64, sys_name, field, old_value, new_value, detected_at) VALUES (?,?,?,?,?,?)",
                                            (row["id64"], row["name"], "population", str(row["population"]), str(np_), now_ts)
                                        )
                                    c2.commit()
                                log.info("Watchlist change: %s colonised %s→%s pop %s→%s",
                                         row["name"], row["is_colonised"], nc,
                                         row["population"], np_)
                            else:
                                with db_conn() as c2:
                                    c2.execute(
                                        "UPDATE watchlist SET last_checked=?, last_status=? WHERE id64=?",
                                        (time.time(), "unchanged", row["id64"]),
                                    )
                                    c2.commit()
                        except Exception as exc:
                            log.debug("Scheduled watchlist skip %s: %s", row["id64"], exc)

                await asyncio.gather(*[_chk(r) for r in rows], return_exceptions=True)
                meta_set("watchlist_last_checked", datetime.now(timezone.utc).isoformat())
                log.info("Scheduled watchlist check complete.")
        except Exception as exc:
            log.warning("Scheduled watchlist task error: %s", exc)
        await asyncio.sleep(WATCHLIST_CHECK_INTERVAL)


# ─── App lifecycle ────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    global _http
    _http = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0),
        headers=HEADERS,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        http2=False,
    )
    init_db()
    refresh_task   = asyncio.create_task(daily_refresh_task(),        name="daily_refresh")
    watchlist_task = asyncio.create_task(scheduled_watchlist_check(), name="watchlist_check")
    cleanup_task   = asyncio.create_task(cache_cleanup_task(),         name="cache_cleanup")
    log.info("ED:Finder API v3.16 started — background tasks launched",
             extra={"x_uvloop": _UVLOOP_ACTIVE})

    yield  # ── App is running ─────────────────────────────────────────────

    # ── Shutdown ─────────────────────────────────────────────────────────────
    refresh_task.cancel()
    watchlist_task.cancel()
    cleanup_task.cancel()
    for t in list(_background_tasks):
        t.cancel()
    await asyncio.gather(
        refresh_task, watchlist_task, cleanup_task,
        *_background_tasks,
        return_exceptions=True,
    )
    await _http.aclose()
    _http = None
    log.info("ED:Finder API shutdown complete")


# ─── OBS-3: Request-ID Middleware ────────────────────────────────────────────
class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Generate or propagate an X-Request-ID header on every request.
    The same ID is reflected in the response so clients can correlate logs.
    A thread-local-like contextvar would be ideal; here we inject it into
    the request state so route handlers can log it if needed.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = (
            request.headers.get("X-Request-ID")
            or str(uuid.uuid4())
        )
        request.state.request_id = request_id
        _metrics["requests_total"] += 1

        t0 = time.time()
        response: Response = await call_next(request)
        duration_ms = round((time.time() - t0) * 1000)

        response.headers["X-Request-ID"] = request_id
        # Log every request in structured format
        log.info(
            "%s %s → %d  (%dms)",
            request.method, request.url.path, response.status_code, duration_ms,
            extra={
                "request_id":  request_id,
                "method":      request.method,
                "path":        request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response


# ─── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="ED:Finder API",
    description="Self-hosted caching proxy for Spansh data — ED:Finder",
    version="3.16.0",
    lifespan=lifespan,
)

# OBS-3: Request-ID middleware (must be added before CORS so ID is always set)
app.add_middleware(RequestIDMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Cache-Age", "X-Cache-Status", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-Cache-Age", "X-Cache-Status"],
)


# ─── OBS-2: Prometheus /api/metrics endpoint ─────────────────────────────────
@app.get("/api/metrics", response_class=PlainTextResponse, include_in_schema=False)
async def prometheus_metrics():
    """
    Exposes runtime counters in Prometheus text format.
    Scrape with: prometheus.yml → scrape_configs → job_name: ed-finder
    """
    uptime = time.time() - _metrics["start_time"]
    hits   = _metrics["cache_hits"]
    misses = _metrics["cache_misses"]
    total  = hits + misses
    ratio  = hits / total if total else 0.0

    # Live cache row count
    with db_conn() as conn:
        cache_live = conn.execute(
            "SELECT COUNT(*) FROM cache WHERE created_at + ttl > ?", (time.time(),)
        ).fetchone()[0]

    lines = [
        "# HELP edfinder_uptime_seconds Seconds since the API process started",
        "# TYPE edfinder_uptime_seconds gauge",
        f"edfinder_uptime_seconds {uptime:.2f}",
        "",
        "# HELP edfinder_cache_hits_total Total cache hit count",
        "# TYPE edfinder_cache_hits_total counter",
        f"edfinder_cache_hits_total {hits}",
        "",
        "# HELP edfinder_cache_misses_total Total cache miss count",
        "# TYPE edfinder_cache_misses_total counter",
        f"edfinder_cache_misses_total {misses}",
        "",
        "# HELP edfinder_cache_hit_ratio Cache hit ratio (0..1)",
        "# TYPE edfinder_cache_hit_ratio gauge",
        f"edfinder_cache_hit_ratio {ratio:.4f}",
        "",
        "# HELP edfinder_cache_live_entries Current number of live (non-expired) cache entries",
        "# TYPE edfinder_cache_live_entries gauge",
        f"edfinder_cache_live_entries {cache_live}",
        "",
        "# HELP edfinder_requests_total Total HTTP requests handled",
        "# TYPE edfinder_requests_total counter",
        f"edfinder_requests_total {_metrics['requests_total']}",
        "",
        "# HELP edfinder_spansh_errors_total Total Spansh API errors",
        "# TYPE edfinder_spansh_errors_total counter",
        f"edfinder_spansh_errors_total {_metrics['spansh_errors']}",
        "",
        "# HELP edfinder_circuit_breaker_open 1 if circuit breaker is currently open",
        "# TYPE edfinder_circuit_breaker_open gauge",
        f"edfinder_circuit_breaker_open {1 if _circuit_breaker.state == SpanshCircuitBreaker.OPEN else 0}",
        "",
        "# HELP edfinder_circuit_breaker_open_total Times circuit breaker has opened",
        "# TYPE edfinder_circuit_breaker_open_total counter",
        f"edfinder_circuit_breaker_open_total {_metrics['cb_open_count']}",
        "",
        "# HELP edfinder_uvloop_active 1 if uvloop event loop is in use",
        "# TYPE edfinder_uvloop_active gauge",
        f"edfinder_uvloop_active {1 if _UVLOOP_ACTIVE else 0}",
    ]
    return "\n".join(lines) + "\n"


# ─── Routes — Watchlist ───────────────────────────────────────────────────────
@app.get("/api/watchlist")
async def get_watchlist():
    with db_conn() as conn:
        rows = conn.execute("SELECT * FROM watchlist ORDER BY added_at DESC").fetchall()
    return {"watchlist": [dict(r) for r in rows]}


@app.post("/api/watchlist/{id64}")
async def add_to_watchlist(id64: int, request: Request):
    # FIX-WL1: accept body as raw Request to avoid mutable-default-arg anti-pattern
    # and to gracefully handle missing/empty body
    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        body = {}
    with db_conn() as conn:
        existing = conn.execute("SELECT id64 FROM watchlist WHERE id64 = ?", (id64,)).fetchone()
        if existing:
            return {"status": "already_watching"}
        conn.execute(
            """INSERT INTO watchlist
               (id64, name, x, y, z, added_at, is_colonised, population, last_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                id64,
                body.get("name", "Unknown"),
                body.get("x", 0), body.get("y", 0), body.get("z", 0),
                time.time(),
                int(bool(body.get("is_colonised", 0))),
                int(body.get("population", 0)),
                "watching",
            ),
        )
        conn.commit()
    return {"status": "added", "id64": id64}


@app.delete("/api/watchlist/{id64}")
async def remove_from_watchlist(id64: int):
    with db_conn() as conn:
        conn.execute("DELETE FROM watchlist WHERE id64 = ?", (id64,))
        conn.commit()
    return {"status": "removed", "id64": id64}


@app.get("/api/watchlist/changes")
async def watchlist_changes():
    with db_conn() as conn:
        rows = conn.execute("SELECT * FROM watchlist").fetchall()
    if not rows:
        return {"changes": [], "checked": 0}

    sem = asyncio.Semaphore(5)

    async def _check_one(row):
        async with sem:
            try:
                data = await spansh_get(f"system/{row['id64']}")
                rec  = data.get("record", {})
                nc   = int(bool(rec.get("is_colonised", 0)))
                np_  = int(rec.get("population", 0))
                changed = (nc != row["is_colonised"]) or (np_ != row["population"])
                if changed:
                    now_ts = time.time()
                    with db_conn() as c2:
                        c2.execute(
                            "UPDATE watchlist SET is_colonised=?, population=?, "
                            "last_checked=?, last_status=? WHERE id64=?",
                            (nc, np_, now_ts, "changed", row["id64"]),
                        )
                        # F10: write changelog rows
                        if nc != row["is_colonised"]:
                            c2.execute(
                                "INSERT INTO watchlist_changelog (id64, sys_name, field, old_value, new_value, detected_at) VALUES (?,?,?,?,?,?)",
                                (row["id64"], row["name"], "is_colonised", str(row["is_colonised"]), str(nc), now_ts)
                            )
                        if np_ != row["population"]:
                            c2.execute(
                                "INSERT INTO watchlist_changelog (id64, sys_name, field, old_value, new_value, detected_at) VALUES (?,?,?,?,?,?)",
                                (row["id64"], row["name"], "population", str(row["population"]), str(np_), now_ts)
                            )
                        c2.commit()
                else:
                    with db_conn() as c2:
                        c2.execute(
                            "UPDATE watchlist SET last_checked=?, last_status=? WHERE id64=?",
                            (time.time(), "unchanged", row["id64"]),
                        )
                        c2.commit()
                return {
                    "id64": row["id64"], "name": row["name"],
                    "changed": changed,
                    "old": {"is_colonised": row["is_colonised"], "population": row["population"]},
                    "new": {"is_colonised": nc, "population": np_},
                }
            except Exception as exc:
                log.debug("Watchlist check skip %s: %s", row["id64"], exc)
                return None

    results = await asyncio.gather(*[_check_one(r) for r in rows], return_exceptions=False)
    changes = [r for r in results if r and r["changed"]]
    meta_set("watchlist_last_checked", datetime.now(timezone.utc).isoformat())
    return {"changes": changes, "checked": len(rows)}


@app.get("/api/watchlist/changelog")
async def watchlist_changelog(limit: int = 50):
    # Return the N most recent watchlist change-log entries (F10)
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT id64, sys_name, field, old_value, new_value, detected_at "
            "FROM watchlist_changelog ORDER BY detected_at DESC LIMIT ?",
            (min(limit, 200),)
        ).fetchall()
    return {
        "changelog": [
            {
                "id64":        r["id64"],
                "sys_name":    r["sys_name"],
                "field":       r["field"],
                "old_value":   r["old_value"],
                "new_value":   r["new_value"],
                "detected_at": r["detected_at"],
            }
            for r in rows
        ],
        "count": len(rows)
    }


# ─── Routes — Watchlist Alert Config ─────────────────────────────────────────
@app.patch("/api/watchlist/{id64}/alert")
async def update_alert_config(id64: int, payload: dict):
    """G3: Update alert_config for a watchlist entry."""
    cfg = payload.get("alert_config", {})
    with db_conn() as conn:
        conn.execute(
            "UPDATE watchlist SET alert_config = ? WHERE id64 = ?",
            (json.dumps(cfg), id64)
        )
        conn.commit()
    return {"ok": True}


# ─── Routes — System Notes (G9) ──────────────────────────────────────────────
@app.get("/api/systems/{id64}/note")
async def get_system_note(id64: int):
    """Return the user note for a system."""
    with db_conn() as conn:
        row = conn.execute(
            "SELECT note, updated_at FROM system_notes WHERE id64 = ?", (id64,)
        ).fetchone()
    if row:
        return {"id64": id64, "note": row["note"], "updated_at": row["updated_at"]}
    return {"id64": id64, "note": "", "updated_at": None}


@app.post("/api/systems/{id64}/note")
async def upsert_system_note(id64: int, payload: dict):
    """Create or update a note for a system."""
    note = str(payload.get("note", "")).strip()
    name = str(payload.get("name", ""))
    now = time.time()
    with db_conn() as conn:
        conn.execute(
            """INSERT INTO system_notes (id64, name, note, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(id64) DO UPDATE SET note=excluded.note, updated_at=excluded.updated_at""",
            (id64, name, note, now)
        )
        conn.commit()
    return {"ok": True, "id64": id64, "note": note, "updated_at": now}


@app.delete("/api/systems/{id64}/note")
async def delete_system_note(id64: int):
    """Delete the note for a system."""
    with db_conn() as conn:
        conn.execute("DELETE FROM system_notes WHERE id64 = ?", (id64,))
        conn.commit()
    return {"ok": True}


@app.get("/api/systems/notes")
async def list_notes():
    """Return all systems that have notes."""
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT id64, name, note, updated_at FROM system_notes WHERE note != '' ORDER BY updated_at DESC"
        ).fetchall()
    return {"notes": [dict(r) for r in rows], "count": len(rows)}


# ─── Routes — Cache & Admin ───────────────────────────────────────────────────
@app.get("/api/cache/stats")
async def cache_stats():
    """Return cache statistics broken down by key prefix."""
    now = time.time()
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT key, created_at, ttl FROM cache WHERE created_at + ttl > ?",
            (now,)
        ).fetchall()

    total = len(rows)
    prefixes = {"ac": 0, "sys": 0, "system": 0, "body": 0, "other": 0}
    expiring_soon = 0
    oldest_ts = None
    newest_ts = None

    for row in rows:
        k, ca, ttl = row["key"], row["created_at"], row["ttl"]
        if k.startswith("ac:"):       prefixes["ac"] += 1
        elif k.startswith("sys:"):    prefixes["sys"] += 1
        elif k.startswith("system:"): prefixes["system"] += 1
        elif k.startswith("body:"):   prefixes["body"] += 1
        else:                         prefixes["other"] += 1
        remaining = ca + ttl - now
        if 0 < remaining < 3600:      expiring_soon += 1
        if oldest_ts is None or ca < oldest_ts: oldest_ts = ca
        if newest_ts is None or ca > newest_ts: newest_ts = ca

    last_cleanup = meta_get("last_cache_cleanup", "never")
    return {
        "total": total,
        "by_prefix": prefixes,
        "expiring_soon": expiring_soon,
        "oldest_entry": datetime.fromtimestamp(oldest_ts, tz=timezone.utc).isoformat() if oldest_ts else None,
        "newest_entry": datetime.fromtimestamp(newest_ts, tz=timezone.utc).isoformat() if newest_ts else None,
        "last_cleanup": last_cleanup,
        "hit_ratio": round(_metrics["cache_hits"] / max(_metrics["cache_hits"] + _metrics["cache_misses"], 1), 4),
    }


@app.post("/api/cache/clear")
async def clear_cache(prefix: str = ""):
    """Admin: clear cache entries (optionally by prefix)."""
    cleared = cache_invalidate_pattern(prefix)
    return {"cleared": cleared}


@app.post("/api/refresh")
async def trigger_refresh():
    """Admin: trigger an immediate background data refresh."""
    async def _bg():
        systems = [s.strip() for s in DAILY_SYSTEMS.split(",") if s.strip()]
        for sys_name in systems:
            for radius in DAILY_RADII:
                await _prewarm_one(sys_name, radius)
                await asyncio.sleep(0.5)
        meta_set("last_refresh_end", datetime.now(timezone.utc).isoformat())

    task = asyncio.create_task(_bg())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"status": "refresh started in background"}


# ─── Routes — Core ────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"ok": True}


@app.get("/api/status")
async def api_status():
    """Health check + last refresh time + Spansh reachability."""
    with db_conn() as conn:
        _row = conn.execute(
            "SELECT COUNT(*) FROM cache WHERE created_at + ttl > ?", (time.time(),)
        ).fetchone()
        cache_count = _row[0] if _row is not None else 0
        # AC-1: count persistent autocomplete entries
        _ac_row = conn.execute(
            "SELECT COUNT(*) FROM autocomplete_cache WHERE cached_at > ?",
            (time.time() - TTL_AC_PERSISTENT,)
        ).fetchone()
        ac_count = _ac_row[0] if _ac_row is not None else 0

    spansh_ok = False
    spansh_latency_ms = None
    try:
        t0 = time.time()
        await spansh_get("search", {"q": "Sol"})
        spansh_ok = True
        spansh_latency_ms = round((time.time() - t0) * 1000)
    except Exception:
        pass

    return {
        "status": "online",
        "version": "3.16.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cache_entries": cache_count,
        "ac_cache_entries": ac_count,
        "last_refresh_start": meta_get("last_refresh_start", "never"),
        "last_refresh_end":   meta_get("last_refresh_end",   "never"),
        "watchlist_last_checked": meta_get("watchlist_last_checked", "never"),
        "last_cache_cleanup": meta_get("last_cache_cleanup", "never"),
        "spansh_reachable": spansh_ok,
        "spansh_latency_ms": spansh_latency_ms,
        "spansh_source": SPANSH_BASE,
        "daily_systems": DAILY_SYSTEMS,
        "circuit_breaker": _circuit_breaker.state,
        "uvloop": _UVLOOP_ACTIVE,
    }


@app.get("/api/search")
async def autocomplete(q: str = Query(..., min_length=2, max_length=200)):
    """System name autocomplete — persistent 30-day local cache, falls back to Spansh."""
    # AC-1: check persistent autocomplete cache first (survives reboots + cache clears)
    persistent = ac_cache_get(q)
    if persistent is not None:
        return persistent

    # AC-1: short-lived general cache (1 hour) as second layer
    key = f"ac:{q.lower()}"
    cached = cache_get(key)
    if cached:
        return cached

    # AC-1: not cached at all — fetch from Spansh and store in both caches
    try:
        data = await spansh_get("search", {"q": q})
        ac_cache_set(q, data)                    # persistent 30-day store
        cache_set(key, data, ttl=TTL_AUTOCOMPLETE)  # short-lived general cache
        return data
    except Exception as exc:
        raise HTTPException(502, f"Spansh API error: {exc}")


@app.post("/api/systems/search")
async def systems_search(body: Dict[str, Any]):
    """System search with filters — cached 24 hours. Returns X-Cache-Age header."""
    key = "sys:" + hashlib.md5(json.dumps(body, sort_keys=True).encode()).hexdigest()
    cached, age = cache_get_with_age(key)
    if cached is not None:
        return JSONResponse(
            content=cached,
            headers={"X-Cache-Age": str(int(age)), "X-Cache-Status": "HIT"},
        )
    try:
        data = await spansh_post("systems/search", body)
        cache_set(key, data, ttl=TTL_SEARCH)
        return JSONResponse(
            content=data,
            headers={"X-Cache-Age": "0", "X-Cache-Status": "MISS"},
        )
    except Exception as exc:
        raise HTTPException(502, f"Spansh API error: {exc}")


@app.get("/api/system/{id64}")
async def get_system(id64: int):
    """Full system data — cached 24 hours."""
    key = f"system:{id64}"
    cached = cache_get(key)
    if cached:
        return cached
    try:
        data = await spansh_get(f"system/{id64}")
        cache_set(key, data, ttl=TTL_SYSTEM)
        return data
    except Exception as exc:
        raise HTTPException(502, f"Spansh API error: {exc}")


@app.post("/api/systems/batch")
async def batch_systems(body: Dict[str, Any]):
    """
    Fetch full data for multiple systems in one request.
    Body: { "id64s": [id64, ...] }  (max 100)
    Returns: { "systems": { "<id64>": <system_record>, ... } }
    """
    id64s: List[int] = body.get("id64s", [])
    if not id64s:
        return {"systems": {}}
    # FIX-BATCH: validate id64s are all integers before proceeding
    if not all(isinstance(i, int) for i in id64s):
        raise HTTPException(400, "All id64 values must be integers")
    if len(id64s) > 100:
        raise HTTPException(400, "Maximum 100 systems per batch request")

    results: Dict[str, Any] = {}
    misses: List[int] = []
    max_cache_age: float = 0.0  # BUG-FIX-H: track oldest cache entry to report real age

    for id64 in id64s:
        key = f"system:{id64}"
        cached, age = cache_get_with_age(key)
        if cached is not None:
            results[str(id64)] = cached
            if age is not None and age > max_cache_age:
                max_cache_age = age
        else:
            misses.append(id64)

    if misses:
        sem = asyncio.Semaphore(8)

        async def _fetch(id64: int):
            async with sem:
                try:
                    data = await spansh_get(f"system/{id64}")
                    cache_set(f"system:{id64}", data, ttl=TTL_SYSTEM)
                    results[str(id64)] = data
                except Exception as exc:
                    log.debug("Batch fetch miss for %s: %s", id64, exc)

        await asyncio.gather(*[_fetch(i) for i in misses])

    all_cached = len(misses) == 0
    # Report real cache age (seconds) so frontend can show "cached Xh Ym ago" vs "live data"
    reported_age = int(max_cache_age) if all_cached and max_cache_age > 0 else 0
    return JSONResponse(
        content={"systems": results, "cached": len(id64s) - len(misses), "fetched": len(misses)},
        headers={
            "X-Cache-Age":    str(reported_age),
            "X-Cache-Status": "HIT" if all_cached else "PARTIAL",
        },
    )


@app.get("/api/body/{body_id}")
async def get_body(body_id: int):
    """Body detail — cached 24 hours."""
    key = f"body:{body_id}"
    cached = cache_get(key)
    if cached:
        return cached
    try:
        data = await spansh_get(f"body/{body_id}")
        cache_set(key, data, ttl=TTL_BODY)
        return data
    except Exception as exc:
        raise HTTPException(502, f"Spansh API error: {exc}")
