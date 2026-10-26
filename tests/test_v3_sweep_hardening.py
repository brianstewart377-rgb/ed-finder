"""Hardening from the 2026-10-26 repository sweep (S4, S6, S8, S9).

- S4: a statement or lock timeout on the Ratings V4 routes is a retryable 503,
  as on the Finder routes, not a generic 500.
- S6: share cards advertise https for every public host, whatever scheme an
  intermediate plain-http proxy reports; http stays available for local hosts.
- S8: the web slot sends baseline security headers on every response and
  forwards the edge's scheme instead of its own plain-http one.
- S9: secret comparisons never raise on non-ASCII client text.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import asyncpg
import pytest
from fastapi import HTTPException
from starlette.requests import Request

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

os.environ.setdefault('CORS_ORIGINS', 'https://example.com')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

from edfinder_api import deps, share_router  # noqa: E402
from edfinder_api.config import settings  # noqa: E402
from edfinder_api.routers import ratings_v4  # noqa: E402

WEB_NGINX = ROOT / 'apps' / 'web' / 'nginx'


def _request(headers: dict[str, str], host: str = 'ed-finder.app') -> Request:
    raw = [(b'host', host.encode('latin-1'))]
    raw += [(name.lower().encode('latin-1'), value.encode('latin-1')) for name, value in headers.items()]
    return Request({
        'type': 'http', 'method': 'GET', 'path': '/', 'query_string': b'',
        'headers': raw, 'server': (host, 80), 'client': ('172.23.0.2', 50000), 'scheme': 'http',
    })


# ── S6: share-card scheme ───────────────────────────────────────────────────

@pytest.mark.parametrize('proto', ['http', 'https', '', 'javascript'])
def test_public_host_is_always_https(proto):
    headers = {'x-forwarded-host': 'ed-finder.app'}
    if proto:
        headers['x-forwarded-proto'] = proto
    assert share_router._public_base(_request(headers)) == 'https://ed-finder.app'


@pytest.mark.parametrize('host', ['localhost:5173', '127.0.0.1:8080', 'web', 'app.localhost'])
def test_local_development_hosts_may_use_http(host):
    request = _request({'x-forwarded-host': host, 'x-forwarded-proto': 'http'}, host=host)
    assert share_router._public_base(request) == f'http://{host}'


def test_hostile_forwarded_host_still_falls_back_to_public_https():
    request = _request({'x-forwarded-host': 'evil.example"><script>', 'x-forwarded-proto': 'http'})
    assert share_router._public_base(request) == 'https://ed-finder.app'


# ── S8: web slot headers and forwarded scheme ───────────────────────────────

def test_web_slot_sends_baseline_security_headers_on_every_response():
    config = (WEB_NGINX / 'default.conf.template').read_text(encoding='utf-8')
    server = re.sub(r'#[^\n]*', '', config[config.index('server {'):])
    for header, value in (
        ('X-Frame-Options', '"SAMEORIGIN"'),
        ('Content-Security-Policy', '"frame-ancestors \'self\'"'),
        ('X-Content-Type-Options', '"nosniff"'),
        ('Referrer-Policy', '"strict-origin-when-cross-origin"'),
    ):
        assert re.search(rf'^\s*add_header {re.escape(header)} {re.escape(value)} always;$', server, re.M), header
    assert re.search(r'^\s*add_header Permissions-Policy "[^"]*camera=\(\)[^"]*" always;$', server, re.M)
    # A location with its own add_header would silently drop every inherited
    # header for that location, so none may define one.
    for block in re.findall(r'location [^{]+\{[^}]*\}', server):
        assert 'add_header' not in block, block
    # HSTS belongs to the TLS terminator, not this plain-http hop.
    assert 'Strict-Transport-Security' not in config


def test_web_slot_forwards_the_edge_scheme_not_its_own():
    config = (WEB_NGINX / 'default.conf.template').read_text(encoding='utf-8')
    params = (WEB_NGINX / 'proxy_params').read_text(encoding='utf-8')
    assert 'proxy_set_header X-Forwarded-Proto $forwarded_proto;' in params
    assert 'X-Forwarded-Proto $scheme' not in params
    map_block = config[config.index('map $http_x_forwarded_proto $forwarded_proto {'):config.index('server {')]
    assert '""      $scheme;' in map_block
    assert 'default $http_x_forwarded_proto;' in map_block
    # The envsubst filter only touches EDFINDER_API_UPSTREAM, so these nginx
    # variables survive templating.
    dockerfile = (ROOT / 'apps' / 'web' / 'Dockerfile.release').read_text(encoding='utf-8') \
        if (ROOT / 'apps' / 'web' / 'Dockerfile.release').exists() else ''
    if dockerfile:
        assert 'NGINX_ENVSUBST_FILTER="^EDFINDER_API_UPSTREAM$"' in dockerfile


# ── S9: secret comparisons ──────────────────────────────────────────────────

@pytest.mark.parametrize('supplied,expected,result', [
    ('legacy-secret', 'legacy-secret', True),
    ('legacy-secreT', 'legacy-secret', False),
    ('é', 'legacy-secret', False),
    ('é', 'é', True),
    ('', 'legacy-secret', False),
])
def test_secrets_equal_never_raises(supplied, expected, result):
    assert deps.secrets_equal(supplied, expected) is result


@pytest.mark.asyncio
async def test_non_ascii_admin_token_is_a_rejection_not_a_500(monkeypatch):
    monkeypatch.setattr(settings, 'admin_token', 'legacy-secret')

    async def no_user(_request):
        return None

    monkeypatch.setattr(deps, 'get_request_user', no_user)
    with pytest.raises(HTTPException) as caught:
        await deps.require_admin(_request({'x-admin-token': 'é'}))
    assert caught.value.status_code in (401, 403)


def test_every_client_secret_comparison_uses_the_byte_helper():
    for relative in ('apps/api/src/deps.py', 'apps/api/src/routers/auth.py'):
        source = (ROOT / relative).read_text(encoding='utf-8')
        calls = re.findall(r'hmac\.compare_digest\(([^)]*)\)', source)
        # The only direct call left is inside secrets_equal itself, on bytes.
        assert all('.encode(' in call for call in calls), (relative, calls)


# ── S4: ratings timeouts are 503 ────────────────────────────────────────────

class _RaisingPool:
    def __init__(self, error: Exception):
        self.error = error

    def acquire(self):
        error = self.error

        class _Acquire:
            async def __aenter__(self):
                raise error

            async def __aexit__(self, *exc):
                return False

        return _Acquire()


@pytest.mark.asyncio
@pytest.mark.parametrize('error', [
    asyncpg.exceptions.QueryCanceledError('canceling statement due to statement timeout'),
    asyncpg.exceptions.LockNotAvailableError('canceling statement due to lock timeout'),
])
@pytest.mark.parametrize('explanation', [False, True])
async def test_ratings_timeouts_are_retryable_503(error, explanation):
    with pytest.raises(HTTPException) as caught:
        await ratings_v4._read_system(_RaisingPool(error), 10477373803, explanation=explanation)
    assert caught.value.status_code == 503


@pytest.mark.asyncio
async def test_ratings_generation_timeout_is_503():
    error = asyncpg.exceptions.QueryCanceledError('canceling statement due to statement timeout')
    with pytest.raises(HTTPException) as caught:
        await ratings_v4.generation(_RaisingPool(error))
    assert caught.value.status_code == 503
