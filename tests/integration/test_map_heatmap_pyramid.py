"""Integration: GET /api/map/heatmap served from the decoupled, canonical-keyed
`v3_spatial` density pyramid (`v3_spatial.spatial_generation` /
`v3_spatial.cell_summary`, migration 011), with an explicit legacy-fallback
tag when no such pyramid is currently published.

Lives in `tests/integration/` alongside `test_map_systems_viewport.py`, so it
picks up this directory's `app`/`client`/`pool`/`clean_db` fixtures natively
via `tests/integration/conftest.py` (plain directory-based pytest discovery,
no cross-file import needed).

Requires migration 011 already applied to the disposable test database (reset
from the `spatial_decouple_tmpl` template + psql-apply 011). Mirrors
`tests/integration/test_spatial_publish.py`'s `_v2_table_shim` / destructive-
reset-opt-in pattern: this is a V3-only fixture DB with no `public` schema
tables for the shared `clean_db` autouse fixture to TRUNCATE, so without the
opt-in + shim every test here would skip rather than run.
"""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

os.environ.setdefault('EDFINDER_TEST_DB_ALLOW_DESTRUCTIVE_RESET', 'yes')

TEST_LEVEL = 30  # outside the real 0-6 ladder; CHECK allows level BETWEEN 0 AND 30
TEST_CELL_SIZE_LY = 100.0

# Far outside the real galaxy so these fixture cells never collide with real data.
BASE = 700_000.0


@pytest.fixture(scope="session", autouse=True)
def _v2_table_shim(v3_fixture_db_ready, v3_v2_table_shim):
    """Session-scoped dependency (body lives in conftest): the V3-only fixture
    DB lacks the V2 tables conftest's ``clean_db`` TRUNCATEs; the shared
    ``v3_v2_table_shim`` fixture creates empty stand-ins. Autouse so the
    TRUNCATE always succeeds for these tests."""


async def _seed_pyramid_generation(conn, canonical_id):
    """Build + publish a tiny spatial generation for the live canonical
    generation: one distinctive in-box cell, one out-of-box cell, and a
    batch of low-signal filler cells (all only inside the wide bounds) so a
    single published generation exercises both the happy-path shape and
    honest truncation at the endpoint's minimum allowed `max_cells` (100).

    Returns (spatial_generation_id, version, prior_pointer) for the caller
    to assert against and tear down. `prior_pointer` is the
    `v3_spatial.current_spatial_generation` row (or None) that existed
    before this call, for restoring the pointer afterwards.
    """
    version = 'pyr_' + uuid.uuid4().hex[:16]

    await conn.execute(
        """INSERT INTO v3_spatial.cell_level(spatial_pyramid_version,level,cell_size_ly,intended_scale)
           VALUES($1,$2,$3,'test')""",
        version, TEST_LEVEL, TEST_CELL_SIZE_LY,
    )

    cells = [
        # origin,                    centroid,                                sc  rep_id64      key
        (BASE, BASE, BASE,           BASE + 10.0, BASE + 10.0, BASE + 10.0,    6,  9_800_000_001, 'in-box'),
        (BASE + 100_000.0, 0.0, 0.0, BASE + 100_010.0, 5.0, 5.0,               3,  9_800_000_002, 'out-of-box'),
    ]
    filler_count = 100
    for i in range(filler_count):
        cells.append((
            BASE + 2_000.0 + i, 0.0, 0.0,
            BASE + 2_000.0 + i, 1.0, 1.0,
            1, 9_800_000_003, f'filler-{i}',
        ))
    expected_systems = sum(c[6] for c in cells)

    sgid = await conn.fetchval(
        """INSERT INTO v3_spatial.spatial_generation(canonical_generation_id,pyramid_version,expected_systems)
           VALUES($1,$2,$3) RETURNING spatial_generation_id""",
        canonical_id, version, expected_systems,
    )

    await conn.executemany(
        """INSERT INTO v3_spatial.cell_summary(
               spatial_generation_id,spatial_pyramid_version,level,cell_key,
               system_count,representative_system_id64,
               origin_x_ly,origin_y_ly,origin_z_ly,
               centroid_x_ly,centroid_y_ly,centroid_z_ly)
           VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)""",
        [
            (sgid, version, TEST_LEVEL, cell_key, sc, rep_id64, ox, oy, oz, cx, cy, cz)
            for ox, oy, oz, cx, cy, cz, sc, rep_id64, cell_key in cells
        ],
    )

    await conn.execute(
        """UPDATE v3_spatial.spatial_generation
              SET lifecycle_state='READY',
                  validation_receipt='{"status":"VERIFIED"}'::jsonb,
                  validation_sha256=$2, validated_at=now()
            WHERE spatial_generation_id=$1""",
        sgid, b'y' * 32,
    )

    prior = await conn.fetchrow(
        'SELECT spatial_generation_id, publication_sequence '
        'FROM v3_spatial.current_spatial_generation WHERE singleton'
    )
    expected_current = prior['spatial_generation_id'] if prior else None
    expected_sequence = prior['publication_sequence'] if prior else 0
    await conn.execute(
        "SELECT v3_spatial.publish_spatial_pyramid($1,$2,$3,$4,$5,$6)",
        sgid, expected_current, expected_sequence, canonical_id, 'tester', 'integration',
    )

    return sgid, version, prior


async def _teardown_pyramid_generation(conn, *, sgid, prior):
    """Restore the `v3_spatial.current_spatial_generation` pointer only.

    Everything else this fixture inserts (`v3_spatial.cell_level`,
    `v3_spatial.spatial_generation`, `v3_spatial.cell_summary`) is, by
    design, an append-only ledger the schema's own triggers refuse to mutate
    or delete once written (`guard_spatial_generation` raises "spatial
    generations are retained" on DELETE; the `cell_summary` mutation-reject
    triggers block changes to cells once the owning generation has left
    BUILDING). Making this visible to the live app's own pool connection (a
    separate session from this fixture's) requires a real commit, so --
    unlike a rolled-back-transaction pattern -- these rows cannot be rolled
    back either. They are left behind intentionally: harmless, randomly-keyed
    (UUID) fixture rows on the disposable test database, consistent with the
    ledger's own declared immutability contract. `current_spatial_generation`
    and `spatial_publication_audit` have no such guard, so the pointer alone
    is safe to reset directly.
    """
    del sgid  # kept for symmetry/readability with the seed function's return
    if prior is not None:
        await conn.execute(
            """UPDATE v3_spatial.current_spatial_generation
                  SET spatial_generation_id=$1, publication_sequence=$2
                WHERE singleton""",
            prior['spatial_generation_id'], prior['publication_sequence'],
        )
    else:
        await conn.execute('DELETE FROM v3_spatial.current_spatial_generation WHERE singleton')


@pytest_asyncio.fixture
async def seeded_pyramid(pool, v3_fixture_db_ready):
    # `v3_fixture_db_ready` (tests/integration/conftest.py) skips this fixture
    # -- and therefore the test below that requests it -- when the running DB
    # lacks the V3 lineage (e.g. the protected `Backend integration (PG+Redis)`
    # CI lane, which seeds only the V2 manifest and never applies
    # sql/v3/migrations/*). The legacy-fallback test intentionally does NOT
    # depend on this fixture: `map_heatmap`'s own
    # `UndefinedTableError`/`InvalidSchemaNameError` handling already degrades
    # to the legacy path when v3_meta/v3_spatial is entirely absent, so that
    # assertion is real coverage even on a V2-only DB.
    async with pool.acquire() as conn:
        canonical_id = await conn.fetchval(
            "SELECT generation_id FROM v3_meta.current_canonical_generation WHERE singleton"
        )
    if canonical_id is None:
        pytest.skip('no current canonical generation on this disposable DB')

    async with pool.acquire() as conn:
        sgid, version, prior = await _seed_pyramid_generation(conn, canonical_id)
    try:
        yield sgid, version, canonical_id
    finally:
        async with pool.acquire() as conn:
            await _teardown_pyramid_generation(conn, sgid=sgid, prior=prior)


IN_BOX = {
    'voxel_size': 100, 'min_systems': 1,
    'min_x': BASE - 1_000, 'max_x': BASE + 1_000,
    'min_y': BASE - 1_000, 'max_y': BASE + 1_000,
    'min_z': BASE - 1_000, 'max_z': BASE + 1_000,
}

WIDE_BOX = {
    'voxel_size': 100, 'min_systems': 1,
    'min_x': BASE - 1_000, 'max_x': BASE + 200_000,
    'min_y': -10, 'max_y': BASE + 1_000,
    'min_z': -10, 'max_z': BASE + 1_000,
}


async def test_heatmap_uses_legacy_fallback_when_no_published_pyramid(client, pool):
    # Runs before any pyramid is published in this file (no `seeded_pyramid`
    # dependency), so the disposable DB's `v3_spatial.current_spatial_generation`
    # pointer is still empty here.
    #
    # The legacy-fallback path itself is unchanged/out of scope for this
    # rewrite and reads the V2 `systems`/`ratings` tables (or their
    # pre-aggregated MVs) when no pyramid is published. The pure V3-only
    # `spatial_decouple_run`/`spatial_decouple_tmpl` disposable DB this
    # module targets has no `public` schema at all, so that branch cannot be
    # exercised here; skip cleanly rather than fail on an out-of-scope gap,
    # mirroring the `v3_fixture_db_ready` skip-on-missing-relation pattern
    # this directory's conftest already uses for the opposite (V3-missing)
    # case.
    async with pool.acquire() as conn:
        has_systems = await conn.fetchval("SELECT to_regclass('public.systems')")
    if has_systems is None:
        pytest.skip('legacy systems/ratings tables absent on this V3-only fixture DB')

    r = await client.get('/api/map/heatmap')
    assert r.status_code == 200, r.text
    body = r.json()

    assert body['source'] == 'legacy-fallback'
    assert isinstance(body['cells'], list)
    assert isinstance(body['truncated'], bool)
    assert isinstance(body['count'], int)


async def test_heatmap_serves_published_spatial_pyramid(client, seeded_pyramid):
    """One seed + one `publish_spatial_pyramid` call (the CAS function's
    global-PK `spatial_publication_audit` ledger means a second publish in
    the same disposable-DB session would collide on `publication_sequence`),
    exercised against both a narrow (happy-path shape) and a wide
    (truncation) viewport.
    """
    sgid, version, canonical_id = seeded_pyramid

    r = await client.get('/api/map/heatmap', params=IN_BOX)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body['source'] == 'pyramid'
    assert body['generation_id'] == str(canonical_id)
    assert body['spatial_generation_id'] == str(sgid)
    assert body['spatial_pyramid_version'] == version
    assert body['source_system_count'] == 109
    assert body['coverage_at'] is not None
    assert body['bounds']['min_x'] == IN_BOX['min_x']
    assert body['bounds']['max_z'] == IN_BOX['max_z']
    assert body['count'] == 1
    assert body['truncated'] is False

    cell = body['cells'][0]
    for field in (
        'origin_x_ly', 'origin_y_ly', 'origin_z_ly',
        'centroid_x_ly', 'centroid_y_ly', 'centroid_z_ly',
        'system_count', 'representative_system_id64',
    ):
        assert field in cell, f'missing {field} in cell payload'
    assert cell['system_count'] == 6
    assert cell['representative_system_id64'] == 9_800_000_001
    for legacy_aux_field in (
        'landable_count', 'station_count',
        'biological_system_count', 'terraformable_system_count',
    ):
        assert legacy_aux_field not in cell, f'unexpected legacy aux field {legacy_aux_field!r} in cell payload'

    # 102 real occupied cells fall inside WIDE_BOX (1 primary + 1 "out-of-box"
    # + 100 fillers, all seeded above) -- comfortably more than the endpoint's
    # minimum allowed `max_cells` (100), so this exercises real truncation
    # rather than an edge case that happens to fit.
    r = await client.get('/api/map/heatmap', params={**WIDE_BOX, 'max_cells': 100})
    assert r.status_code == 200, r.text
    body = r.json()

    assert body['source'] == 'pyramid'
    assert body['max_cells'] == 100
    assert body['truncated'] is True
    assert body['count'] == 100
    # Ordered system_count DESC, so the 6-system cell wins the first slot.
    assert body['cells'][0]['system_count'] == 6
    assert 'landable_count' not in body['cells'][0]

    r_full = await client.get('/api/map/heatmap', params={**WIDE_BOX, 'max_cells': 200})
    assert r_full.status_code == 200, r_full.text
    body_full = r_full.json()
    assert body_full['truncated'] is False
    assert body_full['count'] == 102
