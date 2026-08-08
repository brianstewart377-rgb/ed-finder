"""Centralised configuration, logging, rate limiter.

This module is the single source of truth for:
  * `Settings`  — env-var validated settings (pydantic-settings).
  * `settings`  — process-wide singleton, import this everywhere.
  * `log`       — configured root logger (use `logging.getLogger('ed_finder')`
                  subsequently in module files).
  * `limiter`   — slowapi rate limiter, attach via `@limiter.limit(...)`
                  on any route function.

Keep this file side-effect free *except* for logging setup — importing it
must never make network calls, touch the DB, etc.
"""
from __future__ import annotations

import logging
import sys
from typing import Optional

import sentry_sdk
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from slowapi import Limiter
from slowapi.util import get_remote_address


class Settings(BaseSettings):
    database_url:       str  = 'postgresql://postgres:password@localhost:5432/postgres'
    database_readonly_url: Optional[str] = None
    redis_url:          str  = 'redis://redis:6379/0'
    log_level:          str  = 'INFO'
    redis_max_connections: int = 20
    ttl_search:         int  = 3600
    ttl_system:         int  = 86400
    ttl_status:         int  = 60
    ttl_autocomplete:   int  = 86400
    ttl_cluster:        int  = 86400
    rate_limit_search:  str  = '30/minute'
    rate_limit_default: str  = '120/minute'
    app_version:        str  = '3.0.1-hetzner'
    build_sha:          str  = 'unknown'
    admin_token:        Optional[str] = None
    # Optional read-only station enrichment status artifact. This should point
    # at JSON produced by `scripts/station_enrichment_status.py --json` on a
    # filesystem mounted into the API container, for example under /data/logs.
    enrichment_status_json_path: Optional[str] = None
    # Optional read-only warehouse reconciliation/status artifact. This should
    # point at prepublished JSON, usually a warehouse reconciliation report.
    # The API reads and sanitizes it only; it never invokes importer scripts.
    enrichment_warehouse_status_json_path: Optional[str] = None
    # Read-only receipts produced by run_data_invariants_receipted.sh. The API
    # only parses these fixed files to publish freshness/status metrics.
    data_invariants_receipt_paths: str = (
        '/data/receipts/data-invariants/post-deploy/latest.json,'
        '/data/receipts/data-invariants/weekly-latest.json'
    )
    # Per-connection PostgreSQL `statement_timeout` (milliseconds).
    # Applied at pool init by main.py::_init_conn so every query —
    # search, map, status — is bounded server-side. Picked to match the
    # audit's original 15 s budget on the deleted inline-fallback path
    # (commit be6e2b8). Set higher in long-running ad-hoc psql sessions
    # via `SET statement_timeout = ...` per connection.
    statement_timeout_ms: int = 15000
    # CORS: required in production. Default left as a sentinel that the
    # validator rejects so that an unset env in production fails closed.
    # Set CORS_ORIGINS=https://ed-finder.app,https://www.ed-finder.app in .env
    cors_origins:       str  = '__unset__'
    expose_error_detail: bool = False
    # Optional error tracking (GlitchTip, Sentry-API-compatible). Blank
    # disables it entirely — sentry_sdk.init() below is only called when set.
    sentry_dsn:         Optional[str] = None
    # EDDN simulation ingest (apps/api/src/ingest/eddn_client.py): a
    # background task feeding journal_events/body_scan_facts from the
    # live public EDDN relay, for the simulation/buildability engine —
    # the same relay apps/eddn/eddn_listener.py already consumes
    # continuously for systems/bodies/stations, just a narrower slice of
    # events (Scan/FSSBodySignals/SAASignalsFound) into different tables.
    # Defaults ON (decided 2026-08-07) as a deliberate, always-fresh
    # complement to the client-side journal-import lane
    # (journal_import/store.py), which only covers systems a user has
    # actually uploaded a journal for. Kept as a flag, not unconditional,
    # so it can be switched off via env var without a redeploy if it
    # ever needs to be. See CLAUDE.md's roadmap boundaries section for
    # why this is NOT the same thing as the still-deferred "journal-import
    # canonical promotion" work.
    eddn_simulation_ingest_enabled: bool = True

    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    @field_validator(
        'database_readonly_url',
        'enrichment_status_json_path',
        'enrichment_warehouse_status_json_path',
        'sentry_dsn',
        mode='before',
    )
    @classmethod
    def _blank_optional_to_none(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator('cors_origins')
    @classmethod
    def _reject_wildcard_or_unset(cls, v: str) -> str:
        v = (v or '').strip()
        if v in ('__unset__', ''):
            raise ValueError(
                "CORS_ORIGINS must be set explicitly (e.g. "
                "'https://ed-finder.app,https://www.ed-finder.app'). "
                "Wildcard '*' is rejected as defence in depth — admin "
                "endpoints accept bearer tokens and a wildcard CORS "
                "policy enables token-leak vectors."
            )
        if v == '*':
            raise ValueError(
                "CORS_ORIGINS='*' is rejected. Bearer-token endpoints + "
                "credentialed cross-origin requests is a known leak vector. "
                "List explicit origins instead."
            )
        return v


settings = Settings()


# ---------------------------------------------------------------------------
# Logging — set up once at import time so every module gets the same format.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger('ed_finder')


# ---------------------------------------------------------------------------
# Error tracking (GlitchTip, Sentry-API-compatible) — opt-in via SENTRY_DSN.
# generic_error_handler in main.py calls sentry_sdk.capture_exception()
# explicitly, since it swallows every unhandled exception into a JSON
# response before it can reach sentry_sdk's automatic ASGI-level capture.
# ---------------------------------------------------------------------------
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        release=settings.build_sha,
        send_default_pii=False,
        traces_sample_rate=0,
    )


# ---------------------------------------------------------------------------
# Rate limiter (shared across all routers).
#
# Storage: in-memory.
#
# The previous configuration used `storage_uri=settings.redis_url` so the
# limit buckets were Redis-backed, on the premise that "limits apply
# globally across workers & containers". In practice we run a single api
# container with `--workers 1` (per the comment in apps/api/Dockerfile)
# so there is no second process for the bucket to be shared with — the
# Redis storage was buying nothing. What it WAS buying:
#
#   * If Redis is unreachable at api startup, slowapi/limits raises
#     during the first rate-limited request, returning 500. A Redis
#     blip therefore took down every search endpoint.
#   * A Redis hiccup during runtime caused intermittent 500s on
#     `@limiter.limit(...)` paths even though nothing else needed Redis
#     for that request.
#
# Switching to memory:// removes both failure modes. If we ever scale
# the api horizontally (multiple containers behind nginx), revisit —
# but at that point we should also revisit pgbouncer, single-leader
# SSE, and the in-process metrics dict, none of which scale either.
# ---------------------------------------------------------------------------
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.rate_limit_default],
    storage_uri='memory://',
    strategy='moving-window',
)
