import os
import sys
import uuid
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse

import pytest


os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', '/dev/null')

ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
if str(IMPORTER_SRC) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SRC))

import station_type_canonical_pilot as pilot  # noqa: E402


ALLOWED_TEST_HOSTS = {'localhost', '127.0.0.1', '::1', 'postgres'}
PRODUCTION_MARKERS = {'prod', 'production', 'live', 'hetzner'}


def test_postgres_rehearsal_applies_only_station_type_and_emits_artifacts(pg_env):
    artifact = pilot.build_station_type_pilot_dry_run(_report_with(_station_candidate()), generated_at='2026-06-01T00:00:00Z')
    checksum = pilot.artifact_sha256(artifact)
    before = _table_counts(pg_env.admin_conn, pg_env.schema)

    conn = pg_env.connect_as(pg_env.canonical_apply_role)
    try:
        _set_search_path(conn, pg_env.schema)
        audit = pilot.apply_station_type_pilot(
            conn,
            artifact,
            artifact_sha256_expected=checksum,
            expected_candidate_count=1,
            approved_table='stations',
            approved_field='station_type',
            approved_source_run='run-1',
            approved_source_file='file-1',
            approval_id='stage18t-test-approval',
            confirmation=True,
            max_rows=1,
            apply_run_id='stage18t-test-apply',
            generated_at='2026-06-01T00:00:00Z',
        )
    finally:
        conn.close()

    station = _station_row(pg_env.admin_conn, pg_env.schema)
    after = _table_counts(pg_env.admin_conn, pg_env.schema)
    assert station == {
        'id': 900001,
        'system_id64': 424242,
        'name': 'Harper Plant',
        'station_type': 'Orbis',
        'distance_from_star': None,
    }
    assert before == after
    assert audit['schema_version'] == 'station_type_canonical_pilot_apply/v1'
    assert audit['summary'] == {
        'planned': 1,
        'applied': 1,
        'skipped': 0,
        'blocked': 0,
        'canonical_table': 'stations',
        'canonical_field': 'station_type',
    }
    assert audit['rows'][0]['field'] == 'station_type'
    assert audit['rollback_preimage']['schema_version'] == 'station_type_canonical_pilot_rollback_preimage/v1'
    assert audit['rollback_preimage']['rows'][0]['pre_image_value'] == 'Unknown'
    assert audit['post_apply_verification']['schema_version'] == 'station_type_canonical_pilot_verification/v1'
    assert audit['post_apply_verification']['summary']['ok'] is True


@pytest.mark.parametrize(
    'db_station_name,db_station_type,expected_message',
    [
        ('Renamed Plant', 'Unknown', 'identity pre-image mismatch'),
        ('Harper Plant', 'Coriolis', 'pre-image mismatch'),
    ],
)
def test_postgres_rehearsal_fails_closed_on_preimage_mismatch(pg_env, db_station_name, db_station_type, expected_message):
    _reset_station(pg_env.admin_conn, pg_env.schema, name=db_station_name, station_type=db_station_type)
    artifact = pilot.build_station_type_pilot_dry_run(_report_with(_station_candidate()), generated_at='2026-06-01T00:00:00Z')
    checksum = pilot.artifact_sha256(artifact)

    conn = pg_env.connect_as(pg_env.canonical_apply_role)
    try:
        _set_search_path(conn, pg_env.schema)
        with pytest.raises(pilot.Stage18JPlanError, match=expected_message):
            pilot.apply_station_type_pilot(
                conn,
                artifact,
                artifact_sha256_expected=checksum,
                expected_candidate_count=1,
                approved_table='stations',
                approved_field='station_type',
                approved_source_run='run-1',
                approval_id='stage18t-test-approval',
                confirmation=True,
                max_rows=1,
            )
    finally:
        conn.close()

    assert _station_row(pg_env.admin_conn, pg_env.schema)['station_type'] == db_station_type


@pytest.mark.parametrize(
    'overrides,expected_message',
    [
        ({'artifact_sha256_expected': 'bad-checksum'}, 'checksum'),
        ({'expected_candidate_count': 2}, 'expected candidate count'),
        ({'approved_table': 'bodies'}, 'approved table'),
        ({'approved_field': 'body_name'}, 'approved field'),
        ({'approved_source_run': 'wrong-run'}, 'approved source run'),
        ({'max_rows': None}, 'max rows'),
    ],
)
def test_postgres_rehearsal_approval_mismatches_fail_before_update(pg_env, overrides, expected_message):
    artifact = pilot.build_station_type_pilot_dry_run(_report_with(_station_candidate()), generated_at='2026-06-01T00:00:00Z')
    checksum = pilot.artifact_sha256(artifact)
    kwargs = {
        'artifact_sha256_expected': checksum,
        'expected_candidate_count': 1,
        'approved_table': 'stations',
        'approved_field': 'station_type',
        'approved_source_run': 'run-1',
        'approval_id': 'stage18t-test-approval',
        'confirmation': True,
        'max_rows': 1,
    }
    kwargs.update(overrides)

    with pytest.raises(pilot.Stage18JPlanError, match=expected_message):
        pilot.validate_apply_request(artifact, **kwargs)

    assert _station_row(pg_env.admin_conn, pg_env.schema)['station_type'] == 'Unknown'


def test_postgres_permission_boundary_roles_are_disposable_and_scoped(pg_env):
    warehouse_conn = pg_env.connect_as(pg_env.warehouse_loader_role)
    try:
        _set_search_path(warehouse_conn, pg_env.schema)
        _assert_forbidden(warehouse_conn, "UPDATE stations SET station_type = 'Orbis' WHERE id = 900001")
        _assert_forbidden(warehouse_conn, "INSERT INTO systems (id64, name) VALUES (42, 'Forbidden')")
        _assert_forbidden(warehouse_conn, "UPDATE bodies SET name = 'Forbidden' WHERE id = 1")
        _assert_forbidden(warehouse_conn, "DELETE FROM station_body_links WHERE station_id = 900001")
        _assert_forbidden(warehouse_conn, "UPDATE body_rings SET ring_name = 'Forbidden' WHERE id = 1")
        _assert_forbidden(warehouse_conn, "UPDATE body_scan_facts SET is_ringed = true WHERE body_id = 1")
    finally:
        warehouse_conn.close()

    apply_conn = pg_env.connect_as(pg_env.canonical_apply_role)
    try:
        _set_search_path(apply_conn, pg_env.schema)
        with apply_conn.cursor() as cur:
            cur.execute("UPDATE stations SET station_type = 'Orbis' WHERE id = 900001")
        apply_conn.rollback()
        _assert_forbidden(apply_conn, "UPDATE stations SET name = 'Forbidden' WHERE id = 900001")
        _assert_forbidden(apply_conn, "UPDATE stations SET distance_from_star = 10 WHERE id = 900001")
        _assert_forbidden(apply_conn, "UPDATE systems SET name = 'Forbidden' WHERE id64 = 424242")
        _assert_forbidden(apply_conn, "UPDATE bodies SET name = 'Forbidden' WHERE id = 1")
        _assert_forbidden(apply_conn, "UPDATE station_body_links SET body_name = 'Forbidden' WHERE station_id = 900001")
        _assert_forbidden(apply_conn, "UPDATE body_rings SET ring_name = 'Forbidden' WHERE id = 1")
        _assert_forbidden(apply_conn, "UPDATE body_scan_facts SET is_ringed = true WHERE body_id = 1")
    finally:
        apply_conn.close()


@pytest.fixture
def pg_env():
    psycopg2 = pytest.importorskip('psycopg2')
    from psycopg2 import sql

    dsn = _canonical_test_dsn_or_skip()
    token = uuid.uuid4().hex[:12]
    schema = f'stage18t_{token}'
    warehouse_loader_role = f'warehouse_loader_test_{token}'
    canonical_apply_role = f'canonical_apply_test_{token}'
    canonical_read_role = f'canonical_read_test_{token}'
    admin_conn = psycopg2.connect(dsn)
    admin_conn.autocommit = True
    env = _PgEnv(
        psycopg2=psycopg2,
        dsn=dsn,
        admin_conn=admin_conn,
        schema=schema,
        warehouse_loader_role=warehouse_loader_role,
        canonical_apply_role=canonical_apply_role,
        canonical_read_role=canonical_read_role,
        role_password=f'stage18t_{token}',
    )
    try:
        with admin_conn.cursor() as cur:
            _create_schema(cur, sql, env)
        yield env
    finally:
        with admin_conn.cursor() as cur:
            cur.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
            for role in (warehouse_loader_role, canonical_apply_role, canonical_read_role):
                cur.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(role)))
        admin_conn.close()


class _PgEnv:
    def __init__(
        self,
        *,
        psycopg2,
        dsn,
        admin_conn,
        schema,
        warehouse_loader_role,
        canonical_apply_role,
        canonical_read_role,
        role_password,
    ):
        self.psycopg2 = psycopg2
        self.dsn = dsn
        self.admin_conn = admin_conn
        self.schema = schema
        self.warehouse_loader_role = warehouse_loader_role
        self.canonical_apply_role = canonical_apply_role
        self.canonical_read_role = canonical_read_role
        self.role_password = role_password

    def connect_as(self, role):
        conn = self.psycopg2.connect(self.dsn, user=role, password=self.role_password)
        conn.autocommit = False
        return conn


def _canonical_test_dsn_or_skip():
    dsn = os.getenv('EDFINDER_CANONICAL_TEST_DSN')
    confirm = os.getenv('EDFINDER_CONFIRM_CANONICAL_TEST_DB')
    if not dsn:
        pytest.skip('EDFINDER_CANONICAL_TEST_DSN is not set; skipping disposable canonical Postgres rehearsal')
    if confirm != 'yes':
        pytest.skip('EDFINDER_CONFIRM_CANONICAL_TEST_DB must be exactly yes for disposable canonical Postgres rehearsal')
    _assert_safe_test_dsn(dsn)
    return dsn


def _assert_safe_test_dsn(dsn):
    parsed = urlparse(dsn)
    if parsed.scheme:
        host = parsed.hostname
        dbname = parsed.path.lstrip('/')
    else:
        parts = dict(part.split('=', 1) for part in dsn.split() if '=' in part)
        host = parts.get('host')
        dbname = parts.get('dbname')
    if host not in ALLOWED_TEST_HOSTS:
        pytest.fail(f'Unsafe canonical test DSN host {host!r}; expected local disposable host')
    haystack = f'{dsn} {dbname or ""}'.lower()
    if any(marker in haystack for marker in PRODUCTION_MARKERS):
        pytest.fail('Unsafe canonical test DSN contains production-like marker')
    if not dbname:
        pytest.fail('Unsafe canonical test DSN has no database name')


def _create_schema(cur, sql, env):
    cur.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(env.schema)))
    cur.execute(
        sql.SQL(
            "CREATE TYPE {} AS ENUM "
            "('Coriolis', 'Orbis', 'Ocellus', 'Outpost', 'PlanetaryPort', "
            "'PlanetaryOutpost', 'MegaShip', 'AsteroidBase', 'FleetCarrier', 'Unknown')"
        ).format(sql.Identifier(env.schema, 'station_type'))
    )
    cur.execute(sql.SQL('CREATE TABLE {} (id64 BIGINT PRIMARY KEY, name TEXT NOT NULL)').format(sql.Identifier(env.schema, 'systems')))
    cur.execute(
        sql.SQL(
            'CREATE TABLE {} ('
            'id BIGINT PRIMARY KEY, '
            'system_id64 BIGINT NOT NULL, '
            'name TEXT NOT NULL, '
            'station_type {} NOT NULL DEFAULT \'Unknown\', '
            'distance_from_star REAL DEFAULT NULL)'
        ).format(sql.Identifier(env.schema, 'stations'), sql.Identifier(env.schema, 'station_type'))
    )
    cur.execute(sql.SQL('CREATE TABLE {} (id BIGINT PRIMARY KEY, system_id64 BIGINT, name TEXT)').format(sql.Identifier(env.schema, 'bodies')))
    cur.execute(sql.SQL('CREATE TABLE {} (station_id BIGINT PRIMARY KEY, body_name TEXT)').format(sql.Identifier(env.schema, 'station_body_links')))
    cur.execute(sql.SQL('CREATE TABLE {} (id BIGINT PRIMARY KEY, ring_name TEXT)').format(sql.Identifier(env.schema, 'body_rings')))
    cur.execute(sql.SQL('CREATE TABLE {} (body_id BIGINT PRIMARY KEY, is_ringed BOOLEAN)').format(sql.Identifier(env.schema, 'body_scan_facts')))
    cur.execute(sql.SQL('INSERT INTO {} (id64, name) VALUES (424242, %s)').format(sql.Identifier(env.schema, 'systems')), ('Test System',))
    cur.execute(
        sql.SQL('INSERT INTO {} (id, system_id64, name, station_type) VALUES (900001, 424242, %s, %s)').format(
            sql.Identifier(env.schema, 'stations')
        ),
        ('Harper Plant', 'Unknown'),
    )
    cur.execute(sql.SQL('INSERT INTO {} (id, system_id64, name) VALUES (1, 424242, %s)').format(sql.Identifier(env.schema, 'bodies')), ('Test 1',))
    cur.execute(sql.SQL('INSERT INTO {} (station_id, body_name) VALUES (900001, %s)').format(sql.Identifier(env.schema, 'station_body_links')), ('Test 1',))
    cur.execute(sql.SQL('INSERT INTO {} (id, ring_name) VALUES (1, %s)').format(sql.Identifier(env.schema, 'body_rings')), ('Test Ring',))
    cur.execute(sql.SQL('INSERT INTO {} (body_id, is_ringed) VALUES (1, false)').format(sql.Identifier(env.schema, 'body_scan_facts')))
    for role in (env.warehouse_loader_role, env.canonical_apply_role, env.canonical_read_role):
        cur.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD %s').format(sql.Identifier(role)), (env.role_password,))
        cur.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO {}').format(sql.Identifier(env.schema), sql.Identifier(role)))
        cur.execute(sql.SQL('GRANT USAGE ON TYPE {} TO {}').format(sql.Identifier(env.schema, 'station_type'), sql.Identifier(role)))
        for table in ('systems', 'stations', 'bodies', 'station_body_links', 'body_rings', 'body_scan_facts'):
            cur.execute(sql.SQL('GRANT SELECT ON {} TO {}').format(sql.Identifier(env.schema, table), sql.Identifier(role)))
    cur.execute(sql.SQL('GRANT UPDATE (station_type) ON {} TO {}').format(sql.Identifier(env.schema, 'stations'), sql.Identifier(env.canonical_apply_role)))


def _set_search_path(conn, schema):
    from psycopg2 import sql

    with conn.cursor() as cur:
        cur.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))


def _reset_station(conn, schema, *, name='Harper Plant', station_type='Unknown'):
    from psycopg2 import sql

    with conn.cursor() as cur:
        cur.execute(
            sql.SQL('UPDATE {} SET name = %s, station_type = %s, distance_from_star = NULL WHERE id = 900001').format(
                sql.Identifier(schema, 'stations')
            ),
            (name, station_type),
        )


def _station_row(conn, schema):
    from psycopg2 import sql

    with conn.cursor() as cur:
        cur.execute(
            sql.SQL('SELECT id, system_id64, name, station_type::text, distance_from_star FROM {} WHERE id = 900001').format(
                sql.Identifier(schema, 'stations')
            )
        )
        row = cur.fetchone()
    return {
        'id': row[0],
        'system_id64': row[1],
        'name': row[2],
        'station_type': row[3],
        'distance_from_star': row[4],
    }


def _table_counts(conn, schema):
    from psycopg2 import sql

    counts = {}
    with conn.cursor() as cur:
        for table in ('systems', 'stations', 'bodies', 'station_body_links', 'body_rings', 'body_scan_facts'):
            cur.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(schema, table)))
            counts[table] = cur.fetchone()[0]
    return counts


def _assert_forbidden(conn, statement):
    with pytest.raises(Exception):
        with conn.cursor() as cur:
            cur.execute(statement)
    conn.rollback()


def _report_with(*candidates):
    return {
        'schema_version': 'enrichment_staging_reconciliation/v1',
        'dry_run': True,
        'filters': {
            'source_run_key': 'run-1',
            'source_file_key': 'file-1',
            'source': 'edsm_nightly_stations',
        },
        'summary': {'canonical_writes_planned': 0},
        'station_candidates': list(candidates),
    }


def _station_candidate():
    return {
        'entity': 'station',
        'candidate_action': 'candidate_update',
        'source': {
            'source_run_key': 'run-1',
            'source_file_key': 'file-1',
            'source_record_key': 'record-1',
            'source_record_hash': 'hash-1',
            'system_id64': 424242,
            'system_name': 'Test System',
            'market_id': 1001,
            'edsm_station_id': None,
            'station_name': 'Harper Plant',
            'source_class': 'semi-stable',
            'confidence': 'source_station_snapshot',
            'freshness_class': 'source_updated_at',
            'source_updated_at': '2026-05-31T12:00:00Z',
        },
        'canonical': {
            'system_id64': 424242,
            'system_name': 'Test System',
            'station_id': 900001,
            'market_id': 1001,
            'edsm_station_id': None,
            'station_name': 'Harper Plant',
            'station_type': 'Unknown',
        },
        'canonical_matches': [{
            'system_id64': 424242,
            'system_name': 'Test System',
            'station_id': 900001,
            'market_id': 1001,
            'edsm_station_id': None,
            'station_name': 'Harper Plant',
            'station_type': 'Unknown',
        }],
        'differences': [{'field': 'station_type', 'staged': 'Orbis Starport', 'canonical': 'Unknown'}],
        'warnings': [],
        'confidence': 'high',
        'risk_class': 'clear',
        'risk_flags': [],
        'review_classifications': [],
        'reconciliation_state': 'confirmed',
        'source_freshness': {
            'freshness_class': 'source_updated_at',
            'source_updated_at': '2026-05-31T12:00:00Z',
            'freshness_impact': 'timestamped_source',
        },
        'report_only': False,
        'canonical_writes_planned': 0,
    }
