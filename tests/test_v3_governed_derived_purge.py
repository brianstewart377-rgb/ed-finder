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
from types import SimpleNamespace
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
from scripts.operator.lib import v3_purge_transactions as purge_transactions  # noqa: E402
from scripts.operator.lib import v3_generation_purge as purge_operator  # noqa: E402
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
        # The fixture bulk-loads canonical/metadata rows before these tests.
        # Their automatic ANALYZE, and catalog maintenance after the migration
        # DDL or a rewrite, can acquire an XID even though no competing
        # application writer exists. 016 deliberately rejects *every* other
        # backend_xid, including an autovacuum worker's; do not relax that
        # production check to hide this disposable-database scheduling race.
        connection.execute('RESET SESSION AUTHORIZATION')
        _suppress_fixture_automatic_maintenance(connection)
        if creator == 'non_superuser':
            connection.execute('SET SESSION AUTHORIZATION edfinder_v3')
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


def _suppress_fixture_automatic_maintenance(connection):
    """Keep background workers out; explicit VACUUM/ANALYZE tests still run.

    Preserve the purge tables' unset autovacuum_enabled defaults so the fence
    restoration tests continue exercising the real unset and false cases.
    These fresh disposable tables cannot approach anti-wraparound thresholds.
    Migration/rewrite DDL also schedules maintenance of pg_class, pg_attribute
    and the other database-local catalogs. Suppressing only application tables
    leaves those workers racing later negative assertions in purge_assert_phase.
    Never alter shared catalogs, whose options affect other test databases.
    """
    assert connection.info.dbname.startswith('v4_test_')
    with connection.transaction():
        # Only this fixture's superuser setup connection may change the fresh
        # database's catalog reloptions; the setting ends with this transaction.
        connection.execute("SET LOCAL allow_system_table_mods=on")
        _set_fixture_maintenance_options(connection)
    _wait_for_fixture_maintenance(connection)


def _set_fixture_maintenance_options(connection):
    for schema, table, toast in connection.execute(
        '''SELECT n.nspname,c.relname,c.reltoastrelid<>0 FROM pg_class c
           JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE (n.nspname LIKE 'v3_%' OR n.nspname='pg_catalog')
             AND c.relkind='r' AND NOT c.relisshared
           ORDER BY n.nspname,c.relname''',
    ).fetchall():
        if schema == 'v3_derived' and table in RELATIONS:
            options = '''autovacuum_analyze_threshold=2147483647,
                autovacuum_analyze_scale_factor=0,
                autovacuum_vacuum_threshold=2147483647,
                autovacuum_vacuum_scale_factor=0'''
            if toast:
                options += ''',toast.autovacuum_vacuum_threshold=2147483647,
                    toast.autovacuum_vacuum_scale_factor=0'''
        else:
            options = 'autovacuum_enabled=false'
            if toast:
                options += ',toast.autovacuum_enabled=false'
        connection.execute(sql.SQL('ALTER TABLE {} SET ({})').format(
            sql.Identifier(schema, table), sql.SQL(options),
        ))


def _wait_for_fixture_maintenance(connection):
    # A worker already selected before its table's options changed is allowed
    # to finish, never canceled. Retain 016's predicate and fail on a fixed
    # deadline rather than retrying an arbitrary failed mutation.
    deadline = monotonic() + 10
    while competing := connection.execute(
        '''SELECT pid,backend_type,state,backend_xid::text,left(query,200)
           FROM pg_stat_activity
           WHERE datname=current_database() AND pid<>pg_backend_pid()
             AND (backend_xid IS NOT NULL OR
                  (backend_type='client backend' AND state IS NULL))''',
    ).fetchall():
        if monotonic() >= deadline:
            pytest.fail(f'disposable purge fixture still has competing backends after 10 seconds: {competing!r}')
        sleep(0.05)


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
                    # 019 (copy-and-drop), 020 (its swap lock order) and 021
                    # (its verification chunk bound) must be installed by the
                    # same payload owner.
                    if creator == 'non_superuser' and migration.name in (
                            *CHAIN, PURGE_MIGRATION, '019_v3_purge_copy_and_drop.sql',
                            '020_v3_purge_swap_lock_order.sql', '021_v3_purge_verify_chunk_bound.sql'):
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


def _seed(data, *, survivor_search_built=True, survivor_products_published=False):
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
        if identifier == SURVIVOR and survivor_products_published:
            _build_survivor_archetype(connection, [record['id64'] for record in records])
        if identifier != TARGETS[0][1]:
            seal_source(connection, identifier, _eof(data))
        if identifier == SURVIVOR:
            assert validate_generation(connection, identifier)['status'] == 'VERIFIED'
            if survivor_products_published:
                _ready_survivor_products(connection)
            assert connection.execute(
                'SELECT v3_meta.publish_derived_generation(%s,%s,%s,%s,%s,%s,%s,%s)',
                (identifier, None, 0, snapshot.generation_id, snapshot.publication_sequence,
                 'fixture', 'published survivor', []),
            ).fetchone()[0] == 1
            if survivor_products_published:
                for code in ('system_search', 'system_archetype'):
                    connection.execute('SELECT v3_meta.publish_derived_product(%s,%s,%s)',
                                       (SURVIVOR, code, 'fixture'))
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


def _build_survivor_archetype(connection, system_ids):
    """One wide archetype row per published survivor system, as F2d builds."""
    from tests.test_v3_derived_product_publication import _insert_archetype_row
    manifest = {'product_code': 'system_archetype', 'product_version': 'v3-archetype-test'}
    connection.execute(
        '''INSERT INTO v3_meta.derived_product (derived_generation_id,product_code,product_version,
               manifest,manifest_sha256,expected_rows)
           VALUES (%s,'system_archetype','v3-archetype-test',%s,%s,%s)''',
        (SURVIVOR, Jsonb(manifest), b'a' * 32, len(system_ids)),
    )
    for system_id in system_ids:
        _insert_archetype_row(connection, SURVIVOR, system_id)


def _ready_survivor_products(connection):
    connection.execute(
        '''UPDATE v3_meta.derived_product SET lifecycle_state='READY',validation_receipt=%s,
               validation_sha256=%s,validated_at=transaction_timestamp()
           WHERE derived_generation_id=%s''',
        (Jsonb({'status': 'VERIFIED'}), b'v' * 32, SURVIVOR),
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


def _operator_query(connection, calls=None):
    """Run the operator's exact bounded SQL on this disposable database.

    ClientCursor binds values safely while supporting the fixed multi-statement
    transaction used by psql in production. Return evidence only after COMMIT,
    matching the production adapter's successful-exit contract.
    """
    def query(statement, parameters=None, *, write=False):
        # Runtime starts a fresh psql login for each query. Reusing the fixture
        # connection must not leave the previous query's executor SET ROLE in
        # force for the deliberately owner-role competing-writer observation.
        connection.execute('RESET ROLE')
        if calls is not None:
            calls.append({'write': write, 'statement': statement})
        results = []
        try:
            with psycopg.ClientCursor(connection) as cursor:
                cursor.execute(statement, parameters)
                while True:
                    if cursor.description is not None:
                        rows = cursor.fetchall()
                        assert len(rows) == 1 and len(rows[0]) == 1
                        results.append(rows[0][0])
                    if not cursor.nextset():
                        break
            if statement == purge_transactions.BATCH_SQL:
                assert len(results) == 2 and all(isinstance(result, dict) for result in results)
                assert type(results[0].get('start_event')) is int and results[0]['start_event'] > 0
                assert set(results[0]) == {'start_event'}
                assert set(results[1]) == {'rows_affected'}
                return {**results[0], **results[1]}
            assert len(results) == 1
            return results[0]
        except BaseException:
            connection.rollback()
            raise
    return query


def test_operator_plan_and_status_observation_sql_is_readonly_under_executor(database):
    connection = database[0]
    _seed(database)
    calls = []
    query = _operator_query(connection, calls)
    identity = query(purge_operator.IDENTITY_SQL)
    assert identity['database'] == connection.info.dbname
    assert identity['current_user'] == EXECUTOR
    assert identity['data_directory'] is None
    assert identity['application_role'] == APPLICATION
    assert identity['version'] >= 180000
    objects = query(purge_operator.OBJECTS_SQL)
    assert isinstance(objects, list) and objects
    assert {'v3_derived.' + relation for relation in RELATIONS} <= {
        item['relation'] for item in objects
    }
    assert all(item['path'] and item['total_bytes'] >= 0 for item in objects)
    ages = query(purge_operator.AGES_SQL)
    assert int(ages['xid_next']) > 0
    assert {item['relation_code'] for item in ages['objects']} == set(RELATIONS)
    assert all(item['xid_limit'] > 0 and item['mxid_limit'] > 0 for item in ages['objects'])
    # jsonb renders the oid type as text; the controller's own validator must
    # accept the live PostgreSQL 18 shape, not only hand-built fixtures.
    assert all(type(item['oid']) is int for item in ages['objects'])
    validated = purge_operator.age_sample(SimpleNamespace(query=query))
    assert {(item['relation_code'], item['scope']) for item in validated['objects']} == {
        (item['relation_code'], item['scope']) for item in ages['objects']}
    wal = query(purge_operator.WAL_SQL)
    assert wal['lsn'] and wal['bytes'] is None
    assert isinstance(wal['archiver'], dict)
    assert isinstance(wal['slots'], list) and isinstance(wal['replication'], list)
    pointers = query(purge_operator.POINTER_IDENTITIES_SQL)
    assert pointers['derived']['derived_generation_id'] == str(SURVIVOR)
    assert pointers['derived']['generation_key'] == 'ratings_v4_prod_p4_parallel_v1'
    assert all(pointers[k]['publication_sequence'] > 0 for k in ('canonical', 'derived', 'spatial'))
    summary_oid = connection.execute(
        """SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname='v3_app' AND c.relname='system_archetype_summary'""",
    ).fetchone()[0]
    assert connection.execute(
        """SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname='v3_derived' AND c.relname='system_archetype_summary'""",
    ).fetchone() is None
    # 016 grants the executor no v3_app access. The direct payload check must
    # work with that unchanged privilege boundary, including unpublished rows.
    assert not connection.execute(
        "SELECT has_schema_privilege(current_user,'v3_app','USAGE')",
    ).fetchone()[0]
    assert not connection.execute(
        "SELECT has_table_privilege(current_user,%s,'SELECT')", (summary_oid,),
    ).fetchone()[0]
    extra = query(purge_operator.EXTRA_COUNTS_SQL)
    assert set(extra) == {str(identifier) for _, identifier in TARGETS} | {str(SURVIVOR)}
    exclusions = {'cluster_run', 'cluster', 'cluster_member', 'system_archetype'}
    assert all(set(counts) == exclusions for counts in extra.values())
    assert all(not any(counts.values()) for counts in extra.values())
    excluded_counts = query(purge_transactions.EXCLUSIONS_SQL)
    assert set(excluded_counts) == exclusions and not any(excluded_counts.values())
    progress = query(purge_operator.PROGRESS_SQL)
    assert progress['requests'] == []
    assert progress['relation_progress'] == [] and progress['events'] == []
    metadata = query(purge_operator.STATUS_METADATA_SQL)
    assert metadata['snapshot']['derived']['derived_generation_id'] == str(SURVIVOR)
    assert metadata['snapshot']['survivors'] is None
    assert {target['id'] for target in metadata['targets']} == {str(identifier) for _, identifier in TARGETS}
    assert not any(call['write'] for call in calls)
    assert all('BEGIN READ ONLY' in call['statement'] for call in calls)
    assert _count(connection, 'v3_meta.derived_generation_purge_request') == 0


def test_published_survivor_read_freezes_exact_archetype_rows_under_executor(database):
    connection = database[0]
    _seed(database, survivor_products_published=True)
    calls = []
    query = _operator_query(connection, calls)
    observed = query(purge_operator.PUBLISHED_SURVIVORS_SQL)
    systems = _count(connection, 'v3_derived.system_rating_vector', SURVIVOR)
    assert systems > 0
    assert observed['system_archetype_rows'] == _count(connection, 'v3_derived.system_archetype', SURVIVOR) == systems
    assert set(observed['products']) == {'system_search', 'system_archetype'}
    assert all(product['lifecycle_state'] == 'READY' and isinstance(product['published_at'], str)
               for product in observed['products'].values())
    snapshot = query('SET ROLE v3_derived_purge_executor; SELECT v3_meta.purge_snapshot();')
    assert snapshot['survivors']['system_search'] == systems
    runtime = SimpleNamespace(query=query)
    frozen = purge_operator.published_survivors(runtime, snapshot['survivors'], require_published=True)
    assert frozen == observed
    report = {}
    reviewed = {'published_survivors': frozen}
    assert purge_operator.survivor_gate(runtime, reviewed, report, 'published_survivors_after') == frozen
    # 016's snapshot does not see the published archetype product: a changed
    # survivor row count is caught only by this operator read. A guard-free
    # owner fault injection stands in for drift the guards should prevent.
    connection.execute('RESET ROLE')
    connection.execute('ALTER TABLE v3_derived.system_archetype DISABLE TRIGGER USER')
    connection.execute('DELETE FROM v3_derived.system_archetype WHERE derived_generation_id=%s AND system_id64='
                       '(SELECT min(system_id64) FROM v3_derived.system_archetype WHERE derived_generation_id=%s)',
                       (SURVIVOR, SURVIVOR))
    connection.execute('ALTER TABLE v3_derived.system_archetype ENABLE TRIGGER USER')
    assert query('SET ROLE v3_derived_purge_executor; SELECT v3_meta.purge_snapshot();') == snapshot
    with pytest.raises(ValueError, match='published_archetype_survivor_count_drift'):
        purge_operator.survivor_gate(runtime, reviewed, report, 'published_survivors_after')
    assert not any(call['write'] for call in calls if call['statement'] == purge_operator.PUBLISHED_SURVIVORS_SQL)
    assert all('BEGIN READ ONLY' in call['statement'] for call in calls
               if call['statement'] == purge_operator.PUBLISHED_SURVIVORS_SQL)


def test_production_survivor_proof_refuses_unpublished_finder_products(database):
    connection = database[0]
    _seed(database)
    query = _operator_query(connection)
    snapshot = query('SET ROLE v3_derived_purge_executor; SELECT v3_meta.purge_snapshot();')
    runtime = SimpleNamespace(query=query)
    observed = purge_operator.published_survivors(runtime, snapshot['survivors'])
    assert observed['system_archetype_rows'] == 0
    with pytest.raises(ValueError, match='published_survivor_product_count_unproven'):
        purge_operator.published_survivors(runtime, snapshot['survivors'], require_published=True)


def test_status_relation_sql_isolates_access_exclusive_lock_timeout(database):
    connection = database[0]
    _seed(database)
    expected = {
        relation: {
            'targets': {str(identifier): _count(connection, 'v3_derived.' + relation, identifier)
                        for _, identifier in TARGETS},
            'survivors': _count(connection, 'v3_derived.' + relation, SURVIVOR),
        } for relation in RELATIONS
    }
    query = _operator_query(connection)
    assert set(purge_operator.STATUS_RELATION_SQL) == set(RELATIONS)
    lock_dsn = make_conninfo(connection.info.dsn, password=connection.info.password)
    with psycopg.connect(lock_dsn, autocommit=True) as rewrite:
        # VACUUM FULL holds this same relation lock. A catalog-only status
        # observation must remain useful while its optional count probe waits.
        with rewrite.transaction():
            rewrite.execute('LOCK TABLE v3_derived.system_search IN ACCESS EXCLUSIVE MODE')
            assert query(purge_operator.STATUS_METADATA_SQL)['snapshot']['survivors'] is None
            assert query(purge_operator.PROGRESS_SQL)['requests'] == []
            with pytest.raises(psycopg.errors.LockNotAvailable):
                query(purge_operator.STATUS_RELATION_SQL['system_search'])
            for relation in RELATIONS[1:]:
                observed = query(purge_operator.STATUS_RELATION_SQL[relation])
                assert observed['targets'] == expected[relation]['targets']
                assert observed['survivors'] == expected[relation]['survivors']
                assert observed['total_bytes'] > 0
    # A timed-out read leaves no failed transaction or false cached count.
    observed = query(purge_operator.STATUS_RELATION_SQL['system_search'])
    assert observed['targets'] == expected['system_search']['targets']
    assert observed['survivors'] == expected['system_search']['survivors']
    assert observed['total_bytes'] > 0


def test_operator_sql_layer_plans_authorizes_verifies_and_refuses_early_completion(database):
    connection = database[0]
    _seed(database)
    calls = []
    query = _operator_query(connection, calls)
    plan = purge_transactions.collect_plan(query, 'b' * 40, 'disposable-fixture', 'operator SQL validation')
    assert {(target['key'], target['state']) for target in plan['targets']} == {
        ('ratings_v4_prod_p4', 'BUILDING'), ('ratings_v4_prod_p4_opt1', 'VALIDATING'),
    }
    assert plan['snapshot']['derived']['derived_generation_id'] == str(SURVIVOR)
    assert all(plan['snapshot']['survivors'].values())
    assert not any(call['write'] for call in calls)
    assert _count(connection, 'v3_meta.derived_generation_purge_request') == 0
    authorized = purge_transactions.authorize(query, plan)
    ids = authorized['purge_ids']
    assert len(ids) == 2
    assert authorized['snapshot'] == plan['snapshot']
    assert authorized['competing_writer_wait']['remaining_competing_writers'] == 0
    calls.clear()
    empty = purge_transactions.verify_empty(query, purge_ids=ids)
    assert empty['empty'] is True and not any(empty['counts'].values())
    assert not any(call['write'] for call in calls)
    events_before = _count(connection, 'v3_meta.derived_generation_purge_event')
    with pytest.raises(purge_transactions.PurgeTransactionError, match='purge_completion_preconditions_failed'):
        purge_transactions.complete(query, plan, _receipt(), purge_ids=ids)
    assert not any(call['write'] for call in calls)
    assert _count(connection, 'v3_meta.derived_generation_purge_event') == events_before
    assert all(_count(connection, 'v3_derived.' + relation, TARGETS[0][1]) > 0 for relation in RELATIONS)


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
    assert all(value == prior for _, value in before)
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
    query = _operator_query(connection)
    # The stable application views hide unpublished generations. Both helper
    # queries must still observe and reject direct target payload rows.
    assert query(purge_operator.EXTRA_COUNTS_SQL)[str(generation_id)][exclusion] == 1
    assert query(purge_transactions.EXCLUSIONS_SQL)[exclusion] == 1
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
        _wait_for_fixture_maintenance(connection)
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
    # Exercise P2b1's exact completion SQL after real child-first deletion,
    # physical rewrites, ANALYZE, and verified restoration of every fence.
    # This is an idempotent completion; no synthetic rewrite receipt is used.
    reviewed_plan = connection.execute(
        'SELECT reviewed_plan FROM v3_meta.derived_generation_purge_request LIMIT 1',
    ).fetchone()[0]
    completed = purge_transactions.complete(
        _operator_query(connection), reviewed_plan, _receipt(),
        purge_ids=[str(identifier) for identifier in ids.values()],
    )
    assert set(completed['completed_ids']) == {str(identifier) for identifier in ids.values()}
    assert completed['competing_writer_wait']['remaining_competing_writers'] == 0
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
    _wait_for_fixture_maintenance(connection)
    connection.execute('SELECT v3_meta.purge_record_event(%s,%s,%s,%s)',
                       (purge_id, 'REWRITE_VERIFIED', 'system_search', Jsonb(_receipt())))
    before = _count(connection, 'v3_meta.derived_generation_purge_event')
    for request_id in ids.values():
        # A shared-catalog worker may have been selected in this database by
        # another fixture's role DDL; its options must remain cluster-wide.
        _wait_for_fixture_maintenance(connection)
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
    _wait_for_fixture_maintenance(connection)
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


def _fence_sql_rows(connection, statement):
    """Execute the exact multi-statement psql text, retaining its SELECT result."""
    cursor = connection.execute(statement, prepare=False)
    rows = []
    while True:
        if cursor.description is not None:
            rows = cursor.fetchall()
        if not cursor.nextset():
            return rows


@pytest.mark.parametrize(('opening', 'closing'), (
    ('BATCH_STARTED', 'BATCH_ROLLED_BACK'),
    ('REWRITE_STARTED', 'REWRITE_ROLLED_BACK'),
    ('SERVICES_QUIESCED', 'SERVICES_RESTORED'),
    ('WRITER_FENCE_ENABLED', 'WRITER_FENCE_RESTORED'),
    ('AUTOVACUUM_DISABLED', 'AUTOVACUUM_RESTORED'),
    ('FAILED_STOP', None),
))
def test_operator_fixed_sql_reports_every_real_016_state_and_verified_restoration(database, opening, closing):
    # This fixture installs 016 only. The fence's copy-aware STATE_SQL also reads
    # 019's functions (proved in tests/test_v3_purge_copy_operator_pg18.py); the
    # 016 semantics under test are the shared part, LEGACY_STATE_SQL.
    from scripts.operator.lib.v3_purge_state import LEGACY_STATE_SQL as STATE_SQL

    connection = database[0]
    purge_id = _authorize(database)[TARGETS[0][1]]
    connection.execute('RESET ROLE')
    relation = None if opening in ('SERVICES_QUIESCED', 'WRITER_FENCE_ENABLED') else 'system_search'
    connection.execute(
        '''INSERT INTO v3_meta.derived_generation_purge_event
           (purge_id,event_kind,relation_code,failure_evidence)
           VALUES(%s,%s,%s,%s)''',
        (purge_id, opening, relation, Jsonb({'integrity_failed': True}) if opening == 'FAILED_STOP' else None),
    )
    observed = _fence_sql_rows(connection, STATE_SQL)[0][0]
    assert observed['read_only'] == 'on'
    assert [row['event_kind'] for row in observed['unresolved']] == [opening]
    if closing is None:
        # An integrity failure remains a fence even after a recovery acknowledgement.
        sequence = observed['unresolved'][0]['event_sequence']
        connection.execute(
            '''INSERT INTO v3_meta.derived_generation_purge_event(purge_id,event_kind,operational_payload)
               VALUES(%s,'FAILED_STOP',%s)''',
            (purge_id, Jsonb({'acknowledge_failed_stop': sequence})),
        )
        assert _fence_sql_rows(connection, STATE_SQL)[0][0]['unresolved'] == observed['unresolved']
        return
    connection.execute(
        '''INSERT INTO v3_meta.derived_generation_purge_event(purge_id,event_kind,relation_code)
           VALUES(%s,%s,%s)''', (purge_id, closing, relation),
    )
    if opening == 'WRITER_FENCE_ENABLED':
        # 016 counts only verified=true, never a missing/false/string true value.
        assert _fence_sql_rows(connection, STATE_SQL)[0][0]['unresolved']
        for verified in (False, 'true'):
            connection.execute(
                '''INSERT INTO v3_meta.derived_generation_purge_event
                   (purge_id,event_kind,relation_code,operational_payload) VALUES(%s,%s,%s,%s)''',
                (purge_id, closing, relation, Jsonb({'verified': verified})),
            )
            assert _fence_sql_rows(connection, STATE_SQL)[0][0]['unresolved']
        connection.execute(
            '''INSERT INTO v3_meta.derived_generation_purge_event
               (purge_id,event_kind,operational_payload) VALUES(%s,%s,%s)''',
            (purge_id, closing, Jsonb({'verified': True})),
        )
    assert _fence_sql_rows(connection, STATE_SQL)[0][0]['unresolved'] == []


def test_operator_and_backup_sql_resolve_only_matching_record_and_live_backend(database):
    # This fixture installs 016 only. The fence's copy-aware STATE_SQL also reads
    # 019's functions (proved in tests/test_v3_purge_copy_operator_pg18.py); the
    # 016 semantics under test are the shared part, LEGACY_STATE_SQL.
    from scripts.operator.lib.v3_purge_state import LEGACY_STATE_SQL as STATE_SQL

    connection = database[0]
    ids = _authorize(database)
    connection.execute('RESET ROLE')
    source = (ROOT / 'deploy/v3-production/backup/pgbackrest-operation.sh').read_text()
    backup_sql = source.split("<<'SQL'\n", 1)[1].split('\nSQL', 1)[0]
    purge_id, other_id = ids.values()
    # PID plus backend_start, not PID alone, authenticates a live record.
    connection.execute(
        '''INSERT INTO v3_meta.derived_generation_purge_event
           (purge_id,event_kind,relation_code,backend_pid,backend_start)
           SELECT %s,'BATCH_STARTED','system_search',pid,backend_start
           FROM pg_stat_activity WHERE pid=pg_backend_pid()''', (purge_id,),
    )
    assert len(_fence_sql_rows(connection, backup_sql)) == 1
    # Another request's closure must not close this batch (even on the same plan).
    connection.execute(
        '''INSERT INTO v3_meta.derived_generation_purge_event(purge_id,event_kind,relation_code)
           VALUES(%s,'BATCH_COMMITTED','system_search')''', (other_id,),
    )
    assert len(_fence_sql_rows(connection, backup_sql)) == 1
    assert _fence_sql_rows(connection, STATE_SQL)[0][0]['unresolved'][0]['purge_id'] == str(purge_id)
    connection.execute(
        '''INSERT INTO v3_meta.derived_generation_purge_event(purge_id,event_kind,relation_code)
           VALUES(%s,'BATCH_ROLLED_BACK','system_search')''', (purge_id,),
    )
    assert _fence_sql_rows(connection, backup_sql) == []
    # Dead backend identity never suppresses scheduled backups, but still fences mutators.
    connection.execute(
        '''INSERT INTO v3_meta.derived_generation_purge_event
           (purge_id,event_kind,relation_code,backend_pid,backend_start)
           SELECT %s,'REWRITE_STARTED','system_search',pid,backend_start-interval '1 second'
           FROM pg_stat_activity WHERE pid=pg_backend_pid()''', (purge_id,),
    )
    assert _fence_sql_rows(connection, backup_sql) == []
    assert _fence_sql_rows(connection, STATE_SQL)[0][0]['unresolved'][0]['event_kind'] == 'REWRITE_STARTED'
    connection.execute(
        '''INSERT INTO v3_meta.derived_generation_purge_event(purge_id,event_kind,relation_code)
           VALUES(%s,'FAILED_STOP','system_search')''', (purge_id,),
    )
    assert _fence_sql_rows(connection, STATE_SQL)[0][0]['unresolved'] == []


@pytest.mark.parametrize('gate', ('floor', 'wal'))
def test_failed_stop_after_committed_batch_preserves_counts_and_allows_resume(database, gate):
    """A safety stop fences progress, without undoing an earlier small commit."""
    connection = database[0]
    purge_id = _authorize(database)[TARGETS[0][1]]
    _writer_fence(connection, purge_id)
    connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)',
                       (purge_id, 'system_search'))
    assert _batch(connection, purge_id, 'system_search', size=3) == 3
    assert _count(connection, 'v3_derived.system_search', TARGETS[0][1]) == 9
    unsafe = _receipt()
    unsafe.update({'filesystem_free_bytes': 99_999_999_999} if gate == 'floor'
                  else {'wal_healthy': False})
    before_events = _count(connection, 'v3_meta.derived_generation_purge_event')
    with pytest.raises(psycopg.Error):
        with connection.transaction():
            _start_batch(connection, purge_id, 'system_search', size=3, evidence=unsafe)
    assert _count(connection, 'v3_meta.derived_generation_purge_event') == before_events
    assert _count(connection, 'v3_derived.system_search', TARGETS[0][1]) == 9
    failure = {**unsafe, 'code': gate + '_gate_failed', 'integrity_failed': False}
    connection.execute('SELECT v3_meta.purge_record_event(%s,%s,%s,%s)',
                       (purge_id, 'FAILED_STOP', 'system_search', Jsonb(failure)))
    assert connection.execute(
        '''SELECT failure_evidence->'integrity_failed' FROM v3_meta.derived_generation_purge_event
           WHERE purge_id=%s AND event_kind='FAILED_STOP' ORDER BY event_sequence DESC LIMIT 1''',
        (purge_id,),
    ).fetchone()[0] is False
    # A new dispatch consumes the next database-selected range, not the old
    # receipt's row count or a Python-side continuation cursor.
    assert _batch(connection, purge_id, 'system_search', size=3) == 3
    assert _count(connection, 'v3_derived.system_search', TARGETS[0][1]) == 6
    assert _count(connection, 'v3_derived.system_search', SURVIVOR) == 12


def test_abort_autovacuum_headroom_refuses_without_closing_fence_then_restores(database):
    connection = database[0]
    purge_id = _authorize(database)[TARGETS[0][1]]
    _writer_fence(connection, purge_id)
    connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)',
                       (purge_id, 'system_search'))
    current_bytes = connection.execute(
        "SELECT pg_total_relation_size('v3_derived.system_search'::regclass)",
    ).fetchone()[0]
    assert current_bytes > 0
    inadequate = {**_receipt(), 'aborted': True, 'autovacuum_budget_bytes': current_bytes,
                  'filesystem_free_bytes': 100_000_000_000 + current_bytes - 1}
    connection.execute('SELECT v3_meta.purge_record_event(%s,%s,%s,%s)',
                       (purge_id, 'FAILED_STOP', 'system_search', Jsonb(inadequate)))
    events_before = _count(connection, 'v3_meta.derived_generation_purge_event')
    with pytest.raises(psycopg.Error):
        with connection.transaction():
            connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,true)',
                               (purge_id, 'system_search'))
    assert _count(connection, 'v3_meta.derived_generation_purge_event') == events_before
    assert connection.execute(
        '''SELECT option_value FROM pg_class c,LATERAL pg_options_to_table(c.reloptions)
           WHERE c.oid='v3_derived.system_search'::regclass AND option_name='autovacuum_enabled' ''',
    ).fetchone()[0] == 'false'
    _abort_autovacuum_fence(connection, purge_id, 'system_search')
    assert connection.execute(
        "SELECT count(*) FROM v3_meta.derived_generation_purge_event WHERE event_kind='AUTOVACUUM_RESTORED'",
    ).fetchone()[0] == 1
    assert connection.execute(
        "SELECT count(*) FROM v3_meta.derived_generation_purge_event WHERE event_kind='REWRITE_VERIFIED'",
    ).fetchone()[0] == 0


def test_delete_operator_adapter_observes_and_adopts_real_016_physical_fence(database):
    connection = database[0]
    requests = _authorize(database)
    ids = [str(purge_id) for purge_id in requests.values()]
    query = _operator_query(connection)
    observed = purge_transactions.phase_state(query, ids, 'system_search')
    assert observed['target_counts'] == {str(identity): 12 for identity in requests}
    assert observed['autovacuum_fences'] == []
    assert purge_transactions.autovacuum_fence(query, ids, 'system_search')['adopted'] is False
    adopted = purge_transactions.autovacuum_fence(query, ids, 'system_search')
    assert adopted['adopted'] is True
    assert adopted['event']['relation_code'] == 'system_search'
    assert adopted['event']['operational_payload']['heap']['xid_ceiling'] == 100_000_000
    assert _count(connection, 'v3_meta.derived_generation_purge_event') == 3


def test_delete_operator_payload_adapter_commits_start_and_small_batch_on_same_backend(database):
    connection = database[0]
    requests = _authorize(database)
    ids = [str(purge_id) for purge_id in requests.values()]
    purge_id = str(requests[TARGETS[0][1]])
    query = _operator_query(connection)
    purge_transactions.autovacuum_fence(query, ids, 'system_search')
    _writer_fence(connection, purge_id)
    result = purge_transactions.payload_batch(query, purge_id, 'system_search', 3, _receipt())
    assert result['start_event'] > 0 and result['rows_affected'] == 3
    assert _count(connection, 'v3_derived.system_search', TARGETS[0][1]) == 9
    assert _count(connection, 'v3_derived.system_search', SURVIVOR) == 12
    events = connection.execute(
        '''SELECT event_kind,operational_payload FROM v3_meta.derived_generation_purge_event
           WHERE purge_id=%s AND event_kind IN ('BATCH_STARTED','BATCH_COMMITTED')
           ORDER BY event_sequence''', (purge_id,),
    ).fetchall()
    assert [event[0] for event in events] == ['BATCH_STARTED', 'BATCH_COMMITTED']
    assert events[1][1]['start_event'] == result['start_event']
    assert query(purge_transactions.BATCH_RANGE_SQL, {
        'purge_id': purge_id, 'relation': 'system_search', 'start_event': str(result['start_event']),
    }) == {'selected': 3, 'range_rows': 0}
    assert purge_transactions.metadata_state(query, ids)['open_batches'] == []


_RESOLVER_CASES = (
    ('BATCH_STARTED', ('BATCH_COMMITTED', 'BATCH_ROLLED_BACK')),
    ('REWRITE_STARTED', ('REWRITE_VERIFIED', 'REWRITE_ROLLED_BACK', 'FAILED_STOP')),
    ('REWRITE_STARTED', ('REWRITE_VERIFIED', 'REWRITE_ROLLED_BACK')),
    ('SERVICES_QUIESCED', ('SERVICES_RESTORED',)),
    ('WRITER_FENCE_ENABLED', ('WRITER_FENCE_RESTORED',)),
    ('AUTOVACUUM_DISABLED', ('AUTOVACUUM_RESTORED',)),
)


def _reference_open_event(events, plan_ids, purge_id, code, opening, closing):
    """The resolver's definition: the newest opening with no later closing."""
    if purge_id not in plan_ids:
        return None
    scope = {purge_id} if opening == 'BATCH_STARTED' else plan_ids
    for sequence, owner, kind, relation, payload in sorted(events, reverse=True):
        if owner not in scope or kind != opening or relation != code:
            continue
        if not any(
            other == owner and later_relation == code and later > sequence and later_kind in closing
            and (opening != 'WRITER_FENCE_ENABLED' or later_payload.get('verified') is True)
            for later, other, later_kind, later_relation, later_payload in events
        ):
            return sequence
    return None


def test_open_event_resolver_matches_its_anti_join_definition_on_random_ledgers(database):
    import random

    connection = database[0]
    plan_ids = set(_authorize(database).values())
    connection.execute('RESET ROLE')
    stranger = uuid4()
    kinds = sorted({kind for opening, closing in _RESOLVER_CASES for kind in (opening, *closing)})
    relations = (None, 'system_search', 'economy_opportunity')
    payloads = ({}, {'verified': True}, {'verified': False}, {'verified': 'true'})
    generator = random.Random(20261017)
    non_null = 0
    for _ in range(12):
        # The ledger is append-only, so each round extends the same history.
        for _ in range(generator.randint(5, 25)):
            connection.execute(
                '''INSERT INTO v3_meta.derived_generation_purge_event
                   (purge_id,event_kind,relation_code,operational_payload) VALUES(%s,%s,%s,%s)''',
                (generator.choice(sorted(plan_ids)), generator.choice(kinds),
                 generator.choice(relations), Jsonb(generator.choice(payloads))),
            )
        events = [tuple(row) for row in connection.execute(
            '''SELECT event_sequence,purge_id,event_kind,relation_code,operational_payload
               FROM v3_meta.derived_generation_purge_event''')]
        for purge_id in (*sorted(plan_ids), stranger):
            for code in relations:
                for opening, closing in _RESOLVER_CASES:
                    observed = connection.execute(
                        'SELECT (v3_meta.purge_open_event(%s,%s,%s,%s)).event_sequence',
                        (purge_id, code, opening, list(closing)),
                    ).fetchone()[0]
                    expected = _reference_open_event(events, plan_ids, purge_id, code, opening, closing)
                    assert observed == expected, (purge_id, code, opening, closing)
                    non_null += expected is not None
    assert non_null > 50


def test_state_and_open_event_stay_fast_with_production_scale_batch_history(database):
    """The 1% rehearsal stopped when STATE_SQL passed its 10s limit.

    Every delete batch appends a BATCH_STARTED/BATCH_COMMITTED pair. The
    resolver once compared each opening with each closing event, so cost grew
    with the square of the batch count. Twenty thousand closed batches per
    relation and request took about 30 seconds per call before the rewrite.
    """
    # This fixture installs 016 only. The fence's copy-aware STATE_SQL also reads
    # 019's functions (proved in tests/test_v3_purge_copy_operator_pg18.py); the
    # 016 semantics under test are the shared part, LEGACY_STATE_SQL.
    from scripts.operator.lib.v3_purge_state import LEGACY_STATE_SQL as STATE_SQL

    connection = database[0]
    ids = sorted(_authorize(database).values())
    connection.execute('RESET ROLE')
    connection.execute(
        '''INSERT INTO v3_meta.derived_generation_purge_event(purge_id,event_kind,relation_code)
           SELECT purge_id,kind,relation_code
           FROM unnest(%s::uuid[]) AS purge_id,
                unnest(ARRAY['system_search','economy_opportunity']) AS relation_code,
                generate_series(1,20000) AS batch,
                unnest(ARRAY['BATCH_STARTED','BATCH_COMMITTED']) WITH ORDINALITY AS k(kind,step)
           ORDER BY batch,step''', (ids,),
    )
    # One batch left open on the newest relation must still be reported.
    connection.execute(
        '''INSERT INTO v3_meta.derived_generation_purge_event(purge_id,event_kind,relation_code)
           VALUES(%s,'BATCH_STARTED','economy_opportunity')''', (ids[0],),
    )
    connection.execute('ANALYZE v3_meta.derived_generation_purge_event')
    started = monotonic()
    observed = _fence_sql_rows(connection, STATE_SQL)[0][0]
    state_seconds = monotonic() - started
    assert [(row['event_kind'], row['relation_code']) for row in observed['unresolved']] == [
        ('BATCH_STARTED', 'economy_opportunity')]
    assert state_seconds < 3, state_seconds
    for code in ('system_search', 'economy_opportunity'):
        started = monotonic()
        connection.execute(
            "SELECT v3_meta.purge_open_event(%s,%s,'BATCH_STARTED',ARRAY['BATCH_COMMITTED','BATCH_ROLLED_BACK'])",
            (ids[1], code),
        ).fetchone()
        assert monotonic() - started < 1, code
