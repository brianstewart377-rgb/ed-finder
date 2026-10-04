"""F3 Task 4: `GET /api/archetypes/rankings` repointed onto V3 via the ranking profile.

Mirrors tests/test_local_search_v3.py's fixture/harness pattern: a disposable
PG18 database built with `tests.ratings_v4_pg_fixture.canonical_database`,
both the F1 `system_search` and F2b `system_archetype` products
registered/built/validated against the same base Ratings V4 generation, then
published so `v3_app.*` exposes them.

There is no existing async HTTP-client test harness for these endpoints
(see test_local_search_v3.py's module docstring), so this file follows the
same pattern: it calls `edfinder_api.routers.archetypes._archetype_rankings_v3`
directly with a real asyncpg pool connected to the same disposable database
psycopg created -- the plain, DB-pool-taking helper the thin, rate-limited
`@router.get('/rankings')` handler delegates to.
"""
from __future__ import annotations

import inspect
import os
from pathlib import Path
import sys
from uuid import uuid4

from fastapi import HTTPException
import pytest

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('CORS_ORIGINS', 'https://archetype-rankings-v3-test.invalid')
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

from edfinder_api.ranking.profile import RANKING_VERSION  # noqa: E402
from edfinder_api.routers import archetypes  # noqa: E402


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
    key = 'archetype_rankings_v3_test_' + uuid4().hex
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
         'test', 'archetype rankings v3 fixture'),
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


def _pick_scored_archetype_key(connection) -> str:
    """Pick an archetype_key present in the fixture with score variance,
    so ordering assertions aren't trivially satisfied by a single value."""
    row = connection.execute('''
        SELECT archetype_key
          FROM v3_app.system_archetype
         GROUP BY archetype_key
        HAVING count(DISTINCT archetype_score) > 1
         ORDER BY archetype_key
         LIMIT 1
    ''').fetchone()
    assert row, 'fixture must contain an archetype_key with score variance'
    return row[0]


@pytest.mark.asyncio
async def test_archetype_rankings_v3_orders_by_archetype_score_with_count(database):
    connection, _, _, _ = database
    _build_published_generation(database)

    archetype_key = _pick_scored_archetype_key(connection)

    all_rows = connection.execute('''
        SELECT a.system_id64, a.archetype_score, a.confidence, s.completeness,
               s.x_ly, s.y_ly, s.z_ly
          FROM v3_app.system_archetype a
          JOIN v3_app.system_search s ON s.system_id64 = a.system_id64
         WHERE a.archetype_key = %s
    ''', (archetype_key,)).fetchall()
    # `_pick_scored_archetype_key` guarantees >1 distinct archetype_score for
    # this key -- using the max score as the threshold guarantees at least
    # one row passes (the max itself) and at least one row is excluded (any
    # row scored below it), so the count assertion below is never vacuous.
    min_score_threshold = max(row[1] for row in all_rows)
    rows = [row for row in all_rows if row[1] >= min_score_threshold]
    assert rows
    assert len(rows) < len(all_rows)

    def sort_key(row):
        system_id64, score, confidence, completeness, x, y, z = row
        dist = (x * x + y * y + z * z) ** 0.5
        return (-(score * confidence * completeness), dist, system_id64)

    expected_order = [row[0] for row in sorted(rows, key=sort_key)]

    pool = await _asyncpg_pool(connection)
    try:
        result = await archetypes._archetype_rankings_v3(
            archetype=archetype_key,
            min_score=min_score_threshold,
            galaxy_region=None,
            max_distance_ly=None,
            has_elw=None,
            min_slots=None,
            max_contamination=None,
            limit=50,
            offset=0,
            pool=pool,
        )
    finally:
        await pool.close()

    assert result['source'] == f'v3:{RANKING_VERSION}'
    assert result['archetype'] == archetype_key
    assert [row['id64'] for row in result['results']] == expected_order
    # The count/total assertion: F3 Task 3 had a CRITICAL count-crash from
    # hand-slicing params instead of using build_count_query. Confirm both
    # the returned page and the reported total agree with the expected,
    # filtered (min_score >= threshold) row set -- not just that a count
    # came back.
    assert result['total'] == len(expected_order)
    assert result['count'] == len(expected_order)


@pytest.mark.asyncio
async def test_archetype_rankings_v3_reports_actual_summary_not_invented_archetype(database):
    """Finding #20: each row must report the system's ACTUAL primary/secondary
    archetype and overall best potential (from the summary), with the requested
    archetype echoed separately as `selected_archetype` -- not the requested
    key stamped onto `primary_archetype` with `secondary=None`/potential=None."""
    connection, _, _, _ = database
    _build_published_generation(database)

    archetype_key = _pick_scored_archetype_key(connection)
    summary = {
        sid: (primary, secondary, best)
        for sid, primary, secondary, best in connection.execute('''
            SELECT system_id64, primary_archetype, secondary_archetype,
                   best_colony_potential
              FROM v3_app.system_archetype_summary
        ''').fetchall()
    }

    pool = await _asyncpg_pool(connection)
    try:
        result = await archetypes._archetype_rankings_v3(
            archetype=archetype_key, min_score=0, galaxy_region=None,
            max_distance_ly=None, has_elw=None, min_slots=None,
            max_contamination=None, limit=50, offset=0, pool=pool,
        )
    finally:
        await pool.close()

    assert result['results'], 'need at least one ranked row'
    for row in result['results']:
        assert row['selected_archetype'] == archetype_key
        expected_primary, expected_secondary, expected_best = summary[row['id64']]
        assert row['primary_archetype'] == expected_primary
        assert row['secondary_archetype'] == expected_secondary
        assert row['overall_development_potential'] == float(expected_best)


@pytest.mark.asyncio
async def test_archetype_rankings_v3_honours_max_distance_hard_filter_and_count(database):
    connection, _, _, _ = database
    _build_published_generation(database)

    archetype_key = _pick_scored_archetype_key(connection)

    all_rows = connection.execute('''
        SELECT a.system_id64, s.x_ly, s.y_ly, s.z_ly
          FROM v3_app.system_archetype a
          JOIN v3_app.system_search s ON s.system_id64 = a.system_id64
         WHERE a.archetype_key = %s
    ''', (archetype_key,)).fetchall()
    distances = sorted((row[0], (row[1] ** 2 + row[2] ** 2 + row[3] ** 2) ** 0.5) for row in all_rows)
    assert len(distances) > 1, 'fixture must have more than one system to split by distance'
    # Median distance as the cutoff guarantees at least one system inside and
    # at least one outside, regardless of the actual coordinate spread.
    threshold = distances[len(distances) // 2][1]
    expected_ids = {system_id64 for system_id64, dist in distances if dist <= threshold}
    assert expected_ids
    assert len(expected_ids) < len(distances), 'fixture must contain a system beyond the threshold too'

    pool = await _asyncpg_pool(connection)
    try:
        result = await archetypes._archetype_rankings_v3(
            archetype=archetype_key,
            min_score=0,
            galaxy_region=None,
            max_distance_ly=threshold,
            has_elw=None,
            min_slots=None,
            max_contamination=None,
            limit=50,
            offset=0,
            pool=pool,
        )
    finally:
        await pool.close()

    returned_ids = {row['id64'] for row in result['results']}
    assert returned_ids == expected_ids
    assert result['total'] == len(expected_ids)
    assert result['count'] == len(expected_ids)


@pytest.mark.asyncio
async def test_archetype_rankings_v3_rejects_unknown_archetype():
    with pytest.raises(HTTPException) as excinfo:
        await archetypes._archetype_rankings_v3(
            archetype='not_a_real_archetype',
            min_score=40,
            galaxy_region=None,
            max_distance_ly=None,
            has_elw=None,
            min_slots=None,
            max_contamination=None,
            limit=50,
            offset=0,
            pool=object(),  # never touched -- validation happens before any DB access
        )
    assert excinfo.value.status_code == 422


@pytest.mark.asyncio
async def test_archetype_rankings_v3_rejects_min_slots():
    with pytest.raises(HTTPException) as excinfo:
        await archetypes._archetype_rankings_v3(
            archetype='mining_hub',
            min_score=40,
            galaxy_region=None,
            max_distance_ly=None,
            has_elw=None,
            min_slots=5,
            max_contamination=None,
            limit=50,
            offset=0,
            pool=object(),
        )
    assert excinfo.value.status_code == 422


@pytest.mark.asyncio
async def test_archetype_rankings_v3_rejects_max_contamination():
    with pytest.raises(HTTPException) as excinfo:
        await archetypes._archetype_rankings_v3(
            archetype='mining_hub',
            min_score=40,
            galaxy_region=None,
            max_distance_ly=None,
            has_elw=None,
            min_slots=None,
            max_contamination=10.0,
            limit=50,
            offset=0,
            pool=object(),
        )
    assert excinfo.value.status_code == 422


@pytest.mark.asyncio
async def test_archetype_rankings_v3_has_elw_maps_to_elw_count_bounds(monkeypatch):
    """Finding #23: has_elw is honoured in BOTH directions now that
    system_search exposes elw_count with min+max range filters -- true ->
    elw_count_min=1 (at least one ELW), false -> elw_count_max=0 (exactly
    zero). Neither 422s. Capture the hard_filters handed to the builder and
    bail before any pool use."""
    captured: dict = {}

    def _fake_build_ranked(spec, **kwargs):
        captured.clear()
        captured.update(kwargs['hard_filters'])
        raise RuntimeError('stop-before-pool')

    monkeypatch.setattr(archetypes, 'build_ranked_query', _fake_build_ranked)

    async def _run(has_elw):
        with pytest.raises(RuntimeError):
            await archetypes._archetype_rankings_v3(
                archetype='mining_hub', min_score=40, galaxy_region=None,
                max_distance_ly=None, has_elw=has_elw, min_slots=None,
                max_contamination=None, limit=50, offset=0, pool=object(),
            )
        return dict(captured)

    false_filters = await _run(False)
    assert false_filters.get('elw_count_max') == 0
    assert 'elw_count_min' not in false_filters

    true_filters = await _run(True)
    assert true_filters.get('elw_count_min') == 1
    assert 'elw_count_max' not in true_filters


@pytest.mark.asyncio
async def test_archetype_rankings_v3_requires_published_generation():
    """No published generation -> 404, not a silently empty result set."""

    class _Transaction:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

    class _Connection:
        def transaction(self, *, isolation=None, readonly=True):
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
        await archetypes._archetype_rankings_v3(
            archetype='mining_hub',
            min_score=40,
            galaxy_region=None,
            max_distance_ly=None,
            has_elw=None,
            min_slots=None,
            max_contamination=None,
            limit=50,
            offset=0,
            pool=_Pool(),
        )
    assert excinfo.value.status_code == 404


def test_archetype_rankings_v3_reads_no_legacy_relation():
    """Static drift guard: the V3 archetype-rankings path never touches a
    legacy/public relation -- mirrors
    test_local_search_v3.test_local_search_v3_reads_no_legacy_relation."""
    src = ''.join(
        inspect.getsource(fn).lower()
        for fn in (
            archetypes._archetype_rankings_v3,
            archetypes._build_v3_ranking_row,
            archetypes.get_archetype_rankings,
        )
    )
    forbidden = (
        'mv_archetype_rankings', 'system_archetype_scores', 'system_archetype_traits',
        'from systems', 'cluster_summary', 'public.',
    )
    assert not any(term in src for term in forbidden)
