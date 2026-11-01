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


GENERATION = '00000000-0000-0000-0000-00000000c0de'


class _Row(dict):
    pass


async def _fake_generation(pool):
    return 'v3_gen_fixture', GENERATION


async def test_og_image_reads_and_writes_through_deps_helpers(monkeypatch):
    # Direct cache-helper unit test; HTTP rate limiting has separate coverage.
    monkeypatch.setattr(share_router.limiter, 'enabled', False)
    calls: dict[str, list] = {'get': [], 'set': []}

    async def fake_get(key, redis=None):
        calls['get'].append((key, redis))
        return None

    async def fake_set(key, value, ttl, redis=None):
        calls['set'].append((key, value, ttl, redis))

    async def fake_lookup(pool, schema, generation_id, id64):
        assert (schema, generation_id) == ('v3_gen_fixture', GENERATION)
        return share_router.ShareSystem(generation_id, _Row(
            id64=id64, name='Sol', x_ly=0.0, y_ly=0.0, z_ly=0.0, loaded_body_count=41))

    monkeypatch.setattr(share_router, 'cache_get', fake_get)
    monkeypatch.setattr(share_router, 'cache_set', fake_set)
    monkeypatch.setattr(share_router, '_resolve_generation', _fake_generation)
    monkeypatch.setattr(share_router, '_lookup_system', fake_lookup)
    monkeypatch.setattr(share_router, '_render_card', lambda **kwargs: PNG)

    response = await share_router.og_image(10477373803, request=_Request(), generation=None, pool=object())

    key = f'og:v3:{GENERATION}:10477373803'
    assert response.body == PNG
    assert response.headers['X-Cache'] == 'MISS'
    assert calls['get'] == [(key, 'sentinel-redis')]
    assert len(calls['set']) == 1
    set_key, value, ttl, redis = calls['set'][0]
    assert set_key == key
    assert value == share_router._encode_cached_png(PNG)
    assert ttl == share_router.OG_CACHE_TTL_SECONDS == 7 * 24 * 3600
    assert redis == 'sentinel-redis'


async def test_og_image_cache_hit_streams_cached_png(monkeypatch):
    # Direct cache-helper unit test; HTTP rate limiting has separate coverage.
    monkeypatch.setattr(share_router.limiter, 'enabled', False)
    async def fake_get(key, redis=None):
        return share_router._encode_cached_png(PNG)

    async def fail_set(*args, **kwargs):
        raise AssertionError('cache_set must not be called on a hit')

    async def fail_lookup(*args, **kwargs):
        raise AssertionError('a cache hit must not read the system row')

    monkeypatch.setattr(share_router, 'cache_get', fake_get)
    monkeypatch.setattr(share_router, 'cache_set', fail_set)
    monkeypatch.setattr(share_router, '_resolve_generation', _fake_generation)
    monkeypatch.setattr(share_router, '_lookup_system', fail_lookup)

    response = await share_router.og_image(1, request=_Request(), generation=None, pool=object())

    assert response.body == PNG
    assert response.headers['X-Cache'] == 'HIT'
    assert response.media_type == 'image/png'


def test_share_lookups_never_read_legacy_v2_relations():
    """V3 production has no V2 systems/ratings relations (CHANGES.md); the
    preview reads only the generation-pinned canonical schema."""
    source = (API_SRC / 'share_router.py').read_text(encoding='utf-8')
    assert 'FROM systems' not in source
    assert 'JOIN ratings' not in source and 'FROM ratings' not in source
    assert 'current_canonical_generation' in source
    assert '{schema}.systems' in source
    assert '/inspect?system=' in source
    assert '/#system/' not in source
