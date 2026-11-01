"""Planner body facts from a disposable PG18 published canonical generation.

The shared canonical_database loader builds the original V3 baseline and
publishes the retained source fixture. Economy facts use a validated, published
derived generation; expectations come from its immutable mechanics rows.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import re
from uuid import uuid4

import asyncpg
import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from edfinder_api.config import limiter
from edfinder_api.deps import get_readonly_pool
from edfinder_api.routers import plan
from edfinder_api.routers import v3 as v3_routes
from edfinder_api.routers.plan_economy_facts import economy_kind
from scripts.ratings_v4.canonical_stream import CanonicalSnapshot
from scripts.ratings_v4.production_generation import (
    create_generation, seal_source, validate_generation, write_chunk,
)
from tests.ratings_v4_pg_fixture import canonical_database

pytestmark = pytest.mark.db
SOL = 10477373803
MAIA = 8216113749
UNKNOWN = 4242
ROOT = Path(__file__).resolve().parents[1]
SHARED_FIELDS = (
    'body_id', 'name', 'direct_parent_body_id', 'body_type', 'is_main_star',
    'is_landable', 'radius_km', 'distance_from_arrival_ls', 'lifecycle_state',
)
BODY_ECONOMY_FIELDS = (
    'economy_kind', 'economy_parent_id', 'in_binary_pair', 'tidally_locked',
    'volcanism_present', 'terraformable',
)
SYSTEM_ECONOMY_FIELDS = (
    'economy_facts_generation_id', 'reserve_level', 'has_black_hole',
    'has_white_dwarf', 'has_neutron_star',
)


def _apply_derived_migrations(conn):
    for name in (
        '003_ratings_v4_derived.sql',
        '004_v3_search_spatial_clusters.sql',
        '006_v3_derived_product_lifecycle.sql',
        '010_v3_system_search_body_type_counts.sql',
        '011_v3_system_archetype.sql',
        '015_v3_derived_product_publication.sql',
    ):
        conn.execute((ROOT / 'sql/v3/migrations' / name).read_text())


def _publish_economy_facts(conn, canonical, payloads):
    snapshot = CanonicalSnapshot.pin(conn)
    exported = snapshot.export_chunk(conn, [row['id64'] for row in canonical['systems']])
    generation = create_generation(conn, snapshot, 'plan_economy_facts_fixture')
    records = [payload['system'] for payload in payloads]
    assert write_chunk(conn, generation, 0, exported, snapshot.metadata, records)
    seal_source(conn, generation, {
        'consumed_to_eof': True,
        'artifact_sha256': snapshot.metadata['artifact']['content_sha256'].removeprefix('\\x'),
        'size_bytes': snapshot.metadata['artifact']['size_bytes'],
        'systems': len(exported['systems']),
        'bodies': len(exported['bodies']),
    })
    validate_generation(conn, generation)
    conn.execute('SELECT v3_meta.publish_derived_generation(%s,%s,%s,%s,%s,%s,%s,%s)', (
        generation, None, 0, snapshot.generation_id, snapshot.publication_sequence,
        'test', 'verified planner economy facts fixture', [],
    ))
    return generation


@pytest.fixture(scope='module')
def database():
    with canonical_database() as (conn, canonical, _, payloads):
        assert int(conn.execute('SHOW server_version_num').fetchone()[0]) // 10000 == 18
        _apply_derived_migrations(conn)
        _publish_economy_facts(conn, canonical, payloads)
        yield conn, canonical


@asynccontextmanager
async def _pool(conn):
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


@pytest_asyncio.fixture
async def pool(database):
    conn, _ = database
    async with _pool(conn) as created:
        yield created


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


def _canonical_fields(result):
    return {
        **{key: value for key, value in result.items()
           if key not in (*SYSTEM_ECONOMY_FIELDS, 'economy_notes', 'bodies')},
        'bodies': [{key: value for key, value in body.items()
                    if key not in BODY_ECONOMY_FIELDS} for body in result['bodies']],
    }


def _assert_economy_unavailable(result):
    assert all(result[key] is None for key in SYSTEM_ECONOMY_FIELDS)
    assert result['economy_notes'] == []
    for body in result['bodies']:
        assert all(body[key] is None for key in BODY_ECONOMY_FIELDS), body['body_id']


@pytest.mark.asyncio
@pytest.mark.parametrize('system_id', [SOL, MAIA], ids=['sol-rings-and-belt', 'maia-biological'])
async def test_plan_bodies_match_canonical_membership_and_facts(pool, system_id):
    publication = await _published(pool)
    schema = publication['relation_schema']
    expected_bodies = await pool.fetch(
        f'SELECT * FROM {schema}.bodies WHERE system_id64=$1 ORDER BY body_pk', system_id)
    assert expected_bodies, 'the fixture system must exercise body membership'
    derived_generation = await pool.fetchval(
        '''SELECT current.derived_generation_id
             FROM v3_meta.current_derived_generation current
             JOIN v3_meta.derived_generation generation USING(derived_generation_id)
            WHERE current.singleton AND generation.lifecycle_state='PUBLISHED'
              AND generation.canonical_generation_id=$1''', publication['generation_id'])
    assert derived_generation is not None
    mechanics = {
        row['body_pk']: row for row in await pool.fetch(
            '''SELECT body_pk, body_class, spectral_class, tidally_locked,
                      volcanism, terraformable, reserve_level
                 FROM v3_derived.body_mechanics
                WHERE derived_generation_id=$1 AND system_id64=$2''',
            derived_generation, system_id)
    }
    assert mechanics, 'the fixture system must exercise published economy facts'

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
        f'''SELECT ring_pk, body_pk, kind, lifecycle_state FROM {schema}.rings
             WHERE system_id64=$1''', system_id)
    ring_bodies = {
        row['body_pk'] for row in ring_rows
        if row['kind'] == 'RING' and row['lifecycle_state'] == 'ACTIVE'
    }
    belt_only_bodies = {row['body_pk'] for row in ring_rows if row['kind'] == 'BELT'} - ring_bodies
    expected_belts = await pool.fetch(
        f'''SELECT ring.ring_pk::text AS belt_id, ring.name,
                   ring.body_pk::text AS parent_body_id,
                   ring_type.display_name AS ring_type, reserve_type.display_name AS reserve,
                   ring.mass_mt, ring.inner_radius_km, ring.outer_radius_km,
                   ring.lifecycle_state
              FROM {schema}.rings ring
              LEFT JOIN v3_vocab.ring_type ring_type USING(ring_type_id)
              LEFT JOIN v3_vocab.reserve_type reserve_type USING(reserve_type_id)
             WHERE ring.system_id64=$1 AND ring.kind='BELT'
             ORDER BY ring.ring_pk''', system_id)
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
    assert result['economy_facts_generation_id'] == str(derived_generation)
    bodies = result['bodies']
    assert result['belts'] == [dict(row) for row in expected_belts]
    assert {belt['belt_id'] for belt in result['belts']}.isdisjoint(
        str(row['ring_pk']) for row in ring_rows if row['kind'] == 'RING')
    if system_id == SOL:
        assert expected_belts
        assert any(belt['ring_type'] is not None for belt in result['belts'])
        assert any(belt['reserve'] is None for belt in result['belts'])
    canonical_bodies = canonical_response.json()
    expected_ids = [str(row['body_pk']) for row in expected_bodies]
    assert [row['body_id'] for row in bodies] == expected_ids
    assert [row['body_id'] for row in canonical_bodies] == expected_ids
    assert [{key: row[key] for key in SHARED_FIELDS} for row in bodies] == [
        {key: row[key] for key in SHARED_FIELDS} for row in canonical_bodies]

    for body, expected in zip(bodies, expected_bodies, strict=True):
        facts = mechanics.get(expected['body_pk'])
        assert body['economy_kind'] == (
            economy_kind(facts['body_class'], facts['spectral_class']) if facts else None)
        for field, column in (
            ('tidally_locked', 'tidally_locked'),
            ('volcanism_present', 'volcanism'),
            ('terraformable', 'terraformable'),
        ):
            assert body[field] is (facts[column] if facts else None)
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

    active_mechanics = [mechanics[row['body_pk']] for row in expected_bodies
                        if row['lifecycle_state'] == 'ACTIVE' and row['body_pk'] in mechanics]
    reserves = {row['reserve_level'] for row in active_mechanics if row['reserve_level'] is not None}
    reserves.update(row['reserve'].strip().lower().removesuffix(' resources').strip()
                    for row in expected_belts
                    if row['lifecycle_state'] == 'ACTIVE' and row['reserve'] is not None)
    assert result['reserve_level'] == (next(iter(reserves)) if len(reserves) == 1 else None)
    assert result['economy_notes'] == (
        ['reserve levels disagree: ' + ', '.join(sorted(reserves))] if len(reserves) > 1 else [])
    active_kinds = {economy_kind(row['body_class'], row['spectral_class']) for row in active_mechanics}
    for kind in ('black_hole', 'white_dwarf', 'neutron_star'):
        assert result[f'has_{kind}'] is (kind in active_kinds)


@pytest.mark.asyncio
@pytest.mark.parametrize('lifecycle_state', ('MISSING_CANDIDATE', 'RETIRED'))
async def test_plan_bodies_ignore_non_current_rings(pool, lifecycle_state):
    publication = await _published(pool)
    schema = publication['relation_schema']
    body_pk = await pool.fetchval(
        f'''SELECT body_pk FROM {schema}.rings
             WHERE system_id64=$1 AND kind='RING' AND lifecycle_state='ACTIVE'
             ORDER BY ring_pk LIMIT 1''', SOL)
    assert body_pk is not None
    rings = await pool.fetch(
        f'''SELECT ring_pk, lifecycle_state, retired_at FROM {schema}.rings
             WHERE body_pk=$1 AND kind='RING' ORDER BY ring_pk''', body_pk)
    assert rings
    try:
        await pool.execute(
            f'''UPDATE {schema}.rings SET lifecycle_state=$2,
                       retired_at=CASE WHEN $2='RETIRED' THEN CURRENT_TIMESTAMP ELSE retired_at END
                 WHERE body_pk=$1 AND kind='RING' ''', body_pk, lifecycle_state)
        assert not await pool.fetchval(
            f'''SELECT EXISTS(SELECT 1 FROM {schema}.rings
                 WHERE body_pk=$1 AND kind='RING' AND lifecycle_state='ACTIVE')''', body_pk)
        async with _client(pool) as client:
            response = await client.get(f'/api/v1/plan/systems/{SOL}/bodies')
        assert response.status_code == 200, response.text
        body = next(row for row in response.json()['bodies'] if row['body_id'] == str(body_pk))
        assert body['has_rings'] is False
    finally:
        await pool.executemany(
            f'UPDATE {schema}.rings SET lifecycle_state=$2, retired_at=$3 WHERE ring_pk=$1',
            [(ring['ring_pk'], ring['lifecycle_state'], ring['retired_at']) for ring in rings])


@pytest.mark.asyncio
@pytest.mark.parametrize('lifecycle_state', ('MISSING_CANDIDATE', 'RETIRED'))
async def test_plan_belts_preserve_lifecycle_null_ring_type_and_resolve_reserve(pool, lifecycle_state):
    publication = await _published(pool)
    schema = publication['relation_schema']
    belt = await pool.fetchrow(
        f'''SELECT ring_pk, ring_type_id, reserve_type_id, lifecycle_state, retired_at
              FROM {schema}.rings
             WHERE system_id64=$1 AND kind='BELT' ORDER BY ring_pk LIMIT 1''', SOL)
    assert belt is not None
    reserve = await pool.fetchrow(
        'SELECT reserve_type_id, display_name FROM v3_vocab.reserve_type ORDER BY reserve_type_id LIMIT 1')
    assert reserve is not None
    try:
        await pool.execute(
            f'''UPDATE {schema}.rings
                   SET ring_type_id=NULL, reserve_type_id=$2, lifecycle_state=$3,
                       retired_at=CASE WHEN $3='RETIRED' THEN CURRENT_TIMESTAMP ELSE retired_at END
                 WHERE ring_pk=$1''', belt['ring_pk'], reserve['reserve_type_id'], lifecycle_state)
        expected_lifecycle = await pool.fetchval(
            f'SELECT lifecycle_state FROM {schema}.rings WHERE ring_pk=$1', belt['ring_pk'])
        async with _client(pool) as client:
            response = await client.get(f'/api/v1/plan/systems/{SOL}/bodies')
        assert response.status_code == 200, response.text
        result = next(row for row in response.json()['belts']
                      if row['belt_id'] == str(belt['ring_pk']))
        assert result['ring_type'] is None
        assert result['reserve'] == reserve['display_name']
        assert result['lifecycle_state'] == expected_lifecycle == lifecycle_state
    finally:
        await pool.execute(
            f'''UPDATE {schema}.rings
                   SET ring_type_id=$2, reserve_type_id=$3, lifecycle_state=$4, retired_at=$5
                 WHERE ring_pk=$1''', belt['ring_pk'], belt['ring_type_id'],
            belt['reserve_type_id'], belt['lifecycle_state'], belt['retired_at'])


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
    derived_generation = await pool.fetchval(
        'SELECT derived_generation_id FROM v3_meta.current_derived_generation WHERE singleton')
    assert missing.json() == {
        'generation_id': str(publication['generation_id']),
        'publication_sequence': str(publication['publication_sequence']),
        'system_id64': str(UNKNOWN), 'bodies': [], 'belts': [],
        'economy_facts_generation_id': str(derived_generation),
        'reserve_level': None, 'has_black_hole': False, 'has_white_dwarf': False,
        'has_neutron_star': False, 'economy_notes': [],
    }


@pytest.mark.asyncio
async def test_plan_bodies_without_published_economy_preserve_canonical_facts():
    # Migration 015 forbids deleting a published derived pointer. Exercise its
    # genuine absence before first publication in a separate disposable fixture.
    with canonical_database() as (conn, canonical, _, payloads):
        _apply_derived_migrations(conn)
        async with _pool(conn) as pool, _client(pool) as client:
            assert not await pool.fetchval('SELECT EXISTS(SELECT 1 FROM v3_meta.current_derived_generation)')
            response = await client.get(f'/api/v1/plan/systems/{SOL}/bodies')
            assert response.status_code == 200, response.text
            result = response.json()
            _assert_economy_unavailable(result)

            generation = _publish_economy_facts(conn, canonical, payloads)
            published_response = await client.get(f'/api/v1/plan/systems/{SOL}/bodies')
            assert published_response.status_code == 200, published_response.text
            published_result = published_response.json()
            assert published_result['economy_facts_generation_id'] == str(generation)
            assert _canonical_fields(result) == _canonical_fields(published_result)


@pytest.mark.asyncio
async def test_plan_bodies_with_retired_economy_generation_preserve_canonical_facts(pool):
    async with _client(pool) as client:
        before = await client.get(f'/api/v1/plan/systems/{SOL}/bodies')
    assert before.status_code == 200, before.text
    assert before.json()['economy_facts_generation_id'] is not None
    pointer = await pool.fetchrow('SELECT * FROM v3_meta.current_derived_generation')
    assert pointer is not None
    try:
        await pool.execute(
            '''UPDATE v3_meta.derived_generation SET lifecycle_state='RETIRED'
                WHERE derived_generation_id=$1''', pointer['derived_generation_id'])
        async with _client(pool) as client:
            response = await client.get(f'/api/v1/plan/systems/{SOL}/bodies')
        assert response.status_code == 200, response.text
        result = response.json()
        _assert_economy_unavailable(result)
        assert _canonical_fields(result) == _canonical_fields(before.json())
    finally:
        await pool.execute(
            '''UPDATE v3_meta.derived_generation SET lifecycle_state='PUBLISHED'
                WHERE derived_generation_id=$1''', pointer['derived_generation_id'])


@pytest.mark.asyncio
async def test_plan_bodies_with_stale_economy_generation_preserve_canonical_facts(pool):
    publication = await _published(pool)
    schema = publication['relation_schema']
    async with _client(pool) as client:
        before = await client.get(f'/api/v1/plan/systems/{SOL}/bodies')
    assert before.status_code == 200, before.text
    derived_generation = before.json()['economy_facts_generation_id']
    assert derived_generation is not None

    replacement = uuid4()
    # Publish the same canonical facts in a new generation, leaving the
    # independently published derived pointer on the old canonical identity.
    async with pool.acquire() as connection, connection.transaction():
        await connection.execute(
            '''INSERT INTO v3_meta.canonical_generation(
                   generation_id,generation_key,relation_schema,manifest_sha256,build_source_run_id)
               SELECT $1,'plan_changed','v3_gen_plan_changed',manifest_sha256,build_source_run_id
                 FROM v3_meta.canonical_generation WHERE generation_id=$2''',
            replacement, publication['generation_id'])
        await connection.execute('SELECT v3_meta.create_canonical_generation_relations($1)', replacement)
        await connection.execute(
            '''INSERT INTO v3_meta.canonical_generation_input(
                   generation_id,input_ordinal,source_id,source_run_id,artifact_id,input_role)
               SELECT $1,input_ordinal,source_id,source_run_id,artifact_id,input_role
                 FROM v3_meta.canonical_generation_input WHERE generation_id=$2''',
            replacement, publication['generation_id'])
        for table in ('systems', 'bodies', 'rings', 'body_signal_current'):
            await connection.execute(
                f'INSERT INTO v3_gen_plan_changed.{table} SELECT * FROM {schema}.{table}')
        await connection.execute('SELECT v3_meta.finalize_canonical_generation($1,$2)',
                                 replacement, {'fixture': 'planner canonical generation changed'})
        await connection.execute('SELECT v3_meta.publish_canonical_generation($1,$2,$3)',
                                 replacement, 'planner stale economy fixture', 'disposable-test')
    try:
        async with _client(pool) as client:
            response = await client.get(f'/api/v1/plan/systems/{SOL}/bodies')
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['generation_id'] == str(replacement)
        assert result['publication_sequence'] == str(publication['publication_sequence'] + 1)
        current_derived = await pool.fetchrow(
            '''SELECT generation.derived_generation_id, generation.canonical_generation_id,
                      generation.lifecycle_state
                 FROM v3_meta.current_derived_generation current
                 JOIN v3_meta.derived_generation generation USING(derived_generation_id)
                WHERE current.singleton''')
        assert str(current_derived['derived_generation_id']) == derived_generation
        assert current_derived['canonical_generation_id'] == publication['generation_id']
        assert current_derived['lifecycle_state'] == 'PUBLISHED'
        _assert_economy_unavailable(result)
        expected = _canonical_fields(before.json())
        expected.update(generation_id=str(replacement),
                        publication_sequence=str(publication['publication_sequence'] + 1))
        assert _canonical_fields(result) == expected
    finally:
        await pool.execute('SELECT v3_meta.publish_canonical_generation($1,$2,$3)',
                           publication['generation_id'], 'restore planner fixture', 'disposable-test')


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
