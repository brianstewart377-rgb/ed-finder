#!/usr/bin/env python3
"""
ED Finder — Hetzner Backend
Version: 3.1 (PostgreSQL 16 / asyncpg)

This file is the **composition root**. It wires config, state, middleware,
lifespan, exception handlers, and router mounts. All business logic lives
in routers/ and helpers/.

Endpoint surface (see individual router docstrings for detail):

  routers/meta.py       health, status, local/status, metrics
  routers/watchlist.py  watchlist CRUD + changelog
  routers/notes.py      per-system user notes
  routers/events.py     EDDN SSE live feed + recent
  routers/admin.py      cache stats/clear + cluster-rebuild trigger
  routers/search.py     autocomplete + local/galaxy/cluster search
  routers/systems.py    per-system / per-body detail + batch lookup
  routers/map.py        galaxy regions, cluster hulls, heatmap, timeline
  routers/ratings.py    rating rerank with custom weights (v3.1 — preserved unchanged)
  routers/archetypes.py archetype rankings, rerank, system detail, simulate, profiles
  share_router.py       /s/{id64} OG-tagged share preview + PNG
"""
import asyncio
import os
import pathlib as _pl
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

import asyncpg
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse as _FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# Shared config, state, deps
from config  import settings, log, limiter
from state   import set_pool, set_redis, metrics as _metrics

# Routers
from routers.admin     import router as admin_router
from routers.events    import router as events_router, eddn_pubsub_bridge
from routers.map       import router as map_router
from routers.meta      import router as meta_router
from routers.notes     import router as notes_router
from routers.profile   import router as profile_router
from routers.archetypes  import router as archetypes_router
from routers.ratings     import router as ratings_router
from routers.simulation  import router as simulation_router
from routers.search    import router as search_router
from routers.systems   import router as systems_router
from routers.watchlist import router as watchlist_router
from share_router      import router as share_router

# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------
_sse_pubsub_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _sse_pubsub_task
    log.info(f"ED Finder Hetzner backend v{settings.app_version} starting ...")

    async def _init_conn(conn: asyncpg.Connection) -> None:
        """Per-connection initialiser.

        Audit fix (2026-05-08, AUDIT_REPORT.md §Phase 6): without this
        codec, asyncpg returns JSONB columns as strings, which made
        /api/profile/sync round-trip a stringified JSON instead of the
        original dict. Registering the codec at pool-init time fixes
        every JSONB read across the app.

        NOTE: `statement_timeout` is NOT set here — pgBouncer's
        transaction-pool mode wipes session-level SETs when it returns
        a server connection to its own pool (verified in prod
        2026-05-09: `SHOW statement_timeout` came back `0` over a
        pooled connection). Instead, it lives in the
        `server_settings={'statement_timeout': …}` startup parameters
        on `asyncpg.create_pool()` above, which pgBouncer preserves.
        """
        import json as _json
        await conn.set_type_codec(
            'jsonb',
            encoder=_json.dumps,
            decoder=_json.loads,
            schema='pg_catalog',
        )
        await conn.set_type_codec(
            'json',
            encoder=_json.dumps,
            decoder=_json.loads,
            schema='pg_catalog',
        )

    pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=5, max_size=20,
        # asyncpg's client-side ceiling — kept generous as a final
        # backstop. The real query budget is enforced server-side via
        # `statement_timeout` below.
        command_timeout=300,
        # pgBouncer transaction-pool mode requires prepared-statement cache off.
        statement_cache_size=0,
        server_settings={
            'application_name': 'ed_finder_api',
            # `statement_timeout` MUST live here, not in `init=_init_conn`.
            # asyncpg sends `server_settings` as protocol-level startup
            # parameters which pgBouncer transaction-pool mode preserves
            # across pooled connections, whereas a `SET statement_timeout`
            # issued from the init callback is wiped by pgBouncer's
            # implicit `DISCARD ALL` / `RESET` between transactions.
            # Verified in prod 2026-05-09: `SHOW statement_timeout` over
            # an asyncpg+pgbouncer pooled conn returned `0` (= unlimited)
            # despite the init callback running. Making it a startup
            # parameter fixes this without disabling pgbouncer pooling.
            'statement_timeout': str(settings.statement_timeout_ms),
        },
        init=_init_conn,
    )
    set_pool(pool)

    redis = None
    try:
        redis = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=settings.redis_max_connections,
            socket_connect_timeout=3,
            socket_timeout=3,
            retry_on_timeout=True,
        )
        await redis.ping()
        set_redis(redis)
        log.info("Redis connected ✓ (pool max=%d)", settings.redis_max_connections)
    except Exception as e:
        log.warning(f"Redis unavailable ({e}) — running without cache")
        set_redis(None)
        redis = None

    if redis is not None:
        _sse_pubsub_task = asyncio.create_task(eddn_pubsub_bridge())
        log.info("EDDN→SSE pub/sub bridge started ✓")

    # Load facility catalogue into memory (simulation engine domain layer)
    try:
        async with pool.acquire() as _conn:
            _rows = await _conn.fetch('SELECT * FROM facility_templates ORDER BY tier, id')
            from domain.facilities import load_catalogue_from_rows
            load_catalogue_from_rows([dict(r) for r in _rows])
            log.info(f"Facility catalogue loaded ✓ ({len(_rows)} facilities)")
    except Exception as _e:
        log.warning(f"Facility catalogue load failed ({_e}) — simulation endpoints will use empty catalogue")

    log.info("PostgreSQL pool ready ✓")
    app.state.pool  = pool
    app.state.redis = redis
    yield

    if _sse_pubsub_task:
        _sse_pubsub_task.cancel()
        try:
            await _sse_pubsub_task
        except (asyncio.CancelledError, Exception):
            pass
    if pool:   await pool.close()
    if redis:  await redis.aclose()
    log.info("Shutdown complete")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title='ED Finder API',
    version=settings.app_version,
    description='Search 186M Elite Dangerous star systems by economy, body types, and distance.',
    lifespan=lifespan,
    docs_url='/docs',
    redoc_url='/redoc',
)

# Rate limiter — attach to app state (slowapi middleware auto-discovers it).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(',') if o.strip()],
    allow_methods=['GET', 'POST', 'PATCH', 'DELETE', 'OPTIONS'],
    allow_headers=['Content-Type', 'X-Admin-Token', 'Authorization'],
)
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware('http')
async def metrics_middleware(request: Request, call_next: Any) -> Response:
    _metrics['requests_total'] += 1
    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000
    if duration_ms > 2000:
        log.warning('Slow request %s %s: %.0fms', request.method, request.url.path, duration_ms)
    return response


# ---------------------------------------------------------------------------
# Exception handlers (RFC 7807 Problem Details)
# ---------------------------------------------------------------------------
@app.exception_handler(HTTPException)
async def problem_details_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            'type':     f'https://httpstatuses.com/{exc.status_code}',
            'title':    exc.detail if isinstance(exc.detail, str) else 'Error',
            'status':   exc.status_code,
            'detail':   exc.detail,
            'instance': str(request.url),
        },
        headers=getattr(exc, 'headers', None),
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    _metrics['errors_total'] += 1
    log.exception('Unhandled error on %s %s', request.method, request.url)
    detail = str(exc) if settings.expose_error_detail else 'Internal server error'
    return JSONResponse(
        status_code=500,
        content={
            'type':   'https://httpstatuses.com/500',
            'title':  'Internal Server Error',
            'status': 500,
            'detail': detail,
        },
    )


# ---------------------------------------------------------------------------
# Router mounts
#
# Order matters only for the SPA fallback at the bottom: API routes must
# match before `/{full_path:path}` swallows them. The /s/<id64> share
# router is mounted first so its ~^/s/[0-9]+$ pattern beats the SPA.
# ---------------------------------------------------------------------------
app.include_router(share_router)
app.include_router(meta_router)
app.include_router(watchlist_router)
app.include_router(notes_router)
app.include_router(profile_router)
app.include_router(admin_router)
app.include_router(events_router)
app.include_router(search_router)
app.include_router(systems_router)
app.include_router(map_router)
app.include_router(archetypes_router)
app.include_router(ratings_router)
app.include_router(simulation_router)


# ---------------------------------------------------------------------------
# SPA fallback + static files
#
# In Docker the production bundle is baked at /app/frontend/ (next to
# apps/api/src/), which is what `__file__.parent.parent / 'frontend'`
# resolves to. In a local dev clone the equivalent location is
# `frontend-v2/dist/` (post-`yarn build`). Try both, in that order, so
# `python -m uvicorn main:app` works directly from the repo root without
# rebuilding the image.
# ---------------------------------------------------------------------------
def _resolve_frontend_dir() -> _pl.Path:
    here       = _pl.Path(__file__).resolve().parent
    candidates = [
        here.parent / 'frontend',                    # Docker baked layout
        here.parent.parent.parent / 'frontend-v2' / 'dist',  # local dev
    ]
    for c in candidates:
        if c.is_dir():
            return c
    # No bundle on disk yet — fall back to the Docker location so the
    # 404 path still works; static-mount block below skips when missing.
    return candidates[0]


_FRONTEND_DIR = _resolve_frontend_dir()

# Mount static assets directory before registering the catch-all so that
# /static/<file> is served by StaticFiles (which includes its own safe path
# resolution).
if _FRONTEND_DIR.is_dir():
    app.mount('/static', StaticFiles(directory=str(_FRONTEND_DIR)), name='static')


_FRONTEND_REAL = _FRONTEND_DIR.resolve()


def _safe_frontend_path(raw: str) -> Optional[_pl.Path]:
    """Resolve a user-supplied path relative to the frontend dir, rejecting
    anything that escapes via '..' or symlinks."""
    if not raw:
        return None
    try:
        candidate = (_FRONTEND_DIR / raw).resolve()
    except (OSError, RuntimeError):
        return None
    # Must be inside the frontend directory (or equal to it).
    if candidate != _FRONTEND_REAL and _FRONTEND_REAL not in candidate.parents:
        return None
    return candidate


@app.get('/{full_path:path}', include_in_schema=False)
async def spa_fallback(full_path: str):
    # API paths should have been matched already; if someone requests
    # /api/<unknown> return 404 JSON instead of serving index.html.
    if full_path.startswith('api/'):
        raise HTTPException(404, f'API endpoint {full_path} not found')

    # No frontend bundle present (e.g. local dev before `yarn build`):
    # short-circuit with a 404 instead of FileResponse'ing a missing file.
    if not _FRONTEND_DIR.is_dir():
        raise HTTPException(
            404,
            'Frontend bundle not built. Run `cd frontend-v2 && yarn build`.',
        )

    candidate = _safe_frontend_path(full_path)
    if candidate and candidate.is_file():
        return _FileResponse(str(candidate))
    # Fall back to index.html for SPA routing
    return _FileResponse(str(_FRONTEND_DIR / 'index.html'))


if __name__ == '__main__':
    import uvicorn
    port = int(os.environ.get('PORT', 5000))
    uvicorn.run(app, host='0.0.0.0', port=port, log_level=settings.log_level.lower())

