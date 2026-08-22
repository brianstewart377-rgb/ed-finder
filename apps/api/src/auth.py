"""Opaque web-session helpers for Frontier-authenticated ED-Finder users."""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from typing import Optional

import asyncpg
from fastapi import HTTPException, Request

from edfinder_api.config import settings
from edfinder_api.state import get_pool_singleton


@dataclass(frozen=True)
class AuthenticatedUser:
    id: int
    frontier_customer_id: str
    commander_name: Optional[str]
    stored_is_owner: bool

    @property
    def is_owner(self) -> bool:
        return (
            self.stored_is_owner
            or self.frontier_customer_id in settings.frontier_owner_ids
        )


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def new_session_token() -> str:
    return secrets.token_urlsafe(48)


def user_from_record(record: asyncpg.Record) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=int(record['id']),
        frontier_customer_id=str(record['frontier_customer_id']),
        commander_name=(
            str(record['commander_name'])
            if record['commander_name'] is not None
            else None
        ),
        stored_is_owner=bool(record['is_owner']),
    )


async def load_session_user(
    pool: asyncpg.Pool,
    raw_token: str,
) -> Optional[AuthenticatedUser]:
    if not raw_token:
        return None
    async with pool.acquire() as conn:
        record = await conn.fetchrow(
            """
            SELECT
                users.id,
                users.frontier_customer_id,
                users.commander_name,
                users.is_owner
            FROM web_sessions AS sessions
            JOIN app_users AS users ON users.id = sessions.user_id
            WHERE sessions.token_hash = $1
              AND sessions.revoked_at IS NULL
              AND sessions.expires_at > NOW()
            """,
            token_digest(raw_token),
        )
    return user_from_record(record) if record is not None else None


async def get_request_user(request: Request) -> Optional[AuthenticatedUser]:
    pool = get_pool_singleton()
    if pool is None:
        return None
    raw_token = request.cookies.get(settings.auth_session_cookie_name, '')
    return await load_session_user(pool, raw_token)


def require_same_origin(request: Request) -> None:
    """Reject cookie-authenticated writes from untrusted browser origins.

    SameSite=Lax blocks ordinary cross-site POSTs, but sibling subdomains are
    still considered the same *site*. Checking Origin as well prevents a
    compromised sibling service from driving an owner session through CSRF.
    """
    if request.method.upper() in {'GET', 'HEAD', 'OPTIONS'}:
        return
    origin = request.headers.get('Origin', '').strip().rstrip('/')
    allowed = {
        value.strip().rstrip('/')
        for value in settings.cors_origins.split(',')
        if value.strip()
    }
    if not origin or origin not in allowed:
        raise HTTPException(403, 'Trusted request origin required')
