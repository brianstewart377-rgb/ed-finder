"""Governed purge capability on disposable PostgreSQL 18, never production.

The canonical_database import also makes CI's PG18 discovery select this file.
Roles are cluster objects: serialize their lifecycle and remove only roles this
fixture created, before the randomly named disposable database is dropped.
"""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from time import monotonic, sleep
from unittest.mock import patch
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.types.json import Jsonb
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ratings_v4.canonical_stream import CanonicalSnapshot  # noqa: E402
from scripts.ratings_v4.production_generation import (  # noqa: E402
    create_generation, seal_source, validate_generation, write_chunk,
)
from scripts.v3_system_search import (  # noqa: E402
    build_available, register_product,
)
from tests.ratings_v4_pg_fixture import canonical_database  # noqa: E402

MIGRATIONS = ROOT / 'sql/v3/migrations'
CHAIN = (
    '003_ratings_v4_derived.sql',
    '004_v3_search_spatial_clusters.sql',
    '006_v3_derived_product_lifecycle.sql',
    '010_v3_system_search_body_type_counts.sql',
    '011_v3_system_archetype.sql',
    '012_v3_spatial_pyramid_decouple.sql',
    '013_v3_system_search_parallel.sql',
    '015_v3_derived_product_publication.sql',
)
PURGE_MIGRATION = '016_v3_governed_derived_purge.sql'
EXECUTOR = 'v3_derived_purge_executor'
APPLICATION = 'edfinder_v3'
TARGETS = (
    ('ratings_v4_prod_p4', UUID('49a0c00d-e722-4209-afd8-9d62b877e30a')),
    ('ratings_v4_prod_p4_opt1', UUID('403b2d43-820c-414a-ad57-0d4de0ca3e82')),
)
SURVIVOR = UUID('cfc25d36-3bc7-4011-a465-d6460eaaf826')
RELATIONS = ('system_search', 'economy_opportunity', 'body_mechanics', 'system_rating_vector')
RETAINED = (
    'v3_meta.derived_generation', 'v3_meta.derived_product',
    'v3_meta.derived_publication_audit', 'v3_meta.derived_product_publication_audit',
    'v3_derived.build_chunk', 'v3_derived.search_build_chunk',
    'v3_derived.archetype_build_chunk', 'v3_meta.search_rebuild_plan',
    'v3_meta.search_rebuild_range', 'v3_meta.schema_migration',
)
EVENT_KINDS = {
    'AUTHORIZED', 'BATCH_COMMITTED', 'RELATION_LOGICALLY_EMPTY',
    'REWRITE_STARTED', 'REWRITE_VERIFIED', 'COMPLETED', 'FAILED_STOP',
    'BATCH_STARTED', 'BATCH_ROLLED_BACK', 'REWRITE_ROLLED_BACK',
    'SERVICES_QUIESCED', 'SERVICES_RESTORED', 'AUTOVACUUM_DISABLED',
    'AUTOVACUUM_RESTORED', 'WRITER_FENCE_ENABLED', 'WRITER_FENCE_RESTORED',
    'REWRITE_CANCEL_REQUESTED', 'BATCH_CANCEL_REQUESTED',
}


@contextmanager
def installed_purge(connection, *, creator='superuser', apply_chain=False, application_present=True):
    """Install 016 while owning the entire lifecycle of its test-only roles."""
    assert connection.info.server_version >= 180000, 'purge validation requires PostgreSQL 18'
    base_dsn = os.environ['RATINGS_V4_VALIDATION_DATABASE_URL']
    cleanup_dsn = make_conninfo(base_dsn, dbname=connection.info.dbname)
    lock_connection = psycopg.connect(base_dsn, autocommit=True)
    lock_connection.execute('SELECT pg_advisory_lock(764016099)')
    created_application = False
    executor_was_absent = False
    application_connection = None
    try:
        assert connection.execute(
            'SELECT rolsuper FROM pg_roles WHERE rolname=current_user',
        ).fetchone()[0], 'the disposable PG18 fixture must be administered by its test superuser'
        for name in (APPLICATION, EXECUTOR):
            assert not connection.execute(
                'SELECT 1 FROM pg_roles WHERE rolname=%s', (name,),
            ).fetchone(), f'test refuses to adopt existing cluster role {name}'
        executor_was_absent = True
        if application_present:
            connection.execute('CREATE ROLE edfinder_v3 LOGIN CREATEROLE')
            created_application = True
        if creator == 'non_superuser':
            assert application_present
            database_name = connection.execute('SELECT current_database()').fetchone()[0]
            connection.execute(sql.SQL('GRANT CREATE ON DATABASE {} TO edfinder_v3').format(
                sql.Identifier(database_name),
            ))
            for schema_name, in connection.execute(
                "SELECT nspname FROM pg_namespace WHERE nspname LIKE 'v3_%'",
            ).fetchall():
                connection.execute(sql.SQL('GRANT ALL ON SCHEMA {} TO edfinder_v3 WITH GRANT OPTION').format(
                    sql.Identifier(schema_name),
                ))
                connection.execute(sql.SQL('GRANT ALL ON ALL TABLES IN SCHEMA {} TO edfinder_v3 WITH GRANT OPTION').format(
                    sql.Identifier(schema_name),
                ))
            # Change session authorization as well: SET ROLE executor must be
            # checked against the non-superuser creator's new membership, not
            # the test administrator's superuser ability to assume any role.
            connection.execute('SET SESSION AUTHORIZATION edfinder_v3')
        if apply_chain:
            for name in CHAIN:
                connection.execute((MIGRATIONS / name).read_text())
        else:
            for name in ('012_v3_spatial_pyramid_decouple.sql', '013_v3_system_search_parallel.sql'):
                connection.execute((MIGRATIONS / name).read_text())
        connection.execute((MIGRATIONS / PURGE_MIGRATION).read_text())
        if creator == 'non_superuser':
            test_password = uuid4().hex
            connection.execute(sql.SQL('ALTER ROLE edfinder_v3 PASSWORD {}').format(sql.Literal(test_password)))
            application_connection = psycopg.connect(
                make_conninfo(cleanup_dsn, user=APPLICATION, password=test_password), autocommit=True,
            )
            # pg_stat_activity records the authenticated login. Close the
            # setup connection so the app owner sees no opaque administrator
            # session beside the real application-role test connections.
            connection.close()
            connection = application_connection
        yield connection
    finally:
        if application_connection is not None:
            application_connection.close()
            connection = psycopg.connect(cleanup_dsn, autocommit=True)
        try:
            connection.rollback()
            connection.execute('RESET SESSION AUTHORIZATION')
            connection.execute('RESET ROLE')
            for name in (EXECUTOR, APPLICATION):
                exists = connection.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (name,)).fetchone()
                if exists and ((name == EXECUTOR and executor_was_absent) or
                               (name == APPLICATION and created_application)):
                    connection.execute(sql.SQL('DROP OWNED BY {} CASCADE').format(sql.Identifier(name)))
                    connection.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(name)))
        finally:
            if application_connection is not None:
                connection.close()
            lock_connection.execute('SELECT pg_advisory_unlock(764016099)')
            lock_connection.close()


@pytest.fixture(params=('superuser', 'non_superuser'))
def database(request):
    with canonical_database() as data:
        connection = data[0]
        with installed_purge(connection, creator=request.param, apply_chain=True) as installed:
            yield (installed, *data[1:])


def test_fresh_superuser_manifest_install_does_not_require_the_production_application_role():
    with canonical_database() as data:
        connection = data[0]
        with installed_purge(connection, apply_chain=True, application_present=False):
            assert connection.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (APPLICATION,)).fetchone() is None
            assert connection.execute('SELECT rolcanlogin FROM pg_roles WHERE rolname=%s', (EXECUTOR,)).fetchone() == (False,)
            assert connection.execute(
                "SELECT to_regclass('v3_meta.derived_generation_purge_request') IS NOT NULL",
            ).fetchone()[0]


def _count(connection, relation, generation_id=None):
    statement = sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(*relation.split('.')))
    if generation_id is not None:
        statement += sql.SQL(' WHERE derived_generation_id=%s')
        return connection.execute(statement, (generation_id,)).fetchone()[0]
    return connection.execute(statement).fetchone()[0]


def _eof(data):
    _, canonical, metadata, _ = data
    return {
        'consumed_to_eof': True,
        'artifact_sha256': metadata['artifact']['content_sha256'].removeprefix('\\x'),
        'size_bytes': metadata['artifact']['size_bytes'],
        'systems': len(canonical['systems']), 'bodies': len(canonical['bodies']),
    }


def _seed(data, *, survivor_search_built=True):
    connection, _, _, payloads = data
    snapshot = CanonicalSnapshot.pin(connection)
    records = [payload['system'] for payload in payloads]
    canonical = snapshot.export_chunk(connection, [record['id64'] for record in records])
    for key, identifier in (*TARGETS, ('ratings_v4_prod_p4_parallel_v1', SURVIVOR)):
        with patch('scripts.ratings_v4.production_generation.uuid4', return_value=identifier):
            assert create_generation(connection, snapshot, key) == identifier
        assert write_chunk(connection, identifier, 0, canonical, snapshot.metadata, records)
        generation, _, manifest_hash = register_product(connection, key)
        if identifier != SURVIVOR or survivor_search_built:
            assert build_available(connection, generation, manifest_hash)['chunks_written'] == 1
        if identifier != TARGETS[0][1]:
            seal_source(connection, identifier, _eof(data))
        if identifier == SURVIVOR:
            assert validate_generation(connection, identifier)['status'] == 'VERIFIED'
            assert connection.execute(
                'SELECT v3_meta.publish_derived_generation(%s,%s,%s,%s,%s,%s,%s,%s)',
                (identifier, None, 0, snapshot.generation_id, snapshot.publication_sequence,
                 'fixture', 'published survivor', []),
            ).fetchone()[0] == 1
    spatial = uuid4()
    connection.execute(
        '''INSERT INTO v3_spatial.spatial_generation(
               spatial_generation_id,canonical_generation_id,pyramid_version,expected_systems)
           VALUES (%s,%s,'purge_test',%s)''',
        (spatial, snapshot.generation_id, len(records)),
    )
    connection.execute(
        '''UPDATE v3_spatial.spatial_generation
              SET lifecycle_state='READY',validation_receipt='{"status":"VERIFIED"}',
                  validation_sha256=%s,validated_at=now()
            WHERE spatial_generation_id=%s''', (b'v' * 32, spatial),
    )
    connection.execute(
        'SELECT v3_spatial.publish_spatial_pyramid(%s,NULL,0,%s,%s,%s)',
        (spatial, snapshot.generation_id, 'fixture', 'published spatial survivor'),
    )


def _plan(connection):
    targets = [dict(zip(('id', 'key', 'manifest_sha256', 'state'), row, strict=True))
               for row in connection.execute(
                   '''SELECT derived_generation_id::text,generation_key,
                             encode(manifest_sha256,'hex'),lifecycle_state
                      FROM v3_meta.derived_generation
                      WHERE generation_key IN ('ratings_v4_prod_p4','ratings_v4_prod_p4_opt1')
                      ORDER BY generation_key''',
               ).fetchall()]
    for target in targets:
        target['payload_counts'] = {name: _count(connection, 'v3_derived.' + name, target['id'])
                                    for name in RELATIONS}
    plan = {
        'workers_stopped': True,
        'snapshot': connection.execute('SELECT v3_meta.purge_snapshot()').fetchone()[0],
        'plan_sha256': 'a' * 64, 'source_git_sha': 'b' * 40,
        'actor': 'disposable-fixture', 'reason': 'owner-approved purge capability validation',
        'targets': targets,
        'autovacuum': {name: {
            'xid_ceiling': 100_000_000, 'mxid_ceiling': 100_000_000,
            'xid_rate': 0, 'mxid_rate': 0, 'remaining_seconds': 3600,
        } for name in RELATIONS},
    }
    return _sign_plan(connection, plan)


def _sign_plan(connection, plan):
    plan['plan_sha256'] = connection.execute(
        "SELECT encode(sha256(convert_to((%s::jsonb-'plan_sha256')::text,'UTF8')),'hex')",
        (Jsonb(plan),),
    ).fetchone()[0]
    return plan


def _authorize(data, **seed_options):
    _seed(data, **seed_options)
    connection = data[0]
    plan = _plan(connection)
    connection.execute('SET ROLE v3_derived_purge_executor')
    ids = connection.execute('SELECT v3_meta.begin_derived_generation_purge(%s)',
                             (Jsonb(plan),)).fetchone()[0]
    return dict(zip((UUID(target['id']) for target in plan['targets']), ids, strict=True))


def _receipt():
    return {
        'filesystem_free_bytes': 200_000_000_000, 'wal_bytes': 0, 'receipt_sha256': 'c' * 64,
        'batch_peak_bytes': 1_000_000, 'wal_healthy': True, 'wal_same_filesystem': True,
        'rewrite_peak_bytes': 1_000_000,
        'workers_stopped': True, 'observed_at': datetime.now(timezone.utc).isoformat(),
    }


def _writer_fence(connection, purge_id):
    connection.execute('SELECT v3_meta.purge_set_writer_fence(%s,true)', (purge_id,))
    connection.execute('SELECT v3_meta.purge_recycle_writer_sessions(%s,true)', (purge_id,))
    connection.execute('SELECT v3_meta.purge_verify_writer_fence(%s,true,%s)', (purge_id, 'on'))


def _start_batch(connection, purge_id, relation, size=100_000, evidence=None):
    return connection.execute('SELECT v3_meta.purge_start_payload_batch(%s,%s,%s,%s)',
                              (purge_id, relation, size, Jsonb(evidence or _receipt()))).fetchone()[0]


def _batch(connection, purge_id, relation, size=100_000):
    _start_batch(connection, purge_id, relation, size)
    return connection.execute('SELECT v3_meta.purge_derived_payload_batch(%s,%s,%s)',
                              (purge_id, relation, size)).fetchone()[0]


def _abort_autovacuum_fence(connection, purge_id, relation):
    relation_bytes = connection.execute('SELECT pg_total_relation_size(%s::regclass)',
                                       ('v3_derived.' + relation,)).fetchone()[0]
    evidence = {**_receipt(), 'aborted': True, 'autovacuum_budget_bytes': relation_bytes}
    connection.execute('SELECT v3_meta.purge_record_event(%s,%s,%s,%s)',
                       (purge_id, 'FAILED_STOP', relation, Jsonb(evidence)))
    connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,true)', (purge_id, relation))


@contextmanager
def _application_worker(connection):
    connection.execute('RESET ROLE')
    test_password = uuid4().hex
    connection.execute(sql.SQL('ALTER ROLE edfinder_v3 PASSWORD {}').format(sql.Literal(test_password)))
    if connection.execute('SELECT rolsuper FROM pg_roles WHERE rolname=current_user').fetchone()[0]:
        connection.execute('GRANT v3_derived_purge_executor TO edfinder_v3 WITH SET TRUE, INHERIT FALSE')
    app_dsn = make_conninfo(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL'],
                           dbname=connection.info.dbname, user=APPLICATION, password=test_password)
    connection.execute('SET ROLE v3_derived_purge_executor')
    with psycopg.connect(app_dsn, autocommit=True) as worker:
        worker.execute('SET ROLE v3_derived_purge_executor')
        worker.execute('SET default_transaction_read_only=off')
        yield worker


def _wait_for_database_operation(connection, worker, future, kind):
    deadline = monotonic() + 10
    while monotonic() < deadline:
        if future.done():
            future.result()
            pytest.fail('test operation completed before its cancellation could be observed')
        statement = {
            'batch': '''SELECT EXISTS(SELECT 1 FROM pg_stat_activity a JOIN pg_locks l ON l.pid=a.pid
                WHERE a.pid=%s AND a.state='active' AND a.wait_event='PgSleep'
                  AND l.relation='v3_derived.system_search'::regclass
                  AND l.mode='RowExclusiveLock' AND l.granted)''',
            'rewrite': 'SELECT EXISTS(SELECT 1 FROM pg_stat_progress_cluster WHERE pid=%s)',
            'analyze': 'SELECT EXISTS(SELECT 1 FROM pg_stat_progress_analyze WHERE pid=%s)',
            'vacuum': 'SELECT EXISTS(SELECT 1 FROM pg_stat_progress_vacuum WHERE pid=%s)',
        }[kind]
        if connection.execute(statement, (worker.info.backend_pid,)).fetchone()[0]:
            return
        sleep(0.01)
    worker.cancel()
    pytest.fail('test operation never entered the authenticated cancellation state')


def test_authorization_is_atomic_and_records_both_original_states(database):
    connection = database[0]
    ids = _authorize(database)
    assert set(ids) == {identifier for _, identifier in TARGETS}
    assert connection.execute(
        '''SELECT generation_key,lifecycle_state,failure IS NOT NULL,failed_at IS NOT NULL
           FROM v3_meta.derived_generation WHERE derived_generation_id=ANY(%s)
           ORDER BY generation_key''', (list(ids),),
    ).fetchall() == [(key, 'FAILED', True, True) for key, _ in TARGETS]
    assert connection.execute(
        'SELECT original_state FROM v3_meta.derived_generation_purge_request ORDER BY generation_key',
    ).fetchall() == [('BUILDING',), ('VALIDATING',)]
    assert connection.execute(
        "SELECT count(*) FROM v3_meta.derived_generation_purge_event WHERE event_kind='AUTHORIZED'",
    ).fetchone()[0] == 2
    assert _count(connection, 'v3_derived.system_rating_vector', SURVIVOR) == 12
    # Reusing the reviewed authorization does not create another tombstone.
    with pytest.raises(psycopg.Error):
        with connection.transaction():
            connection.execute('SELECT v3_meta.begin_derived_generation_purge(%s)', (Jsonb(_plan(connection)),))
    assert _count(connection, 'v3_meta.derived_generation_purge_request') == 2


@pytest.mark.parametrize('fault', (
    'wrong_uuid', 'wrong_key', 'wrong_manifest', 'wrong_state', 'wrong_plan_hash',
    'missing_workers', 'workers_running', 'workers_unknown', 'canonical_drift',
    'derived_drift', 'spatial_drift', 'target_current', 'target_published', 'receipt_failure',
))
def test_authorization_rejects_stale_or_unauthenticated_plan_without_changes(database, fault):
    connection = database[0]
    _seed(database)
    plan = _plan(connection)
    if fault.startswith('wrong_'):
        field, value = {
            'wrong_uuid': ('id', str(uuid4())), 'wrong_key': ('key', 'unauthorized_generation'),
            'wrong_manifest': ('manifest_sha256', '0' * 64), 'wrong_state': ('state', 'READY'),
            'wrong_plan_hash': ('plan_sha256', '0' * 64),
        }[fault]
        (plan if field == 'plan_sha256' else plan['targets'][0])[field] = value
    elif fault == 'missing_workers':
        del plan['workers_stopped']
    elif fault.startswith('workers_'):
        plan['workers_stopped'] = False if fault == 'workers_running' else None
    elif fault.endswith('_drift'):
        plan['snapshot'][fault.removesuffix('_drift')]['publication_sequence'] += 1
    elif fault == 'target_current':
        with pytest.raises(psycopg.Error):
            with connection.transaction():
                connection.execute(
                    'UPDATE v3_meta.current_derived_generation SET derived_generation_id=%s', (TARGETS[0][1],),
                )
        plan['snapshot']['derived']['derived_generation_id'] = str(TARGETS[0][1])
    elif fault == 'target_published':
        connection.execute(
            '''INSERT INTO v3_meta.derived_publication_audit(
                   publication_sequence,to_generation_id,canonical_generation_id,actor,reason)
               VALUES(2,%s,%s,'fixture','prove historical publication refusal')''',
            (TARGETS[0][1], plan['snapshot']['canonical']['generation_id']),
        )
        plan['snapshot'] = connection.execute('SELECT v3_meta.purge_snapshot()').fetchone()[0]
    elif fault == 'receipt_failure':
        connection.execute(
            "ALTER TABLE v3_meta.derived_generation_purge_event ADD CONSTRAINT injected_authorization_failure CHECK (event_kind<>'AUTHORIZED')",
        )
    if fault != 'wrong_plan_hash':
        _sign_plan(connection, plan)
    before = {relation: _count(connection, relation) for relation in RETAINED}
    connection.execute('SET ROLE v3_derived_purge_executor')
    with pytest.raises(psycopg.Error):
        with connection.transaction():
            connection.execute('SELECT v3_meta.begin_derived_generation_purge(%s)', (Jsonb(plan),))
    assert {relation: _count(connection, relation) for relation in RETAINED} == before
    assert _count(connection, 'v3_meta.derived_generation_purge_request') == 0
    assert _count(connection, 'v3_meta.derived_generation_purge_event') == 0
    assert connection.execute(
        '''SELECT lifecycle_state FROM v3_meta.derived_generation
           WHERE generation_key IN ('ratings_v4_prod_p4','ratings_v4_prod_p4_opt1')
           ORDER BY generation_key''',
    ).fetchall() == [('BUILDING',), ('VALIDATING',)]


@pytest.mark.parametrize('relation', ('derived_generation_purge_request', 'derived_generation_purge_event'))
@pytest.mark.parametrize('operation', ('UPDATE', 'DELETE', 'TRUNCATE'))
def test_request_and_events_are_append_only_even_for_the_owner(database, relation, operation):
    connection = database[0]
    _authorize(database)
    connection.execute('RESET ROLE')
    statement = {
        'UPDATE': sql.SQL('UPDATE v3_meta.{} SET purge_id=purge_id'),
        'DELETE': sql.SQL('DELETE FROM v3_meta.{}'),
        'TRUNCATE': sql.SQL('TRUNCATE v3_meta.{}'),
    }[operation].format(sql.Identifier(relation))
    # PostgreSQL may reject TRUNCATE of the referenced request table during
    # its FK precheck, before invoking the independently installed deny trigger.
    error = psycopg.Error if operation == 'TRUNCATE' and relation.endswith('_request') else psycopg.errors.RaiseException
    with pytest.raises(error):
        with connection.transaction():
            connection.execute(statement)


@pytest.mark.parametrize('prior', (None, 'false'))
def test_autovacuum_fence_restores_exact_heap_and_toast_prior_options(database, prior):
    connection = database[0]
    ids = _authorize(database)
    purge_id = ids[TARGETS[0][1]]
    connection.execute('RESET ROLE')
    if prior is not None:
        connection.execute('ALTER TABLE v3_derived.system_search SET (autovacuum_enabled=false,toast.autovacuum_enabled=false)')
    def options():
        return connection.execute(
            '''SELECT c.oid,o.option_value FROM pg_class c
               LEFT JOIN LATERAL pg_options_to_table(c.reloptions) o
                 ON o.option_name='autovacuum_enabled'
               WHERE c.oid='v3_derived.system_search'::regclass
                  OR c.oid=(SELECT reltoastrelid FROM pg_class WHERE oid='v3_derived.system_search'::regclass)
               ORDER BY c.oid''',
        ).fetchall()
    before = options()
    connection.execute('SET ROLE v3_derived_purge_executor')
    connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)', (purge_id, 'system_search'))
    assert all(value == 'false' for _, value in options())
    with pytest.raises(psycopg.Error):
        with connection.transaction():
            connection.execute('SELECT v3_meta.complete_derived_generation_purge(%s,%s)',
                               (purge_id, Jsonb(_receipt())))
    _abort_autovacuum_fence(connection, purge_id, 'system_search')
    assert options() == before
    connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,true)', (purge_id, 'system_search'))


@pytest.mark.parametrize('prior', (None, 'off', 'on'))
def test_writer_fence_refuses_readonly_or_restores_exact_role_defaults(database, prior):
    connection = database[0]
    ids = _authorize(database)
    purge_id = ids[TARGETS[0][1]]
    connection.execute('RESET ROLE')
    if prior:
        connection.execute(sql.SQL('ALTER ROLE edfinder_v3 SET default_transaction_read_only={}').format(sql.Literal(prior)))
    def settings():
        return connection.execute(
            '''SELECT setdatabase,setconfig FROM pg_db_role_setting
               WHERE setrole='edfinder_v3'::regrole ORDER BY setdatabase''',
        ).fetchall()
    before = settings()
    connection.execute('SET ROLE v3_derived_purge_executor')
    if prior == 'on':
        with pytest.raises(psycopg.errors.RaiseException, match='already read-only'):
            with connection.transaction():
                connection.execute('SELECT v3_meta.purge_set_writer_fence(%s,true)', (purge_id,))
        assert settings() == before
        return
    connection.execute('SELECT v3_meta.purge_set_writer_fence(%s,true)', (purge_id,))
    assert any('default_transaction_read_only=on' in config for _, config in settings())
    connection.execute('SELECT v3_meta.purge_recycle_writer_sessions(%s,true)', (purge_id,))
    connection.execute('SELECT v3_meta.purge_verify_writer_fence(%s,true,%s)', (purge_id, 'on'))
    connection.execute('SELECT v3_meta.purge_set_writer_fence(%s,false)', (purge_id,))
    assert settings() == before
    connection.execute('SELECT v3_meta.purge_recycle_writer_sessions(%s,false)', (purge_id,))
    connection.execute('SELECT v3_meta.purge_verify_writer_fence(%s,false,%s)', (purge_id, 'off'))
    connection.execute('SELECT v3_meta.purge_set_writer_fence(%s,false)', (purge_id,))
    assert settings() == before


def test_writer_fence_requires_committed_step_one_and_matching_probe(database):
    connection = database[0]
    purge_id = _authorize(database)[TARGETS[0][1]]
    with pytest.raises(psycopg.Error):
        with connection.transaction():
            connection.execute('SELECT v3_meta.purge_set_writer_fence(%s,true)', (purge_id,))
            connection.execute('SELECT v3_meta.purge_recycle_writer_sessions(%s,true)', (purge_id,))
    connection.execute('SELECT v3_meta.purge_set_writer_fence(%s,true)', (purge_id,))
    with pytest.raises(psycopg.Error):
        with connection.transaction():
            connection.execute('SELECT v3_meta.purge_verify_writer_fence(%s,true,%s)', (purge_id, 'off'))


@pytest.mark.parametrize('prior', (None, 'off'))
def test_writer_fence_recycles_pools_and_fresh_application_probes_match_restore(database, prior):
    connection = database[0]
    purge_id = _authorize(database)[TARGETS[0][1]]
    connection.execute('RESET ROLE')
    test_password = uuid4().hex
    connection.execute(sql.SQL('ALTER ROLE edfinder_v3 PASSWORD {}').format(sql.Literal(test_password)))
    if prior:
        connection.execute('ALTER ROLE edfinder_v3 SET default_transaction_read_only=off')
    app_dsn = make_conninfo(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL'],
                           dbname=connection.info.dbname, user=APPLICATION, password=test_password)
    with psycopg.connect(app_dsn, autocommit=True) as old_pool:
        assert old_pool.execute('SHOW default_transaction_read_only').fetchone()[0] == 'off'
        connection.execute('SET ROLE v3_derived_purge_executor')
        connection.execute('SELECT v3_meta.purge_set_writer_fence(%s,true)', (purge_id,))
        assert connection.execute('SELECT v3_meta.purge_recycle_writer_sessions(%s,true)',
                                  (purge_id,)).fetchone()[0] >= 1
        with pytest.raises(psycopg.OperationalError):
            old_pool.execute('SELECT 1')
    with psycopg.connect(app_dsn, autocommit=True) as fenced_pool:
        observed = fenced_pool.execute('SHOW default_transaction_read_only').fetchone()[0]
        assert observed == 'on'
        connection.execute('SELECT v3_meta.purge_verify_writer_fence(%s,true,%s)', (purge_id, observed))
        connection.execute('SELECT v3_meta.purge_set_writer_fence(%s,false)', (purge_id,))
        assert connection.execute('SELECT v3_meta.purge_recycle_writer_sessions(%s,false)',
                                  (purge_id,)).fetchone()[0] >= 1
        with pytest.raises(psycopg.OperationalError):
            fenced_pool.execute('SELECT 1')
    with psycopg.connect(app_dsn, autocommit=True) as restored_pool:
        observed = restored_pool.execute('SHOW default_transaction_read_only').fetchone()[0]
        assert observed == 'off'
        connection.execute('SELECT v3_meta.purge_verify_writer_fence(%s,false,%s)', (purge_id, observed))


@pytest.mark.parametrize('kind', ('batch', 'rewrite'))
@pytest.mark.parametrize('identity', ('unrelated', 'reused_pid'))
def test_cancel_functions_refuse_an_unrelated_or_reused_backend(database, kind, identity):
    connection = database[0]
    purge_id = _authorize(database)[TARGETS[0][1]]
    connection.execute('RESET ROLE')
    test_dsn = make_conninfo(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL'], dbname=connection.info.dbname)
    with psycopg.connect(test_dsn, autocommit=True) as unrelated:
        pid, started = unrelated.execute(
            'SELECT pid,backend_start FROM pg_stat_activity WHERE pid=pg_backend_pid()',
        ).fetchone()
        if identity == 'reused_pid':
            started = datetime(2000, 1, 1, tzinfo=timezone.utc)
        connection.execute(
            '''INSERT INTO v3_meta.derived_generation_purge_event(
                   purge_id,event_kind,relation_code,relation_oid,backend_pid,backend_start)
               VALUES(%s,%s,'system_search','v3_derived.system_search'::regclass,%s,%s)''',
            (purge_id, 'BATCH_STARTED' if kind == 'batch' else 'REWRITE_STARTED', pid, started),
        )
        connection.execute('SET ROLE v3_derived_purge_executor')
        statement = sql.SQL('SELECT v3_meta.{}(%s,%s)').format(sql.Identifier('cancel_purge_' + kind))
        with pytest.raises(psycopg.errors.RaiseException):
            with connection.transaction():
                connection.execute(statement, (purge_id, 'system_search'))
        assert unrelated.execute('SELECT 1').fetchone()[0] == 1
        with pytest.raises(psycopg.errors.RaiseException):
            with connection.transaction():
                connection.execute(statement, (uuid4(), 'system_search'))


def test_cancel_batch_signals_only_recorded_backend_and_rolls_back_payload(database):
    connection = database[0]
    purge_id = _authorize(database)[TARGETS[0][1]]
    _writer_fence(connection, purge_id)
    connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)', (purge_id, 'system_search'))
    connection.execute('RESET ROLE')
    connection.execute(
        '''CREATE FUNCTION v3_meta.test_delay_purge_receipt() RETURNS trigger LANGUAGE plpgsql AS $$
           BEGIN PERFORM pg_sleep(30); RETURN NEW; END $$''',
    )
    connection.execute(
        '''CREATE TRIGGER test_delay_purge_receipt BEFORE INSERT ON v3_meta.derived_generation_purge_event
           FOR EACH ROW WHEN (NEW.event_kind='BATCH_COMMITTED')
           EXECUTE FUNCTION v3_meta.test_delay_purge_receipt()''',
    )
    connection.execute('SET ROLE v3_derived_purge_executor')
    with _application_worker(connection) as worker:
        _start_batch(worker, purge_id, 'system_search', size=3)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(worker.execute, 'SELECT v3_meta.purge_derived_payload_batch(%s,%s,%s)',
                                 (purge_id, 'system_search', 3))
            _wait_for_database_operation(connection, worker, future, 'batch')
            assert connection.execute('SELECT v3_meta.cancel_purge_batch(%s,%s)',
                                      (purge_id, 'system_search')).fetchone()[0]
            with pytest.raises(psycopg.errors.QueryCanceled):
                future.result(timeout=10)
    assert _count(connection, 'v3_derived.system_search', TARGETS[0][1]) == 12
    assert _count(connection, 'v3_derived.system_search', SURVIVOR) == 12
    connection.execute('SELECT v3_meta.purge_record_event(%s,%s,%s,%s)',
                       (purge_id, 'BATCH_ROLLED_BACK', 'system_search', Jsonb({'recovered': True})))
    assert connection.execute(
        "SELECT count(*) FROM v3_meta.derived_generation_purge_event WHERE event_kind='BATCH_CANCEL_REQUESTED'",
    ).fetchone()[0] == 1


@pytest.mark.parametrize('operation', ('rewrite', 'analyze'))
def test_cancel_rewrite_or_trailing_analyze_preserves_relation_and_recovers(database, operation):
    connection = database[0]
    ids = _authorize(database)
    purge_id = ids[TARGETS[0][1]]
    _writer_fence(connection, purge_id)
    connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)', (purge_id, 'system_search'))
    for request_id in ids.values():
        assert _batch(connection, request_id, 'system_search') == 12
    connection.execute('SELECT v3_meta.complete_derived_payload_relation(%s,%s,%s)',
                       (purge_id, 'system_search', Jsonb(_receipt())))
    connection.execute('RESET ROLE')
    connection.execute(
        '''CREATE FUNCTION v3_meta.test_slow_rewrite_key(value_ bigint) RETURNS bigint
           LANGUAGE plpgsql IMMUTABLE AS $$ BEGIN PERFORM pg_sleep(0.1); RETURN value_; END $$''',
    )
    connection.execute(
        'CREATE INDEX test_slow_rewrite_key ON v3_derived.system_search (v3_meta.test_slow_rewrite_key(system_id64))',
    )
    connection.execute('SET ROLE v3_derived_purge_executor')
    with _application_worker(connection) as worker:
        worker.execute('SELECT v3_meta.purge_record_event(%s,%s,%s,%s)',
                       (purge_id, 'REWRITE_STARTED', 'system_search', Jsonb(_receipt())))
        before = worker.execute("SELECT pg_relation_filenode('v3_derived.system_search')").fetchone()[0]
        if operation == 'analyze':
            worker.execute('VACUUM (FULL) v3_derived.system_search')
        command = 'VACUUM (FULL) v3_derived.system_search' if operation == 'rewrite' else 'ANALYZE v3_derived.system_search'
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(worker.execute, command)
            _wait_for_database_operation(connection, worker, future, operation)
            assert connection.execute('SELECT v3_meta.cancel_purge_rewrite(%s,%s)',
                                      (purge_id, 'system_search')).fetchone()[0]
            with pytest.raises(psycopg.errors.QueryCanceled):
                future.result(timeout=10)
    after = connection.execute("SELECT pg_relation_filenode('v3_derived.system_search')").fetchone()[0]
    assert (after == before) is (operation == 'rewrite')
    assert _count(connection, 'v3_derived.system_search', SURVIVOR) == 12
    assert _count(connection, 'v3_derived.system_search', TARGETS[0][1]) == 0
    connection.execute('RESET ROLE')
    connection.execute('DROP INDEX v3_derived.test_slow_rewrite_key')
    connection.execute('DROP FUNCTION v3_meta.test_slow_rewrite_key(bigint)')
    connection.execute('SET ROLE v3_derived_purge_executor')
    if operation == 'rewrite':
        connection.execute('SELECT v3_meta.purge_record_event(%s,%s,%s,%s)',
                           (purge_id, 'REWRITE_ROLLED_BACK', 'system_search', Jsonb({'recovered': True})))
    else:
        connection.execute('ANALYZE v3_derived.system_search')
        connection.execute('SELECT pg_stat_force_next_flush()')
        connection.execute('SELECT v3_meta.purge_record_event(%s,%s,%s,%s)',
                           (purge_id, 'REWRITE_VERIFIED', 'system_search', Jsonb({**_receipt(), 'recovered': True})))


@pytest.mark.parametrize('fault', ('disk', 'wal', 'filesystem', 'workers', 'stale', 'future'))
def test_each_batch_requires_fresh_disk_wal_and_worker_evidence(database, fault):
    connection = database[0]
    purge_id = _authorize(database)[TARGETS[0][1]]
    _writer_fence(connection, purge_id)
    connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)', (purge_id, 'system_search'))
    evidence = _receipt()
    field, value = {
        'disk': ('filesystem_free_bytes', 99_999_999_999), 'wal': ('wal_healthy', False),
        'filesystem': ('wal_same_filesystem', False), 'workers': ('workers_stopped', False),
        'stale': ('observed_at', '2000-01-01T00:00:00+00:00'),
        'future': ('observed_at', '2100-01-01T00:00:00+00:00'),
    }[fault]
    evidence[field] = value
    before = _count(connection, 'v3_derived.system_search', TARGETS[0][1])
    events = _count(connection, 'v3_meta.derived_generation_purge_event')
    with pytest.raises(psycopg.Error):
        with connection.transaction():
            _start_batch(connection, purge_id, 'system_search', evidence=evidence)
    assert _count(connection, 'v3_derived.system_search', TARGETS[0][1]) == before
    assert _count(connection, 'v3_meta.derived_generation_purge_event') == events


@pytest.mark.parametrize('fault', ('xid_age', 'mxid_age', 'xid_projection', 'mxid_projection', 'deadline'))
def test_autovacuum_fence_rejects_unsafe_age_ceiling_and_projected_deadline(database, fault):
    connection = database[0]
    _seed(database)
    plan = _plan(connection)
    field, value = {
        'xid_age': ('xid_ceiling', 0), 'mxid_age': ('mxid_ceiling', 0),
        'xid_projection': ('xid_rate', 1_000_000_000),
        'mxid_projection': ('mxid_rate', 1_000_000_000), 'deadline': ('remaining_seconds', 0),
    }[fault]
    plan['autovacuum']['system_search'][field] = value
    _sign_plan(connection, plan)
    connection.execute('SET ROLE v3_derived_purge_executor')
    purge_id = connection.execute('SELECT v3_meta.begin_derived_generation_purge(%s)', (Jsonb(plan),)).fetchone()[0][0]
    before = _count(connection, 'v3_meta.derived_generation_purge_event')
    with pytest.raises(psycopg.errors.RaiseException, match='age ceiling|deadline'):
        with connection.transaction():
            connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)',
                               (purge_id, 'system_search'))
    assert _count(connection, 'v3_meta.derived_generation_purge_event') == before


def test_competing_transaction_with_an_assigned_xid_blocks_the_next_batch(database):
    connection = database[0]
    purge_id = _authorize(database)[TARGETS[0][1]]
    _writer_fence(connection, purge_id)
    connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)', (purge_id, 'system_search'))
    with _application_worker(connection) as writer:
        with writer.transaction():
            writer.execute('SELECT pg_current_xact_id()')
            with pytest.raises(psycopg.errors.RaiseException, match='competing writing transaction'):
                with connection.transaction():
                    _start_batch(connection, purge_id, 'system_search')
    assert _count(connection, 'v3_derived.system_search', TARGETS[0][1]) == 12
    assert _batch(connection, purge_id, 'system_search', size=3) == 3


def test_inactive_physical_replication_slot_refuses_phase_and_is_cleaned_up(database):
    connection = database[0]
    purge_id = _authorize(database)[TARGETS[0][1]]
    slot_name = 'v3_purge_test_' + uuid4().hex
    # The administrator remains in the fixture's maintenance database, so it
    # cannot obscure the operating database's fail-closed session inspection.
    with psycopg.connect(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL'], autocommit=True) as slot_admin:
        created = False
        try:
            slot_admin.execute('SELECT pg_create_physical_replication_slot(%s,true)', (slot_name,))
            created = True
            assert connection.execute(
                'SELECT active FROM pg_replication_slots WHERE slot_name=%s', (slot_name,),
            ).fetchone() == (False,)
            before = _count(connection, 'v3_meta.derived_generation_purge_event')
            with pytest.raises(psycopg.errors.RaiseException, match='unhealthy WAL retention'):
                with connection.transaction():
                    connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)',
                                       (purge_id, 'system_search'))
            assert _count(connection, 'v3_meta.derived_generation_purge_event') == before
            assert _count(connection, 'v3_derived.system_search', TARGETS[0][1]) == 12
        finally:
            if created:
                slot_admin.execute('SELECT pg_drop_replication_slot(%s)', (slot_name,))


def test_active_vacuum_progress_refuses_phase_before_disabling_autovacuum(database):
    connection = database[0]
    purge_id = _authorize(database)[TARGETS[0][1]]
    _writer_fence(connection, purge_id)
    before = _count(connection, 'v3_meta.derived_generation_purge_event')
    with _application_worker(connection) as worker:
        worker.execute("SET vacuum_cost_delay='100ms'")
        worker.execute('SET vacuum_cost_limit=1')
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(worker.execute,
                                 'VACUUM (DISABLE_PAGE_SKIPPING, INDEX_CLEANUP ON) v3_derived.system_search')
            try:
                _wait_for_database_operation(connection, worker, future, 'vacuum')
                with pytest.raises(psycopg.errors.RaiseException, match='vacuum active on purge relation'):
                    with connection.transaction():
                        connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)',
                                           (purge_id, 'system_search'))
            finally:
                if not future.done():
                    worker.cancel()
                try:
                    future.result(timeout=10)
                except psycopg.errors.QueryCanceled:
                    pass
    assert _count(connection, 'v3_meta.derived_generation_purge_event') == before
    assert _count(connection, 'v3_derived.system_search', TARGETS[0][1]) == 12


def test_autovacuum_age_ceiling_rechecks_between_committed_batches(database):
    connection = database[0]
    _seed(database)
    plan = _plan(connection)
    age = connection.execute(
        '''SELECT max(age(relfrozenxid)::bigint) FROM pg_class
           WHERE oid='v3_derived.system_search'::regclass OR
                 oid=(SELECT reltoastrelid FROM pg_class WHERE oid='v3_derived.system_search'::regclass)''',
    ).fetchone()[0]
    plan['autovacuum']['system_search']['xid_ceiling'] = age + 50
    _sign_plan(connection, plan)
    connection.execute('SET ROLE v3_derived_purge_executor')
    purge_id = connection.execute('SELECT v3_meta.begin_derived_generation_purge(%s)', (Jsonb(plan),)).fetchone()[0][0]
    _writer_fence(connection, purge_id)
    connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)', (purge_id, 'system_search'))
    assert _batch(connection, purge_id, 'system_search', size=3) == 3
    for _ in range(100):
        connection.execute('SELECT pg_current_xact_id()')
    with pytest.raises(psycopg.errors.RaiseException, match='age ceiling'):
        with connection.transaction():
            _start_batch(connection, purge_id, 'system_search', size=3)
    assert _count(connection, 'v3_derived.system_search', TARGETS[0][1]) == 9


def test_live_published_product_append_is_detected_as_survivor_drift_at_phase_boundary(database):
    connection = database[0]
    ids = _authorize(database, survivor_search_built=False)
    purge_id = ids[TARGETS[0][1]]
    _writer_fence(connection, purge_id)
    connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)', (purge_id, 'system_search'))
    for request_id in ids.values():
        assert _batch(connection, request_id, 'system_search') == 12
    connection.execute('RESET ROLE')
    generation, _, manifest_hash = register_product(connection, 'ratings_v4_prod_p4_parallel_v1')
    assert build_available(connection, generation, manifest_hash)['chunks_written'] == 1
    assert _count(connection, 'v3_derived.system_search', SURVIVOR) == 12
    connection.execute('SET ROLE v3_derived_purge_executor')
    events = _count(connection, 'v3_meta.derived_generation_purge_event')
    with pytest.raises(psycopg.errors.RaiseException, match='survivor.*drift'):
        with connection.transaction():
            connection.execute('SELECT v3_meta.complete_derived_payload_relation(%s,%s,%s)',
                               (purge_id, 'system_search', Jsonb(_receipt())))
    assert _count(connection, 'v3_meta.derived_generation_purge_event') == events
    assert _count(connection, 'v3_derived.system_search', SURVIVOR) == 12


def test_foreign_keys_still_reject_wrong_parent_delete_if_phase_receipt_is_corrupt(database):
    connection = database[0]
    purge_id = _authorize(database)[TARGETS[0][1]]
    _writer_fence(connection, purge_id)
    connection.execute('RESET ROLE')
    for prior in ('system_search', 'economy_opportunity'):
        # Deliberate owner-side fault injection; ordinary executor privileges
        # cannot forge these receipts. The FK remains an independent backstop.
        connection.execute(
            '''INSERT INTO v3_meta.derived_generation_purge_event(purge_id,event_kind,relation_code)
               VALUES(%s,'REWRITE_VERIFIED',%s)''', (purge_id, prior),
        )
    connection.execute('SET ROLE v3_derived_purge_executor')
    connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)', (purge_id, 'body_mechanics'))
    before = _count(connection, 'v3_derived.body_mechanics', TARGETS[0][1])
    _start_batch(connection, purge_id, 'body_mechanics')
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with connection.transaction():
            connection.execute('SELECT v3_meta.purge_derived_payload_batch(%s,%s,%s)',
                               (purge_id, 'body_mechanics', 100_000))
    assert _count(connection, 'v3_derived.body_mechanics', TARGETS[0][1]) == before
    assert connection.execute(
        "SELECT count(*) FROM v3_meta.derived_generation_purge_event WHERE event_kind='BATCH_COMMITTED'",
    ).fetchone()[0] == 0


def test_batch_requires_committed_start_and_rolls_back_payload_when_receipt_fails(database):
    connection = database[0]
    purge_id = _authorize(database)[TARGETS[0][1]]
    _writer_fence(connection, purge_id)
    connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)', (purge_id, 'system_search'))
    with pytest.raises(psycopg.Error):
        with connection.transaction():
            _start_batch(connection, purge_id, 'system_search', size=3)
            connection.execute('SELECT v3_meta.purge_derived_payload_batch(%s,%s,%s)', (purge_id, 'system_search', 3))
    _start_batch(connection, purge_id, 'system_search', size=3)
    connection.execute('RESET ROLE')
    connection.execute(
        "ALTER TABLE v3_meta.derived_generation_purge_event ADD CONSTRAINT injected_receipt_failure CHECK (event_kind<>'BATCH_COMMITTED')",
    )
    connection.execute('SET ROLE v3_derived_purge_executor')
    before = _count(connection, 'v3_derived.system_search', TARGETS[0][1])
    with pytest.raises(psycopg.errors.CheckViolation):
        with connection.transaction():
            connection.execute('SELECT v3_meta.purge_derived_payload_batch(%s,%s,%s)', (purge_id, 'system_search', 3))
    assert _count(connection, 'v3_derived.system_search', TARGETS[0][1]) == before
    assert _count(connection, 'v3_derived.system_search', SURVIVOR) == 12
    connection.execute('RESET ROLE')
    connection.execute('ALTER TABLE v3_meta.derived_generation_purge_event DROP CONSTRAINT injected_receipt_failure')
    connection.execute('SET ROLE v3_derived_purge_executor')
    assert connection.execute('SELECT v3_meta.purge_derived_payload_batch(%s,%s,%s)',
                              (purge_id, 'system_search', 3)).fetchone()[0] == 3


def test_shared_physical_fence_does_not_let_other_target_adopt_batch_range(database):
    connection = database[0]
    ids = _authorize(database)
    first, second = (ids[identifier] for _, identifier in TARGETS)
    _writer_fence(connection, first)
    connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)', (first, 'system_search'))
    _start_batch(connection, first, 'system_search', size=3)
    with pytest.raises(psycopg.Error):
        with connection.transaction():
            connection.execute('SELECT v3_meta.purge_derived_payload_batch(%s,%s,%s)',
                               (second, 'system_search', 3))
    assert _count(connection, 'v3_derived.system_search', TARGETS[1][1]) == 12
    assert connection.execute('SELECT v3_meta.purge_derived_payload_batch(%s,%s,%s)',
                              (first, 'system_search', 3)).fetchone()[0] == 3
    assert _batch(connection, second, 'system_search', size=3) == 3
    _abort_autovacuum_fence(connection, second, 'system_search')
    assert connection.execute(
        '''SELECT option_value FROM pg_class c CROSS JOIN LATERAL pg_options_to_table(c.reloptions)
           WHERE c.oid='v3_derived.system_search'::regclass AND option_name='autovacuum_enabled' ''',
    ).fetchone() is None


def test_departed_batch_client_is_resolved_from_durable_start_then_resumes(database):
    connection = database[0]
    purge_id = _authorize(database)[TARGETS[0][1]]
    _writer_fence(connection, purge_id)
    connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)', (purge_id, 'system_search'))
    test_dsn = make_conninfo(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL'], dbname=connection.info.dbname)
    with psycopg.connect(test_dsn, autocommit=True) as departed:
        departed.execute('SET ROLE v3_derived_purge_executor')
        _start_batch(departed, purge_id, 'system_search', size=3)
    assert _count(connection, 'v3_derived.system_search', TARGETS[0][1]) == 12
    connection.execute('SELECT v3_meta.purge_record_event(%s,%s,%s,%s)',
                       (purge_id, 'BATCH_ROLLED_BACK', 'system_search', Jsonb({'recovered': True})))
    assert _batch(connection, purge_id, 'system_search', size=3) == 3
    assert _count(connection, 'v3_derived.system_search', TARGETS[0][1]) == 9


def test_survivor_and_pointer_drift_and_wrong_dependency_stop_before_deletion(database):
    connection = database[0]
    purge_id = _authorize(database)[TARGETS[0][1]]
    _writer_fence(connection, purge_id)
    with pytest.raises(psycopg.Error):
        with connection.transaction():
            connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)',
                               (purge_id, 'body_mechanics'))
    connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)', (purge_id, 'system_search'))
    before = _count(connection, 'v3_derived.system_search', TARGETS[0][1])
    connection.execute('RESET ROLE')
    connection.execute('UPDATE v3_spatial.current_spatial_generation SET publication_sequence=2')
    connection.execute('SET ROLE v3_derived_purge_executor')
    with pytest.raises(psycopg.Error):
        with connection.transaction():
            _start_batch(connection, purge_id, 'system_search')
    assert _count(connection, 'v3_derived.system_search', TARGETS[0][1]) == before


def test_competing_spatial_lock_refuses_authorization(database):
    connection = database[0]
    _seed(database)
    plan = _plan(connection)
    test_dsn = make_conninfo(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL'], dbname=connection.info.dbname)
    with psycopg.connect(test_dsn, autocommit=True) as competing:
        competing.execute('SELECT pg_advisory_lock(764004001)')
        connection.execute('SET ROLE v3_derived_purge_executor')
        with pytest.raises(psycopg.errors.RaiseException, match='competing'):
            with connection.transaction():
                connection.execute('SELECT v3_meta.begin_derived_generation_purge(%s)', (Jsonb(plan),))
        assert _count(connection, 'v3_meta.derived_generation_purge_request') == 0


@pytest.mark.parametrize('exclusion', ('cluster_run', 'system_archetype'))
def test_any_excluded_cluster_or_archetype_target_payload_stops_authorization(database, exclusion):
    connection = database[0]
    _seed(database)
    generation_id = TARGETS[0][1]
    if exclusion == 'cluster_run':
        connection.execute(
            '''INSERT INTO v3_spatial.cluster_run(
                   derived_generation_id,cluster_run_id,owner_domain,algorithm,algorithm_version,parameters)
               VALUES(%s,%s,'fixture','fixture','1','{}')''', (generation_id, uuid4()),
        )
    else:
        from tests.test_v3_system_archetype_migration import (
            _insert_wide_row, _register_archetype_product, _valid_row,
        )
        _register_archetype_product(connection, generation_id, 1)
        system_id64 = connection.execute(
            'SELECT system_id64 FROM v3_derived.system_rating_vector WHERE derived_generation_id=%s LIMIT 1',
            (generation_id,),
        ).fetchone()[0]
        _insert_wide_row(connection, _valid_row(generation_id, system_id64))
    plan = _plan(connection)
    connection.execute('SET ROLE v3_derived_purge_executor')
    with pytest.raises(psycopg.errors.RaiseException, match='cluster or archetype'):
        with connection.transaction():
            connection.execute('SELECT v3_meta.begin_derived_generation_purge(%s)', (Jsonb(plan),))
    assert _count(connection, 'v3_meta.derived_generation_purge_request') == 0
    assert _count(connection, 'v3_meta.derived_generation_purge_event') == 0


def test_spoofed_purge_setting_does_not_authorize_owner_delete_or_mixed_statement(database):
    connection = database[0]
    ids = _authorize(database)
    connection.execute('RESET ROLE')
    with pytest.raises(psycopg.errors.RaiseException):
        with connection.transaction():
            connection.execute("SELECT set_config('v3.purge_id',%s,true)", (str(ids[TARGETS[0][1]]),))
            connection.execute('DELETE FROM v3_derived.system_search WHERE derived_generation_id=ANY(%s)',
                               ([TARGETS[0][1], SURVIVOR],))
    assert _count(connection, 'v3_derived.system_search', TARGETS[0][1]) == 12
    assert _count(connection, 'v3_derived.system_search', SURVIVOR) == 12


def test_all_payload_relations_purge_child_first_preserving_receipts_and_complete_idempotently(database):
    connection = database[0]
    ids = _authorize(database)
    purge_id = ids[TARGETS[0][1]]
    retained = {relation: _count(connection, relation) for relation in RETAINED}
    survivors = {relation: _count(connection, 'v3_derived.' + relation, SURVIVOR) for relation in RELATIONS}
    assert all(survivors.values())
    _writer_fence(connection, purge_id)
    for relation in RELATIONS:
        connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)', (purge_id, relation))
        for identifier, request_id in ids.items():
            expected = _count(connection, 'v3_derived.' + relation, identifier)
            assert expected > 0
            deleted = 0
            while _count(connection, 'v3_derived.' + relation, identifier):
                changed = _batch(connection, request_id, relation, size=100)
                assert 0 < changed <= 100
                deleted += changed
            assert deleted == expected
        connection.execute('SELECT v3_meta.complete_derived_payload_relation(%s,%s,%s)',
                           (purge_id, relation, Jsonb(_receipt())))
        connection.execute('SELECT v3_meta.complete_derived_payload_relation(%s,%s,%s)',
                           (purge_id, relation, Jsonb(_receipt())))
        connection.execute('SELECT v3_meta.purge_record_event(%s,%s,%s,%s)',
                           (purge_id, 'REWRITE_STARTED', relation, Jsonb(_receipt())))
        before = connection.execute('SELECT relfilenode FROM pg_class WHERE oid=%s::regclass',
                                    ('v3_derived.' + relation,)).fetchone()[0]
        connection.execute(sql.SQL('VACUUM (FULL, ANALYZE) v3_derived.{}').format(sql.Identifier(relation)))
        connection.execute('SELECT pg_stat_force_next_flush()')
        connection.execute('SELECT pg_stat_clear_snapshot()')
        assert connection.execute('SELECT relfilenode FROM pg_class WHERE oid=%s::regclass',
                                  ('v3_derived.' + relation,)).fetchone()[0] != before
        connection.execute('SELECT v3_meta.purge_record_event(%s,%s,%s,%s)',
                           (purge_id, 'REWRITE_VERIFIED', relation, Jsonb(_receipt())))
        assert _count(connection, 'v3_derived.' + relation, SURVIVOR) == survivors[relation]
    connection.execute('SELECT v3_meta.purge_set_writer_fence(%s,false)', (purge_id,))
    connection.execute('SELECT v3_meta.purge_recycle_writer_sessions(%s,false)', (purge_id,))
    connection.execute('SELECT v3_meta.purge_verify_writer_fence(%s,false,%s)', (purge_id, 'off'))
    # A failed final ledger append leaves no false completion, after every
    # payload deletion and physical rewrite has already committed independently.
    connection.execute('RESET ROLE')
    connection.execute(
        "ALTER TABLE v3_meta.derived_generation_purge_event ADD CONSTRAINT injected_completion_failure CHECK (event_kind<>'COMPLETED')",
    )
    connection.execute('SET ROLE v3_derived_purge_executor')
    with pytest.raises(psycopg.errors.CheckViolation):
        with connection.transaction():
            connection.execute('SELECT v3_meta.complete_derived_generation_purge(%s,%s)',
                               (purge_id, Jsonb(_receipt())))
    connection.execute('RESET ROLE')
    connection.execute('ALTER TABLE v3_meta.derived_generation_purge_event DROP CONSTRAINT injected_completion_failure')
    connection.execute('SET ROLE v3_derived_purge_executor')
    for request_id in ids.values():
        connection.execute('SELECT v3_meta.complete_derived_generation_purge(%s,%s)',
                           (request_id, Jsonb(_receipt())))
        count = _count(connection, 'v3_meta.derived_generation_purge_event')
        connection.execute('SELECT v3_meta.complete_derived_generation_purge(%s,%s)',
                           (request_id, Jsonb(_receipt())))
        assert _count(connection, 'v3_meta.derived_generation_purge_event') == count
    assert {relation: _count(connection, relation) for relation in RETAINED} == retained
    assert connection.execute(
        "SELECT count(*) FROM v3_meta.derived_generation_purge_event WHERE event_kind='COMPLETED'",
    ).fetchone()[0] == 2


@pytest.mark.parametrize('interruption', ('before_rewrite', 'after_rewrite_before_receipt'))
def test_rewrite_recovery_uses_recorded_filenode_and_requires_trailing_analyze(database, interruption):
    connection = database[0]
    ids = _authorize(database)
    purge_id = ids[TARGETS[0][1]]
    _writer_fence(connection, purge_id)
    connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)', (purge_id, 'system_search'))
    for target_id in ids.values():
        assert _batch(connection, target_id, 'system_search') == 12
    connection.execute('SELECT v3_meta.complete_derived_payload_relation(%s,%s,%s)',
                       (purge_id, 'system_search', Jsonb(_receipt())))
    connection.execute('SELECT v3_meta.purge_record_event(%s,%s,%s,%s)',
                       (purge_id, 'REWRITE_STARTED', 'system_search', Jsonb(_receipt())))
    recorded = connection.execute(
        '''SELECT relation_oid,relfilenode_before,backend_pid,backend_start
           FROM v3_meta.derived_generation_purge_event WHERE event_kind='REWRITE_STARTED'
           ORDER BY event_sequence DESC LIMIT 1''',
    ).fetchone()
    assert all(value is not None for value in recorded)
    if interruption == 'before_rewrite':
        connection.execute('SELECT v3_meta.purge_record_event(%s,%s,%s,%s)',
                           (purge_id, 'REWRITE_ROLLED_BACK', 'system_search', Jsonb({'recovered': True})))
        connection.execute('SELECT v3_meta.purge_record_event(%s,%s,%s,%s)',
                           (purge_id, 'REWRITE_STARTED', 'system_search', Jsonb(_receipt())))
    connection.execute('VACUUM (FULL) v3_derived.system_search')
    rewritten = connection.execute("SELECT pg_relation_filenode('v3_derived.system_search')").fetchone()[0]
    assert rewritten != recorded[1]
    with pytest.raises(psycopg.Error):
        with connection.transaction():
            connection.execute('SELECT v3_meta.purge_record_event(%s,%s,%s,%s)',
                               (purge_id, 'REWRITE_VERIFIED', 'system_search', Jsonb(_receipt())))
    connection.execute('ANALYZE v3_derived.system_search')
    connection.execute('SELECT pg_stat_force_next_flush()')
    connection.execute('SELECT pg_stat_clear_snapshot()')
    if interruption == 'after_rewrite_before_receipt':
        connection.execute('RESET ROLE')
        connection.execute(
            "ALTER TABLE v3_meta.derived_generation_purge_event ADD CONSTRAINT injected_rewrite_receipt_failure CHECK(event_kind<>'REWRITE_VERIFIED')",
        )
        connection.execute('SET ROLE v3_derived_purge_executor')
        with pytest.raises(psycopg.errors.CheckViolation):
            with connection.transaction():
                connection.execute('SELECT v3_meta.purge_record_event(%s,%s,%s,%s)',
                                   (purge_id, 'REWRITE_VERIFIED', 'system_search', Jsonb(_receipt())))
        connection.execute('RESET ROLE')
        connection.execute('ALTER TABLE v3_meta.derived_generation_purge_event DROP CONSTRAINT injected_rewrite_receipt_failure')
        connection.execute('SET ROLE v3_derived_purge_executor')
    with pytest.raises(psycopg.Error):
        with connection.transaction():
            connection.execute('SELECT v3_meta.complete_derived_generation_purge(%s,%s)',
                               (purge_id, Jsonb(_receipt())))
    connection.execute('SELECT v3_meta.purge_record_event(%s,%s,%s,%s)',
                       (purge_id, 'REWRITE_VERIFIED', 'system_search', Jsonb({**_receipt(), 'recovered': True})))
    assert connection.execute("SELECT pg_relation_filenode('v3_derived.system_search')").fetchone()[0] == rewritten
    assert connection.execute(
        "SELECT recovered FROM v3_meta.derived_generation_purge_event WHERE event_kind='REWRITE_VERIFIED'",
    ).fetchall() == [(True,)]
    assert _count(connection, 'v3_derived.system_search', SURVIVOR) == 12


def test_role_creation_and_exact_maintenance_surface(database):
    connection = database[0]
    creator = connection.execute('SELECT current_user').fetchone()[0]
    if creator == APPLICATION:
        assert connection.execute(
            '''SELECT m.set_option,m.inherit_option FROM pg_auth_members m
               JOIN pg_roles r ON r.oid=m.roleid JOIN pg_roles c ON c.oid=m.member
               WHERE r.rolname=%s AND c.rolname=current_user''', (EXECUTOR,),
        ).fetchone() == (True, False)
    assert connection.execute(
        'SELECT rolcanlogin,rolsuper,rolcreaterole FROM pg_roles WHERE rolname=%s', (EXECUTOR,),
    ).fetchone() == (False, False, False)
    connection.execute('SET ROLE v3_derived_purge_executor')
    for relation in RELATIONS:
        assert connection.execute('SELECT has_table_privilege(current_user,%s,%s)',
                                  ('v3_derived.' + relation, 'MAINTAIN')).fetchone()[0]
        connection.execute(sql.SQL('VACUUM (FULL, ANALYZE) v3_derived.{}').format(sql.Identifier(relation)))
    assert not connection.execute('SELECT has_table_privilege(current_user,%s,%s)',
                                  ('v3_derived.build_chunk', 'MAINTAIN')).fetchone()[0]
    # PostgreSQL VACUUM skips an inaccessible relation with a warning. Assert the
    # privilege and unchanged filenode as well as observing that no rewrite ran.
    before = connection.execute("SELECT pg_relation_filenode('v3_derived.build_chunk')").fetchone()[0]
    connection.execute('VACUUM (FULL) v3_derived.build_chunk')
    assert connection.execute("SELECT pg_relation_filenode('v3_derived.build_chunk')").fetchone()[0] == before


@pytest.mark.parametrize('operation', ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'DISABLE TRIGGER'))
def test_executor_cannot_mutate_payload_or_ledger_directly(database, operation):
    connection = database[0]
    relations = [*('v3_derived.' + name for name in RELATIONS), *RETAINED,
                 'v3_meta.derived_generation_purge_request', 'v3_meta.derived_generation_purge_event',
                 'v3_derived.system_archetype', 'v3_spatial.cluster_run',
                 'v3_spatial.cluster', 'v3_spatial.cluster_member']
    connection.execute('SET ROLE v3_derived_purge_executor')
    for relation in relations:
        qualified = sql.Identifier(*relation.split('.'))
        statements = {
            'INSERT': sql.SQL('INSERT INTO {} DEFAULT VALUES'),
            'UPDATE': sql.SQL('UPDATE {} SET derived_generation_id=derived_generation_id'),
            'DELETE': sql.SQL('DELETE FROM {}'),
            'TRUNCATE': sql.SQL('TRUNCATE {}'),
            'DISABLE TRIGGER': sql.SQL('ALTER TABLE {} DISABLE TRIGGER ALL'),
        }
        if operation == 'UPDATE':
            # Ledger/audit schemas have different keys; select any real column.
            column = connection.execute(
                '''SELECT attname FROM pg_attribute WHERE attrelid=%s::regclass
                   AND attnum>0 AND NOT attisdropped ORDER BY attnum LIMIT 1''', (relation,),
            ).fetchone()[0]
            statement = sql.SQL('UPDATE {} SET {}={}').format(qualified, sql.Identifier(column), sql.Identifier(column))
        else:
            statement = statements[operation].format(qualified)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with connection.transaction():
                connection.execute(statement)


def test_unknown_request_relation_and_batch_limits_fail_closed(database):
    connection = database[0]
    connection.execute('SET ROLE v3_derived_purge_executor')
    for relation, batch_size in (
        ('system_search', 1), ('system_search', 0), ('system_search', -1),
        ('system_search', 100001), ('system_archetype', 1), ('cluster_member', 1),
        ('system_search; DROP SCHEMA v3_meta CASCADE', 1),
    ):
        with pytest.raises(psycopg.Error):
            with connection.transaction():
                connection.execute('SELECT v3_meta.purge_derived_payload_batch(%s,%s,%s)',
                                   (uuid4(), relation, batch_size))
    assert _count(connection, 'v3_meta.derived_generation_purge_request') == 0
    assert _count(connection, 'v3_meta.derived_generation_purge_event') == 0
