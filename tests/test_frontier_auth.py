from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'apps' / 'api' / 'src'))

from edfinder_api.auth import AuthenticatedUser, token_digest  # noqa: E402
from edfinder_api.config import settings  # noqa: E402
from edfinder_api import deps  # noqa: E402
from edfinder_api.routers import auth as auth_router  # noqa: E402


def _request(
    *,
    admin_token: str = '',
    method: str = 'GET',
    origin: str = '',
    host: str = 'testserver',
    path: str = '/',
    query_string: bytes = b'',
    scheme: str = 'http',
    client_host: str = '127.0.0.1',
    real_ip: str = '',
) -> Request:
    headers = [(b'host', host.encode('ascii'))]
    if admin_token:
        headers.append((b'x-admin-token', admin_token.encode('ascii')))
    if origin:
        headers.append((b'origin', origin.encode('ascii')))
    if real_ip:
        headers.append((b'x-real-ip', real_ip.encode('ascii')))
    return Request({
        'type': 'http',
        'method': method,
        'path': path,
        'headers': headers,
        'query_string': query_string,
        'server': (host, 443 if scheme == 'https' else 80),
        'client': (client_host, 1234),
        'scheme': scheme,
    })


class _AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _RecordingConnection:
    def __init__(self):
        self.queries: list[str] = []

    def transaction(self):
        return _AsyncContext(self)

    async def execute(self, query: str, *_args):
        self.queries.append(' '.join(query.split()))


class _RecordingPool:
    def __init__(self):
        self.connection = _RecordingConnection()

    def acquire(self):
        return _AsyncContext(self.connection)


def test_frontier_authorize_url_uses_registered_callback_pkce_and_scopes(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, 'frontier_client_id', 'client-123')
    monkeypatch.setattr(settings, 'frontier_redirect_uri', 'https://ed-finder.app/api/auth/frontier/callback')

    result = auth_router.build_frontier_authorize_url(
        state='state-value',
        code_challenge='challenge-value',
    )

    parsed = urlsplit(result)
    query = parse_qs(parsed.query)
    assert f'{parsed.scheme}://{parsed.netloc}{parsed.path}' == 'https://auth.frontierstore.net/auth'
    assert query == {
        'response_type': ['code'],
        'client_id': ['client-123'],
        'redirect_uri': ['https://ed-finder.app/api/auth/frontier/callback'],
        'scope': ['auth capi'],
        'audience': ['all'],
        'state': ['state-value'],
        'code_challenge': ['challenge-value'],
        'code_challenge_method': ['S256'],
    }


@pytest.mark.parametrize(
    ('candidate', 'expected'),
    [
        ('/#admin', '/#admin'),
        ('/safe?next=1#operator', '/safe?next=1#operator'),
        ('https://evil.invalid/', '/'),
        ('//evil.invalid/path', '/'),
        ('/ok\r\nLocation: https://evil.invalid', '/'),
    ],
)
def test_return_target_is_restricted_to_local_paths(candidate: str, expected: str):
    assert auth_router._safe_return_to(candidate) == expected


def test_oauth_rate_limit_uses_nginx_overwritten_client_address():
    request = _request(client_host='172.20.0.8', real_ip='203.0.113.42')
    assert auth_router._oauth_client_address(request) == '203.0.113.42'


def test_oauth_rate_limit_ignores_forwarded_header_from_direct_client():
    request = _request(client_host='127.0.0.1', real_ip='203.0.113.42')
    assert auth_router._oauth_client_address(request) == '127.0.0.1'


@pytest.mark.asyncio
async def test_frontier_login_canonicalizes_to_registered_callback_host(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, 'frontier_client_id', 'client-123')
    monkeypatch.setattr(settings, 'frontier_client_secret', 'shared-secret')
    monkeypatch.setattr(
        settings,
        'frontier_redirect_uri',
        'https://ed-finder.app/api/auth/frontier/callback',
    )

    pool = _RecordingPool()
    response = await auth_router.frontier_login(
        _request(
            host='www.ed-finder.app',
            path='/api/auth/frontier/login',
            query_string=b'return_to=%2F%23admin',
            scheme='https',
        ),
        pool=pool,
    )

    assert response.status_code == 307
    assert response.headers['location'] == (
        'https://ed-finder.app/api/auth/frontier/login?return_to=%2F%23admin'
    )
    assert pool.connection.queries == []
    assert 'set-cookie' not in response.headers


@pytest.mark.asyncio
async def test_frontier_login_reaps_expired_states_before_insert(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, 'frontier_client_id', 'client-123')
    monkeypatch.setattr(settings, 'frontier_client_secret', 'shared-secret')
    monkeypatch.setattr(
        settings,
        'frontier_redirect_uri',
        'https://ed-finder.app/api/auth/frontier/callback',
    )
    pool = _RecordingPool()

    response = await auth_router.frontier_login(
        _request(
            host='ed-finder.app',
            path='/api/auth/frontier/login',
            scheme='https',
        ),
        return_to='/#admin',
        pool=pool,
    )

    assert response.status_code == 302
    state_cookie = response.headers['set-cookie']
    assert settings.auth_state_cookie_name in state_cookie
    assert 'Domain=' not in state_cookie
    assert 'Path=/api/auth/frontier' in state_cookie
    assert pool.connection.queries[0] == (
        'DELETE FROM oauth_login_states WHERE expires_at <= NOW()'
    )
    assert pool.connection.queries[1].startswith('INSERT INTO oauth_login_states')


@pytest.mark.asyncio
async def test_frontier_token_transport_failure_returns_bad_gateway(monkeypatch: pytest.MonkeyPatch):
    class _FailingClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, url: str, **_kwargs):
            raise httpx.ConnectError(
                'Frontier is unreachable',
                request=httpx.Request('POST', url),
            )

    monkeypatch.setattr(auth_router.httpx, 'AsyncClient', _FailingClient)

    with pytest.raises(HTTPException) as caught:
        await auth_router._exchange_frontier_code('code', 'verifier')

    assert caught.value.status_code == 502
    assert caught.value.detail == 'Frontier token exchange failed'


@pytest.mark.asyncio
@pytest.mark.parametrize('payload', [None, [], 'not-an-object'])
async def test_frontier_token_success_requires_object_payload(
    monkeypatch: pytest.MonkeyPatch,
    payload: object,
):
    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    class _Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, _url: str, **_kwargs):
            return _Response()

    monkeypatch.setattr(auth_router.httpx, 'AsyncClient', _Client)

    with pytest.raises(HTTPException) as caught:
        await auth_router._exchange_frontier_code('code', 'verifier')

    assert caught.value.status_code == 502
    assert caught.value.detail == 'Frontier token exchange returned an invalid response'


def test_frontier_identity_uses_parent_account_and_stores_only_commander_name(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, 'frontier_auth_base_url', 'https://auth.frontierstore.net')

    identity = auth_router.identity_from_frontier_payloads(
        {
            'iss': 'https://auth.frontierstore.net',
            'usr': {'customer_id': 'platform-child', 'email': 'ignored@example.invalid'},
        },
        {
            'customer_id': 'platform-child',
            'parent_id': 'frontier-parent',
            'email': 'ignored@example.invalid',
        },
        {
            'commander': {'name': '  Test Cmdr  ', 'credits': 999999},
            'lastSystem': {'name': 'Do not retain'},
        },
    )

    assert identity.model_dump() == {
        'customer_id': 'frontier-parent',
        'commander_name': 'Test Cmdr',
    }


def test_session_token_digest_is_deterministic_without_storing_raw_token():
    digest = token_digest('raw-secret-session')
    assert digest == token_digest('raw-secret-session')
    assert digest != 'raw-secret-session'
    assert len(digest) == 64


@pytest.mark.asyncio
async def test_require_admin_accepts_legacy_token(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, 'admin_token', 'legacy-secret')
    await deps.require_admin(_request(admin_token='legacy-secret'))


@pytest.mark.asyncio
async def test_require_admin_accepts_owner_session(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, 'admin_token', 'legacy-secret')

    async def owner_user(_request: Request) -> AuthenticatedUser:
        return AuthenticatedUser(
            id=1,
            frontier_customer_id='owner-id',
            commander_name='Owner Cmdr',
            stored_is_owner=True,
        )

    monkeypatch.setattr(deps, 'get_request_user', owner_user)
    await deps.require_admin(_request())


@pytest.mark.asyncio
async def test_owner_session_write_requires_trusted_origin(monkeypatch: pytest.MonkeyPatch):
    async def owner_user(_request: Request) -> AuthenticatedUser:
        return AuthenticatedUser(
            id=1,
            frontier_customer_id='owner-id',
            commander_name='Owner Cmdr',
            stored_is_owner=True,
        )

    monkeypatch.setattr(settings, 'cors_origins', 'https://ed-finder.app,https://www.ed-finder.app')
    monkeypatch.setattr(deps, 'get_request_user', owner_user)

    await deps.require_admin(_request(method='POST', origin='https://ed-finder.app'))
    with pytest.raises(HTTPException) as caught:
        await deps.require_admin(_request(method='POST', origin='https://review.ed-finder.app'))
    assert caught.value.status_code == 403
    assert caught.value.detail == 'Trusted request origin required'


@pytest.mark.asyncio
async def test_legacy_admin_token_write_does_not_require_browser_origin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, 'admin_token', 'legacy-secret')
    await deps.require_admin(_request(admin_token='legacy-secret', method='POST'))


@pytest.mark.asyncio
async def test_require_admin_rejects_authenticated_non_owner(monkeypatch: pytest.MonkeyPatch):
    async def regular_user(_request: Request) -> AuthenticatedUser:
        return AuthenticatedUser(
            id=2,
            frontier_customer_id='regular-id',
            commander_name='Regular Cmdr',
            stored_is_owner=False,
        )

    monkeypatch.setattr(settings, 'frontier_owner_customer_ids', '')
    monkeypatch.setattr(deps, 'get_request_user', regular_user)
    with pytest.raises(HTTPException) as caught:
        await deps.require_admin(_request())
    assert caught.value.status_code == 403
    assert caught.value.detail == 'Owner access required'


def test_frontier_account_migration_is_manifested_and_does_not_store_oauth_tokens():
    migration = (ROOT / 'sql' / '048_frontier_accounts.sql').read_text(encoding='utf-8')
    manifest = (ROOT / 'sql' / 'migration-manifest.txt').read_text(encoding='utf-8')

    assert '048_frontier_accounts.sql' in manifest
    assert 'frontier_customer_id' in migration
    assert 'commander_name' in migration
    assert 'web_sessions' in migration
    assert 'oauth_login_states' in migration
    assert 'access_token' not in migration
    assert 'refresh_token' not in migration
