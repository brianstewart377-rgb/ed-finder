from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('CORS_ORIGINS', 'http://testserver')
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'apps' / 'api' / 'src'))

from edfinder_api import deps  # noqa: E402
from edfinder_api.auth import (  # noqa: E402
    AuthenticatedUser,
    set_session_cookie,
    token_digest,
)
from edfinder_api.config import settings  # noqa: E402
from edfinder_api.routers import auth as auth_router  # noqa: E402


def _request(
    *,
    admin_token: str = '',
    cookie: str = '',
    method: str = 'GET',
    origin: str = '',
    host: str = 'testserver',
    path: str = '/',
    query_string: bytes = b'',
    scheme: str = 'http',
) -> Request:
    headers = [(b'host', host.encode('ascii'))]
    if admin_token:
        headers.append((b'x-admin-token', admin_token.encode('ascii')))
    if cookie:
        headers.append((b'cookie', cookie.encode('ascii')))
    if origin:
        headers.append((b'origin', origin.encode('ascii')))
    return Request({
        'type': 'http',
        'method': method,
        'path': path,
        'headers': headers,
        'query_string': query_string,
        'server': (host, 443 if scheme == 'https' else 80),
        'client': ('127.0.0.1', 1234),
        'scheme': scheme,
    })


def _user(*, owner: bool) -> AuthenticatedUser:
    return AuthenticatedUser(
        account_id=uuid.uuid4(),
        commander_name=None,
        is_owner=owner,
        recent_auth_at=datetime.now(timezone.utc),
        session_id=uuid.uuid4(),
    )


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
        self.args: list[tuple[object, ...]] = []

    def transaction(self):
        return _AsyncContext(self)

    async def execute(self, query: str, *args):
        self.queries.append(' '.join(query.split()))
        self.args.append(args)


class _RecordingPool:
    def __init__(self):
        self.connection = _RecordingConnection()

    def acquire(self):
        return _AsyncContext(self.connection)


def test_frontier_authorize_url_uses_registered_callback_pkce_and_auth_only(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, 'frontier_client_id', 'client-123')
    monkeypatch.setattr(
        settings,
        'frontier_redirect_uri',
        'https://ed-finder.app/api/auth/frontier/callback',
    )

    result = auth_router.build_frontier_authorize_url(
        state='state-value',
        code_challenge='challenge-value',
    )

    parsed = urlsplit(result)
    query = parse_qs(parsed.query)
    assert f'{parsed.scheme}://{parsed.netloc}{parsed.path}' == (
        'https://auth.frontierstore.net/auth'
    )
    assert query == {
        'response_type': ['code'],
        'client_id': ['client-123'],
        'redirect_uri': ['https://ed-finder.app/api/auth/frontier/callback'],
        'scope': ['auth'],
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
        ('/\\evil.invalid/path', '/'),
        ('/ok\r\nLocation: https://evil.invalid', '/'),
    ],
)
def test_return_target_is_restricted_to_local_paths(candidate: str, expected: str):
    assert auth_router._safe_return_to(candidate) == expected


@pytest.mark.asyncio
async def test_frontier_login_canonicalizes_v3_login_to_callback_host(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, 'frontier_client_id', 'client-123')
    monkeypatch.setattr(settings, 'frontier_client_secret', 'shared-secret')
    monkeypatch.setattr(
        settings,
        'frontier_redirect_uri',
        'https://ed-finder.app/api/auth/frontier/callback',
    )
    response = await auth_router.frontier_login(
        _request(
            host='www.ed-finder.app',
            path='/api/v1/auth/frontier/login',
            query_string=b'return_to=%2F%23admin',
            scheme='https',
        ),
        pool=_RecordingPool(),
    )

    assert response.status_code == 307
    assert response.headers['location'] == (
        'https://ed-finder.app/api/v1/auth/frontier/login?return_to=%2F%23admin'
    )


@pytest.mark.asyncio
async def test_frontier_login_hashes_state_and_sets_secure_one_time_cookie(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, 'frontier_client_id', 'client-123')
    monkeypatch.setattr(settings, 'frontier_client_secret', 'shared-secret')
    monkeypatch.setattr(settings, 'auth_cookie_secure', True)
    pool = _RecordingPool()

    response = await auth_router.frontier_login(
        _request(
            host='ed-finder.app',
            path='/api/v1/auth/frontier/login',
            scheme='https',
        ),
        return_to='/#admin',
        pool=pool,
    )

    assert response.status_code == 302
    assert pool.connection.queries[0] == (
        'DELETE FROM v3_identity.oauth_login_state WHERE expires_at <= NOW()'
    )
    assert pool.connection.queries[1].startswith(
        'INSERT INTO v3_identity.oauth_login_state'
    )
    stored_digest = bytes(pool.connection.args[1][0])
    returned_state = parse_qs(urlsplit(response.headers['location']).query)['state'][0]
    assert stored_digest == token_digest(returned_state)
    assert returned_state not in pool.connection.args[1]
    cookie = response.headers['set-cookie']
    assert settings.auth_state_cookie_name in cookie
    assert 'HttpOnly' in cookie
    assert 'Secure' in cookie
    assert 'SameSite=lax' in cookie
    assert 'Path=/api' in cookie


@pytest.mark.asyncio
async def test_frontier_callback_rejects_missing_or_mismatched_state(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, 'frontier_client_id', 'client-123')
    monkeypatch.setattr(settings, 'frontier_client_secret', 'shared-secret')
    with pytest.raises(HTTPException, match='state did not match') as caught:
        await auth_router.frontier_callback(
            _request(cookie=f'{settings.auth_state_cookie_name}=cookie-state'),
            code='code',
            state='different-state',
            pool=_RecordingPool(),
        )
    assert caught.value.status_code == 400


@pytest.mark.asyncio
async def test_frontier_token_transport_failure_returns_bad_gateway(
    monkeypatch: pytest.MonkeyPatch,
):
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
async def test_frontier_malformed_token_json_returns_bad_gateway(
    monkeypatch: pytest.MonkeyPatch,
):
    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            raise ValueError('malformed JSON')

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
    assert caught.value.detail == 'Frontier token exchange failed'


@pytest.mark.parametrize('token_payload', [[], 'string', 123, None])
@pytest.mark.asyncio
async def test_frontier_non_object_token_json_returns_bad_gateway(
    monkeypatch: pytest.MonkeyPatch,
    token_payload: object,
):
    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return token_payload

    class _Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, _url: str, **_kwargs):
            return _Response()

        async def get(self, _url: str, **_kwargs):
            pytest.fail(
                'Frontier account lookup must not run for an invalid token response'
            )

    monkeypatch.setattr(auth_router.httpx, 'AsyncClient', _Client)
    with pytest.raises(HTTPException) as caught:
        await auth_router._exchange_frontier_code('code', 'verifier')

    assert caught.value.status_code == 502
    assert caught.value.detail == 'Frontier token exchange returned an invalid response'


@pytest.mark.parametrize(
    ('token_payload', 'expected_detail'),
    [
        ({'token_type': 'Bearer'}, 'Frontier token exchange returned no access token'),
        (
            {'access_token': 'discarded-access', 'token_type': 'Basic'},
            'Frontier returned an invalid token type',
        ),
        (
            {'access_token': 'discarded-access', 'token_type': ''},
            'Frontier returned an invalid token type',
        ),
        (
            {'access_token': 'discarded-access', 'token_type': None},
            'Frontier returned an invalid token type',
        ),
        (
            {'access_token': 'discarded-access', 'token_type': []},
            'Frontier returned an invalid token type',
        ),
    ],
)
@pytest.mark.asyncio
async def test_frontier_invalid_token_contract_returns_bad_gateway(
    monkeypatch: pytest.MonkeyPatch,
    token_payload: dict[str, object],
    expected_detail: str,
):
    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return token_payload

    class _Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, _url: str, **_kwargs):
            return _Response()

        async def get(self, _url: str, **_kwargs):
            pytest.fail(
                'Frontier account lookup must not run for an invalid token response'
            )

    monkeypatch.setattr(auth_router.httpx, 'AsyncClient', _Client)
    with pytest.raises(HTTPException) as caught:
        await auth_router._exchange_frontier_code('code', 'verifier')

    assert caught.value.status_code == 502
    assert caught.value.detail == expected_detail
    assert 'discarded-access' not in str(caught.value.detail)


@pytest.mark.parametrize('wrong_shape', [[], 'string', 123, None])
@pytest.mark.parametrize('wrong_endpoint', ['decode', 'me'])
@pytest.mark.asyncio
async def test_frontier_non_object_account_json_returns_bad_gateway(
    monkeypatch: pytest.MonkeyPatch,
    wrong_endpoint: str,
    wrong_shape: object,
):
    class _Response:
        def __init__(self, payload: object):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class _Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, _url: str, **_kwargs):
            return _Response({
                'access_token': 'discarded-access',
                'refresh_token': 'discarded-refresh',
                'token_type': 'Bearer',
            })

        async def get(self, url: str, **_kwargs):
            if url.endswith('/decode'):
                payload = (
                    wrong_shape
                    if wrong_endpoint == 'decode'
                    else {
                        'iss': auth_router.FRONTIER_ISSUER,
                        'usr': {'customer_id': 'platform-child'},
                    }
                )
                return _Response(payload)
            payload = (
                wrong_shape
                if wrong_endpoint == 'me'
                else {
                    'customer_id': 'platform-child',
                    'parent_id': 'stable-parent',
                }
            )
            return _Response(payload)

    monkeypatch.setattr(auth_router.httpx, 'AsyncClient', _Client)
    with pytest.raises(HTTPException) as caught:
        await auth_router._exchange_frontier_code('code', 'verifier')

    assert caught.value.status_code == 502
    assert caught.value.detail == 'Frontier returned an invalid account response'
    assert 'discarded-access' not in str(caught.value.detail)
    assert 'discarded-refresh' not in str(caught.value.detail)


@pytest.mark.asyncio
async def test_identity_login_calls_decode_and_me_but_not_capi_or_persists_tokens(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[str] = []

    class _Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class _Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, url: str, **_kwargs):
            calls.append(url)
            return _Response({
                'access_token': 'discarded-access',
                'refresh_token': 'discarded-refresh',
                'token_type': 'Bearer',
            })

        async def get(self, url: str, **_kwargs):
            calls.append(url)
            if url.endswith('/decode'):
                return _Response({
                    'iss': auth_router.FRONTIER_ISSUER,
                    'usr': {'customer_id': 'platform-child'},
                })
            return _Response({
                'customer_id': 'platform-child',
                'parent_id': 'stable-parent',
            })

    monkeypatch.setattr(auth_router.httpx, 'AsyncClient', _Client)
    result = await auth_router._exchange_frontier_code('code', 'verifier')

    assert result == {
        'issuer': auth_router.FRONTIER_ISSUER,
        'subject': 'stable-parent',
        'commander_name': None,
        'journal_fid': None,
    }
    assert calls == [
        f'{auth_router.FRONTIER_ISSUER}/token',
        f'{auth_router.FRONTIER_ISSUER}/decode',
        f'{auth_router.FRONTIER_ISSUER}/me',
    ]
    assert all('companion.orerve.net' not in url for url in calls)


def test_frontier_identity_uses_stable_parent_and_keeps_commander_separate():
    identity = auth_router.identity_from_frontier_payloads(
        {
            'iss': auth_router.FRONTIER_ISSUER,
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
        'issuer': auth_router.FRONTIER_ISSUER,
        'subject': 'frontier-parent',
        'commander_name': 'Test Cmdr',
        'journal_fid': None,
    }


def test_frontier_identity_rejects_issuer_and_customer_conflicts():
    with pytest.raises(HTTPException, match='issuer'):
        auth_router.identity_from_frontier_payloads(
            {'iss': 'https://evil.invalid', 'usr': {'customer_id': 'one'}},
            {'customer_id': 'one'},
        )
    with pytest.raises(HTTPException, match='conflicting'):
        auth_router.identity_from_frontier_payloads(
            {'iss': auth_router.FRONTIER_ISSUER, 'usr': {'customer_id': 'one'}},
            {'customer_id': 'two'},
        )


def test_session_token_digest_and_cookie_security(monkeypatch: pytest.MonkeyPatch):
    digest = token_digest('raw-secret-session')
    assert digest == token_digest('raw-secret-session')
    assert digest != 'raw-secret-session'
    assert len(digest) == 32

    monkeypatch.setattr(settings, 'auth_cookie_secure', True)
    response = Response()
    set_session_cookie(response, 'raw-secret-session')
    cookie = response.headers['set-cookie']
    assert cookie.startswith(f'{settings.auth_session_cookie_name}=')
    assert 'HttpOnly' in cookie
    assert 'Secure' in cookie
    assert 'SameSite=lax' in cookie
    assert 'Path=/' in cookie


def test_frontier_state_cookie_can_be_cleared(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, 'auth_cookie_secure', True)
    response = Response()
    auth_router._delete_state_cookie(response)
    cookie = response.headers['set-cookie']
    assert cookie.startswith(f'{settings.auth_state_cookie_name}=""')
    assert 'Max-Age=0' in cookie
    assert 'HttpOnly' in cookie
    assert 'Secure' in cookie
    assert 'SameSite=lax' in cookie
    assert 'Path=/api' in cookie


@pytest.mark.asyncio
async def test_require_admin_preserves_token_and_accepts_owner_session(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, 'admin_token', 'legacy-secret')
    await deps.require_admin(_request(admin_token='legacy-secret'))

    async def owner_user(_request: Request) -> AuthenticatedUser:
        return _user(owner=True)

    monkeypatch.setattr(deps, 'get_request_user', owner_user)
    await deps.require_admin(_request())


@pytest.mark.asyncio
async def test_owner_cookie_write_requires_exact_trusted_origin(
    monkeypatch: pytest.MonkeyPatch,
):
    async def owner_user(_request: Request) -> AuthenticatedUser:
        return _user(owner=True)

    monkeypatch.setattr(
        settings,
        'cors_origins',
        'https://ed-finder.app,https://www.ed-finder.app',
    )
    monkeypatch.setattr(deps, 'get_request_user', owner_user)
    await deps.require_admin(
        _request(method='POST', origin='https://ed-finder.app')
    )
    with pytest.raises(HTTPException) as caught:
        await deps.require_admin(
            _request(method='POST', origin='https://review.ed-finder.app')
        )
    assert caught.value.status_code == 403


@pytest.mark.asyncio
async def test_authenticated_non_owner_is_denied(
    monkeypatch: pytest.MonkeyPatch,
):
    async def regular_user(_request: Request) -> AuthenticatedUser:
        return _user(owner=False)

    monkeypatch.setattr(deps, 'get_request_user', regular_user)
    with pytest.raises(HTTPException) as caught:
        await deps.require_admin(_request())
    assert caught.value.status_code == 403
    assert caught.value.detail == 'Owner access required'


def test_openapi_exposes_v3_contract_and_hides_registered_callback_alias():
    from edfinder_api.main import app

    paths = app.openapi()['paths']
    for path in (
        '/api/v1/auth/frontier/login',
        '/api/v1/auth/frontier/callback',
        '/api/v1/auth/frontier/link',
        '/api/v1/auth/session',
        '/api/v1/auth/logout',
        '/api/v1/auth/owner/claim',
        '/api/v1/auth/identities',
        '/api/v1/auth/identities/{external_identity_id}',
    ):
        assert path in paths
    assert '/api/auth/frontier/callback' not in paths
    assert '/api/auth/session' not in paths
