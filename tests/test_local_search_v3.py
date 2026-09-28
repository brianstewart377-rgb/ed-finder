"""F3 Task 3: `POST /api/local/search` repointed onto V3 via the ranking profile.

Mirrors tests/test_ratings_v4_system_search.py + tests/test_v3_system_archetype_
validate.py's fixture/harness pattern: a disposable PG18 database built with
`tests.ratings_v4_pg_fixture.canonical_database`, both the F1 `system_search`
and F2b `system_archetype` products registered/built/validated against the
same base Ratings V4 generation, then published so `v3_app.*` exposes them.

There is no existing async HTTP-client test harness for these endpoints
(`tests/test_ratings_v4_api.py` calls the async handler function directly
against a real/mock pool rather than going through FastAPI's TestClient), so
this file follows that same pattern: it calls
`edfinder_api.local_search.local_db_search_v3` directly with a real asyncpg
pool connected to the same disposable database psycopg created.
"""
from __future__ import annotations

import inspect
import os
from pathlib import Path
import sys
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('CORS_ORIGINS', 'https://local-search-v3-test.invalid')
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'apps/api/src'))

from scripts.ratings_v4.canonical_stream import CanonicalSnapshot  # noqa: E402
from scripts.ratings_v4.production_generation import (  # noqa: E402
    create_generation, seal_source, validate_generation, write_chunk,
)
import scripts.v3_system_archetype as archetype_builder  # noqa: E402
from scripts.v3_system_search import (  # noqa: E402
    build_available as search_build_available,
    register_product as search_register_product,
    validate_product as search_validate_product,
)
from tests.ratings_v4_pg_fixture import canonical_database  # noqa: E402

from edfinder_api import local_search  # noqa: E402
from edfinder_api.ranking.profile import RANKING_VERSION  # noqa: E402


@pytest.fixture
def database():
    with canonical_database() as (connection, canonical, metadata, payloads):
        for name in (
            '003_ratings_v4_derived.sql',
            '004_v3_search_spatial_clusters.sql',
            '006_v3_derived_product_lifecycle.sql',
            '010_v3_system_search_body_type_counts.sql',
            '011_v3_system_archetype.sql',
        ):
            connection.execute((ROOT / 'sql/v3/migrations' / name).read_text())
        yield connection, canonical, metadata, payloads


def _ratings_generation(database, *, chunk_size=4):
    connection, _, _, payloads = database
    snapshot = CanonicalSnapshot.pin(connection)
    key = 'local_search_v3_test_' + uuid4().hex
    generation_id = create_generation(connection, snapshot, key)
    records = [payload['system'] for payload in payloads]
    for ordinal, start in enumerate(range(0, len(records), chunk_size)):
        chunk = records[start:start + chunk_size]
        canonical = snapshot.export_chunk(connection, [record['id64'] for record in chunk])
        assert write_chunk(connection, generation_id, ordinal, canonical, snapshot.metadata, chunk)
    return key, generation_id, snapshot, records


def _eof_receipt(database):
    _, canonical, metadata, _ = database
    return {
        'consumed_to_eof': True,
        'artifact_sha256': metadata['artifact']['content_sha256'].removeprefix('\\x'),
        'size_bytes': metadata['artifact']['size_bytes'],
        'systems': len(canonical['systems']),
        'bodies': len(canonical['bodies']),
    }


def _publish(connection, generation_id, snapshot):
    return connection.execute(
        'SELECT v3_meta.publish_derived_generation(%s,%s,%s,%s,%s,%s,%s)',
        (generation_id, None, 0, snapshot.generation_id, snapshot.publication_sequence,
         'test', 'local search v3 fixture'),
    ).fetchone()[0]


def _build_published_generation(database) -> None:
    """Register+build+validate the search and archetype products, seal/validate
    the base Ratings generation, and publish -- both products must be VERIFIED
    before `v3_meta.publish_derived_generation` allows publication."""
    connection, _, _, _ = database
    key, generation_id, snapshot, _ = _ratings_generation(database)

    search_generation, _, search_manifest_sha = search_register_product(connection, key)
    search_build_available(connection, search_generation, search_manifest_sha)

    archetype_generation, _, archetype_manifest_sha = archetype_builder.register_product(connection, key)
    archetype_builder.build_available(connection, archetype_generation, archetype_manifest_sha)

    seal_source(connection, generation_id, _eof_receipt(database))
    ready_receipt = validate_generation(connection, generation_id)
    assert ready_receipt['status'] == 'VERIFIED'

    search_verified = search_validate_product(connection, search_generation, search_manifest_sha)
    assert search_verified['status'] == 'VERIFIED'
    archetype_verified = archetype_builder.validate_product(
        connection, archetype_generation, archetype_manifest_sha)
    assert archetype_verified['status'] == 'VERIFIED'

    assert _publish(connection, generation_id, snapshot) == 1


async def _asyncpg_pool(connection):
    import asyncpg
    from psycopg.conninfo import conninfo_to_dict

    base_dsn = os.environ['RATINGS_V4_VALIDATION_DATABASE_URL']
    settings = conninfo_to_dict(base_dsn)
    return await asyncpg.create_pool(
        host=settings.get('host'),
        port=int(settings.get('port', 5432)),
        user=settings.get('user'),
        password=settings.get('password'),
        database=connection.info.dbname,
        min_size=1, max_size=2, statement_cache_size=0,
    )


@pytest.mark.asyncio
async def test_local_search_v3_orders_by_best_colony_potential_with_no_pick(database):
    connection, _, _, _ = database
    _build_published_generation(database)

    summary_rows = connection.execute('''
        SELECT system_id64, best_colony_potential, archetype_confidence
          FROM v3_app.system_archetype_summary
    ''').fetchall()
    completeness = dict(connection.execute('''
        SELECT system_id64, completeness FROM v3_app.system_search
    ''').fetchall())
    expected_order = [
        system_id64 for system_id64, _, _ in sorted(
            summary_rows,
            key=lambda row: (-(row[1] * row[2] * completeness[row[0]]), row[0]),
        )
    ]
    assert len(expected_order) == 12  # authoritative fixture: 12 systems

    pool = await _asyncpg_pool(connection)
    try:
        result = await local_search.local_db_search_v3(
            {'galaxy_wide': True, 'size': 50, 'from': 0}, pool,
        )
    finally:
        await pool.close()

    assert result['source'] == f'v3:{RANKING_VERSION}'
    assert [row['id64'] for row in result['results']] == expected_order
    assert result['total'] == len(expected_order)
    assert result['count'] == len(expected_order)


@pytest.mark.asyncio
async def test_local_search_v3_honours_terraformable_hard_filter(database):
    connection, _, _, _ = database
    _build_published_generation(database)

    all_counts = dict(connection.execute('''
        SELECT system_id64, terraformable_count FROM v3_app.system_search
    ''').fetchall())
    expected_ids = {system_id64 for system_id64, count in all_counts.items() if count >= 1}
    assert expected_ids, 'fixture must contain at least one terraformable system'
    assert len(expected_ids) < len(all_counts), 'fixture must contain at least one non-matching system too'

    pool = await _asyncpg_pool(connection)
    try:
        result = await local_search.local_db_search_v3(
            {
                'galaxy_wide': True,
                'size': 50,
                'from': 0,
                'body_filters': {'terraformable_count': {'min': 1}},
            },
            pool,
        )
    finally:
        await pool.close()

    returned_ids = {row['id64'] for row in result['results']}
    assert returned_ids == expected_ids
    assert result['total'] == len(expected_ids)
    assert all(row['terraformable_count'] >= 1 for row in result['results'])


@pytest.mark.asyncio
async def test_local_search_v3_requires_published_generation():
    """No published generation -> 404, not a silently empty result set."""
    from fastapi import HTTPException

    class _Transaction:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

    class _Connection:
        def transaction(self, *, readonly=True):
            return _Transaction()

        async def fetchrow(self, *_args, **_kwargs):
            return None

    class _Acquire:
        async def __aenter__(self):
            return _Connection()

        async def __aexit__(self, *_exc):
            return False

    class _Pool:
        def acquire(self):
            return _Acquire()

    with pytest.raises(HTTPException) as excinfo:
        await local_search.local_db_search_v3({'galaxy_wide': True}, _Pool())
    assert excinfo.value.status_code == 404


def test_local_search_v3_reads_no_legacy_relation():
    """Static drift guard: the V3 search path never touches a legacy/public
    relation -- mirrors tests/test_v3_system_archetype_validate.py's
    `test_module_never_reads_public_schema`, scoped to the new function set
    rather than the whole (still partly legacy) module."""
    src = ''.join(
        inspect.getsource(fn).lower()
        for fn in (
            local_search.local_db_search_v3,
            local_search._current_derived_generation,
            local_search._v3_hard_filters,
            local_search._build_v3_system_record,
            local_search._v3_count_sql,
        )
    )
    forbidden = (
        'from systems', 'join ratings', 'mv_archetype_rankings',
        'cluster_summary', 'system_archetype_scores', 'system_archetype_traits',
        'public.',
    )
    assert not any(term in src for term in forbidden)
