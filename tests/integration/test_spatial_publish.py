"""Migration 011 publish pointer + CAS function contract, on a disposable DB.

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

os.environ.setdefault('EDFINDER_TEST_DB_ALLOW_DESTRUCTIVE_RESET', 'yes')
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


def _ready_spatial_generation(conn, canonical_id, version='pyramid_v1', expected=1):
    """Insert a spatial_generation and force it READY with a minimal VERIFIED receipt."""
    sgid = conn.execute(
        "INSERT INTO v3_spatial.spatial_generation(canonical_generation_id,pyramid_version,expected_systems) "
        "VALUES(%s,%s,%s) RETURNING spatial_generation_id", (canonical_id, version, expected),
    ).fetchone()[0]
    conn.execute(
        "UPDATE v3_spatial.spatial_generation "
        "SET lifecycle_state='READY',validation_receipt=%s::jsonb,validation_sha256=%s,validated_at=now() "
        "WHERE spatial_generation_id=%s",
        ('{"status":"VERIFIED"}', b'y' * 32, sgid),
    )
    return sgid


def _current_canonical(conn):
    return conn.execute(
        "SELECT generation_id, publication_sequence FROM v3_meta.current_canonical_generation WHERE singleton"
    ).fetchone()


def test_publish_requires_candidate_matches_current_canonical(db_conn):
    """A pyramid whose canonical != the live canonical pointer cannot publish."""
    other = _seed_canonical(db_conn)          # not the current canonical
    sgid = _ready_spatial_generation(db_conn, other)
    cur = _current_canonical(db_conn)
    if cur is None:
        pytest.skip('no current_canonical_generation seeded on this disposable DB')
    cur_ptr = db_conn.execute(
        "SELECT spatial_generation_id, publication_sequence FROM v3_spatial.current_spatial_generation WHERE singleton"
    ).fetchone()
    expected_current = cur_ptr[0] if cur_ptr else None
    expected_sequence = cur_ptr[1] if cur_ptr else 0
    with pytest.raises(psycopg.errors.RaiseException):
        db_conn.execute(
            "SELECT v3_spatial.publish_spatial_pyramid(%s,%s,%s,%s,%s,%s)",
            (sgid, expected_current, expected_sequence, cur[0], 'tester', 'unit test'),
        )


def test_publish_swaps_pointer_and_audits(db_conn):
    cur = _current_canonical(db_conn)
    if cur is None:
        pytest.skip('no current_canonical_generation seeded on this disposable DB')
    # Build a spatial generation for the *live* canonical generation.
    sgid = _ready_spatial_generation(db_conn, cur[0])
    cur_ptr = db_conn.execute(
        "SELECT spatial_generation_id, publication_sequence FROM v3_spatial.current_spatial_generation WHERE singleton"
    ).fetchone()
    expected_current = cur_ptr[0] if cur_ptr else None
    expected_sequence = cur_ptr[1] if cur_ptr else 0
    seq = db_conn.execute(
        "SELECT v3_spatial.publish_spatial_pyramid(%s,%s,%s,%s,%s,%s)",
        (sgid, expected_current, expected_sequence, cur[0], 'tester', 'unit test'),
    ).fetchone()[0]
    assert seq == expected_sequence + 1
    state = db_conn.execute(
        "SELECT lifecycle_state FROM v3_spatial.spatial_generation WHERE spatial_generation_id=%s", (sgid,),
    ).fetchone()[0]
    assert state == 'PUBLISHED'
    ptr = db_conn.execute(
        "SELECT spatial_generation_id FROM v3_spatial.current_spatial_generation WHERE singleton"
    ).fetchone()[0]
    assert str(ptr) == str(sgid)
    audit = db_conn.execute(
        "SELECT actor, reason FROM v3_spatial.spatial_publication_audit WHERE publication_sequence=%s", (seq,),
    ).fetchone()
    assert audit == ('tester', 'unit test')
