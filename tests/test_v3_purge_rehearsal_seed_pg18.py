"""The actual harness migration and seed SQL against a fresh disposable PG18 DB.

``canonical_database`` validates the local CI service identity before any test
connection is opened. The manifest is loaded into a second, empty random DB,
so no fixture schema or rows hide missing seed prerequisites. This adds one
small 200-system seed to the existing Finder PG18 discovery lane.
"""
from contextlib import contextmanager
import json
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.types.json import Jsonb

from scripts.operator.lib import v3_purge_rewrite as rewrite
from scripts.operator.lib import v3_purge_transactions as transactions
from scripts.rehearsal import v3_derived_purge_rehearsal as rehearsal
from tests.ratings_v4_pg_fixture import canonical_database


@contextmanager
def fresh_harness_database():
    """Serialize cluster roles and remove only our own database/capability."""
    with canonical_database() as canonical:
        administrator = canonical[0]
        assert 180000 <= administrator.info.server_version < 190000
        assert administrator.execute('SELECT rolsuper FROM pg_roles WHERE rolname=current_user').fetchone()[0]
        database = 'v4_test_purge_seed_' + uuid4().hex
        created = False
        executor_was_absent = False
        observer_was_absent = False
        administrator.execute('SELECT pg_advisory_lock(764016099)')
        try:
            executor_was_absent = administrator.execute(
                'SELECT 1 FROM pg_roles WHERE rolname=%s', ('v3_derived_purge_executor',),
            ).fetchone() is None
            observer_was_absent = administrator.execute(
                'SELECT 1 FROM pg_roles WHERE rolname=%s', (rehearsal.OBSERVER_USER,),
            ).fetchone() is None
            administrator.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
            created = True
            with psycopg.connect(make_conninfo(administrator.info.dsn, password=administrator.info.password, dbname=database), autocommit=True) as connection:
                yield connection
        finally:
            if created:
                administrator.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(database)))
            if observer_was_absent and administrator.execute(
                    'SELECT 1 FROM pg_roles WHERE rolname=%s', (rehearsal.OBSERVER_USER,),
            ).fetchone():
                administrator.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(rehearsal.OBSERVER_USER)))
            if executor_was_absent and administrator.execute(
                    'SELECT 1 FROM pg_roles WHERE rolname=%s', ('v3_derived_purge_executor',),
            ).fetchone():
                # All grants from this test were in the now-dropped database.
                # An unrelated database dependency means this role must remain.
                try:
                    administrator.execute('DROP ROLE v3_derived_purge_executor')
                except psycopg.errors.DependentObjectsStillExist:
                    pass
            administrator.execute('SELECT pg_advisory_unlock(764016099)')


def _sql_adapter(connection):
    def execute(statement, parameters=None):
        outputs = []
        with psycopg.ClientCursor(connection) as cursor:
            cursor.execute(statement, parameters)
            while True:
                if cursor.description is not None:
                    for row in cursor.fetchall():
                        value = row[0]
                        outputs.append(json.dumps(value, default=str) if isinstance(value, (dict, list)) else str(value))
                if not cursor.nextset():
                    break
        return '\n'.join(outputs)
    return execute


def test_harness_full_manifest_and_tiny_seed_produce_real_plan_prerequisites(tmp_path):
    with fresh_harness_database() as connection:
        harness = rehearsal.Harness('tiny', 'pg18-seed-test', tmp_path)
        harness.sql = _sql_adapter(connection)
        harness.migrate()
        manifest = [line.split()[:2] for line in
                    (rehearsal.ROOT / 'sql/v3/migration-manifest.txt').read_text().splitlines()
                    if line.strip() and not line.startswith('#')]
        ledger = connection.execute(
            "SELECT encode(migration_sha256,'hex'),migration_name FROM v3_meta.schema_migration",
        ).fetchall()
        assert sorted(ledger) == sorted(tuple(entry) for entry in manifest)
        assert manifest[-1][1] == rehearsal.controller.MIGRATION

        harness.seed()
        identities = {key: identity for key, (identity, _) in rehearsal.controller.TARGETS.items()}
        identities[rehearsal.controller.PUBLISHED_KEY] = rehearsal.controller.PUBLISHED_ID
        for relation in rehearsal.RELATIONS:
            actual = dict(connection.execute(sql.SQL(
                'SELECT derived_generation_id::text,count(*) FROM v3_derived.{} GROUP BY derived_generation_id',
            ).format(sql.Identifier(relation))).fetchall())
            expected = {identity: harness.counts[relation][key]
                        for key, identity in identities.items() if harness.counts[relation][key]}
            assert actual == expected
        states = dict(connection.execute(
            'SELECT generation_key,lifecycle_state FROM v3_meta.derived_generation',
        ).fetchall())
        assert states == {'ratings_v4_prod_p4': 'BUILDING', 'ratings_v4_prod_p4_opt1': 'VALIDATING',
                          'ratings_v4_prod_p4_parallel_v1': 'PUBLISHED'}
        assert connection.execute(
            'SELECT derived_generation_id::text,publication_sequence FROM v3_meta.current_derived_generation',
        ).fetchall() == [(rehearsal.controller.PUBLISHED_ID, 1)]
        assert connection.execute(
            '''SELECT publication_sequence,from_generation_id,to_generation_id::text,actor,reason
               FROM v3_meta.derived_publication_audit''',
        ).fetchall() == [(1, None, rehearsal.controller.PUBLISHED_ID, 'disposable-rehearsal', 'synthetic seed')]
        assert connection.execute(
            "SELECT to_regprocedure('v3_meta.publish_derived_generation(uuid,uuid,bigint,uuid,bigint,text,text)')",
        ).fetchone() == (None,)
        assert connection.execute(
            'SELECT publication_sequence FROM v3_meta.current_canonical_generation',
        ).fetchone() == (4,)
        assert connection.execute(
            '''SELECT p.publication_sequence,s.lifecycle_state FROM v3_spatial.current_spatial_generation p
               JOIN v3_spatial.spatial_generation s USING(spatial_generation_id)''',
        ).fetchone() == (1, 'PUBLISHED')

        def query(statement, parameters=None, *, write=False):
            assert not write
            connection.execute('RESET ROLE')
            try:
                return json.loads(harness.sql(statement, parameters))
            finally:
                connection.execute('RESET ROLE')
        exclusions = query(transactions.EXCLUSIONS_SQL)
        assert exclusions == {'cluster_run': 0, 'cluster': 0, 'cluster_member': 0, 'system_archetype': 0}
        # This is the same plan collection/hash SQL the real action runs, and
        # requires all three published pointers plus both target manifests.
        plan = transactions.collect_plan(query, 'a' * 40, 'pg18-rehearsal-test', 'Synthetic seed verification')
        assert plan['snapshot']['spatial']['publication_sequence'] == 1
        assert plan['snapshot']['derived']['derived_generation_id'] == rehearsal.controller.PUBLISHED_ID
        assert {target['key'] for target in plan['targets']} == set(rehearsal.controller.TARGETS)
        for target in plan['targets']:
            assert target['payload_counts'] == {
                relation: harness.counts[relation][target['key']] for relation in rehearsal.RELATIONS}
        assert plan['snapshot']['survivors'] == {
            relation: harness.counts[relation][rehearsal.controller.PUBLISHED_KEY]
            for relation in rehearsal.RELATIONS}

        # Authenticate as the dedicated login, rather than SET ROLE on the
        # application connection: recycling selects the authenticated usename.
        password = uuid4().hex
        connection.execute(sql.SQL('ALTER ROLE {} PASSWORD {}').format(
            sql.Identifier(rehearsal.OBSERVER_USER), sql.Literal(password)))
        with psycopg.connect(make_conninfo(connection.info.dsn, user=rehearsal.OBSERVER_USER,
                                          password=password), autocommit=True) as observer:
            assert observer.execute('SHOW default_transaction_read_only').fetchone() == ('on',)
            assert observer.execute('SELECT current_user').fetchone() == (rehearsal.OBSERVER_USER,)
            assert observer.execute('SELECT count(*) FROM v3_meta.derived_generation').fetchone() == (3,)
            assert observer.execute(
                '''SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls
                   FROM pg_roles WHERE rolname=current_user''',
            ).fetchone() == (False, False, False, False, False)
            # Even an explicitly read-write transaction cannot acquire a
            # payload write privilege through this observer login.
            observer.execute('SET default_transaction_read_only=off')
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                observer.execute('DELETE FROM v3_derived.system_rating_vector WHERE false')


def test_observer_survives_real_writer_fence_session_recycles():
    from tests.test_v3_governed_derived_purge import _authorize, installed_purge

    with canonical_database() as data, installed_purge(data[0], apply_chain=True) as connection:
        purge_id = next(iter(_authorize(data).values()))
        connection.execute('RESET ROLE')
        connection.execute(rehearsal.OBSERVER_SETUP)
        password = uuid4().hex
        for role in (rehearsal.USER, rehearsal.OBSERVER_USER):
            connection.execute(sql.SQL('ALTER ROLE {} PASSWORD {}').format(
                sql.Identifier(role), sql.Literal(password)))
        try:
            observer_dsn = make_conninfo(connection.info.dsn, user=rehearsal.OBSERVER_USER, password=password)
            application_dsn = make_conninfo(connection.info.dsn, user=rehearsal.USER, password=password)
            with psycopg.connect(observer_dsn, autocommit=True) as observer:
                observer_pid = observer.execute('SELECT pg_backend_pid()').fetchone()[0]
                for enabled in (True, False):
                    with psycopg.connect(application_dsn, autocommit=True) as application:
                        connection.execute('SET ROLE v3_derived_purge_executor')
                        connection.execute('SELECT v3_meta.purge_set_writer_fence(%s,%s)', (purge_id, enabled))
                        assert connection.execute(
                            'SELECT v3_meta.purge_recycle_writer_sessions(%s,%s)', (purge_id, enabled),
                        ).fetchone()[0] >= 1
                        with pytest.raises(psycopg.OperationalError):
                            application.execute('SELECT 1')
                    # The same authenticated observer remains alive at both
                    # fence boundaries, including ledger sampling queries.
                    assert observer.execute('SELECT pg_backend_pid()').fetchone()[0] == observer_pid
                    assert observer.execute('SELECT count(*) FROM v3_meta.derived_generation_purge_event').fetchone()[0] > 0
                    observed = 'on' if enabled else 'off'
                    connection.execute('SELECT v3_meta.purge_verify_writer_fence(%s,%s,%s)',
                                       (purge_id, enabled, observed))
        finally:
            connection.execute('RESET ROLE')
            connection.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(rehearsal.OBSERVER_USER)))
            connection.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(rehearsal.OBSERVER_USER)))


def test_rewrite_verified_transaction_rolls_back_and_recovers_without_second_rewrite():
    from tests.test_v3_governed_derived_purge import (
        _authorize, _batch, _operator_query, _receipt, _wait_for_fixture_maintenance,
        _writer_fence, installed_purge,
    )

    with canonical_database() as data, installed_purge(data[0], apply_chain=True) as connection:
        purge_ids = [str(identity) for identity in _authorize(data).values()]
        purge_id = purge_ids[0]
        relation = 'system_search'
        _writer_fence(connection, purge_id)
        connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)', (purge_id, relation))
        for request in purge_ids:
            assert _batch(connection, request, relation) > 0
        connection.execute('SELECT v3_meta.complete_derived_payload_relation(%s,%s,%s)',
                           (purge_id, relation, Jsonb(_receipt())))
        connection.execute('RESET ROLE')
        # A real dispatch backend commits STARTED and VACUUM independently,
        # then departs before the verification transaction begins.
        with psycopg.connect(make_conninfo(connection.info.dsn, password=connection.info.password),
                             autocommit=True) as backend:
            backend.execute('SET ROLE v3_derived_purge_executor')
            backend.execute('SELECT v3_meta.purge_record_event(%s,%s,%s,%s)',
                            (purge_id, 'REWRITE_STARTED', relation, Jsonb(_receipt())))
            backend.execute(rewrite.rewrite_command(relation))
            backend.execute('SELECT pg_stat_force_next_flush()')
        _wait_for_fixture_maintenance(connection)
        query = _operator_query(connection)
        opened = transactions.metadata_state(query, purge_ids)['open_rewrites']
        assert len(opened) == 1
        started = opened[0]
        rewritten = connection.execute("SELECT pg_relation_filenode('v3_derived.system_search')").fetchone()[0]
        assert started['relation_oid'] is not None and started['relfilenode_before'] != rewritten

        connection.execute('SET ROLE v3_derived_purge_executor')
        with pytest.raises(psycopg.errors.DivisionByZero):
            with connection.transaction():
                inserted = connection.execute('SELECT v3_meta.purge_record_event(%s,%s,%s,%s)',
                    (purge_id, 'REWRITE_VERIFIED', relation, Jsonb(_receipt()))).fetchone()[0]
                assert connection.execute(
                    'SELECT event_kind FROM v3_meta.derived_generation_purge_event WHERE event_sequence=%s',
                    (inserted,),
                ).fetchone() == ('REWRITE_VERIFIED',)
                connection.execute('SELECT 1 / 0')
        assert transactions.metadata_state(query, purge_ids)['open_rewrites'] == opened
        assert connection.execute(
            "SELECT count(*) FROM v3_meta.derived_generation_purge_event WHERE event_kind='REWRITE_VERIFIED'",
        ).fetchone() == (0,)
        plan = connection.execute('SELECT reviewed_plan FROM v3_meta.derived_generation_purge_request LIMIT 1').fetchone()[0]
        with pytest.raises(transactions.PurgeTransactionError, match='purge_completion_preconditions_failed'):
            transactions.complete(query, plan, _receipt(), purge_ids=purge_ids)

        resolved = rewrite.resolve_rewrites(query, purge_ids, relation, cancel=False,
                                            receipt=_receipt, statement_timeout_ms=60_000)
        assert resolved['verified_relations'] == [relation]
        assert transactions.metadata_state(query, purge_ids)['open_rewrites'] == []
        assert connection.execute(
            "SELECT recovered FROM v3_meta.derived_generation_purge_event WHERE event_kind='REWRITE_VERIFIED'",
        ).fetchall() == [(True,)]
        assert rewrite.resolve_rewrites(query, purge_ids, relation, cancel=False)['resolved_rewrite_events'] == []
        assert connection.execute("SELECT pg_relation_filenode('v3_derived.system_search')").fetchone()[0] == rewritten
        assert connection.execute(
            "SELECT count(*) FROM v3_meta.derived_generation_purge_event WHERE event_kind='REWRITE_STARTED'",
        ).fetchone() == (1,)
