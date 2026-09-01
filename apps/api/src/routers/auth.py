"""Frontier OAuth sign-in, opaque sessions, and one-time owner linking."""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlencode, urlsplit

import asyncpg
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from edfinder_api.auth import (
    AuthenticatedUser,
    get_request_user,
    new_session_token,
    require_same_origin,
    token_digest,
    user_from_record,
)
from edfinder_api.config import limiter, settings
from edfinder_api.deps import get_pool

router = APIRouter(prefix='/api/auth', tags=['auth'])


class AuthUserResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    commander_name: Optional[str] = None
    is_owner: bool


class AuthSessionResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    authenticated: bool
    user: Optional[AuthUserResponse] = None
    owner_claim_available: bool = False


class OwnerClaimRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    admin_token: str = Field(min_length=1, max_length=512)


class FrontierIdentity(BaseModel):
    model_config = ConfigDict(extra='forbid')

    customer_id: str
    commander_name: Optional[str] = None


def _frontier_ready() -> bool:
    return bool(settings.frontier_client_id and settings.frontier_client_secret)


def _require_frontier_ready() -> None:
    if not _frontier_ready():
        raise HTTPException(503, 'Frontier sign-in is not configured')


def _base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')


def _safe_return_to(value: Optional[str]) -> str:
    candidate = (value or '/').strip()
    parsed = urlsplit(candidate)
    if (
        not candidate.startswith('/')
        or candidate.startswith('//')
        or parsed.scheme
        or parsed.netloc
        or '\r' in candidate
        or '\n' in candidate
    ):
        return '/'
    return candidate


def _oauth_client_address(request: Request) -> str:
    """Use nginx's overwritten client header only from a private proxy peer."""
    peer = request.client.host if request.client else ''
    try:
        peer_ip = ipaddress.ip_address(peer)
    except ValueError:
        return peer or 'unknown'

    # The API port is host-loopback-only. Requests arriving from nginx use its
    # private Docker address, and nginx overwrites X-Real-IP with its resolved
    # $remote_addr (CF-Connecting-IP only for a trusted Cloudflare peer; the
    # socket address otherwise). Never accept this header from direct/loopback
    # clients, where it is caller-controlled.
    if peer_ip.is_private and not peer_ip.is_loopback:
        forwarded = request.headers.get('x-real-ip', '').strip()
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    return str(peer_ip)


def build_frontier_authorize_url(*, state: str, code_challenge: str) -> str:
    query = urlencode({
        'response_type': 'code',
        'client_id': settings.frontier_client_id or '',
        'redirect_uri': settings.frontier_redirect_uri,
        'scope': 'auth capi',
        'audience': 'all',
        'state': state,
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256',
    })
    return f"{settings.frontier_auth_base_url.rstrip('/')}/auth?{query}"


def identity_from_frontier_payloads(
    decoded: dict[str, Any],
    account: dict[str, Any],
    profile: Optional[dict[str, Any]],
) -> FrontierIdentity:
    if decoded.get('iss') != settings.frontier_auth_base_url.rstrip('/'):
        raise HTTPException(502, 'Frontier returned an unexpected token issuer')

    decoded_user = decoded.get('usr')
    if not isinstance(decoded_user, dict):
        raise HTTPException(502, 'Frontier token did not contain an account identity')

    parent_id = account.get('parent_id') if isinstance(account, dict) else None
    account_id = account.get('customer_id') if isinstance(account, dict) else None
    decoded_id = decoded_user.get('customer_id')
    customer_id = str(parent_id or account_id or decoded_id or '').strip()
    if not customer_id:
        raise HTTPException(502, 'Frontier account identity was empty')

    commander_name: Optional[str] = None
    if isinstance(profile, dict):
        commander = profile.get('commander')
        if isinstance(commander, dict):
            raw_name = commander.get('name')
            if isinstance(raw_name, str) and raw_name.strip():
                commander_name = raw_name.strip()[:128]

    return FrontierIdentity(
        customer_id=customer_id,
        commander_name=commander_name,
    )


async def _exchange_frontier_code(code: str, verifier: str) -> dict[str, Any]:
    headers = {
        'Accept': 'application/json',
        'User-Agent': settings.frontier_user_agent,
    }
    async with httpx.AsyncClient(headers=headers, timeout=12.0) as client:
        try:
            token_response = await client.post(
                f"{settings.frontier_auth_base_url.rstrip('/')}/token",
                data={
                    'grant_type': 'authorization_code',
                    'client_id': settings.frontier_client_id,
                    'client_secret': settings.frontier_client_secret,
                    'code': code,
                    'code_verifier': verifier,
                    'redirect_uri': settings.frontier_redirect_uri,
                },
            )
            token_response.raise_for_status()
            token_payload = token_response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(502, 'Frontier token exchange failed') from exc

        if not isinstance(token_payload, dict):
            raise HTTPException(502, 'Frontier token exchange returned an invalid response')

        access_token = token_payload.get('access_token')
        token_type = token_payload.get('token_type') or 'Bearer'
        if not isinstance(access_token, str) or not access_token:
            raise HTTPException(502, 'Frontier token exchange returned no access token')
        if not isinstance(token_type, str) or not token_type.isalpha():
            raise HTTPException(502, 'Frontier returned an invalid token type')

        auth_headers = {'Authorization': f'{token_type} {access_token}'}
        try:
            decode_response = await client.get(
                f"{settings.frontier_auth_base_url.rstrip('/')}/decode",
                headers=auth_headers,
            )
            decode_response.raise_for_status()
            decoded = decode_response.json()

            account_response = await client.get(
                f"{settings.frontier_auth_base_url.rstrip('/')}/me",
                headers=auth_headers,
            )
            account_response.raise_for_status()
            account = account_response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(502, 'Frontier account lookup failed') from exc

        profile: Optional[dict[str, Any]] = None
        try:
            profile_response = await client.get(
                f"{settings.frontier_capi_base_url.rstrip('/')}/profile",
                headers=auth_headers,
            )
            if profile_response.is_success:
                candidate = profile_response.json()
                if isinstance(candidate, dict):
                    profile = candidate
        except (httpx.HTTPError, ValueError):
            # CAPI maintenance should not prevent account sign-in. The account
            # remains valid and Commander name can be filled on a later login.
            profile = None

    if not isinstance(decoded, dict) or not isinstance(account, dict):
        raise HTTPException(502, 'Frontier returned an invalid account response')
    return identity_from_frontier_payloads(decoded, account, profile).model_dump()


async def _consume_login_state(
    pool: asyncpg.Pool,
    state: str,
) -> Optional[asyncpg.Record]:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('DELETE FROM oauth_login_states WHERE expires_at <= NOW()')
            return await conn.fetchrow(
                """
                DELETE FROM oauth_login_states
                WHERE state_hash = $1
                  AND expires_at > NOW()
                RETURNING code_verifier, return_to
                """,
                token_digest(state),
            )


async def _upsert_user_and_session(
    pool: asyncpg.Pool,
    identity: FrontierIdentity,
) -> tuple[AuthenticatedUser, str]:
    raw_session = new_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=settings.auth_session_ttl_seconds,
    )
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                'DELETE FROM web_sessions WHERE expires_at <= NOW() AND revoked_at IS NULL'
            )
            await conn.execute('DELETE FROM web_sessions WHERE revoked_at IS NOT NULL')
            record = await conn.fetchrow(
                """
                INSERT INTO app_users (
                    frontier_customer_id,
                    commander_name,
                    is_owner,
                    last_login_at,
                    updated_at
                )
                VALUES ($1, $2, $3, NOW(), NOW())
                ON CONFLICT (frontier_customer_id) DO UPDATE
                SET
                    commander_name = COALESCE(EXCLUDED.commander_name, app_users.commander_name),
                    is_owner = app_users.is_owner OR EXCLUDED.is_owner,
                    last_login_at = NOW(),
                    updated_at = NOW()
                RETURNING id, frontier_customer_id, commander_name, is_owner
                """,
                identity.customer_id,
                identity.commander_name,
                identity.customer_id in settings.frontier_owner_ids,
            )
            await conn.execute(
                """
                INSERT INTO web_sessions (token_hash, user_id, expires_at)
                VALUES ($1, $2, $3)
                """,
                token_digest(raw_session),
                int(record['id']),
                expires_at,
            )
    return user_from_record(record), raw_session


async def _owner_claim_available(
    pool: asyncpg.Pool,
    user: AuthenticatedUser,
) -> bool:
    if user.is_owner or not settings.admin_token or settings.frontier_owner_ids:
        return False
    async with pool.acquire() as conn:
        owner_exists = await conn.fetchval('SELECT EXISTS(SELECT 1 FROM app_users WHERE is_owner)')
    return not bool(owner_exists)


def _session_response(
    user: Optional[AuthenticatedUser],
    *,
    owner_claim_available: bool = False,
) -> AuthSessionResponse:
    if user is None:
        return AuthSessionResponse(authenticated=False)
    return AuthSessionResponse(
        authenticated=True,
        user=AuthUserResponse(
            commander_name=user.commander_name,
            is_owner=user.is_owner,
        ),
        owner_claim_available=owner_claim_available,
    )


def _canonical_frontier_login_url(request: Request) -> Optional[str]:
    """Keep the OAuth state cookie on the registered callback host."""
    callback = urlsplit(settings.frontier_redirect_uri)
    if callback.scheme not in {'http', 'https'} or not callback.netloc:
        return None
    if request.url.netloc.casefold() == callback.netloc.casefold():
        return None
    query = f'?{request.url.query}' if request.url.query else ''
    return f'{callback.scheme}://{callback.netloc}{request.url.path}{query}'


@router.get('/frontier/login')
@limiter.limit('20/minute', key_func=_oauth_client_address)
async def frontier_login(
    request: Request,
    return_to: Optional[str] = None,
    pool: asyncpg.Pool = Depends(get_pool),
):
    _require_frontier_ready()
    canonical_url = _canonical_frontier_login_url(request)
    if canonical_url is not None:
        return RedirectResponse(canonical_url, status_code=307)

    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = _base64url(hashlib.sha256(verifier.encode('ascii')).digest())
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=settings.auth_state_ttl_seconds,
    )
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                'DELETE FROM oauth_login_states WHERE expires_at <= NOW()'
            )
            await conn.execute(
                """
                INSERT INTO oauth_login_states (
                    state_hash,
                    code_verifier,
                    return_to,
                    expires_at
                )
                VALUES ($1, $2, $3, $4)
                """,
                token_digest(state),
                verifier,
                _safe_return_to(return_to),
                expires_at,
            )

    response = RedirectResponse(
        build_frontier_authorize_url(state=state, code_challenge=challenge),
        status_code=302,
    )
    response.set_cookie(
        settings.auth_state_cookie_name,
        state,
        max_age=settings.auth_state_ttl_seconds,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite='lax',
        path='/api/auth/frontier',
    )
    return response


@router.get('/frontier/callback')
@limiter.limit('20/minute', key_func=_oauth_client_address)
async def frontier_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    pool: asyncpg.Pool = Depends(get_pool),
):
    _require_frontier_ready()
    cookie_state = request.cookies.get(settings.auth_state_cookie_name, '')
    if not state or not cookie_state or not hmac.compare_digest(state, cookie_state):
        raise HTTPException(400, 'Frontier sign-in state did not match')

    stored = await _consume_login_state(pool, state)
    if stored is None:
        raise HTTPException(400, 'Frontier sign-in state expired or was already used')
    return_to = _safe_return_to(str(stored['return_to']))

    if error or not code:
        response = RedirectResponse('/?auth=denied#finder', status_code=302)
        response.delete_cookie(
            settings.auth_state_cookie_name,
            path='/api/auth/frontier',
        )
        return response

    identity_payload = await _exchange_frontier_code(code, str(stored['code_verifier']))
    user, raw_session = await _upsert_user_and_session(
        pool,
        FrontierIdentity.model_validate(identity_payload),
    )

    response = RedirectResponse(return_to, status_code=302)
    response.set_cookie(
        settings.auth_session_cookie_name,
        raw_session,
        max_age=settings.auth_session_ttl_seconds,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite='lax',
        path='/',
    )
    response.delete_cookie(
        settings.auth_state_cookie_name,
        path='/api/auth/frontier',
    )
    return response


@router.get('/session', response_model=AuthSessionResponse)
async def auth_session(
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
):
    user = await get_request_user(request)
    claim_available = (
        await _owner_claim_available(pool, user)
        if user is not None
        else False
    )
    return _session_response(user, owner_claim_available=claim_available)


@router.post('/logout', response_model=AuthSessionResponse)
async def auth_logout(
    request: Request,
    response: Response,
    pool: asyncpg.Pool = Depends(get_pool),
):
    require_same_origin(request)
    raw_session = request.cookies.get(settings.auth_session_cookie_name, '')
    if raw_session:
        async with pool.acquire() as conn:
            await conn.execute(
                'UPDATE web_sessions SET revoked_at = NOW() WHERE token_hash = $1',
                token_digest(raw_session),
            )
    response.delete_cookie(settings.auth_session_cookie_name, path='/')
    return _session_response(None)


@router.post('/owner/claim', response_model=AuthSessionResponse)
@limiter.limit('5/minute')
async def claim_owner(
    request: Request,
    payload: OwnerClaimRequest,
    pool: asyncpg.Pool = Depends(get_pool),
):
    require_same_origin(request)
    user = await get_request_user(request)
    if user is None:
        raise HTTPException(401, 'Sign in with Frontier before linking the owner account')
    if user.is_owner:
        return _session_response(user)
    if not settings.admin_token or not hmac.compare_digest(
        payload.admin_token,
        settings.admin_token,
    ):
        raise HTTPException(401, 'Invalid admin token')

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext('ed-finder-owner-claim'))"
            )
            owner_exists = await conn.fetchval(
                'SELECT EXISTS(SELECT 1 FROM app_users WHERE is_owner)'
            )
            if owner_exists:
                raise HTTPException(409, 'An owner account is already linked')
            record = await conn.fetchrow(
                """
                UPDATE app_users
                SET is_owner = TRUE, updated_at = NOW()
                WHERE id = $1
                RETURNING id, frontier_customer_id, commander_name, is_owner
                """,
                user.id,
            )
    return _session_response(user_from_record(record))
