"""Tests for the V3 spatial density pyramid cell-level registry + canonical-density
builder.

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
    target = db_isolation.target_from_env(os.environ)
    try:
        conn = psycopg.connect(target.dsn)
    except psycopg.OperationalError as exc:
        pytest.skip(f'disposable test Postgres unreachable at {target.redacted_dsn}: {exc}')
        return
    conn.autocommit = False
    # The V3 spatial schema (migration 012_v3_spatial_pyramid_decouple) is only
    # present on a disposable DB with the V3 lineage applied. CI lanes that seed
    # the legacy V2 schema reach a live-but-wrong-schema Postgres, so skip (like
    # the tests/integration spatial suites do via v3_fixture_db_ready) rather than
    # erroring on missing v3_spatial/v3_source relations.
    if conn.execute("SELECT to_regclass('v3_spatial.spatial_generation')").fetchone()[0] is None:
        conn.rollback()
        conn.close()
        pytest.skip('V3 spatial schema (migration 012) not applied to the disposable test DB')
        return
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


def _seed_spatial(conn, *, systems=None):
    """Seed a canonical_generation + a real {gen}.systems relation + a
    BUILDING spatial_generation. Returns (spatial_generation_id, schema, count).

    Only the columns the builder reads (id64, x_ly, y_ly, z_ly) are
    created on the fixture systems table; the real relation has more, but the
    builder never selects them. NOTE: the canonical systems table's primary key
    column is `id64` (not `system_id64`); the builder reads `id64` and stores it
    into cell_summary.representative_system_id64.
    """
    import uuid
    from psycopg import sql

    gid, run_id = uuid.uuid4(), uuid.uuid4()
    key = 'spx_' + gid.hex[:16]
    schema = 'v3_gen_' + key
    source_id = conn.execute(
        "INSERT INTO v3_source.source(source_code,display_name,authority_class) "
        "VALUES(%s,'Fixture','OPERATOR_ADJUDICATION') RETURNING source_id", (key,),
    ).fetchone()[0]
    rights_id = conn.execute(
        "INSERT INTO v3_source.source_rights_policy(source_id,policy_version,rights_class,retention_class,effective_at) "
        "VALUES(%s,'test','CANONICAL_ELIGIBLE','TEST',now()) RETURNING rights_policy_id", (source_id,),
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
        "VALUES(%s,%s,%s,%s,%s)", (gid, key, schema, b'x' * 32, run_id),
    )
    conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    conn.execute(sql.SQL(
        'CREATE TABLE {}.systems (id64 bigint PRIMARY KEY, '
        'x_ly double precision NOT NULL, y_ly double precision NOT NULL, z_ly double precision NOT NULL)'
    ).format(sql.Identifier(schema)))
    if systems is None:
        systems = [(1001, 10.0, 10.0, 10.0), (1002, 20.0, 20.0, 20.0), (1003, 150.0, 0.0, 0.0)]
    for sid, x, y, z in systems:
        conn.execute(
            sql.SQL('INSERT INTO {}.systems(id64,x_ly,y_ly,z_ly) VALUES(%s,%s,%s,%s)').format(sql.Identifier(schema)),
            (sid, x, y, z),
        )
    sgid = conn.execute(
        "INSERT INTO v3_spatial.spatial_generation(canonical_generation_id,pyramid_version,expected_systems) "
        "VALUES(%s,'pyramid_v1',%s) RETURNING spatial_generation_id", (gid, len(systems)),
    ).fetchone()[0]
    return str(sgid), schema, len(systems)


_TEST_LEVEL = 30
_TEST_SIZE = 100.0


def _register_test_level(conn, version='pyramid_v1'):
    conn.execute(
        "INSERT INTO v3_spatial.cell_level(spatial_pyramid_version,level,cell_size_ly,intended_scale) "
        "VALUES(%s,%s,%s,'test') ON CONFLICT DO NOTHING", (version, _TEST_LEVEL, _TEST_SIZE),
    )


def test_canonical_schema_for_spatial_resolves_schema(db_conn):
    from scripts.v3_spatial_pyramid import canonical_schema_for_spatial
    sgid, schema, _n = _seed_spatial(db_conn)
    assert canonical_schema_for_spatial(db_conn, sgid) == schema


def test_canonical_schema_for_spatial_raises_for_unknown_generation(db_conn):
    import uuid
    from scripts.v3_spatial_pyramid import canonical_schema_for_spatial
    with pytest.raises(ValueError):
        canonical_schema_for_spatial(db_conn, str(uuid.uuid4()))


def test_canonical_system_count_matches_seeded_systems(db_conn):
    from scripts.v3_spatial_pyramid import canonical_system_count
    sgid, _schema, n = _seed_spatial(db_conn)
    assert canonical_system_count(db_conn, sgid) == n


def test_build_level_aggregates_density_and_centroid(db_conn):
    from scripts.v3_spatial_pyramid import build_level
    sgid, _schema, _n = _seed_spatial(db_conn)
    _register_test_level(db_conn)
    n = build_level(db_conn, spatial_generation_id=sgid, version='pyramid_v1',
                    level=_TEST_LEVEL, cell_size_ly=_TEST_SIZE)
    assert n == 2  # (10,10,10)+(20,20,20) share one cell; (150,0,0) is another
    cell = db_conn.execute(
        "SELECT system_count, representative_system_id64, centroid_x_ly "
        "FROM v3_spatial.cell_summary WHERE spatial_generation_id=%s AND cell_key='0.0.0'", (sgid,),
    ).fetchone()
    assert cell[0] == 2
    assert cell[1] == 1001            # nearest the (15,15,15) centroid; tiebreak min id
    assert abs(cell[2] - 15.0) < 1e-9


def test_build_level_representative_prefers_distance_over_id64_tiebreak(db_conn):
    """`representative_system_id64` must be the system nearest the cell's
    data-centroid, not merely the smallest (or largest) id64 in the cell.

    Three systems share one cell (all within [0,100) on every axis, so they
    floor-bucket to '0.0.0'): id64 4001 at x=10, id64 4002 at x=15, id64 4003
    at x=50 (y=z=10 for all three). The data-centroid is x=(10+15+50)/3=25,
    y=10, z=10. Distances along x from the centroid are unambiguous:
    4001 -> 15, 4002 -> 10, 4003 -> 25, so 4002 (the *middle* id64, neither
    the min nor the max of the three) is strictly nearest and must be picked.
    A builder that ignored distance and fell back to min(id64) would wrongly
    return 4001; one that fell back to max(id64) would wrongly return 4003.
    Only genuine distance-to-centroid ordering picks 4002.
    """
    from scripts.v3_spatial_pyramid import build_level
    systems = [(4001, 10.0, 10.0, 10.0), (4002, 15.0, 10.0, 10.0), (4003, 50.0, 10.0, 10.0)]
    sgid, _schema, _n = _seed_spatial(db_conn, systems=systems)
    _register_test_level(db_conn)
    n = build_level(db_conn, spatial_generation_id=sgid, version='pyramid_v1',
                    level=_TEST_LEVEL, cell_size_ly=_TEST_SIZE)
    assert n == 1
    cell = db_conn.execute(
        "SELECT system_count, representative_system_id64, centroid_x_ly "
        "FROM v3_spatial.cell_summary WHERE spatial_generation_id=%s AND cell_key='0.0.0'", (sgid,),
    ).fetchone()
    assert cell[0] == 3
    assert cell[1] == 4002            # nearest the x=25 centroid; not min(id64)=4001, not max(id64)=4003
    assert abs(cell[2] - 25.0) < 1e-9


def test_build_level_handles_negative_coordinates(db_conn):
    """Postgres `floor()` rounds toward negative infinity, so a naive
    truncation-style cell-key computation would silently misbucket negative
    coordinates -- this pins the actual floor-division math for a negative
    origin cell.
    """
    from scripts.v3_spatial_pyramid import build_level
    systems = [(2001, -50.0, -75.0, -25.0), (2002, -10.0, -99.0, -1.0)]
    sgid, _schema, _n = _seed_spatial(db_conn, systems=systems)
    _register_test_level(db_conn)
    n = build_level(db_conn, spatial_generation_id=sgid, version='pyramid_v1',
                    level=_TEST_LEVEL, cell_size_ly=_TEST_SIZE)
    assert n == 1
    cell = db_conn.execute(
        "SELECT system_count, origin_x_ly, origin_y_ly, origin_z_ly, cell_key "
        "FROM v3_spatial.cell_summary WHERE spatial_generation_id=%s", (sgid,),
    ).fetchone()
    assert cell[0] == 2
    assert cell[1] == -100.0
    assert cell[2] == -100.0
    assert cell[3] == -100.0
    assert cell[4] == '-1.-1.-1'


def test_build_level_is_insert_only_and_repeat_raises(db_conn):
    from scripts.v3_spatial_pyramid import build_level
    sgid, _schema, _n = _seed_spatial(db_conn)
    _register_test_level(db_conn)
    build_level(db_conn, spatial_generation_id=sgid, version='pyramid_v1',
                level=_TEST_LEVEL, cell_size_ly=_TEST_SIZE)
    with pytest.raises(psycopg.errors.UniqueViolation):
        build_level(db_conn, spatial_generation_id=sgid, version='pyramid_v1',
                    level=_TEST_LEVEL, cell_size_ly=_TEST_SIZE)
    db_conn.rollback()


def test_build_all_levels_returns_level_to_cell_count(db_conn):
    from scripts.v3_spatial_pyramid import CELL_LEVELS, build_all_levels, register_cell_levels
    sgid, _schema, _n = _seed_spatial(db_conn)
    register_cell_levels(db_conn)
    counts = build_all_levels(db_conn, spatial_generation_id=sgid)
    assert set(counts) == {lvl.level for lvl in CELL_LEVELS}
    # The coarsest registered level (2560ly cells) must merge all three fixture
    # systems (max separation ~150ly) into a single occupied cell.
    coarsest = min(CELL_LEVELS, key=lambda lvl: lvl.level)
    assert counts[coarsest.level] == 1


def test_reconcile_passes_when_sum_matches_canonical(db_conn):
    from scripts.v3_spatial_pyramid import build_level, reconcile, canonical_system_count
    sgid, _schema, n = _seed_spatial(db_conn)
    _register_test_level(db_conn)
    build_level(db_conn, spatial_generation_id=sgid, version='pyramid_v1',
                level=_TEST_LEVEL, cell_size_ly=_TEST_SIZE)
    count = canonical_system_count(db_conn, sgid)
    assert count == n
    result = reconcile(db_conn, spatial_generation_id=sgid, version='pyramid_v1', canonical_count=count)
    assert result['per_level_system_sum'][_TEST_LEVEL] == n


def test_reconcile_fails_closed_on_short_level(db_conn):
    from scripts.v3_spatial_pyramid import build_level, reconcile, ReconciliationError
    sgid, _schema, n = _seed_spatial(db_conn)
    _register_test_level(db_conn)
    build_level(db_conn, spatial_generation_id=sgid, version='pyramid_v1',
                level=_TEST_LEVEL, cell_size_ly=_TEST_SIZE)
    with pytest.raises(ReconciliationError):
        reconcile(db_conn, spatial_generation_id=sgid, version='pyramid_v1', canonical_count=n + 1)


def test_reconcile_raises_when_levels_registered_but_cell_summary_empty(db_conn):
    """Levels ARE registered in `v3_spatial.cell_level` for `version`, but
    nothing was ever built into `cell_summary` for this (generation, version):
    `per_level_system_sum` being empty must raise `ReconciliationError` naming
    the missing levels, not return a vacuously "passed" dict.
    """
    from scripts.v3_spatial_pyramid import reconcile, ReconciliationError
    sgid, _schema, n = _seed_spatial(db_conn)
    _register_test_level(db_conn)
    with pytest.raises(ReconciliationError):
        reconcile(db_conn, spatial_generation_id=sgid, version='pyramid_v1', canonical_count=n)


def test_reconcile_raises_when_version_has_no_registered_levels(db_conn):
    from scripts.v3_spatial_pyramid import reconcile, ReconciliationError
    sgid, _schema, n = _seed_spatial(db_conn)
    with pytest.raises(ReconciliationError):
        reconcile(db_conn, spatial_generation_id=sgid, version='no_such_version', canonical_count=n)


def test_build_receipt_returns_expected_keys_and_sums(db_conn):
    from scripts.v3_spatial_pyramid import build_all_levels, build_receipt, canonical_system_count, register_cell_levels
    sgid, _schema, _n = _seed_spatial(db_conn)
    register_cell_levels(db_conn)
    per_level_cells = build_all_levels(db_conn, spatial_generation_id=sgid)
    count = canonical_system_count(db_conn, sgid)

    receipt = build_receipt(
        db_conn, spatial_generation_id=sgid, version='pyramid_v1',
        canonical_count=count, per_level=per_level_cells,
    )

    assert receipt['spatial_pyramid_version'] == 'pyramid_v1'
    assert receipt['source'] == 'canonical-catalogue'
    assert receipt['canonical_count'] == count
    assert receipt['reconciliation'] == 'passed'
    assert receipt['spatial_generation_id'] == str(sgid)
    assert receipt['coverage_at'] is not None
    assert set(receipt['per_level']) == set(per_level_cells)
    for level, cell_count in per_level_cells.items():
        info = receipt['per_level'][level]
        assert info['cell_count'] == cell_count
        assert info['system_count_sum'] == count
    # No secret-shaped keys/values sneak into the receipt.
    blob = repr(receipt).lower()
    for forbidden in ('password', 'secret', 'token', 'dsn', 'apikey'):
        assert forbidden not in blob


def test_build_receipt_raises_when_reconciliation_fails(db_conn):
    from scripts.v3_spatial_pyramid import build_all_levels, build_receipt, ReconciliationError, register_cell_levels
    sgid, _schema, n = _seed_spatial(db_conn)
    register_cell_levels(db_conn)
    per_level_cells = build_all_levels(db_conn, spatial_generation_id=sgid)
    with pytest.raises(ReconciliationError):
        build_receipt(
            db_conn, spatial_generation_id=sgid, version='pyramid_v1',
            canonical_count=n + 1, per_level=per_level_cells,
        )


def test_build_receipt_raises_for_unknown_generation(db_conn):
    import uuid
    from scripts.v3_spatial_pyramid import build_receipt
    with pytest.raises(ValueError):
        build_receipt(
            db_conn, spatial_generation_id=str(uuid.uuid4()), version='pyramid_v1',
            canonical_count=0, per_level={},
        )


def test_mark_pyramid_ready_transitions_and_is_idempotent(db_conn):
    from scripts.v3_spatial_pyramid import (
        register_cell_levels, build_level, build_receipt, canonical_system_count,
        mark_pyramid_ready,
    )
    sgid, _schema, n = _seed_spatial(db_conn)
    register_cell_levels(db_conn, 'pyramid_v1')
    _register_test_level(db_conn)
    build_level(db_conn, spatial_generation_id=sgid, version='pyramid_v1',
                level=_TEST_LEVEL, cell_size_ly=_TEST_SIZE)
    # Build the real ladder levels too so reconcile's expected set is satisfied.
    from scripts.v3_spatial_pyramid import build_all_levels
    build_all_levels(db_conn, spatial_generation_id=sgid, version='pyramid_v1')
    count = canonical_system_count(db_conn, sgid)
    receipt = build_receipt(db_conn, spatial_generation_id=sgid, version='pyramid_v1',
                            canonical_count=count, per_level={})
    mark_pyramid_ready(db_conn, spatial_generation_id=sgid, version='pyramid_v1', receipt=receipt)
    state = db_conn.execute(
        "SELECT lifecycle_state FROM v3_spatial.spatial_generation WHERE spatial_generation_id=%s", (sgid,),
    ).fetchone()[0]
    assert state == 'READY'
    # idempotent no-op
    mark_pyramid_ready(db_conn, spatial_generation_id=sgid, version='pyramid_v1', receipt=receipt)


def test_mark_pyramid_ready_rejects_unreconciled_receipt(db_conn):
    from scripts.v3_spatial_pyramid import mark_pyramid_ready
    sgid, _schema, _n = _seed_spatial(db_conn)
    with pytest.raises(ValueError):
        mark_pyramid_ready(db_conn, spatial_generation_id=sgid, version='pyramid_v1',
                           receipt={'reconciliation': 'not-run'})
