"""Tests for the V3 spatial density pyramid cell-level registry + source resolver.

Reuses the `db_conn` fixture pattern from
`tests/test_journal_commander_association.py`: a real, disposable-DB-only
connection routed through `tests/helpers/db_isolation`, wrapped in a rolled
back transaction so nothing persists between tests. Skips (rather than fails)
when no local disposable Postgres is reachable.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
import pytest

os.environ.setdefault('CORS_ORIGINS', 'http://testserver')

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tests.helpers import db_isolation  # noqa: E402


@pytest.fixture
def db_conn():
    """A real, disposable-DB-only connection wrapped in a rolled-back transaction.

    Reuses the repo's fail-closed DB isolation helpers (tests/helpers/db_isolation.py)
    so this never targets a production-looking host/database. Skips (rather than
    fails) when no local disposable Postgres is reachable, per the project's
    "real-service tests must skip explicitly when the service is absent" rule.
    """
    target = db_isolation.default_target(os.environ)
    try:
        conn = psycopg.connect(target.dsn)
    except psycopg.OperationalError as exc:
        pytest.skip(f'disposable test Postgres unreachable at {target.redacted_dsn}: {exc}')
        return
    conn.autocommit = False
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


def test_cell_levels_registered(db_conn):
    from scripts.v3_spatial_pyramid import PYRAMID_VERSION, CELL_LEVELS, register_cell_levels
    register_cell_levels(db_conn, PYRAMID_VERSION)
    rows = db_conn.execute(
        "SELECT level, cell_size_ly FROM v3_spatial.cell_level WHERE spatial_pyramid_version=%s ORDER BY level",
        (PYRAMID_VERSION,),
    ).fetchall()
    assert [r[0] for r in rows] == [lvl.level for lvl in CELL_LEVELS]
    # sizes strictly decrease as level increases (coarse -> fine)
    sizes = [r[1] for r in rows]
    assert sizes == sorted(sizes, reverse=True)


def test_register_cell_levels_is_idempotent(db_conn):
    from scripts.v3_spatial_pyramid import PYRAMID_VERSION, register_cell_levels
    register_cell_levels(db_conn, PYRAMID_VERSION)
    register_cell_levels(db_conn, PYRAMID_VERSION)  # must not raise or duplicate
    n = db_conn.execute(
        "SELECT count(*) FROM v3_spatial.cell_level WHERE spatial_pyramid_version=%s",
        (PYRAMID_VERSION,),
    ).fetchone()[0]
    from scripts.v3_spatial_pyramid import CELL_LEVELS
    assert n == len(CELL_LEVELS)


# Test-only cell level, well outside CELL_LEVELS' real 0-6 ladder but inside the
# schema's CHECK(level BETWEEN 0 AND 30), so it never collides with a real level.
_TEST_CELL_LEVEL = 30
_TEST_CELL_SIZE_LY = 100.0

# Matches the three fixture rows `_seed_generation` always inserts.
SEEDED_SYSTEM_COUNT = 3


def _seed_generation(conn, *, omit_last: bool = False) -> str:
    """Seed the minimal `v3_meta.canonical_generation` -> `v3_meta.derived_generation`
    chain plus three `v3_derived.system_search` rows with known coordinates and aux
    flags, entirely inside the caller's (rolled-back) transaction.

    `omit_last=True` drops the last of the three fixture systems, simulating an
    incomplete/short aggregation source (e.g. a partial `system_search` build) while
    `SEEDED_SYSTEM_COUNT` (the canonical truth) stays at 3 -- this is what
    `reconcile` must fail closed on.

    Mirrors the minimal-fixture pattern in
    `tests/test_journal_contributions_postgres.py`'s `generation()` helper: only the
    FKs `v3_meta.derived_generation` and `v3_derived.system_search` actually require
    (source/source_run/canonical_generation identity) are created. No canonical
    `{schema}.systems`/`bodies` relations are needed because `build_level`'s
    `source='system_search'` path never reads them, and
    `v3_derived.system_search`'s FK to `v3_derived.system_rating_vector` is
    DEFERRABLE INITIALLY DEFERRED, so it is never checked inside a transaction this
    test always rolls back instead of commits.
    """
    import uuid

    gid, run_id = uuid.uuid4(), uuid.uuid4()
    key = 'pyramidtest_' + gid.hex[:16]
    source_id = conn.execute(
        "INSERT INTO v3_source.source(source_code,display_name,authority_class) "
        "VALUES(%s,'Fixture','OPERATOR_ADJUDICATION') RETURNING source_id",
        (key,),
    ).fetchone()[0]
    rights_id = conn.execute(
        "INSERT INTO v3_source.source_rights_policy(source_id,policy_version,rights_class,retention_class,effective_at) "
        "VALUES(%s,'test','CANONICAL_ELIGIBLE','TEST',now()) RETURNING rights_policy_id",
        (source_id,),
    ).fetchone()[0]
    conn.execute(
        """INSERT INTO v3_source.source_run(source_run_id,source_id,rights_policy_id,acquisition_kind,trust_zone,
               run_state,idempotency_key,started_at,completed_at,importer_version,importer_code_sha256,
               importer_config_sha256,normalizer_version,normalizer_sha256)
           VALUES(%s,%s,%s,'BULK_SNAPSHOT','CANONICAL','SUCCEEDED',%s,now(),now(),'test',%s,%s,'test',%s)""",
        (run_id, source_id, rights_id, key, b'x' * 32, b'x' * 32, b'x' * 32),
    )
    conn.execute(
        "INSERT INTO v3_meta.canonical_generation(generation_id,generation_key,relation_schema,manifest_sha256,build_source_run_id) "
        "VALUES(%s,%s,%s,%s,%s)",
        (gid, key, 'v3_gen_' + key, b'x' * 32, run_id),
    )

    dgid = uuid.uuid4()
    conn.execute(
        """INSERT INTO v3_meta.derived_generation(
               derived_generation_id,canonical_generation_id,canonical_publication_sequence,
               generation_key,mechanics_version,scorer_version,adapter_version,
               manifest,manifest_sha256,expected_systems,expected_bodies)
           VALUES(%s,%s,1,%s,'test','test','test','{}'::jsonb,%s,3,0)""",
        (dgid, gid, key, b'x' * 32),
    )

    # v3_derived.system_search is guarded (migration 006) by a v3_meta.derived_product
    # row: inserts are only accepted while that product is BUILDING.
    conn.execute(
        """INSERT INTO v3_meta.derived_product(
               derived_generation_id,product_code,product_version,manifest,manifest_sha256,expected_rows)
           VALUES(%s,'system_search','test','{}'::jsonb,%s,3)""",
        (dgid, b'x' * 32),
    )

    # (10,10,10) and (20,20,20) share cell (0,0,0) at size 100ly; (150,0,0) is its
    # own cell (1,0,0). landable_count 1 & 2 sum to 3 in the shared cell; the first
    # system has_biologicals; the third has_terraformable.
    systems = [
        (1001, 'Alpha', 10.0, 10.0, 10.0, 5, 1, 0, True, False),
        (1002, 'Beta', 20.0, 20.0, 20.0, 5, 2, 1, False, False),
        (1003, 'Gamma', 150.0, 0.0, 0.0, 5, 0, 0, False, True),
    ]
    if omit_last:
        systems = systems[:-1]
    for system_id64, name, x, y, z, body_count, landable_count, station_count, biologicals, terraformable in systems:
        conn.execute(
            """INSERT INTO v3_derived.system_search(
                   derived_generation_id,system_id64,name,x_ly,y_ly,z_ly,position_ly,
                   body_count,landable_count,station_count,has_rings,has_biologicals,
                   has_geologicals,has_terraformable,completeness,confidence)
               VALUES(%(gen)s,%(sid)s,%(name)s,%(x)s,%(y)s,%(z)s,cube(ARRAY[%(x)s,%(y)s,%(z)s]),
                      %(bc)s,%(lc)s,%(sc)s,false,%(bio)s,false,%(terra)s,1.0,1.0)""",
            {
                'gen': dgid, 'sid': system_id64, 'name': name, 'x': x, 'y': y, 'z': z,
                'bc': body_count, 'lc': landable_count, 'sc': station_count,
                'bio': biologicals, 'terra': terraformable,
            },
        )
    return str(dgid)


@pytest.fixture
def seeded_generation(db_conn):
    return _seed_generation(db_conn)


@pytest.fixture
def seeded_generation_missing_one(db_conn):
    return _seed_generation(db_conn, omit_last=True)


def _register_test_cell_level(conn, version: str) -> None:
    conn.execute(
        """INSERT INTO v3_spatial.cell_level
               (spatial_pyramid_version,level,cell_size_ly,intended_scale)
           VALUES (%s,%s,%s,'test')
           ON CONFLICT (spatial_pyramid_version,level) DO NOTHING""",
        (version, _TEST_CELL_LEVEL, _TEST_CELL_SIZE_LY),
    )


def test_build_level_aggregates_counts_and_centroid(db_conn, seeded_generation):
    from scripts.v3_spatial_pyramid import PYRAMID_VERSION, register_cell_levels, build_level
    register_cell_levels(db_conn, PYRAMID_VERSION)
    _register_test_cell_level(db_conn, PYRAMID_VERSION)

    n = build_level(
        db_conn, derived_generation_id=seeded_generation, version=PYRAMID_VERSION,
        level=_TEST_CELL_LEVEL, cell_size_ly=_TEST_CELL_SIZE_LY, source='system_search',
    )
    assert n == 2  # two occupied cells

    origin_cell = db_conn.execute(
        """SELECT system_count, landable_count, station_count,
                  biological_system_count, terraformable_system_count,
                  centroid_x_ly, centroid_y_ly, centroid_z_ly, origin_x_ly,
                  cell_key, representative_system_id64
             FROM v3_spatial.cell_summary
            WHERE derived_generation_id=%s AND level=%s AND origin_x_ly=0
            """,
        (seeded_generation, _TEST_CELL_LEVEL),
    ).fetchone()
    assert origin_cell[0] == 2                      # system_count
    assert origin_cell[1] == 3                      # SUM(landable_count) 1+2
    assert origin_cell[2] == 1                      # SUM(station_count) 0+1
    assert origin_cell[3] == 1                      # biological_system_count (COUNT FILTER)
    assert origin_cell[4] == 0                      # terraformable_system_count
    assert origin_cell[5] == pytest.approx(15.0)    # centroid_x avg(10,20)
    assert origin_cell[6] == pytest.approx(15.0)    # centroid_y avg(10,20)
    assert origin_cell[7] == pytest.approx(15.0)    # centroid_z avg(10,20)
    assert origin_cell[9] == '0.0.0'
    assert origin_cell[10] == 1001                  # min(system_id64)

    far_cell = db_conn.execute(
        """SELECT system_count, landable_count, biological_system_count,
                  terraformable_system_count, origin_x_ly, cell_key
             FROM v3_spatial.cell_summary
            WHERE derived_generation_id=%s AND level=%s AND origin_x_ly=100
            """,
        (seeded_generation, _TEST_CELL_LEVEL),
    ).fetchone()
    assert far_cell[0] == 1
    assert far_cell[1] == 0
    assert far_cell[2] == 0
    assert far_cell[3] == 1                         # terraformable_system_count
    assert far_cell[5] == '1.0.0'


def test_build_level_is_insert_only_and_repeat_raises(db_conn, seeded_generation):
    """`cell_summary` is immutable once written (migration 004 triggers): a second
    build for the same (generation, version, level) must fail on the primary key
    rather than silently duplicating or updating rows.
    """
    from scripts.v3_spatial_pyramid import PYRAMID_VERSION, register_cell_levels, build_level
    register_cell_levels(db_conn, PYRAMID_VERSION)
    _register_test_cell_level(db_conn, PYRAMID_VERSION)

    build_level(
        db_conn, derived_generation_id=seeded_generation, version=PYRAMID_VERSION,
        level=_TEST_CELL_LEVEL, cell_size_ly=_TEST_CELL_SIZE_LY, source='system_search',
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        build_level(
            db_conn, derived_generation_id=seeded_generation, version=PYRAMID_VERSION,
            level=_TEST_CELL_LEVEL, cell_size_ly=_TEST_CELL_SIZE_LY, source='system_search',
        )
    db_conn.rollback()


def test_build_all_levels_returns_level_to_cell_count(db_conn, seeded_generation):
    from scripts.v3_spatial_pyramid import PYRAMID_VERSION, CELL_LEVELS, register_cell_levels, build_all_levels
    register_cell_levels(db_conn, PYRAMID_VERSION)

    counts = build_all_levels(
        db_conn, derived_generation_id=seeded_generation, version=PYRAMID_VERSION,
        source='system_search',
    )
    assert set(counts) == {lvl.level for lvl in CELL_LEVELS}
    # The coarsest registered level (2560ly cells) must merge all three fixture
    # systems (max separation ~150ly) into a single occupied cell.
    coarsest = min(CELL_LEVELS, key=lambda lvl: lvl.level)
    assert counts[coarsest.level] == 1


def test_build_level_unknown_source_raises(db_conn, seeded_generation):
    from scripts.v3_spatial_pyramid import PYRAMID_VERSION, build_level
    with pytest.raises(ValueError):
        build_level(
            db_conn, derived_generation_id=seeded_generation, version=PYRAMID_VERSION,
            level=_TEST_CELL_LEVEL, cell_size_ly=_TEST_CELL_SIZE_LY, source='bogus',
        )


def test_build_level_canonical_source_not_implemented(db_conn, seeded_generation):
    from scripts.v3_spatial_pyramid import PYRAMID_VERSION, build_level
    with pytest.raises(NotImplementedError):
        build_level(
            db_conn, derived_generation_id=seeded_generation, version=PYRAMID_VERSION,
            level=_TEST_CELL_LEVEL, cell_size_ly=_TEST_CELL_SIZE_LY, source='canonical',
        )


# --- Task 3: reconciliation gate + validation receipt -----------------------------


def test_reconcile_passes_when_sum_matches(db_conn, seeded_generation):
    from scripts.v3_spatial_pyramid import PYRAMID_VERSION, register_cell_levels, build_all_levels, reconcile
    register_cell_levels(db_conn, PYRAMID_VERSION)
    build_all_levels(db_conn, derived_generation_id=seeded_generation, source='system_search')
    result = reconcile(
        db_conn, derived_generation_id=seeded_generation, version=PYRAMID_VERSION,
        canonical_count=SEEDED_SYSTEM_COUNT,
    )
    assert result['canonical_count'] == SEEDED_SYSTEM_COUNT
    assert result['per_level_system_sum']
    assert all(v == SEEDED_SYSTEM_COUNT for v in result['per_level_system_sum'].values())


def test_reconcile_fails_closed_on_incomplete_source(db_conn, seeded_generation_missing_one):
    from scripts.v3_spatial_pyramid import (
        PYRAMID_VERSION, register_cell_levels, build_all_levels, reconcile, ReconciliationError,
    )
    register_cell_levels(db_conn, PYRAMID_VERSION)
    # Built from a system_search that is short by one system -> every level's Σ is
    # 2, not the canonical truth of 3 -> reconciliation must fail closed.
    build_all_levels(db_conn, derived_generation_id=seeded_generation_missing_one, source='system_search')
    with pytest.raises(ReconciliationError):
        reconcile(
            db_conn, derived_generation_id=seeded_generation_missing_one, version=PYRAMID_VERSION,
            canonical_count=SEEDED_SYSTEM_COUNT,
        )


def test_reconcile_fails_closed_when_canonical_count_exceeds_built_sum(db_conn, seeded_generation):
    """Fails closed even when the pyramid build itself is internally consistent: a
    `canonical_count` the built cells cannot possibly reach (e.g. the caller read a
    stale/larger canonical count) must still raise, not silently pass.
    """
    from scripts.v3_spatial_pyramid import PYRAMID_VERSION, register_cell_levels, build_all_levels, reconcile, ReconciliationError
    register_cell_levels(db_conn, PYRAMID_VERSION)
    build_all_levels(db_conn, derived_generation_id=seeded_generation, source='system_search')
    with pytest.raises(ReconciliationError):
        reconcile(
            db_conn, derived_generation_id=seeded_generation, version=PYRAMID_VERSION,
            canonical_count=SEEDED_SYSTEM_COUNT + 1,
        )


def test_reconcile_raises_when_levels_registered_but_cell_summary_empty(db_conn, seeded_generation):
    """The previously-vacuous case a reviewer flagged: levels ARE registered in
    `v3_spatial.cell_level` for `version`, but nothing was ever built into
    `cell_summary` for this (generation, version) -- e.g. the wrong generation id,
    the wrong version, or a build that silently wrote zero rows. Since Fix 1,
    `per_level_system_sum` being empty must raise `ReconciliationError` naming the
    missing levels, not return a vacuously "passed" dict from a validation loop
    that ran zero times.
    """
    from scripts.v3_spatial_pyramid import PYRAMID_VERSION, register_cell_levels, reconcile, ReconciliationError
    register_cell_levels(db_conn, PYRAMID_VERSION)
    # Deliberately never call build_level/build_all_levels: cell_summary stays
    # empty for seeded_generation even though PYRAMID_VERSION has levels registered.
    with pytest.raises(ReconciliationError):
        reconcile(
            db_conn, derived_generation_id=seeded_generation, version=PYRAMID_VERSION,
            canonical_count=SEEDED_SYSTEM_COUNT,
        )


def test_reconcile_raises_when_version_has_no_registered_levels(db_conn, seeded_generation):
    from scripts.v3_spatial_pyramid import reconcile, ReconciliationError
    # No register_cell_levels call at all for this version -> v3_spatial.cell_level
    # has zero rows for it -> nothing to reconcile against.
    with pytest.raises(ReconciliationError):
        reconcile(
            db_conn, derived_generation_id=seeded_generation, version='no_such_version',
            canonical_count=SEEDED_SYSTEM_COUNT,
        )


def test_build_receipt_returns_expected_keys_and_sums(db_conn, seeded_generation):
    from scripts.v3_spatial_pyramid import PYRAMID_VERSION, register_cell_levels, build_all_levels, build_receipt
    register_cell_levels(db_conn, PYRAMID_VERSION)
    per_level_cells = build_all_levels(db_conn, derived_generation_id=seeded_generation, source='system_search')

    receipt = build_receipt(
        db_conn, derived_generation_id=seeded_generation, version=PYRAMID_VERSION,
        source='system_search', canonical_count=SEEDED_SYSTEM_COUNT, per_level=per_level_cells,
    )

    assert receipt['spatial_pyramid_version'] == PYRAMID_VERSION
    assert receipt['source'] == 'system_search'
    assert receipt['canonical_count'] == SEEDED_SYSTEM_COUNT
    assert receipt['reconciliation'] == 'passed'
    assert receipt['derived_generation_id'] == str(seeded_generation)
    assert receipt['coverage_at'] is not None
    assert set(receipt['per_level']) == set(per_level_cells)
    for level, cell_count in per_level_cells.items():
        info = receipt['per_level'][level]
        assert info['cell_count'] == cell_count
        assert info['system_count_sum'] == SEEDED_SYSTEM_COUNT
    # No secret-shaped keys/values sneak into the receipt.
    blob = repr(receipt).lower()
    for forbidden in ('password', 'secret', 'token', 'dsn', 'apikey'):
        assert forbidden not in blob


def test_build_receipt_raises_when_reconciliation_fails(db_conn, seeded_generation_missing_one):
    from scripts.v3_spatial_pyramid import (
        PYRAMID_VERSION, register_cell_levels, build_all_levels, build_receipt, ReconciliationError,
    )
    register_cell_levels(db_conn, PYRAMID_VERSION)
    per_level_cells = build_all_levels(
        db_conn, derived_generation_id=seeded_generation_missing_one, source='system_search',
    )
    with pytest.raises(ReconciliationError):
        build_receipt(
            db_conn, derived_generation_id=seeded_generation_missing_one, version=PYRAMID_VERSION,
            source='system_search', canonical_count=SEEDED_SYSTEM_COUNT, per_level=per_level_cells,
        )


def test_build_receipt_raises_for_unknown_generation(db_conn):
    """Fix 2: an unresolvable `derived_generation_id` (e.g. a typo'd or stale id)
    must raise `ValueError` -- mirroring `_canonical_schema`'s convention -- rather
    than silently emitting a receipt with `canonical_generation_id`/`coverage_at`
    set to None.
    """
    import uuid
    from scripts.v3_spatial_pyramid import PYRAMID_VERSION, build_receipt
    with pytest.raises(ValueError):
        build_receipt(
            db_conn, derived_generation_id=str(uuid.uuid4()), version=PYRAMID_VERSION,
            source='system_search', canonical_count=0, per_level={},
        )


# --- resolve_source, now that generation fixtures exist (carried-over gap) --------


def _seed_generation_with_canonical(conn, *, canonical_count: int, search_count: int) -> str:
    """Seed a canonical generation with real `{schema}.systems` physical relations
    (via `v3_meta.create_canonical_generation_relations`, the same stored procedure
    production canonical builds use), plus a derived generation and `canonical_count`
    / `search_count`-controlled row counts, so `resolve_source`'s canonical-count
    comparison query has a real table to run against.

    Returns the derived_generation_id (str).
    """
    import uuid

    gid, run_id = uuid.uuid4(), uuid.uuid4()
    key = 'pyrsrc_' + gid.hex[:16]
    schema = 'v3_gen_' + key
    source_id = conn.execute(
        "INSERT INTO v3_source.source(source_code,display_name,authority_class) "
        "VALUES(%s,'Fixture','OPERATOR_ADJUDICATION') RETURNING source_id",
        (key,),
    ).fetchone()[0]
    rights_id = conn.execute(
        "INSERT INTO v3_source.source_rights_policy(source_id,policy_version,rights_class,retention_class,effective_at) "
        "VALUES(%s,'test','CANONICAL_ELIGIBLE','TEST',now()) RETURNING rights_policy_id",
        (source_id,),
    ).fetchone()[0]
    conn.execute(
        """INSERT INTO v3_source.source_run(source_run_id,source_id,rights_policy_id,acquisition_kind,trust_zone,
               run_state,idempotency_key,started_at,completed_at,importer_version,importer_code_sha256,
               importer_config_sha256,normalizer_version,normalizer_sha256)
           VALUES(%s,%s,%s,'BULK_SNAPSHOT','CANONICAL','SUCCEEDED',%s,now(),now(),'test',%s,%s,'test',%s)""",
        (run_id, source_id, rights_id, key, b'x' * 32, b'x' * 32, b'x' * 32),
    )
    conn.execute(
        "INSERT INTO v3_meta.canonical_generation(generation_id,generation_key,relation_schema,manifest_sha256,build_source_run_id) "
        "VALUES(%s,%s,%s,%s,%s)",
        (gid, key, schema, b'x' * 32, run_id),
    )
    # Real physical `{schema}.systems`/`bodies` relations, the same call production
    # canonical-generation builds make; resolve_source's fallback-count query reads
    # `{schema}.systems` directly, so a fixture without this would be faking the
    # comparison rather than exercising it.
    conn.execute('SELECT v3_meta.create_canonical_generation_relations(%s)', (gid,))

    for i in range(canonical_count):
        conn.execute(
            f"""INSERT INTO {schema}.systems
                   (id64,name,x_ly,y_ly,z_ly,loaded_body_count,grid_x,grid_y,grid_z,
                    macro_grid_key,source_id,source_run_id,freshness_checked_at)
                VALUES (%(id)s,%(name)s,%(x)s,0,0,0,0,0,0,0,%(src)s,%(run)s,now())""",
            {'id': 2000 + i, 'name': f'Canon{i}', 'x': float(i), 'src': source_id, 'run': run_id},
        )

    dgid = uuid.uuid4()
    conn.execute(
        """INSERT INTO v3_meta.derived_generation(
               derived_generation_id,canonical_generation_id,canonical_publication_sequence,
               generation_key,mechanics_version,scorer_version,adapter_version,
               manifest,manifest_sha256,expected_systems,expected_bodies)
           VALUES(%s,%s,1,%s,'test','test','test','{}'::jsonb,%s,%s,0)""",
        (dgid, gid, key, b'x' * 32, max(search_count, 1)),
    )
    conn.execute(
        """INSERT INTO v3_meta.derived_product(
               derived_generation_id,product_code,product_version,manifest,manifest_sha256,expected_rows)
           VALUES(%s,'system_search','test','{}'::jsonb,%s,%s)""",
        (dgid, b'x' * 32, max(search_count, 1)),
    )
    for i in range(search_count):
        conn.execute(
            """INSERT INTO v3_derived.system_search(
                   derived_generation_id,system_id64,name,x_ly,y_ly,z_ly,position_ly,
                   body_count,landable_count,station_count,has_rings,has_biologicals,
                   has_geologicals,has_terraformable,completeness,confidence)
               VALUES(%(gen)s,%(sid)s,%(name)s,%(x)s,0,0,cube(ARRAY[%(x)s,0,0]),
                      0,0,0,false,false,false,false,1.0,1.0)""",
            {'gen': dgid, 'sid': 3000 + i, 'name': f'Search{i}', 'x': float(i)},
        )
    return str(dgid)


def test_resolve_source_returns_system_search_when_counts_match(db_conn):
    from scripts.v3_spatial_pyramid import resolve_source
    dgid = _seed_generation_with_canonical(db_conn, canonical_count=2, search_count=2)
    assert resolve_source(db_conn, dgid) == 'system_search'


def test_resolve_source_returns_canonical_when_counts_differ(db_conn):
    from scripts.v3_spatial_pyramid import resolve_source
    dgid = _seed_generation_with_canonical(db_conn, canonical_count=3, search_count=2)
    assert resolve_source(db_conn, dgid) == 'canonical'


# --- Task 4: register the pyramid derived-product + mark READY; resolve via
# the current published generation. Architecture (verified against
# sql/v3/migrations/006_v3_derived_product_lifecycle.sql and
# scripts/v3_system_search.py): `v3_meta.derived_product.lifecycle_state` is
# only BUILDING/READY/FAILED and never self-publishes. PUBLISHED + the atomic
# active pointer are generation-level (`v3_meta.current_derived_generation`,
# swapped by `v3_meta.publish_derived_generation`), gated on all products
# being READY. There is no per-pyramid PUBLISHED state or pointer here. -------


def _build_reconciled_receipt(conn, derived_generation_id, version=None):
    """Build every registered level + assemble a real, reconciled `build_receipt`
    for `derived_generation_id`, the exact input `mark_pyramid_ready` expects.
    """
    from scripts.v3_spatial_pyramid import PYRAMID_VERSION, build_all_levels, build_receipt

    version = version or PYRAMID_VERSION
    per_level = build_all_levels(conn, derived_generation_id=derived_generation_id, version=version, source='system_search')
    return build_receipt(
        conn, derived_generation_id=derived_generation_id, version=version,
        source='system_search', canonical_count=SEEDED_SYSTEM_COUNT, per_level=per_level,
    )


def _publish_generation_directly(conn, derived_generation_id) -> None:
    """Walk a fixture `v3_meta.derived_generation` row through the exact
    BUILDING -> VALIDATING -> READY -> PUBLISHED transition chain enforced by
    migration 003's `guard_derived_manifest` trigger, then point
    `v3_meta.current_derived_generation` at it -- the same generation-level
    mechanism `apps/api/src/routers/ratings_v4.py:_current` and
    `v3_meta.publish_derived_generation` read/write.

    This bypasses the heavy production `scripts/ratings_v4/production_generation.py`
    pipeline (chunk replay, content sealing) and `publish_derived_generation`'s
    canonical-generation compare-and-swap preconditions, since this task only
    needs a real PUBLISHED generation + current-generation pointer to exercise
    `pyramid_for_current_generation`'s read path, not a faithful Ratings V4
    build or a governed publish. `guard_derived_manifest` only guards UPDATE/
    DELETE (not INSERT), so the earlier direct INSERT in `_seed_generation`
    (already BUILDING) is unaffected; each UPDATE below is one legal step in
    its documented transition list.
    """
    # content_sha256/source_receipt may only change while OLD.lifecycle_state
    # is still 'BUILDING' (guard_derived_manifest's source/content seal rule),
    # so they are set on this first BUILDING->VALIDATING step, not the next one.
    conn.execute(
        """UPDATE v3_meta.derived_generation
              SET lifecycle_state='VALIDATING',
                  content_sha256=%s, source_receipt='{}'::jsonb
            WHERE derived_generation_id=%s""",
        (b'x' * 32, derived_generation_id),
    )
    conn.execute(
        """UPDATE v3_meta.derived_generation
              SET lifecycle_state='READY', validated_at=now(),
                  validation_receipt='{"status":"VERIFIED"}'::jsonb
            WHERE derived_generation_id=%s""",
        (derived_generation_id,),
    )
    conn.execute(
        "UPDATE v3_meta.derived_generation SET lifecycle_state='PUBLISHED', published_at=now() "
        "WHERE derived_generation_id=%s",
        (derived_generation_id,),
    )
    conn.execute(
        """INSERT INTO v3_meta.current_derived_generation(singleton, derived_generation_id, publication_sequence)
           VALUES(true, %s, 1)
           ON CONFLICT(singleton) DO UPDATE
               SET derived_generation_id=EXCLUDED.derived_generation_id,
                   publication_sequence=EXCLUDED.publication_sequence,
                   published_at=now()""",
        (derived_generation_id,),
    )


def test_mark_pyramid_ready_transitions_building_to_ready_with_receipt(db_conn, seeded_generation):
    from scripts.v3_spatial_pyramid import PYRAMID_VERSION, PRODUCT_CODE, register_cell_levels, mark_pyramid_ready

    register_cell_levels(db_conn, PYRAMID_VERSION)
    receipt = _build_reconciled_receipt(db_conn, seeded_generation)

    mark_pyramid_ready(
        db_conn, derived_generation_id=seeded_generation, version=PYRAMID_VERSION, receipt=receipt,
    )

    row = db_conn.execute(
        """SELECT lifecycle_state, product_version, validation_receipt, validation_sha256, validated_at
             FROM v3_meta.derived_product
            WHERE derived_generation_id=%s AND product_code=%s""",
        (seeded_generation, PRODUCT_CODE),
    ).fetchone()
    assert row is not None
    assert row[0] == 'READY'
    assert row[1] == PYRAMID_VERSION
    assert row[2]['status'] == 'VERIFIED'
    assert row[2]['reconciliation'] == 'passed'
    assert row[3] is not None
    assert row[4] is not None


def test_mark_pyramid_ready_is_idempotent(db_conn, seeded_generation):
    from scripts.v3_spatial_pyramid import PYRAMID_VERSION, PRODUCT_CODE, register_cell_levels, mark_pyramid_ready

    register_cell_levels(db_conn, PYRAMID_VERSION)
    receipt = _build_reconciled_receipt(db_conn, seeded_generation)

    mark_pyramid_ready(db_conn, derived_generation_id=seeded_generation, version=PYRAMID_VERSION, receipt=receipt)
    mark_pyramid_ready(db_conn, derived_generation_id=seeded_generation, version=PYRAMID_VERSION, receipt=receipt)

    rows = db_conn.execute(
        "SELECT lifecycle_state FROM v3_meta.derived_product WHERE derived_generation_id=%s AND product_code=%s",
        (seeded_generation, PRODUCT_CODE),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 'READY'


def test_mark_pyramid_ready_rejects_unreconciled_receipt(db_conn, seeded_generation):
    from scripts.v3_spatial_pyramid import PYRAMID_VERSION, register_cell_levels, mark_pyramid_ready

    register_cell_levels(db_conn, PYRAMID_VERSION)
    with pytest.raises(ValueError):
        mark_pyramid_ready(
            db_conn, derived_generation_id=seeded_generation, version=PYRAMID_VERSION,
            receipt={'reconciliation': 'failed', 'canonical_count': SEEDED_SYSTEM_COUNT},
        )


def test_pyramid_for_current_generation_returns_gen_and_version_when_ready_and_current(db_conn, seeded_generation):
    import uuid
    from scripts.v3_spatial_pyramid import (
        PYRAMID_VERSION, register_cell_levels, mark_pyramid_ready, pyramid_for_current_generation,
    )

    register_cell_levels(db_conn, PYRAMID_VERSION)
    receipt = _build_reconciled_receipt(db_conn, seeded_generation)
    mark_pyramid_ready(db_conn, derived_generation_id=seeded_generation, version=PYRAMID_VERSION, receipt=receipt)

    _publish_generation_directly(db_conn, seeded_generation)

    result = pyramid_for_current_generation(db_conn)
    assert result == (uuid.UUID(seeded_generation), PYRAMID_VERSION)


def test_pyramid_for_current_generation_returns_none_when_no_current_generation(db_conn, seeded_generation):
    from scripts.v3_spatial_pyramid import (
        PYRAMID_VERSION, register_cell_levels, mark_pyramid_ready, pyramid_for_current_generation,
    )

    # Product is READY, but nothing has published this generation as current.
    register_cell_levels(db_conn, PYRAMID_VERSION)
    receipt = _build_reconciled_receipt(db_conn, seeded_generation)
    mark_pyramid_ready(db_conn, derived_generation_id=seeded_generation, version=PYRAMID_VERSION, receipt=receipt)

    assert pyramid_for_current_generation(db_conn) is None


def test_pyramid_for_current_generation_returns_none_when_product_not_ready(db_conn, seeded_generation):
    from scripts.v3_spatial_pyramid import pyramid_for_current_generation

    # Generation is current/PUBLISHED, but the spatial-pyramid product was
    # never registered/readied for it.
    _publish_generation_directly(db_conn, seeded_generation)

    assert pyramid_for_current_generation(db_conn) is None
