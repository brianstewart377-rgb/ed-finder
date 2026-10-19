"""Share OG image: Redis cache goes through the bounded deps helpers.

`og_image` used to call `redis.get` / `redis.setex` directly, bypassing the
0.1 s cache I/O timeout in `deps.cache_get` / `deps.cache_set`. A slow or
wedged Redis therefore held every link-unfurl request for the socket
timeout. The route now uses the shared helpers with the PNG base64-encoded
(the shared client runs with decode_responses=True).
"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

os.environ.setdefault('CORS_ORIGINS', 'https://example.com')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

from edfinder_api import share_router  # noqa: E402

PNG = share_router.PNG_SIGNATURE + b'\x00' * 32


def test_source_has_no_bare_redis_calls():
    source = (API_SRC / 'share_router.py').read_text(encoding='utf-8')
    assert 'redis.get(' not in source
    assert 'redis.setex(' not in source
    assert 'from edfinder_api.deps import cache_get, cache_set' in source


def test_png_round_trips_through_the_json_cache_encoding():
    encoded = share_router._encode_cached_png(PNG)
    assert isinstance(encoded, str)
    assert share_router._decode_cached_png(encoded) == PNG


def test_decode_rejects_non_png_and_garbage():
    assert share_router._decode_cached_png(None) is None
    assert share_router._decode_cached_png('') is None
    assert share_router._decode_cached_png(123) is None
    assert share_router._decode_cached_png('not base64!!') is None
    assert share_router._decode_cached_png(base64.b64encode(b'GIF89a....').decode()) is None


def test_decode_rejects_oversized_payloads():
    huge = base64.b64encode(share_router.PNG_SIGNATURE + b'\x00' * share_router.OG_CACHE_MAX_BYTES).decode()
    assert share_router._decode_cached_png(huge) is None


class _Request:
    class app:
        class state:
            redis = 'sentinel-redis'
            pool = None


async def test_og_image_reads_and_writes_through_deps_helpers(monkeypatch):
    calls: dict[str, list] = {'get': [], 'set': []}

    async def fake_get(key, redis=None):
        calls['get'].append((key, redis))
        return None

    async def fake_set(key, value, ttl, redis=None):
        calls['set'].append((key, value, ttl, redis))

    monkeypatch.setattr(share_router, 'cache_get', fake_get)
    monkeypatch.setattr(share_router, 'cache_set', fake_set)
    monkeypatch.setattr(share_router, '_render_card', lambda **kwargs: PNG)

    class _Conn:
        async def fetchrow(self, query, *args, **kwargs):
            return {'name': 'Sol', 'x': 0.0, 'y': 0.0, 'z': 0.0, 'score': 50, 'confidence': 0.5, 'rationale': None}

    class _Acquire:
        async def __aenter__(self):
            return _Conn()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Pool:
        def acquire(self):
            return _Acquire()

    request = _Request()
    request.app.state.pool = _Pool()

    response = await share_router.og_image(10477373803, request)

    assert response.body == PNG
    assert response.headers['X-Cache'] == 'MISS'
    assert calls['get'] == [('og:10477373803', 'sentinel-redis')]
    assert len(calls['set']) == 1
    key, value, ttl, redis = calls['set'][0]
    assert key == 'og:10477373803'
    assert value == share_router._encode_cached_png(PNG)
    assert ttl == share_router.OG_CACHE_TTL_SECONDS == 7 * 24 * 3600
    assert redis == 'sentinel-redis'


async def test_og_image_cache_hit_streams_cached_png(monkeypatch):
    async def fake_get(key, redis=None):
        return share_router._encode_cached_png(PNG)

    async def fail_set(*args, **kwargs):
        raise AssertionError('cache_set must not be called on a hit')

    monkeypatch.setattr(share_router, 'cache_get', fake_get)
    monkeypatch.setattr(share_router, 'cache_set', fail_set)

    response = await share_router.og_image(1, _Request())

    assert response.body == PNG
    assert response.headers['X-Cache'] == 'HIT'
    assert response.media_type == 'image/png'
