"""The actual harness migration and seed SQL against a fresh disposable PG18 DB.

``canonical_database`` validates the local CI service identity before any test
connection is opened. The manifest is loaded into a second, empty random DB,
so no fixture schema or rows hide missing seed prerequisites. This adds one
small 200-system seed to the existing Finder PG18 discovery lane.
"""
from contextlib import contextmanager
import json
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.types.json import Jsonb

from scripts.operator.lib import v3_purge_rewrite as rewrite
from scripts.operator.lib import v3_purge_transactions as transactions
from scripts.rehearsal import v3_derived_purge_rehearsal as rehearsal
from scripts.rehearsal import v3_purge_crashes as crashes
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
        parameter_was_granted = True
        administrator.execute('SELECT pg_advisory_lock(764016099)')
        try:
            executor_was_absent = administrator.execute(
                'SELECT 1 FROM pg_roles WHERE rolname=%s', ('v3_derived_purge_executor',),
            ).fetchone() is None
            # The harness grants SET on temp_file_limit; pg_parameter_acl is
            # cluster-wide, so a grant this test made must not outlive it.
            parameter_was_granted = not executor_was_absent and administrator.execute(
                "SELECT has_parameter_privilege('v3_derived_purge_executor','temp_file_limit','SET')",
            ).fetchone()[0]
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
            if not parameter_was_granted and administrator.execute(
                    'SELECT 1 FROM pg_roles WHERE rolname=%s', ('v3_derived_purge_executor',),
            ).fetchone():
                administrator.execute('REVOKE SET ON PARAMETER temp_file_limit FROM v3_derived_purge_executor')
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
        # The whole reviewed manifest, 016 and 019 included, as production holds it.
        assert sorted(ledger) == sorted(tuple(entry) for entry in manifest)
        assert {name for _, name in manifest} >= {rehearsal.controller.MIGRATION, rehearsal.COPY_MIGRATION}
        assert connection.execute(
            "SELECT has_parameter_privilege('v3_derived_purge_executor','temp_file_limit','SET')").fetchone() == (True,)

        # This shared local cluster may run without an archiver; the container
        # sets archive_mode=on. Everything else is the harness's own seed.
        harness.archived = lambda: None
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
        # Post-go-live survivors: both Finder products are published on the
        # surviving generation through 015, and the purge plan's production
        # survivor proof (counts equal each product's expected_rows) holds.
        survivors = harness.survivors
        assert plan['snapshot']['survivors']['system_search'] == survivors['system_search'] == 200
        products = connection.execute(
            """SELECT product_code,product_version,lifecycle_state,validation_receipt->>'status',expected_rows,
                      published_at IS NOT NULL
               FROM v3_meta.derived_product WHERE derived_generation_id=%s ORDER BY 1""",
            (rehearsal.controller.PUBLISHED_ID,)).fetchall()
        assert products == [('system_archetype', 'v3-archetype-4', 'READY', 'VERIFIED', 200, True),
                            ('system_search', 'v3-system-search-2', 'READY', 'VERIFIED', 200, True)]
        assert connection.execute(
            'SELECT product_code,actor FROM v3_meta.derived_product_publication_audit ORDER BY 1',
        ).fetchall() == [('system_archetype', 'disposable-rehearsal'), ('system_search', 'disposable-rehearsal')]
        assert connection.execute(
            'SELECT count(DISTINCT published_at) FROM v3_meta.derived_product WHERE published_at IS NOT NULL',
        ).fetchone() == (1,)
        assert connection.execute(
            'SELECT lifecycle_state,published_at IS NULL FROM v3_meta.derived_product '
            'WHERE derived_generation_id=%s', (rehearsal.controller.TARGETS['ratings_v4_prod_p4_opt1'][0],),
        ).fetchone() == ('READY', True)
        assert connection.execute('SELECT count(*) FROM v3_app.system_search').fetchone() == (200,)
        assert connection.execute('SELECT count(*) FROM v3_app.system_archetype').fetchone() == (200,)
        # Each B/A/S partial ranking index holds a share of the archetype rows.
        tiers = dict(connection.execute(
            'SELECT paradise_tier,count(*) FROM v3_derived.system_archetype GROUP BY 1').fetchall())
        assert {'S', 'A', 'B'} <= set(tiers)
        runtime = SimpleNamespace(query=query)
        frozen = rehearsal.controller.published_survivors(runtime, plan['snapshot']['survivors'],
                                                          require_published=True)
        assert frozen['system_archetype_rows'] == survivors['system_archetype']
        assert {code: item['expected_rows'] for code, item in frozen['products'].items()} == survivors
        # The production planner statistics are on the live opportunity table.
        assert connection.execute(
            """SELECT attstattarget,attoptions FROM pg_attribute
               WHERE attrelid='v3_derived.economy_opportunity'::regclass AND attname='system_id64'""",
        ).fetchone() == (1000, ['n_distinct=-0.13'])
        # Build receipts match the seeded rows per Ratings chunk (019 verify's rule).
        mismatched = connection.execute(
            """SELECT count(*) FROM v3_derived.build_chunk b WHERE b.derived_generation_id=%s AND (
                 b.physical_bodies<>(SELECT count(*) FROM v3_derived.body_mechanics m JOIN v3_derived.system_rating_vector v
                   USING (derived_generation_id,system_id64) WHERE m.derived_generation_id=b.derived_generation_id
                   AND v.chunk_ordinal=b.chunk_ordinal)
              OR b.eligible_opportunities<>(SELECT count(*) FROM v3_derived.economy_opportunity o
                   JOIN v3_derived.system_rating_vector v USING (derived_generation_id,system_id64)
                   WHERE o.derived_generation_id=b.derived_generation_id AND v.chunk_ordinal=b.chunk_ordinal))""",
            (rehearsal.controller.PUBLISHED_ID,)).fetchone()[0]
        assert mismatched == 0
        assert connection.execute(
            'SELECT sum(systems) FROM v3_derived.search_build_chunk WHERE derived_generation_id=%s',
            (rehearsal.controller.PUBLISHED_ID,)).fetchone() == (200,)

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
            # The crash driver's snapshot queries run as this observer: no
            # executor role switch, and oid-typed identities as JSON numbers.
            assert 'SET ROLE' not in crashes.POINTER_OBSERVATION_SQL
            with psycopg.ClientCursor(observer) as cursor:
                cursor.execute(crashes.POINTER_OBSERVATION_SQL)
                pointers = None
                while True:
                    if cursor.description is not None:
                        pointers = cursor.fetchone()[0]
                    if not cursor.nextset():
                        break
            assert pointers['derived']['derived_generation_id'] == rehearsal.controller.PUBLISHED_ID
            with psycopg.ClientCursor(observer) as cursor:
                cursor.execute(crashes.STATE_SQL, {'published': rehearsal.controller.PUBLISHED_ID})
                state = cursor.fetchone()[0]
            assert state['events'] == [] and state['tables'] == {'v3_derived': state['tables']['v3_derived']}
            assert type(state['tables']['v3_derived']) is int and state['invalid_indexes'] == 0
            assert state['live_attoptions'] == ['n_distinct=-0.13'] and state['target_rows'] > 0
            # The copy samplers' reads: temp files (pg_monitor) and each Finder surface.
            assert type(observer.execute(rehearsal.TEMP_SAMPLE_SQL).fetchone()[0]) is int
            for statement in rehearsal.FINDER_READS.values():
                assert observer.execute(statement).fetchone()[0] > 0
            assert observer.execute(crashes.ORPHAN_SQL).fetchone()[0] == {'backends': 0}
            # Even an explicitly read-write transaction cannot acquire a
            # payload write privilege through this observer login.
            observer.execute('SET default_transaction_read_only=off')
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                observer.execute('DELETE FROM v3_derived.system_rating_vector WHERE false')
        _copy_route_over_the_seed(connection, harness, frozen)


def _copy_route_over_the_seed(connection, harness, published_survivors):
    """019's copy-and-drop journey over the harness seed: verify accepts the
    seeded build and Search chunk receipts for all four relations."""
    from tests.test_v3_governed_derived_purge import _plan, _sign_plan
    from tests.test_v3_purge_copy_and_drop import (
        _x, build, chunk, drop, prepare, swap, vacuum, validate, verify,
    )
    connection.execute('RESET ROLE')
    plan = _plan(connection)
    plan['published_survivors'] = published_survivors
    plan = _sign_plan(connection, plan)
    connection.execute('SET ROLE v3_derived_purge_executor')
    purge = connection.execute('SELECT v3_meta.begin_derived_generation_purge(%s)', (Jsonb(plan),)).fetchone()[0][0]
    connection.execute('RESET ROLE')
    survivors = {relation: harness.counts[relation][rehearsal.controller.PUBLISHED_KEY] for relation in rehearsal.RELATIONS}
    for relation in rehearsal.RELATIONS:
        prepare(connection, purge, relation)
        copied = 0
        while (rows := chunk(connection, purge, relation, 100)) > 0:
            copied += rows
        assert copied == survivors[relation]
        build(connection, purge, relation)
        vacuum(connection, relation)
        verify(connection, purge, relation)
        swap(connection, purge, relation)
        validate(connection, purge, relation)
        drop(connection, purge, relation)
        connection.execute('RESET ROLE')
        assert connection.execute(sql.SQL('SELECT count(*) FROM v3_derived.{} WHERE derived_generation_id<>%s').format(
            sql.Identifier(relation)), (rehearsal.controller.PUBLISHED_ID,)).fetchone() == (0,)
    _x(connection, 'SELECT v3_meta.purge_copy_complete(%s)', purge)
    connection.execute('RESET ROLE')
    assert connection.execute('SELECT count(*) FROM v3_app.system_search').fetchone() == (200,)
    assert connection.execute('SELECT count(*) FROM v3_app.system_archetype').fetchone() == (200,)


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
