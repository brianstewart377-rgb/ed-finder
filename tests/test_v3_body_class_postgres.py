"""Optional System Map subtype facts from a published PG18 derived generation."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import asyncpg
from fastapi import FastAPI
import httpx
import pytest
import pytest_asyncio

from edfinder_api.deps import get_readonly_pool
from edfinder_api.routers import v3
from tests.ratings_v4_pg_fixture import canonical_database
from tests import test_v3_derived_product_publication as publication


pytestmark = pytest.mark.db
ROOT = Path(__file__).resolve().parents[1]
SOL = 10477373803
CLASSES = {'Earth': 'Earth-like world', 'Jupiter': 'Class I gas giant', 'Europa': 'Icy body'}


def _seed(conn, canonical, *, candidate=False):
    generation = publication._insert_generation(conn)
    publication._seed_rating(conn, generation, system_id=SOL)
    # Moon deliberately has the scorer's broad fallback, not a subtype fact;
    # Mars has no mechanics row in the published generation at all.
    classes = {**CLASSES, 'Moon': 'planet'}
    if candidate:
        classes = {name: 'Water world' for name in (*classes, 'Mars')}
    for body in canonical['bodies']:
        if body['system_id64'] != SOL or body['name'] not in classes:
            continue
        conn.execute(
            '''INSERT INTO v3_derived.body_mechanics(
                   derived_generation_id,system_id64,body_pk,source_body_id64,
                   body_class,subtype_present)
               VALUES (%s,%s,%s,%s,%s,%s)''',
            (generation, SOL, body['body_pk'], body['source_body_id64'],
             classes[body['name']], candidate or body['name'] != 'Moon'),
        )
    publication._make_ready(conn, generation)
    return generation


@pytest.fixture(scope='module')
def database():
    with canonical_database() as (conn, canonical, *_):
        assert conn.info.server_version // 10000 == 18
        # No Finder products are present: body facts do not need that gate.
        conn.execute((ROOT / 'sql/v3/migrations/003_ratings_v4_derived.sql').read_text())
        generation = _seed(conn, canonical)
        candidate = _seed(conn, canonical, candidate=True)
        canonical_id, sequence = publication._canonical(conn)
        conn.execute('SELECT v3_meta.publish_derived_generation(%s,%s,%s,%s,%s,%s,%s)', (
            generation, None, 0, canonical_id, sequence, 'test', 'body class fixture',
        ))
        yield conn, canonical, candidate


@pytest_asyncio.fixture
async def pool(database):
    created = await asyncpg.create_pool(
        os.environ['RATINGS_V4_VALIDATION_DATABASE_URL'], database=database[0].info.dbname,
        min_size=1, max_size=2,
        server_settings={'search_path': 'pg_catalog', 'default_transaction_read_only': 'on'},
    )
    try:
        yield created
    finally:
        await created.close()


def _client(pool):
    app = FastAPI()
    app.include_router(v3.router)
    app.dependency_overrides[get_readonly_pool] = lambda: pool
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')


async def _bodies(pool):
    async with _client(pool) as client:
        response = await client.get(f'/api/v1/systems/{SOL}/bodies')
    assert response.status_code == 200, response.text
    return response.json()


async def test_body_classes_read_only_the_published_generation(database, pool):
    rows = await _bodies(pool)
    expected = sorted(body['body_pk'] for body in database[1]['bodies'] if body['system_id64'] == SOL)
    assert [row['body_id'] for row in rows] == [str(body_pk) for body_pk in expected]
    by_name = {row['name']: row for row in rows}
    for name, body_class in CLASSES.items():
        assert by_name[name]['body_type'] == 'planet'
        assert by_name[name]['body_class'] == body_class
        assert by_name[name]['body_class_source'] == 'ratings-v4-derived'
    for name in ('Mars', 'Moon', 'Sol', 'Sol barycentre 31'):
        assert by_name[name]['body_class'] is None
        assert by_name[name]['body_class_source'] is None


@pytest.mark.parametrize('pointer_state', ['missing', 'ready'])
async def test_body_inventory_survives_absent_published_derived_generation(database, pool, pointer_state):
    conn, _, candidate = database
    before = await _bodies(pool)
    pointer = conn.execute('DELETE FROM v3_meta.current_derived_generation RETURNING *').fetchone()
    try:
        if pointer_state == 'ready':
            conn.execute('INSERT INTO v3_meta.current_derived_generation VALUES (true,%s,1,now())',
                         (candidate,))
        rows = await _bodies(pool)
        assert rows == [{**body, 'body_class': None, 'body_class_source': None} for body in before]
    finally:
        conn.execute('DELETE FROM v3_meta.current_derived_generation')
        conn.execute('INSERT INTO v3_meta.current_derived_generation VALUES (%s,%s,%s,%s)', pointer)


async def test_body_classes_do_not_cross_canonical_generation_identity(pool, monkeypatch):
    resolve = v3.current_canonical_generation

    async def changed_generation(read_pool):
        schema, generation = await resolve(read_pool)
        # Exercise the SQL lineage boundary with the same body ids/schema and
        # a newly resolved canonical identity, as during a canonical cutover.
        return schema, generation.model_copy(update={'generation_id': str(uuid4())})

    monkeypatch.setattr(v3, 'current_canonical_generation', changed_generation)
    rows = await _bodies(pool)
    assert rows
    assert all(body['body_class'] is None and body['body_class_source'] is None for body in rows)
