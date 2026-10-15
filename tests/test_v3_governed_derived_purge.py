"""Governed purge capability on disposable PostgreSQL 18, never production.

The canonical_database import also makes CI's PG18 discovery select this file.
Roles are cluster objects: serialize their lifecycle, adopt existing roles,
and remove only roles this fixture created if no other database needs them.
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
    """Install 016 without assuming that cluster roles belong to this database."""
    assert connection.info.server_version >= 180000, 'purge validation requires PostgreSQL 18'
    base_dsn = os.environ['RATINGS_V4_VALIDATION_DATABASE_URL']
    cleanup_dsn = make_conninfo(base_dsn, dbname=connection.info.dbname)
    lock_connection = psycopg.connect(base_dsn, autocommit=True)
    lock_connection.execute('SELECT pg_advisory_lock(764016099)')
    created_application = False
    executor_was_absent = False
    granted_membership = False
    application_state = None
    application_connection = None
    try:
        assert connection.execute(
            'SELECT rolsuper FROM pg_roles WHERE rolname=current_user',
        ).fetchone()[0], 'the disposable PG18 fixture must be administered by its test superuser'
        executor_was_absent = not connection.execute(
            'SELECT 1 FROM pg_roles WHERE rolname=%s', (EXECUTOR,),
        ).fetchone()
        application_state = connection.execute(
            '''SELECT rolpassword,
                      (SELECT option_value FROM pg_db_role_setting s,
                       LATERAL pg_options_to_table(s.setconfig)
                       WHERE s.setrole=r.oid AND s.setdatabase=0
                         AND option_name='default_transaction_read_only')
               FROM pg_authid r WHERE rolname=%s''', (APPLICATION,),
        ).fetchone()
        if application_present and application_state is None:
            connection.execute('CREATE ROLE edfinder_v3 LOGIN CREATEROLE')
            created_application = True
        elif application_present:
            connection.execute('ALTER ROLE edfinder_v3 RESET default_transaction_read_only')
        if creator == 'non_superuser':
            assert application_present
            assert connection.execute(
                'SELECT NOT rolsuper AND rolcanlogin AND rolcreaterole FROM pg_roles WHERE rolname=%s',
                (APPLICATION,),
            ).fetchone()[0], 'non-superuser validation needs a LOGIN CREATEROLE application role without SUPERUSER'
            if not executor_was_absent and not connection.execute(
                'SELECT 1 FROM pg_auth_members WHERE roleid=%s::regrole AND member=%s::regrole',
                (EXECUTOR, APPLICATION),
            ).fetchone():
                # Test-superuser setup only: simulate a role originally created
                # by this app owner. 016 itself must never repair membership.
                connection.execute('GRANT v3_derived_purge_executor TO edfinder_v3 WITH INHERIT FALSE, SET TRUE')
                granted_membership = True
            _grant_application_create(connection)
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
            if executor_was_absent:
                # PostgreSQL creates an unavoidable bootstrap-granted ADMIN
                # row beside createrole_self_grant's SET-only row. For later
                # adoption tests, the test administrator provisions a clean
                # SET-only graph on this fixture-created role. Never repair
                # an executor that already existed before this fixture.
                with psycopg.connect(cleanup_dsn, autocommit=True) as administrator:
                    administrator.execute('REVOKE v3_derived_purge_executor FROM edfinder_v3 CASCADE')
                    administrator.execute(
                        'GRANT v3_derived_purge_executor TO edfinder_v3 WITH SET TRUE, INHERIT FALSE, ADMIN FALSE',
                    )
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
            if application_state is not None:
                password, read_only = application_state
                connection.execute(sql.SQL('ALTER ROLE edfinder_v3 PASSWORD {}').format(sql.Literal(password)))
                if read_only is None:
                    connection.execute('ALTER ROLE edfinder_v3 RESET default_transaction_read_only')
                else:
                    connection.execute(sql.SQL('ALTER ROLE edfinder_v3 SET default_transaction_read_only={}').format(
                        sql.Literal(read_only),
                    ))
            elif created_application:
                # A role retained because of another database's dependencies
                # must not retain a test's interrupted writer fence/password.
                connection.execute('ALTER ROLE edfinder_v3 RESET default_transaction_read_only')
                connection.execute('ALTER ROLE edfinder_v3 PASSWORD NULL')
            if granted_membership:
                connection.execute('REVOKE v3_derived_purge_executor FROM edfinder_v3')
            for name in (EXECUTOR, APPLICATION):
                exists = connection.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (name,)).fetchone()
                if exists and ((name == EXECUTOR and executor_was_absent) or
                               (name == APPLICATION and created_application)):
                    connection.execute(sql.SQL('DROP OWNED BY {} CASCADE').format(sql.Identifier(name)))
                    try:
                        connection.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(name)))
                    except psycopg.errors.DependentObjectsStillExist:
                        # DROP OWNED is database-local. Another test database
                        # may still depend on this cluster role; leave it there.
                        pass
        finally:
            if application_connection is not None:
                connection.close()
            lock_connection.execute('SELECT pg_advisory_unlock(764016099)')
            lock_connection.close()


def _grant_application_create(connection):
    connection.execute(sql.SQL('GRANT CREATE ON DATABASE {} TO edfinder_v3').format(
        sql.Identifier(connection.info.dbname),
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


@pytest.fixture(params=('superuser', 'non_superuser'))
def database(request):
    with canonical_database() as data:
        connection = data[0]
        with installed_purge(connection, creator=request.param, apply_chain=True) as installed:
            yield (installed, *data[1:])


def test_fresh_superuser_manifest_install_does_not_require_the_production_application_role():
    with canonical_database() as data:
        connection = data[0]
        application_before = connection.execute('SELECT oid FROM pg_roles WHERE rolname=%s', (APPLICATION,)).fetchone()
        with installed_purge(connection, apply_chain=True, application_present=False):
            assert connection.execute('SELECT oid FROM pg_roles WHERE rolname=%s', (APPLICATION,)).fetchone() == application_before
            assert connection.execute('SELECT rolcanlogin FROM pg_roles WHERE rolname=%s', (EXECUTOR,)).fetchone() == (False,)
            assert connection.execute(
                "SELECT to_regclass('v3_meta.derived_generation_purge_request') IS NOT NULL",
            ).fetchone()[0]


def _remaining_manifest():
    return [ROOT / 'sql' / line.split()[2]
            for line in (ROOT / 'sql/v3/migration-manifest.txt').read_text().splitlines()
            if line.strip() and not line.startswith('#') and line.split()[1] != '001_v3_baseline.sql']


@pytest.mark.parametrize('creator', ('superuser', 'non_superuser'))
def test_second_database_full_manifest_adopts_same_executor_and_installs_local_privileges(creator):
    with canonical_database() as first:
        with installed_purge(first[0], creator=creator, apply_chain=True) as installed:
            role_before = installed.execute('SELECT oid FROM pg_roles WHERE rolname=%s', (EXECUTOR,)).fetchone()
            with canonical_database() as second:
                connection = second[0]
                notices = []
                connection.add_notice_handler(lambda diagnostic: notices.append(diagnostic.message_primary))
                if creator == 'non_superuser':
                    _grant_application_create(connection)
                for migration in _remaining_manifest():
                    # The canonical fixture's identity/journal tables belong to
                    # its administrator; install their migrations as that owner.
                    # The derived lineage (including 016) belongs to the app.
                    if creator == 'non_superuser' and migration.name in (*CHAIN, PURGE_MIGRATION):
                        connection.execute('SET SESSION AUTHORIZATION edfinder_v3')
                    connection.execute(migration.read_text())
                    connection.execute('RESET SESSION AUTHORIZATION')
                assert connection.execute('SELECT oid FROM pg_roles WHERE rolname=%s', (EXECUTOR,)).fetchone() == role_before
                if creator == 'non_superuser':
                    assert any('password check skipped: pg_authid is not readable' in notice for notice in notices)
                    connection.execute('SET SESSION AUTHORIZATION edfinder_v3')
                assert connection.execute(
                    '''SELECT member=current_user::regrole,set_option,inherit_option,admin_option
                       FROM pg_auth_members WHERE roleid=%s::regrole''', (EXECUTOR,),
                ).fetchall() == ([(True, True, False, False)] if creator == 'non_superuser' else [])
                connection.execute('SET ROLE v3_derived_purge_executor')
                for relation in RELATIONS:
                    assert connection.execute('SELECT has_table_privilege(current_user,%s,%s)',
                                              ('v3_derived.' + relation, 'MAINTAIN')).fetchone()[0]
                    assert not connection.execute('SELECT has_table_privilege(current_user,%s,%s)',
                                                  ('v3_derived.' + relation, 'INSERT,UPDATE,DELETE,TRUNCATE')).fetchone()[0]
                assert connection.execute(
                    "SELECT has_function_privilege(current_user,'v3_meta.purge_derived_payload_batch(uuid,text,integer)','EXECUTE')",
                ).fetchone()[0]
                assert connection.execute('SELECT count(*) FROM v3_meta.derived_generation_purge_request').fetchone() == (0,)


def test_full_manifest_before_and_after_purge_fixture_preserves_cluster_role():
    with canonical_database() as before:
        connection = before[0]
        # Hold the fixture's cluster-role lock across all three databases.
        with psycopg.connect(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL'], autocommit=True) as lock:
            lock.execute('SELECT pg_advisory_lock(764016099)')
            created_executor = not connection.execute(
                'SELECT 1 FROM pg_roles WHERE rolname=%s', (EXECUTOR,),
            ).fetchone()
            try:
                for migration in _remaining_manifest():
                    connection.execute(migration.read_text())
                oid = connection.execute('SELECT oid FROM pg_roles WHERE rolname=%s', (EXECUTOR,)).fetchone()
            finally:
                lock.execute('SELECT pg_advisory_unlock(764016099)')
        try:
            with canonical_database() as purge:
                with installed_purge(purge[0], apply_chain=True):
                    assert purge[0].execute('SELECT oid FROM pg_roles WHERE rolname=%s', (EXECUTOR,)).fetchone() == oid
            with canonical_database() as after:
                for migration in _remaining_manifest():
                    after[0].execute(migration.read_text())
                assert after[0].execute('SELECT oid FROM pg_roles WHERE rolname=%s', (EXECUTOR,)).fetchone() == oid
        finally:
            if created_executor:
                connection.execute(sql.SQL('DROP OWNED BY {} CASCADE').format(sql.Identifier(EXECUTOR)))
                try:
                    connection.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(EXECUTOR)))
                except psycopg.errors.DependentObjectsStillExist:
                    pass


def _schema_state(connection):
    """Include grants, function bodies, triggers and ledger in rollback evidence."""
    return (
        connection.execute(
            '''SELECT n.nspname,c.relname,c.relkind,c.relowner,c.relacl::text
               FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
               WHERE n.nspname LIKE 'v3_%' ORDER BY n.nspname,c.relname''',
        ).fetchall(),
        connection.execute(
            '''SELECT p.oid,pg_get_functiondef(p.oid),p.proacl::text
               FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
               WHERE n.nspname LIKE 'v3_%' ORDER BY p.oid''',
        ).fetchall(),
        connection.execute(
            '''SELECT t.oid,pg_get_triggerdef(t.oid) FROM pg_trigger t
               JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
               WHERE n.nspname LIKE 'v3_%' ORDER BY t.oid''',
        ).fetchall(),
        connection.execute('SELECT * FROM v3_meta.schema_migration ORDER BY migration_name').fetchall(),
    )


@pytest.mark.parametrize('unsafe', (
    'LOGIN', 'SUPERUSER', 'CREATEROLE', 'CREATEDB', 'REPLICATION', 'BYPASSRLS',
    'INHERIT', 'CONNECTION LIMIT 1', "PASSWORD 'fixture-only-password'", 'membership',
))
def test_unsafe_existing_executor_fails_closed_and_rolls_back_database(unsafe):
    with canonical_database() as first:
        with installed_purge(first[0], apply_chain=True):
            with canonical_database() as second:
                connection = second[0]
                for migration in CHAIN:
                    connection.execute((MIGRATIONS / migration).read_text())
                before = _schema_state(connection)
                message = 'membership' if unsafe == 'membership' else 'password' if unsafe.startswith('PASSWORD') else 'attributes'
                # Alter cluster state only in this transaction. The failed
                # migration rolls it back too, preserving other databases.
                with pytest.raises(psycopg.errors.RaiseException, match=f'unsafe {EXECUTOR} {message}'):
                    with connection.transaction():
                        if unsafe == 'membership':
                            parent = sql.Identifier('purge_parent_' + uuid4().hex)
                            connection.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(parent))
                            connection.execute(sql.SQL('GRANT {} TO {}').format(parent, sql.Identifier(EXECUTOR)))
                        else:
                            connection.execute(sql.SQL('ALTER ROLE {} {}').format(
                                sql.Identifier(EXECUTOR), sql.SQL(unsafe),
                            ))
                        connection.execute((MIGRATIONS / PURGE_MIGRATION).read_text())
                assert _schema_state(connection) == before
                assert connection.execute("SELECT to_regclass('v3_meta.derived_generation_purge_request')").fetchone() == (None,)


@pytest.mark.parametrize('creator', ('superuser', 'non_superuser'))
@pytest.mark.parametrize('unsafe', ('extra_member', 'creator_admin'))
def test_existing_executor_refuses_unsafe_incoming_memberships(creator, unsafe):
    with canonical_database() as first:
        with installed_purge(first[0], creator=creator, apply_chain=True):
            with canonical_database() as second:
                connection = second[0]
                if creator == 'non_superuser':
                    _grant_application_create(connection)
                    connection.execute('SET SESSION AUTHORIZATION edfinder_v3')
                for migration in CHAIN:
                    connection.execute((MIGRATIONS / migration).read_text())
                creating_role = connection.execute('SELECT current_user').fetchone()[0]
                connection.execute('RESET SESSION AUTHORIZATION')
                before = _schema_state(connection)
                with pytest.raises(psycopg.errors.RaiseException, match=f'unsafe {EXECUTOR} incoming membership'):
                    with connection.transaction():
                        member = creating_role
                        if unsafe == 'extra_member':
                            member = 'purge_extra_' + uuid4().hex
                            connection.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(member)))
                        connection.execute(sql.SQL(
                            'GRANT v3_derived_purge_executor TO {} WITH SET TRUE, INHERIT FALSE, ADMIN {}',
                        ).format(sql.Identifier(member), sql.SQL('TRUE' if unsafe == 'creator_admin' else 'FALSE')))
                        if creator == 'non_superuser':
                            connection.execute('SET SESSION AUTHORIZATION edfinder_v3')
                        connection.execute((MIGRATIONS / PURGE_MIGRATION).read_text())
                connection.execute('RESET SESSION AUTHORIZATION')
                assert _schema_state(connection) == before
                assert connection.execute("SELECT to_regclass('v3_meta.derived_generation_purge_request')").fetchone() == (None,)


@pytest.mark.parametrize('membership', ('missing', 'no_set', 'inherit'))
def test_adoption_never_repairs_non_superuser_creator_membership(membership):
    with canonical_database() as first:
        with installed_purge(first[0], creator='non_superuser', apply_chain=True):
            with canonical_database() as second:
                connection = second[0]
                _grant_application_create(connection)
                connection.execute('SET SESSION AUTHORIZATION edfinder_v3')
                for migration in CHAIN:
                    connection.execute((MIGRATIONS / migration).read_text())
                connection.execute('RESET SESSION AUTHORIZATION')
                before = _schema_state(connection)
                with pytest.raises(psycopg.errors.RaiseException, match='purge creator needs SET without INHERIT'):
                    with connection.transaction():
                        connection.execute('REVOKE v3_derived_purge_executor FROM edfinder_v3')
                        if membership != 'missing':
                            options = 'SET FALSE, INHERIT FALSE' if membership == 'no_set' else 'SET TRUE, INHERIT TRUE'
                            connection.execute(sql.SQL('GRANT v3_derived_purge_executor TO edfinder_v3 WITH {}').format(
                                sql.SQL(options),
                            ))
                        connection.execute('SET SESSION AUTHORIZATION edfinder_v3')
                        connection.execute((MIGRATIONS / PURGE_MIGRATION).read_text())
                connection.execute('RESET SESSION AUTHORIZATION')
                assert _schema_state(connection) == before


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
def _fresh_purge_controller(connection):
    """Retire the application session exempted by the fence's recycle step."""
    if connection.info.user != APPLICATION:
        yield connection
        return
    app_dsn = make_conninfo(connection.info.dsn, password=connection.info.password)
    connection.close()
    with psycopg.connect(app_dsn, autocommit=True) as controller:
        assert controller.execute('SHOW default_transaction_read_only').fetchone()[0] == 'on'
        controller.execute('SET ROLE v3_derived_purge_executor')
        controller.execute('SET default_transaction_read_only=off')
        yield controller


@contextmanager
def _application_worker(connection):
    connection.execute('RESET ROLE')
    test_password = uuid4().hex
    connection.execute(sql.SQL('ALTER ROLE edfinder_v3 PASSWORD {}').format(sql.Literal(test_password)))
    granted_membership = False
    if connection.execute('SELECT rolsuper FROM pg_roles WHERE rolname=current_user').fetchone()[0] and not connection.execute(
        'SELECT 1 FROM pg_auth_members WHERE roleid=%s::regrole AND member=%s::regrole', (EXECUTOR, APPLICATION),
    ).fetchone():
        connection.execute('GRANT v3_derived_purge_executor TO edfinder_v3 WITH SET TRUE, INHERIT FALSE')
        granted_membership = True
    app_dsn = make_conninfo(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL'],
                           dbname=connection.info.dbname, user=APPLICATION, password=test_password)
    connection.execute('SET ROLE v3_derived_purge_executor')
    try:
        with psycopg.connect(app_dsn, autocommit=True) as worker:
            worker.execute('SET ROLE v3_derived_purge_executor')
            worker.execute('SET default_transaction_read_only=off')
            worker.execute("SET statement_timeout='20s'")
            yield worker
    finally:
        if granted_membership:
            connection.execute('RESET ROLE')
            connection.execute('REVOKE v3_derived_purge_executor FROM edfinder_v3')
            connection.execute('SET ROLE v3_derived_purge_executor')


@contextmanager
def _running_operation(worker, command, parameters=None):
    """Cancel and join before releasing a blocker or closing the worker."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(worker.execute, command, parameters)
        try:
            yield future
        finally:
            if not future.done():
                worker.cancel()
            try:
                future.result(timeout=10)
            except psycopg.errors.QueryCanceled:
                pass
            except TimeoutError:
                worker.close()
                raise


def _wait_for_database_operation(connection, worker, future, kind):
    # Activity fields are hidden from the executor for other login roles.
    # Observe as the fixture login; cancellation still runs as the executor.
    connection.execute('RESET ROLE')
    try:
        _observe_database_operation(connection, worker, future, kind)
    finally:
        connection.execute('SET ROLE v3_derived_purge_executor')


def _observe_database_operation(connection, worker, future, kind):
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
            'waiting_rewrite': '''SELECT EXISTS(SELECT 1 FROM pg_stat_activity a JOIN pg_locks l ON l.pid=a.pid
                WHERE a.pid=%s AND a.state='active' AND a.wait_event_type='Lock'
                  AND l.locktype='relation'
                  AND l.database=(SELECT oid FROM pg_database WHERE datname=current_database())
                  AND l.relation='v3_derived.system_search'::regclass
                  AND l.mode='AccessExclusiveLock' AND NOT l.granted)''',
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
    disabled = connection.execute(
        "SELECT operational_payload FROM v3_meta.derived_generation_purge_event WHERE event_kind='AUTOVACUUM_DISABLED'",
    ).fetchall()
    connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)', (purge_id, 'system_search'))
    assert connection.execute(
        "SELECT operational_payload FROM v3_meta.derived_generation_purge_event WHERE event_kind='AUTOVACUUM_DISABLED'",
    ).fetchall() == disabled
    with pytest.raises(psycopg.Error):
        with connection.transaction():
            connection.execute('SELECT v3_meta.complete_derived_generation_purge(%s,%s)',
                               (purge_id, Jsonb(_receipt())))
    _abort_autovacuum_fence(connection, purge_id, 'system_search')
    assert options() == before
    assert connection.execute(
        "SELECT operational_payload FROM v3_meta.derived_generation_purge_event WHERE event_kind='AUTOVACUUM_RESTORED'",
    ).fetchall() == disabled
    connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,true)', (purge_id, 'system_search'))


def test_services_quiesce_requires_one_open_record_and_exact_restore_set(database):
    connection = database[0]
    ids = _authorize(database)
    first, second = (ids[identifier] for _, identifier in TARGETS)
    containers = {'containers': ['api', 'worker']}
    smaller = {'containers': ['api']}
    connection.execute('SELECT v3_meta.purge_record_event(%s,%s,NULL,%s)',
                       (first, 'SERVICES_QUIESCED', Jsonb(containers)))
    before = _count(connection, 'v3_meta.derived_generation_purge_event')
    for request_id in (first, second):
        with pytest.raises(psycopg.errors.RaiseException, match='services already quiesced'):
            with connection.transaction():
                connection.execute('SELECT v3_meta.purge_record_event(%s,%s,NULL,%s)',
                                   (request_id, 'SERVICES_QUIESCED', Jsonb(smaller)))
        with pytest.raises(psycopg.errors.RaiseException, match='restore container set mismatch'):
            with connection.transaction():
                connection.execute('SELECT v3_meta.purge_record_event(%s,%s,NULL,%s)',
                                   (request_id, 'SERVICES_RESTORED', Jsonb(smaller)))
    assert _count(connection, 'v3_meta.derived_generation_purge_event') == before
    connection.execute('SELECT v3_meta.purge_record_event(%s,%s,NULL,%s)',
                       (second, 'SERVICES_RESTORED', Jsonb(containers)))
    assert connection.execute(
        "SELECT purge_id,operational_payload FROM v3_meta.derived_generation_purge_event WHERE event_kind='SERVICES_RESTORED'",
    ).fetchall() == [(first, containers)]
    # Once the exact set is restored, a new quiesce cycle may start.
    connection.execute('SELECT v3_meta.purge_record_event(%s,%s,NULL,%s)',
                       (second, 'SERVICES_QUIESCED', Jsonb(smaller)))
    connection.execute('SELECT v3_meta.purge_record_event(%s,%s,NULL,%s)',
                       (second, 'SERVICES_RESTORED', Jsonb(smaller)))


def test_writer_fence_cannot_open_new_cycle_until_restore_is_verified(database):
    connection = database[0]
    ids = _authorize(database)
    first, second = (ids[identifier] for _, identifier in TARGETS)
    _writer_fence(connection, first)
    connection.execute('SELECT v3_meta.purge_set_writer_fence(%s,false)', (first,))
    connection.execute('RESET ROLE')
    opening = connection.execute(
        "SELECT (v3_meta.purge_open_event(%s,NULL,'WRITER_FENCE_ENABLED',ARRAY['WRITER_FENCE_RESTORED'])).event_sequence",
        (first,),
    ).fetchone()[0]
    assert opening is not None
    assert connection.execute(
        """SELECT option_value FROM pg_db_role_setting s, LATERAL pg_options_to_table(s.setconfig)
           WHERE s.setrole='edfinder_v3'::regrole AND option_name='default_transaction_read_only'
             AND s.setdatabase IN (0,(SELECT oid FROM pg_database WHERE datname=current_database()))""",
    ).fetchall() == []
    connection.execute('SET ROLE v3_derived_purge_executor')
    before = _count(connection, 'v3_meta.derived_generation_purge_event')
    connection.execute('SELECT v3_meta.purge_set_writer_fence(%s,true)', (second,))
    assert _count(connection, 'v3_meta.derived_generation_purge_event') == before
    connection.execute('SELECT v3_meta.purge_recycle_writer_sessions(%s,false)', (second,))
    connection.execute('SELECT v3_meta.purge_verify_writer_fence(%s,false,%s)', (second, 'off'))
    connection.execute('RESET ROLE')
    assert connection.execute(
        "SELECT (v3_meta.purge_open_event(%s,NULL,'WRITER_FENCE_ENABLED',ARRAY['WRITER_FENCE_RESTORED'])).event_sequence",
        (first,),
    ).fetchone()[0] is None
    connection.execute('SET ROLE v3_derived_purge_executor')
    original = connection.execute(
        "SELECT operational_payload->'prior' FROM v3_meta.derived_generation_purge_event WHERE event_kind='WRITER_FENCE_ENABLED' ORDER BY event_sequence LIMIT 1",
    ).fetchone()[0]
    restored = connection.execute(
        "SELECT operational_payload->'prior' FROM v3_meta.derived_generation_purge_event WHERE event_kind='WRITER_FENCE_RESTORED' ORDER BY event_sequence DESC LIMIT 1",
    ).fetchone()[0]
    assert restored == original
    _writer_fence(connection, second)


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
    with _fresh_purge_controller(connection) as connection:
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
            with _running_operation(worker, 'SELECT v3_meta.purge_derived_payload_batch(%s,%s,%s)',
                                    (purge_id, 'system_search', 3)) as future:
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


@pytest.mark.parametrize('command', (
    'VACUUM (FULL, ANALYZE) v3_derived.system_search',
    '  VaCuUm\n(FULL)  v3_derived.system_search; ',
    'VACUUM FULL v3_derived.system_search',
))
def test_cancel_rewrite_waiting_for_relation_lock_rolls_back_and_resolves(database, command):
    connection = database[0]
    ids = _authorize(database)
    purge_id = ids[TARGETS[0][1]]
    _writer_fence(connection, purge_id)
    with _fresh_purge_controller(connection) as connection:
        connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)', (purge_id, 'system_search'))
        for request_id in ids.values():
            assert _batch(connection, request_id, 'system_search') == 12
        connection.execute('SELECT v3_meta.complete_derived_payload_relation(%s,%s,%s)',
                           (purge_id, 'system_search', Jsonb(_receipt())))
        before = connection.execute("SELECT pg_relation_filenode('v3_derived.system_search')").fetchone()[0]
        with _application_worker(connection) as worker:
            worker.execute('SELECT v3_meta.purge_record_event(%s,%s,%s,%s)',
                           (purge_id, 'REWRITE_STARTED', 'system_search', Jsonb(_receipt())))
            with _application_worker(connection) as blocker:
                with blocker.transaction():
                    blocker.execute('LOCK TABLE v3_derived.system_search IN ACCESS SHARE MODE')
                    with _running_operation(worker, command) as future:
                        # Whitespace and case normalization must still identify the
                        # fixed command, before PostgreSQL exposes a progress row.
                        _wait_for_database_operation(connection, worker, future, 'waiting_rewrite')
                        assert not connection.execute(
                            'SELECT EXISTS(SELECT 1 FROM pg_stat_progress_cluster WHERE pid=%s)',
                            (worker.info.backend_pid,),
                        ).fetchone()[0]
                        assert connection.execute('SELECT v3_meta.cancel_purge_rewrite(%s,%s)',
                                                  (purge_id, 'system_search')).fetchone()[0]
                        with pytest.raises(psycopg.errors.QueryCanceled):
                            future.result(timeout=10)
        assert connection.execute("SELECT pg_relation_filenode('v3_derived.system_search')").fetchone()[0] == before
        assert _count(connection, 'v3_derived.system_search', SURVIVOR) == 12
        connection.execute('SELECT v3_meta.purge_record_event(%s,%s,%s,%s)',
                           (purge_id, 'REWRITE_ROLLED_BACK', 'system_search', Jsonb({'recovered': True})))
        assert connection.execute(
            '''SELECT event_kind FROM v3_meta.derived_generation_purge_event
               WHERE purge_id=%s AND event_kind IN ('REWRITE_STARTED','REWRITE_CANCEL_REQUESTED','REWRITE_ROLLED_BACK')
               ORDER BY event_sequence''', (purge_id,),
        ).fetchall() == [('REWRITE_STARTED',), ('REWRITE_CANCEL_REQUESTED',), ('REWRITE_ROLLED_BACK',)]
        connection.execute('RESET ROLE')
        assert connection.execute(
            '''SELECT (v3_meta.purge_open_event(
                   %s,'system_search','REWRITE_STARTED',ARRAY['REWRITE_VERIFIED','REWRITE_ROLLED_BACK'])).event_sequence IS NULL''',
            (purge_id,),
        ).fetchone()[0]


def test_controller_failure_cancels_waiting_rewrite_and_closes_worker_and_blocker(database):
    connection = database[0]
    with pytest.raises(RuntimeError, match='injected controller failure'):
        with _application_worker(connection) as worker, _application_worker(connection) as blocker:
            pids = [worker.info.backend_pid, blocker.info.backend_pid]
            with blocker.transaction():
                blocker.execute('LOCK TABLE v3_derived.system_search IN ACCESS SHARE MODE')
                with _running_operation(worker, 'VACUUM (FULL) v3_derived.system_search') as future:
                    _wait_for_database_operation(connection, worker, future, 'waiting_rewrite')
                    raise RuntimeError('injected controller failure')
    assert worker.closed and blocker.closed
    with pytest.raises(psycopg.errors.QueryCanceled):
        future.result(timeout=10)
    connection.execute('RESET ROLE')
    deadline = monotonic() + 10
    while connection.execute(
        'SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE pid=ANY(%s))', (pids,),
    ).fetchone()[0]:
        assert monotonic() < deadline, 'worker or blocker backend survived cleanup'
        sleep(0.01)
    # No opaque backend or abandoned writing transaction may poison the next
    # authorization in the same database after controller cleanup.
    assert len(_authorize(database)) == 2


@pytest.mark.parametrize('operation', ('rewrite', 'analyze'))
def test_cancel_rewrite_or_trailing_analyze_preserves_relation_and_recovers(database, operation):
    connection = database[0]
    ids = _authorize(database)
    purge_id = ids[TARGETS[0][1]]
    _writer_fence(connection, purge_id)
    with _fresh_purge_controller(connection) as connection:
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
            with _running_operation(worker, command) as future:
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
    with _fresh_purge_controller(connection) as connection:
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
    with _fresh_purge_controller(connection) as connection:
        before = _count(connection, 'v3_meta.derived_generation_purge_event')
        with _application_worker(connection) as worker:
            worker.execute("SET vacuum_cost_delay='100ms'")
            worker.execute('SET vacuum_cost_limit=1')
            with _running_operation(worker,
                                    'VACUUM (DISABLE_PAGE_SKIPPING, INDEX_CLEANUP ON) v3_derived.system_search') as future:
                _wait_for_database_operation(connection, worker, future, 'vacuum')
                with pytest.raises(psycopg.errors.RaiseException, match='vacuum active on purge relation'):
                    with connection.transaction():
                        connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)',
                                           (purge_id, 'system_search'))
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
    with _fresh_purge_controller(connection) as connection:
        connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)', (purge_id, 'system_search'))
        with _application_worker(connection) as departed:
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


def test_verified_rewrite_retries_do_not_open_rewrite_or_autovacuum_fence(database):
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
    connection.execute('VACUUM (FULL, ANALYZE) v3_derived.system_search')
    connection.execute('SELECT pg_stat_force_next_flush()')
    connection.execute('SELECT pg_stat_clear_snapshot()')
    connection.execute('SELECT v3_meta.purge_record_event(%s,%s,%s,%s)',
                       (purge_id, 'REWRITE_VERIFIED', 'system_search', Jsonb(_receipt())))
    before = _count(connection, 'v3_meta.derived_generation_purge_event')
    for request_id in ids.values():
        with pytest.raises(psycopg.errors.RaiseException, match='rewrite already verified'):
            with connection.transaction():
                connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)',
                                   (request_id, 'system_search'))
        with pytest.raises(psycopg.errors.RaiseException, match='rewrite already verified'):
            with connection.transaction():
                connection.execute('SELECT v3_meta.purge_record_event(%s,%s,%s,%s)',
                                   (request_id, 'REWRITE_STARTED', 'system_search', Jsonb(_receipt())))
    assert _count(connection, 'v3_meta.derived_generation_purge_event') == before
    assert connection.execute(
        "SELECT event_kind,count(*) FROM v3_meta.derived_generation_purge_event WHERE event_kind IN ('REWRITE_STARTED','AUTOVACUUM_DISABLED') GROUP BY event_kind ORDER BY event_kind",
    ).fetchall() == [('AUTOVACUUM_DISABLED', 1), ('REWRITE_STARTED', 1)]


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
            # Select an ordinary column: PostgreSQL rejects assignments to
            # GENERATED ALWAYS columns before it checks executor privileges.
            column = connection.execute(
                '''SELECT attname FROM pg_attribute WHERE attrelid=%s::regclass
                   AND attnum>0 AND NOT attisdropped AND attidentity='' AND attgenerated=''
                   ORDER BY attnum LIMIT 1''', (relation,),
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
