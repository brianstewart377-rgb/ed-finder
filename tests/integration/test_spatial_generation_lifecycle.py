"""Migration 011 schema + lifecycle-guard contract, on a disposable DB.

Requires migration 012 already applied to the disposable test database (reset
from the spatial_decouple_tmpl template + psql-apply 011; see the plan's Global
Constraints). Skips when no disposable Postgres is reachable.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import psycopg
import pytest

os.environ.setdefault('CORS_ORIGINS', 'http://testserver')
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from tests.helpers import db_isolation  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _v2_table_shim(v3_fixture_db_ready, v3_v2_table_shim):
    """Session-scoped dependency (body lives in conftest): the V3-only fixture
    DB lacks the V2 tables conftest's ``clean_db`` TRUNCATEs; the shared
    ``v3_v2_table_shim`` fixture creates empty stand-ins. Autouse so the
    TRUNCATE always succeeds for these tests."""


@pytest.fixture
def db_conn():
    target = db_isolation.target_from_env(os.environ)
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


def _seed_canonical(conn) -> uuid.UUID:
    """Minimal canonical_generation chain (no {gen}.systems needed here)."""
    gid, run_id = uuid.uuid4(), uuid.uuid4()
    key = 'spatialtest_' + gid.hex[:16]
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
        "VALUES(%s,%s,%s,%s,%s)", (gid, key, 'v3_gen_' + key, b'x' * 32, run_id),
    )
    return gid


def test_spatial_generation_insert_defaults_building(db_conn):
    gid = _seed_canonical(db_conn)
    sgid = db_conn.execute(
        "INSERT INTO v3_spatial.spatial_generation(canonical_generation_id,pyramid_version,expected_systems) "
        "VALUES(%s,'pyramid_v1',3) RETURNING spatial_generation_id, lifecycle_state",
        (gid,),
    ).fetchone()
    assert sgid[1] == 'BUILDING'


def test_spatial_generation_ready_requires_receipt(db_conn):
    gid = _seed_canonical(db_conn)
    sgid = db_conn.execute(
        "INSERT INTO v3_spatial.spatial_generation(canonical_generation_id,pyramid_version,expected_systems) "
        "VALUES(%s,'pyramid_v1',3) RETURNING spatial_generation_id", (gid,),
    ).fetchone()[0]
    with pytest.raises(psycopg.errors.RaiseException):
        db_conn.execute(
            "UPDATE v3_spatial.spatial_generation SET lifecycle_state='READY' "
            "WHERE spatial_generation_id=%s", (sgid,),
        )


def test_cell_summary_frozen_after_publish(db_conn):
    """Once a spatial_generation leaves BUILDING/VALIDATING/READY, cells are frozen."""
    gid = _seed_canonical(db_conn)
    sgid = db_conn.execute(
        "INSERT INTO v3_spatial.spatial_generation(canonical_generation_id,pyramid_version,expected_systems) "
        "VALUES(%s,'pyramid_v1',1) RETURNING spatial_generation_id", (gid,),
    ).fetchone()[0]
    db_conn.execute(
        "INSERT INTO v3_spatial.cell_level(spatial_pyramid_version,level,cell_size_ly,intended_scale) "
        "VALUES('pyramid_v1',0,2560.0,'wide') ON CONFLICT DO NOTHING",
    )
    db_conn.execute(
        "INSERT INTO v3_spatial.cell_summary(spatial_generation_id,spatial_pyramid_version,level,cell_key,"
        "system_count,representative_system_id64,origin_x_ly,origin_y_ly,origin_z_ly,"
        "centroid_x_ly,centroid_y_ly,centroid_z_ly) "
        "VALUES(%s,'pyramid_v1',0,'0.0.0',1,1001,0,0,0,10,10,10)", (sgid,),
    )
    # Force the generation into RETIRED directly is blocked; simulate a frozen
    # state by marking FAILED (a terminal non-mutable state).
    db_conn.execute(
        "UPDATE v3_spatial.spatial_generation SET lifecycle_state='FAILED',failed_at=now(),failure='test' "
        "WHERE spatial_generation_id=%s", (sgid,),
    )
    with pytest.raises(psycopg.errors.RaiseException):
        db_conn.execute(
            "INSERT INTO v3_spatial.cell_summary(spatial_generation_id,spatial_pyramid_version,level,cell_key,"
            "system_count,representative_system_id64,origin_x_ly,origin_y_ly,origin_z_ly,"
            "centroid_x_ly,centroid_y_ly,centroid_z_ly) "
            "VALUES(%s,'pyramid_v1',0,'9.9.9',1,1002,0,0,0,10,10,10)", (sgid,),
        )
