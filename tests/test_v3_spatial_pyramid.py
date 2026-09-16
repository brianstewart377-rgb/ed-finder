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


def _seed_generation(conn) -> str:
    """Seed the minimal `v3_meta.canonical_generation` -> `v3_meta.derived_generation`
    chain plus three `v3_derived.system_search` rows with known coordinates and aux
    flags, entirely inside the caller's (rolled-back) transaction.

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
    import json
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
