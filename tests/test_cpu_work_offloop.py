"""Public CPU-heavy routes remain responsive without a database or lifespan."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from contextlib import asynccontextmanager
import os
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('CORS_ORIGINS', 'http://test')
os.environ.setdefault('EDDN_SIMULATION_INGEST_ENABLED', 'false')
sys.path.insert(0, str(ROOT / 'apps/api/src'))

from edfinder_api import cpu_work, main, share_router  # noqa: E402
from edfinder_api.config import limiter  # noqa: E402
from edfinder_api.deps import get_pool, get_readonly_pool  # noqa: E402
from edfinder_api.domain.ratings_v4 import MECHANICS_VERSION, SCORER_VERSION  # noqa: E402
from edfinder_api.domain.ratings_v4_canonical import ADAPTER_VERSION  # noqa: E402
from edfinder_api.routers import ratings_v4  # noqa: E402


pytestmark = pytest.mark.unit
GENERATION = '00000000-0000-0000-0000-00000000c0de'
PNG = share_router.PNG_SIGNATURE + b'\x00' * 32


def _explanation(system_id=42):
    return f'/api/ratings/v4/systems/{system_id}/explanation'


class _Pool:
    """Immutable input rows and observable transaction/connection boundaries."""

    def __init__(self):
        self.events = []
        self.acquired = False
        self.in_transaction = False
        self.missing_generation = False
        self.missing_vector = False
        self.current = {
            'derived_generation_id': GENERATION,
            'publication_sequence': 1,
            'canonical_generation_id': 'fixture-canonical',
            'canonical_publication_sequence': 1,
            'scorer_version': SCORER_VERSION,
            'mechanics_version': MECHANICS_VERSION,
            'adapter_version': ADAPTER_VERSION,
            'manifest': {
                'canonical_generation_id': 'fixture-canonical',
                'canonical_schema': 'v3_gen_fixture',
                'source_metadata': {
                    'run': {'source_run_id': 'fixture-source'},
                    'artifact': {'content_sha256': 'ab' * 32},
                },
            },
        }
        self.vector = {
            'derived_generation_id': GENERATION,
            'system_id64': 42,
            'loaded_body_count': 1,
            'physical_body_count': 1,
            'subtype_projection_sha256': bytes(32),
        }
        self.body = {
            **dict.fromkeys(ratings_v4._BODY_FIELDS),
            'derived_generation_id': GENERATION,
            'system_id64': 42,
            'body_pk': 1,
            'source_body_id64': 420,
            'body_class': 'Water world',
            'rings': False,
            'biologicals': False,
            'geologicals': False,
            'volcanism': False,
            'terraformable': False,
            'tidally_locked': False,
            'is_main_star': False,
            'reserve_level': 'Common',
            'usable_ground_opportunity': True,
            'subtype_present': True,
            'subtype_observed_at': None,
        }
        facts = ratings_v4._facts(self.current['manifest'], self.vector, [self.body])
        scores = ratings_v4.rate_all(ratings_v4.opportunities_from_facts(facts))
        for field, attribute, scale in (
            ('potential', 'potential_score', 1),
            ('quality', 'specialisation_quality', 1),
            ('quality_min', 'specialisation_quality_min', 1),
            ('quality_max', 'specialisation_quality_max', 1),
            ('completeness', 'evidence_completeness', 10000),
            ('confidence', 'confidence', 10000),
        ):
            self.vector[field] = [
                None if (value := getattr(scores[economy], attribute)) is None else round(value * scale)
                for economy in ratings_v4.ECONOMIES
            ]

    @asynccontextmanager
    async def acquire(self):
        assert not self.acquired
        self.acquired = True
        self.events.append('acquire')
        try:
            yield self
        finally:
            self.acquired = False
            self.events.append('release')

    @asynccontextmanager
    async def transaction(self, *, readonly):
        assert readonly is True
        assert self.acquired and not self.in_transaction
        self.in_transaction = True
        self.events.append('transaction_enter')
        try:
            yield self
        finally:
            self.in_transaction = False
            self.events.append('transaction_exit')

    async def fetchrow(self, query, *args):
        assert self.acquired and self.in_transaction
        if 'current_derived_generation' in query:
            self.events.append('current')
            return None if self.missing_generation else dict(self.current)
        assert 'system_rating_vector' in query
        self.events.append('vector')
        return None if self.missing_vector else {
            **self.vector, 'derived_generation_id': args[0], 'system_id64': args[1],
        }

    async def fetch(self, query, generation_id, system_id):
        assert self.acquired and self.in_transaction
        assert 'body_mechanics' in query
        self.events.append('bodies')
        return [{**self.body, 'derived_generation_id': generation_id, 'system_id64': system_id}]


@pytest.fixture
def pool(monkeypatch):
    pool = _Pool()
    monkeypatch.setattr(limiter, 'enabled', False)
    monkeypatch.setattr(ratings_v4, '_explanation_cache', OrderedDict())
    # Avoid sharing a semaphore bound by a previous test's event loop.
    monkeypatch.setattr(cpu_work, '_cpu_semaphore', asyncio.Semaphore(cpu_work.CPU_WORK_CONCURRENCY))

    async def readonly_pool():
        return pool

    health_connection = SimpleNamespace(fetchval=AsyncMock(return_value=1))

    @asynccontextmanager
    async def health_acquire():
        yield health_connection

    async def health_pool():
        return SimpleNamespace(acquire=health_acquire)

    monkeypatch.setitem(main.app.dependency_overrides, get_readonly_pool, readonly_pool)
    monkeypatch.setitem(main.app.dependency_overrides, get_pool, health_pool)
    return pool


@pytest.fixture
async def client(pool):
    # ASGITransport deliberately does not enter the application lifespan.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url='http://test',
    ) as client:
        yield client


@pytest.fixture
def og_miss(monkeypatch):
    monkeypatch.setattr(share_router, 'cache_get', AsyncMock(return_value=None))
    monkeypatch.setattr(share_router, 'cache_set', AsyncMock())
    monkeypatch.setattr(
        share_router, '_resolve_generation', AsyncMock(return_value=('v3_gen_fixture', GENERATION)),
    )
    system = share_router.ShareSystem(GENERATION, {
        'id64': 42, 'name': 'Fixture', 'x_ly': 0, 'y_ly': 0, 'z_ly': 0, 'loaded_body_count': 1,
    })
    monkeypatch.setattr(share_router, '_lookup_system', AsyncMock(return_value=system))
    render = Mock(return_value=PNG)
    monkeypatch.setattr(share_router, '_render_card', render)
    return render


async def _wait_started(event):
    async with asyncio.timeout(2):
        while not event.is_set():
            await asyncio.sleep(0.005)


async def _assert_health_responsive(client, path, started, finished):
    request = asyncio.create_task(client.get(path))
    try:
        await _wait_started(started)
        assert not finished.is_set(), 'CPU work blocked the event loop until it finished'
        before = time.monotonic()
        health = await client.get('/api/health')
        elapsed = time.monotonic() - before
        assert health.status_code == 200, health.text
        assert elapsed < 0.2
        assert not finished.is_set()
        assert not request.done()
    finally:
        response = await request
    assert response.status_code == 200, response.text
    return response


async def test_explanation_releases_connection_and_keeps_health_responsive(client, pool, monkeypatch):
    started, finished = threading.Event(), threading.Event()
    event_loop_thread = threading.get_ident()
    original_facts, original_rate_all = ratings_v4._facts, ratings_v4.rate_all

    def facts(*args):
        assert threading.get_ident() != event_loop_thread
        assert not pool.acquired and not pool.in_transaction
        assert pool.events[-2:] == ['transaction_exit', 'release']
        pool.events.append('facts')
        return original_facts(*args)

    def replay(*args):
        assert threading.get_ident() != event_loop_thread
        assert not pool.acquired and not pool.in_transaction
        pool.events.append('replay')
        started.set()
        try:
            time.sleep(0.5)
            return original_rate_all(*args)
        finally:
            finished.set()

    monkeypatch.setattr(ratings_v4, '_facts', facts)
    monkeypatch.setattr(ratings_v4, 'rate_all', replay)
    await _assert_health_responsive(client, _explanation(), started, finished)
    assert pool.events == [
        'acquire', 'transaction_enter', 'current', 'vector', 'bodies',
        'transaction_exit', 'release', 'facts', 'replay',
    ]


async def test_og_render_keeps_health_responsive(client, og_miss, monkeypatch):
    started, finished = threading.Event(), threading.Event()
    event_loop_thread = threading.get_ident()

    def render(*args, **kwargs):
        assert threading.get_ident() != event_loop_thread
        started.set()
        try:
            time.sleep(0.5)
            return PNG
        finally:
            finished.set()

    monkeypatch.setattr(share_router, '_render_card', render)
    response = await _assert_health_responsive(client, '/api/share/og/42', started, finished)
    assert response.content == PNG
    assert response.headers['X-Cache'] == 'MISS'
    assert response.headers['Cache-Control'] == 'public, max-age=3600'


async def test_explanation_cache_reuses_identical_response_after_reading_current_and_vector(client, pool, monkeypatch):
    replay = Mock(wraps=ratings_v4.rate_all)
    monkeypatch.setattr(ratings_v4, 'rate_all', replay)
    first = await client.get(_explanation())
    second = await client.get(_explanation())
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert replay.call_count == 1
    assert pool.events.count('current') == pool.events.count('vector') == 2
    assert len(ratings_v4._explanation_cache) == 1


async def test_non_explanation_read_keeps_summary_without_cpu_admission_or_cache(client, pool, monkeypatch):
    cpu = AsyncMock(side_effect=AssertionError('summary route must not use CPU admission'))
    monkeypatch.setattr(ratings_v4, 'run_cpu_bound', cpu)
    response = await client.get('/api/ratings/v4/systems/42')
    assert response.status_code == 200, response.text
    assert response.json()['ratings'] == ratings_v4._summary(pool.vector)
    assert 'bodies' not in pool.events
    assert not ratings_v4._explanation_cache
    cpu.assert_not_awaited()


@pytest.mark.parametrize('field', [
    'derived_generation_id', 'scorer_version', 'mechanics_version', 'adapter_version',
])
async def test_explanation_cache_key_includes_generation_and_every_version(client, pool, monkeypatch, field):
    replay = Mock(wraps=ratings_v4.rate_all)
    monkeypatch.setattr(ratings_v4, 'rate_all', replay)
    assert (await client.get(_explanation())).status_code == 200
    pool.current[field] += '-new'
    response = await client.get(_explanation())
    assert response.status_code == 200, response.text
    assert replay.call_count == 2
    if field != 'adapter_version':
        assert response.json()[field] == pool.current[field]


async def test_explanation_cache_evicts_oldest_after_257_distinct_keys(client, monkeypatch):
    replay = Mock(wraps=ratings_v4.rate_all)
    monkeypatch.setattr(ratings_v4, 'rate_all', replay)
    for system_id in range(1, 258):
        response = await client.get(_explanation(system_id))
        assert response.status_code == 200, response.text
        assert response.json()['system_id64'] == system_id
    assert replay.call_count == 257
    assert len(ratings_v4._explanation_cache) == 256
    assert (await client.get(_explanation(1))).status_code == 200
    assert replay.call_count == 258
    assert len(ratings_v4._explanation_cache) == 256


async def test_explanation_cache_hit_refreshes_lru_order(client, monkeypatch):
    monkeypatch.setattr(ratings_v4, 'EXPLANATION_CACHE_SIZE', 2)
    replay = Mock(wraps=ratings_v4.rate_all)
    monkeypatch.setattr(ratings_v4, 'rate_all', replay)
    for system_id in (1, 2, 1, 3, 1):
        assert (await client.get(_explanation(system_id))).status_code == 200
    assert replay.call_count == 3
    assert (await client.get(_explanation(2))).status_code == 200
    assert replay.call_count == 4


@pytest.mark.parametrize('missing', ['missing_generation', 'missing_vector'])
async def test_explanation_404_is_never_cached_and_cached_hits_still_validate_publication(
    client, pool, monkeypatch, missing,
):
    replay = Mock(wraps=ratings_v4.rate_all)
    monkeypatch.setattr(ratings_v4, 'rate_all', replay)
    setattr(pool, missing, True)
    for _ in range(2):
        assert (await client.get(_explanation())).status_code == 404
    assert not ratings_v4._explanation_cache
    assert replay.call_count == 0
    setattr(pool, missing, False)
    assert (await client.get(_explanation())).status_code == 200
    assert replay.call_count == 1
    setattr(pool, missing, True)
    assert (await client.get(_explanation())).status_code == 404
    assert replay.call_count == 1


@pytest.mark.parametrize('corruption', ['replay_mismatch', 'facts_body_count'])
async def test_explanation_integrity_503_is_never_cached(client, pool, monkeypatch, corruption):
    replay = Mock(wraps=ratings_v4.rate_all)
    monkeypatch.setattr(ratings_v4, 'rate_all', replay)
    if corruption == 'replay_mismatch':
        pool.vector['potential'][0] += 1
    else:
        pool.vector['physical_body_count'] += 1
    for _ in range(2):
        response = await client.get(_explanation())
        assert response.status_code == 503
        assert response.json()['detail'] == 'Ratings V4 generation failed integrity validation'
    assert not ratings_v4._explanation_cache
    assert pool.events.count('bodies') == 2
    assert replay.call_count == (2 if corruption == 'replay_mismatch' else 0)
    if corruption == 'replay_mismatch':
        pool.vector['potential'][0] -= 1
    else:
        pool.vector['physical_body_count'] -= 1
    assert (await client.get(_explanation())).status_code == 200
    assert len(ratings_v4._explanation_cache) == 1


@pytest.mark.parametrize('second_path', [_explanation(43), '/api/share/og/43'])
async def test_both_routes_share_admission_timeout_and_recover(client, pool, og_miss, monkeypatch, second_path):
    monkeypatch.setattr(cpu_work, '_cpu_semaphore', asyncio.Semaphore(1))
    monkeypatch.setattr(cpu_work, 'CPU_WORK_WAIT_SECONDS', 0.1)
    started, release = threading.Event(), threading.Event()
    original_rate_all = ratings_v4.rate_all

    def replay(*args):
        started.set()
        assert release.wait(3), 'test did not release CPU worker'
        return original_rate_all(*args)

    monkeypatch.setattr(ratings_v4, 'rate_all', replay)
    first = asyncio.create_task(client.get(_explanation()))
    try:
        await _wait_started(started)
        busy = await client.get(second_path)
        assert busy.status_code == 503, busy.text
        assert busy.headers['Retry-After'] == '2'
        assert busy.json()['detail'] == 'Server busy, try again shortly'
        assert not first.done()
        assert not pool.acquired and not pool.in_transaction
        assert not ratings_v4._explanation_cache
        assert og_miss.call_count == 0
    finally:
        release.set()
        result = await first
    assert result.status_code == 200, result.text
    assert (await client.get(second_path)).status_code == 200


async def test_cancelled_request_holds_cpu_slot_until_thread_finishes(pool, monkeypatch):
    monkeypatch.setattr(cpu_work, '_cpu_semaphore', asyncio.Semaphore(1))
    monkeypatch.setattr(cpu_work, 'CPU_WORK_WAIT_SECONDS', 0.1)
    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    def work():
        started.set()
        try:
            assert release.wait(3), 'test did not release CPU worker'
        finally:
            finished.set()

    request = asyncio.create_task(cpu_work.run_cpu_bound(work))
    try:
        await _wait_started(started)
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
        with pytest.raises(cpu_work.CpuWorkBusy):
            await cpu_work.run_cpu_bound(lambda: 'must not start')
        assert not finished.is_set()
    finally:
        release.set()
        await _wait_started(finished)
    assert await cpu_work.run_cpu_bound(lambda value: value, 'recovered') == 'recovered'


@pytest.mark.parametrize('error', [ValueError('bad facts'), TimeoutError('worker timeout')])
async def test_worker_exception_preserves_error_and_releases_cpu_slot(pool, monkeypatch, error):
    monkeypatch.setattr(cpu_work, '_cpu_semaphore', asyncio.Semaphore(1))

    def fail():
        raise error

    with pytest.raises(type(error)) as caught:
        await cpu_work.run_cpu_bound(fail)
    assert caught.value is error
    assert await cpu_work.run_cpu_bound(lambda: 'recovered') == 'recovered'
