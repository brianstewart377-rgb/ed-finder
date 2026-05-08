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

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from slowapi import Limiter
from slowapi.util import get_remote_address


class Settings(BaseSettings):
    database_url:       str  = 'postgresql://postgres:password@localhost:5432/postgres'
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
    admin_token:        Optional[str] = None
    # CORS: required in production. Default left as a sentinel that the
    # validator rejects so that an unset env in production fails closed.
    # Set CORS_ORIGINS=https://ed-finder.app,https://www.ed-finder.app in .env
    cors_origins:       str  = '__unset__'
    expose_error_detail: bool = False

    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

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
# Rate limiter (shared across all routers). Storage backed by Redis so
# limits apply globally across workers & containers.
# ---------------------------------------------------------------------------
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.rate_limit_default],
    storage_uri=settings.redis_url,
    strategy='moving-window',
)
