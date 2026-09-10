from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('CORS_ORIGINS', 'http://testserver')
sys.path.insert(0, str(ROOT / 'apps' / 'api' / 'src'))

from edfinder_api import main as api_main  # noqa: E402
from edfinder_api.request_logging import (  # noqa: E402
    FrontierOAuthAccessLogFilter,
    redact_frontier_oauth_sentry_event,
    redact_frontier_oauth_target,
)


CALLBACK_PATHS = (
    '/api/auth/frontier/callback',
    '/api/v1/auth/frontier/callback',
)
SECRET_QUERY = 'code=frontier-code-canary&state=frontier-state-canary'


def _request(path: str, query: str = SECRET_QUERY) -> Request:
    return Request({
        'type': 'http',
        'method': 'GET',
        'path': path,
        'headers': [(b'host', b'ed-finder.app')],
        'query_string': query.encode('ascii'),
        'server': ('ed-finder.app', 443),
        'client': ('172.20.0.3', 1234),
        'scheme': 'https',
    })


@pytest.mark.parametrize('path', CALLBACK_PATHS)
def test_callback_target_redaction_removes_complete_query(path: str):
    assert redact_frontier_oauth_target(f'{path}?{SECRET_QUERY}') == path
    assert redact_frontier_oauth_target(
        f'https://ed-finder.app{path}?{SECRET_QUERY}'
    ) == f'https://ed-finder.app{path}'


def test_non_callback_target_logging_is_unchanged():
    target = f'/api/local/search?{SECRET_QUERY}'
    assert redact_frontier_oauth_target(target) == target


@pytest.mark.parametrize('path', CALLBACK_PATHS)
def test_uvicorn_access_filter_redacts_callback_query(path: str):
    record = logging.LogRecord(
        name='uvicorn.access',
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=('172.20.0.3:1234', 'GET', f'{path}?{SECRET_QUERY}', '1.1', 302),
        exc_info=None,
    )

    assert FrontierOAuthAccessLogFilter().filter(record) is True
    rendered = record.getMessage()
    assert path in rendered
    assert 'frontier-code-canary' not in rendered
    assert 'frontier-state-canary' not in rendered


@pytest.mark.parametrize('path', CALLBACK_PATHS)
def test_sentry_redaction_removes_callback_query_and_state_cookie(path: str):
    event = {
        'request': {
            'url': f'https://ed-finder.app{path}?{SECRET_QUERY}',
            'query_string': SECRET_QUERY,
            'cookies': {'__Secure-ed_finder_oauth_state': 'frontier-state-canary'},
            'headers': {'Cookie': '__Secure-ed_finder_oauth_state=frontier-state-canary'},
            'env': {
                'QUERY_STRING': SECRET_QUERY,
                'RAW_URI': f'{path}?{SECRET_QUERY}',
                'REQUEST_URI': f'{path}?{SECRET_QUERY}',
            },
        },
    }

    redacted = redact_frontier_oauth_sentry_event(event, {})
    rendered = json.dumps(redacted, sort_keys=True)
    assert redacted['request']['url'] == f'https://ed-finder.app{path}'
    assert 'frontier-code-canary' not in rendered
    assert 'frontier-state-canary' not in rendered


@pytest.mark.asyncio
@pytest.mark.parametrize('path', CALLBACK_PATHS)
async def test_problem_details_callback_instance_excludes_query(path: str):
    response = await api_main.problem_details_handler(
        _request(path),
        HTTPException(400, 'Frontier sign-in state did not match'),
    )
    payload = json.loads(response.body)
    assert payload['instance'] == f'https://ed-finder.app{path}'
    assert 'frontier-code-canary' not in response.body.decode('utf-8')
    assert 'frontier-state-canary' not in response.body.decode('utf-8')


@pytest.mark.asyncio
@pytest.mark.parametrize('path', CALLBACK_PATHS)
async def test_generic_callback_log_excludes_query(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
):
    captured: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        api_main.log,
        'exception',
        lambda *args, **_kwargs: captured.append(args),
    )
    monkeypatch.setattr(api_main.sentry_sdk, 'capture_exception', lambda _exc: None)

    await api_main.generic_error_handler(_request(path), RuntimeError('failure'))

    rendered = ' '.join(str(value) for value in captured[0])
    assert path in rendered
    assert 'frontier-code-canary' not in rendered
    assert 'frontier-state-canary' not in rendered


def test_nginx_access_format_redacts_only_frontier_callbacks():
    for name in ('nginx.conf', 'nginx-ci.conf'):
        config = (ROOT / 'config' / name).read_text(encoding='utf-8')
        assert 'map $uri $edfinder_access_request {' in config
        assert 'default $request;' in config
        for path in CALLBACK_PATHS:
            assert f'{path} "$request_method $uri $server_protocol";' in config
        assert '"$edfinder_access_request"' in config


def test_api_container_does_not_trust_arbitrary_forwarded_addresses():
    dockerfile = (ROOT / 'apps' / 'api' / 'Dockerfile').read_text(encoding='utf-8')

    assert 'FORWARDED_ALLOW_IPS=*' not in dockerfile
    assert '--forwarded-allow-ips' not in dockerfile
