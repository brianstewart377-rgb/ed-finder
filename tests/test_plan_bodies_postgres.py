"""Planner body facts from a disposable PG18 published canonical generation.

The shared canonical_database loader builds the original V3 baseline and
publishes the retained source fixture. Expectations come from that database,
including vocabulary names, so this test needs no derived products.
"""
from __future__ import annotations

import json
import os
import re

import asyncpg
import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from edfinder_api.config import limiter
from edfinder_api.deps import get_readonly_pool
from edfinder_api.routers import plan
from edfinder_api.routers import v3 as v3_routes
from tests.ratings_v4_pg_fixture import canonical_database

pytestmark = pytest.mark.db
SOL = 10477373803
MAIA = 8216113749
UNKNOWN = 4242
SHARED_FIELDS = (
    'body_id', 'name', 'direct_parent_body_id', 'body_type', 'is_main_star',
    'is_landable', 'radius_km', 'distance_from_arrival_ls', 'lifecycle_state',
)


@pytest.fixture(scope='module')
def database():
    with canonical_database() as (conn, canonical, _, _):
        assert int(conn.execute('SHOW server_version_num').fetchone()[0]) // 10000 == 18
        yield conn, canonical


@pytest_asyncio.fixture
async def pool(database):
    conn, _ = database

    async def init(connection):
        await connection.set_type_codec('jsonb', schema='pg_catalog',
                                        encoder=json.dumps, decoder=json.loads)

    created = await asyncpg.create_pool(
        os.environ['RATINGS_V4_VALIDATION_DATABASE_URL'], database=conn.info.dbname,
        min_size=1, max_size=3, init=init,
    )
    try:
        yield created
    finally:
        await created.close()


def _client(pool) -> httpx.AsyncClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(plan.router)
    app.include_router(v3_routes.router)
    app.dependency_overrides[get_readonly_pool] = lambda: pool
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')


async def _published(pool):
    row = await pool.fetchrow(
        '''SELECT generation.relation_schema, current.generation_id, current.publication_sequence
             FROM v3_meta.current_canonical_generation current
             JOIN v3_meta.canonical_generation generation USING(generation_id)
            WHERE current.singleton''')
    assert row is not None
    assert re.fullmatch(r'v3_gen_[a-z][a-z0-9_]{0,30}', row['relation_schema'])
    return row


@pytest.mark.asyncio
@pytest.mark.parametrize('system_id', [SOL, MAIA], ids=['sol-rings-and-belt', 'maia-biological'])
async def test_plan_bodies_match_canonical_membership_and_facts(pool, system_id):
    publication = await _published(pool)
    schema = publication['relation_schema']
    expected_bodies = await pool.fetch(
        f'SELECT * FROM {schema}.bodies WHERE system_id64=$1 ORDER BY body_pk', system_id)
    assert expected_bodies, 'the fixture system must exercise body membership'

    vocabulary = {}
    for table, column in (
        ('atmosphere_classification', 'atmosphere_classification_id'),
        ('terraforming_state', 'terraforming_state_id'),
        ('volcanism_type', 'volcanism_type_id'),
    ):
        vocabulary[column] = {
            row[column]: row['display_name']
            for row in await pool.fetch(f'SELECT {column}, display_name FROM v3_vocab.{table}')
        }
    ring_rows = await pool.fetch(
        f'SELECT body_pk, kind FROM {schema}.rings WHERE system_id64=$1', system_id)
    ring_bodies = {row['body_pk'] for row in ring_rows if row['kind'] == 'RING'}
    belt_only_bodies = {row['body_pk'] for row in ring_rows if row['kind'] == 'BELT'} - ring_bodies
    signal_rows = await pool.fetch(
        f'''SELECT signal.body_pk, signal.signal_count, signal_type.display_name
              FROM {schema}.body_signal_current signal
              JOIN {schema}.bodies body USING(body_pk)
              JOIN v3_vocab.signal_type signal_type USING(signal_type_id)
             WHERE body.system_id64=$1''', system_id)
    expected_signals = {}
    for row in signal_rows:
        counts = expected_signals.setdefault(row['body_pk'], {'Geological': 0, 'Biological': 0})
        if row['display_name'] in counts:
            counts[row['display_name']] += row['signal_count']
    assert any(row['display_name'] == 'Geological' and row['signal_count'] > 0
               for row in signal_rows)
    if system_id == MAIA:
        assert any(row['display_name'] == 'Biological' and row['signal_count'] > 0
                   for row in signal_rows)
    if system_id == SOL:
        # Sol's Sun has an asteroid BELT, while its gas giants have RING rows.
        assert ring_bodies and belt_only_bodies

    async with _client(pool) as client:
        response = await client.get(f'/api/v1/plan/systems/{system_id}/bodies')
        canonical_response = await client.get(f'/api/v1/systems/{system_id}/bodies')
    assert response.status_code == 200, response.text
    assert canonical_response.status_code == 200, canonical_response.text
    result = response.json()
    assert result['generation_id'] == str(publication['generation_id'])
    assert result['publication_sequence'] == str(publication['publication_sequence'])
    assert result['system_id64'] == str(system_id)
    bodies = result['bodies']
    canonical_bodies = canonical_response.json()
    expected_ids = [str(row['body_pk']) for row in expected_bodies]
    assert [row['body_id'] for row in bodies] == expected_ids
    assert [row['body_id'] for row in canonical_bodies] == expected_ids
    assert [{key: row[key] for key in SHARED_FIELDS} for row in bodies] == [
        {key: row[key] for key in SHARED_FIELDS} for row in canonical_bodies]

    for body, expected in zip(bodies, expected_bodies, strict=True):
        for field, column in (
            ('atmosphere', 'atmosphere_classification_id'),
            ('terraforming_state', 'terraforming_state_id'),
            ('volcanism', 'volcanism_type_id'),
        ):
            identity = expected[column]
            assert body[field] == (vocabulary[column][identity] if identity is not None else None)
        assert body['surface_gravity_g'] == expected['surface_gravity_g']
        assert body['surface_temperature_k'] == expected['surface_temperature_k']
        assert body['signals_complete'] == expected['signals_complete']
        assert body['has_rings'] is (expected['body_pk'] in ring_bodies)
        if expected['body_pk'] in belt_only_bodies:
            assert body['has_rings'] is False
        counts = expected_signals.get(expected['body_pk'], {})
        assert body['geological_signals'] == counts.get('Geological', 0)
        assert body['biological_signals'] == counts.get('Biological', 0)
    for column in vocabulary:
        assert any(row[column] is None for row in expected_bodies), column
        assert any(row[column] is not None for row in expected_bodies), column


@pytest.mark.asyncio
async def test_plan_bodies_unknown_system_is_empty_and_ids_are_bounded(pool):
    publication = await _published(pool)
    schema = publication['relation_schema']
    assert not await pool.fetchval(f'SELECT EXISTS(SELECT 1 FROM {schema}.systems WHERE id64=$1)',
                                  UNKNOWN)
    async with _client(pool) as client:
        missing = await client.get(f'/api/v1/plan/systems/{UNKNOWN}/bodies')
        for invalid in ('18446744073709551615', '9223372036854775808', 'not-a-number', '-1'):
            response = await client.get(f'/api/v1/plan/systems/{invalid}/bodies')
            assert response.status_code == 422, (invalid, response.text)
        padded = await client.get(f'/api/v1/plan/systems/000{UNKNOWN}/bodies')
    assert padded.status_code == 200, padded.text
    assert padded.json()['system_id64'] == str(UNKNOWN)
    assert missing.status_code == 200, missing.text
    assert missing.json() == {
        'generation_id': str(publication['generation_id']),
        'publication_sequence': str(publication['publication_sequence']),
        'system_id64': str(UNKNOWN), 'bodies': [],
    }


@pytest.mark.asyncio
async def test_plan_bodies_fail_closed_without_a_published_generation(pool):
    pointer = await pool.fetchrow('DELETE FROM v3_meta.current_canonical_generation RETURNING *')
    assert pointer is not None
    try:
        async with _client(pool) as client:
            response = await client.get(f'/api/v1/plan/systems/{SOL}/bodies')
        assert response.status_code == 503, response.text
        assert response.json()['detail'] == 'No published V3 canonical generation'
    finally:
        await pool.execute('INSERT INTO v3_meta.current_canonical_generation VALUES ($1, $2, $3, $4)',
                           *pointer)
