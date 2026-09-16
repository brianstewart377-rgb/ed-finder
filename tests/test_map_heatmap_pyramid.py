"""Integration: GET /api/map/heatmap served from the reconciled `v3_spatial`
density pyramid for the current *published* derived generation, with an
explicit legacy-fallback tag when no such pyramid is published.

Reuses `tests/integration/conftest.py`'s `app`/`client`/`pool` fixtures via
`pytest_plugins` (this file lives outside `tests/integration/` per the task
brief) and mirrors `tests/test_v3_spatial_pyramid.py`'s minimal fixture-chain
seeding (source -> source_run -> canonical_generation -> derived_generation
-> derived_product -> cell_level/cell_summary -> publish), adapted to asyncpg
since this exercises the live FastAPI app/pool with real commits (not a
rolled-back transaction) and therefore needs explicit teardown.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

# Reuse the `app`/`client`/`pool`/`clean_db` fixtures from
# tests/integration/conftest.py by importing them directly rather than via
# `pytest_plugins`: this file is collected in the same pytest session as
# tests/integration/* (default `testpaths = ["tests"]`), which already loads
# that conftest module via pytest's normal directory-based discovery --
# `pytest_plugins = ['tests.integration.conftest']` here would register the
# same module a second time under a different plugin name and fail
# collection ("Plugin already registered under a different name"). A plain
# import instead just binds the same fixture functions (autouse included)
# into this module's namespace, which pytest picks up without any conflict.
#
# Ruff's pyflakes checks don't know about pytest's fixture-lookup-by-name
# machinery, so it sees two problems that are both intentional here:
#   * F401 on this import -- the names are never referenced directly in this
#     module, only resolved by pytest via fixture name matching.
#   * F811 wherever a test/fixture function below declares a parameter named
#     `client`/`pool` (matching this import) -- pyflakes reads that as
#     "redefining" the imported name, but it's actually pytest requesting the
#     already-imported fixture by name, not a real shadowing bug. Each such
#     def below carries its own noqa suppression for F811, for the same
#     reason.
from tests.integration.conftest import app, client, clean_db, pool  # noqa: F401

pytestmark = pytest.mark.asyncio

PRODUCT_CODE = 'spatial_pyramid'
TEST_LEVEL = 30  # outside the real 0-6 ladder; CHECK allows level BETWEEN 0 AND 30
TEST_CELL_SIZE_LY = 100.0

# Far outside the real galaxy so these fixture cells never collide with real data.
BASE = 700_000.0


async def _seed_pyramid_generation(conn):
    """Seed a real, committed v3_meta/v3_spatial generation chain with two
    occupied `cell_summary` cells at a dedicated test level/version, mark the
    `spatial_pyramid` product READY, and publish the generation as current.

    Returns (derived_generation_id, version, canonical_generation_id,
    source_run_id, source_id, prior_current_row) for the caller to assert
    against and tear down.
    """
    gid, run_id, dgid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    key = 'hmtest' + gid.hex[:16]
    schema = 'v3_gen_' + key
    version = 'pyr_' + gid.hex[:16]

    source_id = await conn.fetchval(
        "INSERT INTO v3_source.source(source_code,display_name,authority_class) "
        "VALUES($1,'Fixture','OPERATOR_ADJUDICATION') RETURNING source_id",
        key,
    )
    rights_id = await conn.fetchval(
        "INSERT INTO v3_source.source_rights_policy"
        "(source_id,policy_version,rights_class,retention_class,effective_at) "
        "VALUES($1,'test','CANONICAL_ELIGIBLE','TEST',now()) RETURNING rights_policy_id",
        source_id,
    )
    await conn.execute(
        """INSERT INTO v3_source.source_run(source_run_id,source_id,rights_policy_id,acquisition_kind,
               trust_zone,run_state,idempotency_key,started_at,completed_at,importer_version,
               importer_code_sha256,importer_config_sha256,normalizer_version,normalizer_sha256)
           VALUES($1,$2,$3,'BULK_SNAPSHOT','CANONICAL','SUCCEEDED',$4,now(),now(),'test',$5,$5,'test',$5)""",
        run_id, source_id, rights_id, key, b'x' * 32,
    )
    await conn.execute(
        "INSERT INTO v3_meta.canonical_generation"
        "(generation_id,generation_key,relation_schema,manifest_sha256,build_source_run_id) "
        "VALUES($1,$2,$3,$4,$5)",
        gid, key, schema, b'x' * 32, run_id,
    )
    await conn.execute(
        """INSERT INTO v3_meta.derived_generation(
               derived_generation_id,canonical_generation_id,canonical_publication_sequence,
               generation_key,mechanics_version,scorer_version,adapter_version,
               manifest,manifest_sha256,expected_systems,expected_bodies)
           VALUES($1,$2,1,$3,'test','test','test','{}'::jsonb,$4,3,0)""",
        dgid, gid, key, b'x' * 32,
    )
    await conn.execute(
        """INSERT INTO v3_meta.derived_product(
               derived_generation_id,product_code,product_version,manifest,manifest_sha256,expected_rows)
           VALUES($1,$2,$3,'{}'::jsonb,$4,3)""",
        dgid, PRODUCT_CODE, version, b'x' * 32,
    )
    await conn.execute(
        """INSERT INTO v3_spatial.cell_level(spatial_pyramid_version,level,cell_size_ly,intended_scale)
           VALUES($1,$2,$3,'test')""",
        version, TEST_LEVEL, TEST_CELL_SIZE_LY,
    )

    # Two occupied test cells with real, arbitrary (but fixture-only)
    # coordinates -- one inside the narrow query bounds used below, one only
    # inside the wide bounds -- plus a batch of low-signal filler cells (also
    # only inside the wide bounds) so the wide-bounds request has enough
    # occupied cells to exercise honest truncation at the endpoint's minimum
    # allowed `max_cells` (100).
    cells = [
        # origin,                  centroid,                            sc lc st bio terra key
        (BASE, BASE, BASE,         BASE + 10.0, BASE + 10.0, BASE + 10.0, 6, 4, 2, 1, 0, 'in-box'),
        (BASE + 100_000.0, 0.0, 0.0, BASE + 100_010.0, 5.0, 5.0,          3, 0, 0, 0, 1, 'out-of-box'),
    ]
    filler_count = 100
    for i in range(filler_count):
        cells.append((
            BASE + 2_000.0 + i, 0.0, 0.0,
            BASE + 2_000.0 + i, 1.0, 1.0,
            1, 0, 0, 0, 0, f'filler-{i}',
        ))

    await conn.executemany(
        """INSERT INTO v3_spatial.cell_summary(
               derived_generation_id,spatial_pyramid_version,level,cell_key,
               origin_x_ly,origin_y_ly,origin_z_ly,system_count,
               centroid_x_ly,centroid_y_ly,centroid_z_ly,
               landable_count,station_count,biological_system_count,
               terraformable_system_count,representative_system_id64)
           VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)""",
        [
            (
                dgid, version, TEST_LEVEL, cell_key,
                ox, oy, oz, sc, cx, cy, cz, lc, stc, bio, terra, 9_800_000_001,
            )
            for ox, oy, oz, cx, cy, cz, sc, lc, stc, bio, terra, cell_key in cells
        ],
    )

    # BUILDING -> READY compare-and-swap for the pyramid product, mirroring
    # scripts/v3_spatial_pyramid.py:mark_pyramid_ready. Must happen while the
    # owning derived_generation is still BUILDING (guard_generation_write
    # requires that state for the cell_summary inserts above).
    await conn.execute(
        """UPDATE v3_meta.derived_product
              SET lifecycle_state='READY',
                  validation_receipt='{"status":"VERIFIED","reconciliation":"passed"}'::jsonb,
                  validation_sha256=$3, validated_at=now()
            WHERE derived_generation_id=$1 AND product_code=$2""",
        dgid, PRODUCT_CODE, b'y' * 32,
    )

    # Walk the derived generation through the exact legal
    # BUILDING -> VALIDATING -> READY -> PUBLISHED transition chain enforced
    # by guard_derived_manifest (migration 003), mirroring
    # tests/test_v3_spatial_pyramid.py:_publish_generation_directly.
    await conn.execute(
        """UPDATE v3_meta.derived_generation
              SET lifecycle_state='VALIDATING', content_sha256=$2, source_receipt='{}'::jsonb
            WHERE derived_generation_id=$1""",
        dgid, b'x' * 32,
    )
    await conn.execute(
        """UPDATE v3_meta.derived_generation
              SET lifecycle_state='READY', validated_at=now(),
                  validation_receipt='{"status":"VERIFIED"}'::jsonb
            WHERE derived_generation_id=$1""",
        dgid,
    )
    await conn.execute(
        "UPDATE v3_meta.derived_generation SET lifecycle_state='PUBLISHED', published_at=now() "
        "WHERE derived_generation_id=$1",
        dgid,
    )

    prior = await conn.fetchrow(
        'SELECT derived_generation_id, publication_sequence '
        'FROM v3_meta.current_derived_generation WHERE singleton'
    )
    await conn.execute(
        """INSERT INTO v3_meta.current_derived_generation(singleton, derived_generation_id, publication_sequence)
           VALUES(true, $1, $2)
           ON CONFLICT(singleton) DO UPDATE
               SET derived_generation_id=EXCLUDED.derived_generation_id,
                   publication_sequence=EXCLUDED.publication_sequence,
                   published_at=now()""",
        dgid, (prior['publication_sequence'] if prior else 0) + 1,
    )

    return dgid, version, gid, run_id, source_id, prior


async def _teardown_pyramid_generation(conn, *, dgid, version, gid, run_id, source_id, prior):
    """Restore the `v3_meta.current_derived_generation` pointer only.

    Everything else this fixture inserts (`v3_source.source*`,
    `v3_meta.canonical_generation`, `v3_meta.derived_generation`,
    `v3_meta.derived_product`, `v3_spatial.cell_level`/`cell_summary`) is, by
    design, an append-only ledger the schema's own triggers refuse to mutate
    or delete once written (`guard_derived_manifest`/`guard_derived_product`
    raise "manifests are retained" on DELETE; `guard_generation_write`
    likewise blocks cell_level/cell_summary changes once the owning
    generation has left `BUILDING`). Making this visible to the live app's
    own pool connection (a separate session from this fixture's) requires a
    real commit, so -- unlike `tests/test_v3_spatial_pyramid.py`'s
    rolled-back-transaction pattern -- these rows cannot be rolled back
    either. They are left behind intentionally: harmless, randomly-keyed
    (UUID) fixture rows on the disposable test database, consistent with the
    ledger's own declared immutability contract.
    """
    if prior is not None:
        await conn.execute(
            """UPDATE v3_meta.current_derived_generation
                  SET derived_generation_id=$1, publication_sequence=$2
                WHERE singleton""",
            prior['derived_generation_id'], prior['publication_sequence'],
        )
    else:
        await conn.execute('DELETE FROM v3_meta.current_derived_generation WHERE singleton')


@pytest_asyncio.fixture
async def seeded_pyramid(pool):  # noqa: F811 -- `pool` fixture requested by name, not a redefinition
    async with pool.acquire() as conn:
        dgid, version, gid, run_id, source_id, prior = await _seed_pyramid_generation(conn)
    try:
        yield dgid, version
    finally:
        async with pool.acquire() as conn:
            await _teardown_pyramid_generation(
                conn, dgid=dgid, version=version, gid=gid, run_id=run_id,
                source_id=source_id, prior=prior,
            )


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


async def test_heatmap_serves_pyramid_when_published_and_ready(client, seeded_pyramid):  # noqa: F811
    dgid, version = seeded_pyramid
    r = await client.get('/api/map/heatmap', params=IN_BOX)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body['source'] == 'pyramid'
    assert body['generation_id'] == str(dgid)
    assert body['spatial_pyramid_version'] == version
    assert body['source_system_count'] == 3
    assert body['coverage_at'] is not None
    assert body['bounds']['min_x'] == IN_BOX['min_x']
    assert body['bounds']['max_z'] == IN_BOX['max_z']
    assert body['count'] == 1
    assert body['truncated'] is False

    cell = body['cells'][0]
    for field in (
        'origin_x_ly', 'origin_y_ly', 'origin_z_ly',
        'centroid_x_ly', 'centroid_y_ly', 'centroid_z_ly',
        'system_count', 'landable_count', 'station_count',
        'biological_system_count', 'terraformable_system_count',
    ):
        assert field in cell, f'missing {field} in cell payload'
    assert cell['system_count'] == 6
    assert cell['landable_count'] == 4
    assert cell['station_count'] == 2
    assert cell['biological_system_count'] == 1
    assert cell['terraformable_system_count'] == 0


async def test_heatmap_truncates_honestly_within_bounds(client, seeded_pyramid):  # noqa: F811
    # 102 real occupied cells fall inside WIDE_BOX (1 primary + 1 "out-of-box"
    # + 100 fillers, all seeded by `seeded_pyramid`) -- comfortably more than
    # the endpoint's minimum allowed `max_cells` (100), so this exercises
    # real truncation rather than an edge case that happens to fit.
    r = await client.get('/api/map/heatmap', params={**WIDE_BOX, 'max_cells': 100})
    assert r.status_code == 200, r.text
    body = r.json()

    assert body['source'] == 'pyramid'
    assert body['max_cells'] == 100
    assert body['truncated'] is True
    assert body['count'] == 100
    # Ordered system_count DESC, so the 6-system cell wins the first slot.
    assert body['cells'][0]['system_count'] == 6

    r_full = await client.get('/api/map/heatmap', params={**WIDE_BOX, 'max_cells': 200})
    assert r_full.status_code == 200, r_full.text
    body_full = r_full.json()
    assert body_full['truncated'] is False
    assert body_full['count'] == 102


async def test_heatmap_uses_legacy_fallback_when_no_published_pyramid(client):  # noqa: F811
    r = await client.get('/api/map/heatmap')
    assert r.status_code == 200, r.text
    body = r.json()

    assert body['source'] == 'legacy-fallback'
    assert isinstance(body['cells'], list)
    assert isinstance(body['truncated'], bool)
    assert isinstance(body['count'], int)
