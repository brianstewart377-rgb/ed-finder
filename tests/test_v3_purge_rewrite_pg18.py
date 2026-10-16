"""Small real rewrite/recovery journey, separate from the large purge module.

The canonical_database reference keeps this module discoverable by the PG18
lane. Each creator fixture rewrites four tiny relations once (plus one rolled
back start), exercising the actual operator SQL rather than forged receipts.
"""
import shutil

import psycopg
from psycopg.types.json import Jsonb

from scripts.operator.lib import v3_purge_rewrite as tool
from scripts.operator.lib import v3_purge_transactions as tx
from scripts.operator.lib import v3_generation_purge as controller
from tests.ratings_v4_pg_fixture import canonical_database  # noqa: F401
from tests.test_v3_governed_derived_purge import (
    RELATIONS, SURVIVOR, TARGETS, _application_worker, _authorize, _batch,
    _count, _fresh_purge_controller, _operator_query, _receipt, _wait_for_fixture_maintenance, _writer_fence,
    database,  # noqa: F401
)


def _query(connection):
    """Same committed JSON boundary as psql, including the post-COMMIT start."""
    def query(statement, parameters=None, *, write=False):
        # Production opens a fresh owner login per query. The reusable test
        # connection must restore that identity before owner-only stats reads.
        connection.execute('RESET ROLE')
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
            if statement == tool.START_SQL:
                assert len(results) == 2 and type(results[0]) is int
                assert results[1]['start_event'] == results[0]
                return results[1]
            assert len(results) == 1 and isinstance(results[0], dict)
            return results[0]
        except BaseException:
            connection.rollback()
            raise
    return query


def test_operator_three_steps_recover_committed_and_rolled_back_then_complete(database, monkeypatch):  # noqa: F811
    connection = database[0]
    ids_by_target = _authorize(database)
    purge_ids = [str(value) for value in ids_by_target.values()]
    purge_id = ids_by_target[TARGETS[0][1]]
    reviewed = connection.execute(
        'SELECT reviewed_plan FROM v3_meta.derived_generation_purge_request LIMIT 1',
    ).fetchone()[0]
    survivors = {relation: _count(connection, 'v3_derived.' + relation, SURVIVOR) for relation in RELATIONS}
    _writer_fence(connection, purge_id)
    with _fresh_purge_controller(connection) as connection:
        observer = _operator_query(connection)

        def analyze(command):
            with _application_worker(connection) as worker:
                worker.execute(tool.session_setup(30_000))
                worker.execute(command)
                worker.execute('SELECT pg_stat_force_next_flush()')

        for index, relation in enumerate(RELATIONS):
            connection.execute('SET ROLE v3_derived_purge_executor')
            _wait_for_fixture_maintenance(connection)
            connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)', (purge_id, relation))
            for request_id in ids_by_target.values():
                assert _batch(connection, request_id, relation) > 0
            for request_id in ids_by_target.values():
                connection.execute('SELECT v3_meta.complete_derived_payload_relation(%s,%s,%s)',
                                   (request_id, relation, Jsonb(_receipt())))
            if index == 1:
                # A controller lost before VACUUM leaves its original node; close
                # that start and prove the next dispatch can really rewrite it.
                with _application_worker(connection) as worker:
                    tool.start_rewrite(_query(worker), purge_ids, relation, _receipt())
                rolled_back = tool.resolve_rewrites(observer, purge_ids, relation, cancel=False)
                assert rolled_back['rolled_back_relations'] == [relation]
                assert rolled_back['verified_relations'] == []
            with _application_worker(connection) as worker:
                worker.execute(tool.session_setup(30_000))
                psql = shutil.which('psql')
                if index == 3 and psql:
                    # Exercise the production binary-pipe adapter against the
                    # local disposable service. Only transport argv is redirected;
                    # its role setup, committed marker and VACUUM are unchanged.
                    actual_popen = controller.subprocess.Popen
                    observed_waits = []
                    def local_popen(argv, **kwargs):
                        assert argv[:3] == ['docker', '--context', 'default']
                        assert worker.info.host in ('127.0.0.1', 'localhost')
                        assert worker.info.dbname.startswith('v4_test_')
                        environment = {**kwargs['env'], 'PGHOST': worker.info.host,
                                       'PGPORT': str(worker.info.port), 'PGDATABASE': worker.info.dbname,
                                       'PGUSER': worker.info.user, 'PGPASSWORD': worker.info.password}
                        return actual_popen([psql, '-X', '--no-psqlrc', '--no-password',
                                             '--tuples-only', '--no-align', '--quiet',
                                             '--set', 'ON_ERROR_STOP=1', '--set', 'VERBOSITY=sqlstate',
                                             '--file=-'], **{**kwargs, 'env': environment})
                    runtime = controller.Runtime({})
                    with monkeypatch.context() as patcher:
                        patcher.setattr(controller.subprocess, 'Popen', local_popen)
                        with runtime.rewrite_backend(30_000, on_wait=lambda: observed_waits.append(True)) as backend:
                            started = tool.start_rewrite(backend.query, purge_ids, relation, _receipt())
                            # The marker is emitted after COMMIT: another backend
                            # sees the durable row before VACUUM is submitted.
                            assert connection.execute(
                                'SELECT backend_pid FROM v3_meta.derived_generation_purge_event WHERE event_sequence=%s',
                                (started['start_event'],),
                            ).fetchone()[0] == started['backend_pid']
                            backend.command(tool.rewrite_command(relation))
                    assert observed_waits and runtime.report['transaction_outcome'] == 'committed'
                elif index == 0:
                    started = tool.start_rewrite(_query(worker), purge_ids, relation, _receipt())
                    # Model process loss after the swap but before ANALYZE. The
                    # dispatcher must analyze this node, never VACUUM it again.
                    worker.execute('VACUUM (FULL) v3_derived.system_search')
                else:
                    started = tool.start_rewrite(_query(worker), purge_ids, relation, _receipt())
                    worker.execute(tool.rewrite_command(relation))
                worker.execute('SELECT pg_stat_force_next_flush()')
            node = connection.execute('SELECT relfilenode FROM pg_class WHERE oid=%s::regclass',
                                      ('v3_derived.' + relation,)).fetchone()[0]
            assert node != started['relfilenode_before']
            if index == 0:
                recovered = tool.resolve_rewrites(observer, purge_ids, relation, cancel=False,
                                                   analyze=analyze, receipt=_receipt)
                assert recovered['verified_relations'] == [relation]
                assert connection.execute('SELECT relfilenode FROM pg_class WHERE oid=%s::regclass',
                                          ('v3_derived.' + relation,)).fetchone()[0] == node
            else:
                _wait_for_fixture_maintenance(connection)
                tool.verify_rewrite(observer, purge_ids, relation, _receipt())
            connection.execute('SET ROLE v3_derived_purge_executor')
            events = connection.execute(
                '''SELECT event_kind,recovered FROM v3_meta.derived_generation_purge_event
                   WHERE relation_code=%s AND event_kind IN
                   ('REWRITE_STARTED','REWRITE_ROLLED_BACK','REWRITE_VERIFIED','AUTOVACUUM_RESTORED')
                   ORDER BY event_sequence''', (relation,),
            ).fetchall()
            expected = [('REWRITE_STARTED', False)]
            if index == 1:
                expected += [('REWRITE_ROLLED_BACK', True), ('REWRITE_STARTED', False)]
            expected += [('REWRITE_VERIFIED', index == 0), ('AUTOVACUUM_RESTORED', False)]
            assert events == expected
            assert _count(connection, 'v3_derived.' + relation, SURVIVOR) == survivors[relation]
            assert not tx.metadata_state(observer, purge_ids)['open_rewrites']
        connection.execute('SET ROLE v3_derived_purge_executor')
        connection.execute('SELECT v3_meta.purge_set_writer_fence(%s,false)', (purge_id,))
        connection.execute('SELECT v3_meta.purge_recycle_writer_sessions(%s,false)', (purge_id,))
        connection.execute('SELECT v3_meta.purge_verify_writer_fence(%s,false,%s)', (purge_id, 'off'))
        completed = tx.complete(observer, reviewed, _receipt(), purge_ids=purge_ids)
        assert set(completed['completed_ids']) == set(purge_ids)
        assert completed['snapshot'] == reviewed['snapshot']
        assert _count(connection, 'v3_meta.derived_generation_purge_event') > 0


def test_rewrite_start_accepts_a_multi_gigabyte_peak_only_in_the_rewrite_field(database):  # noqa: F811
    """Production rewrite peaks are whole relations, far above one delete batch.

    016's shared freshness check bounds batch_peak_bytes below 1 GB. The pre-fix
    evidence reused that field for the rewrite peak and was always refused;
    start_evidence() carries it only as rewrite_peak_bytes.
    """
    connection = database[0]
    ids_by_target = _authorize(database)
    purge_ids = [str(value) for value in ids_by_target.values()]
    purge_id = ids_by_target[TARGETS[0][1]]
    relation = RELATIONS[0]
    peak = 5_000_000_000
    measured = {**_receipt(), 'filesystem_free_bytes': 120_000_000_000}
    _writer_fence(connection, purge_id)
    with _fresh_purge_controller(connection) as connection:
        observer = _operator_query(connection)
        connection.execute('SET ROLE v3_derived_purge_executor')
        _wait_for_fixture_maintenance(connection)
        connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)', (purge_id, relation))
        for request_id in ids_by_target.values():
            assert _batch(connection, request_id, relation) > 0
        for request_id in ids_by_target.values():
            connection.execute('SELECT v3_meta.complete_derived_payload_relation(%s,%s,%s)',
                               (request_id, relation, Jsonb(_receipt())))
        with _application_worker(connection) as worker:
            legacy = {**measured, 'batch_peak_bytes': peak, 'rewrite_peak_bytes': peak}
            try:
                tool.start_rewrite(_query(worker), purge_ids, relation, legacy)
            except psycopg.errors.RaiseException as exc:
                assert 'fresh disk, WAL or worker evidence missing or unsafe' in str(exc)
            else:
                raise AssertionError('016 accepted a batch peak of one whole relation')
        with _application_worker(connection) as worker:
            evidence = tool.start_evidence(measured, peak, {'attempts': 1})
            assert evidence['batch_peak_bytes'] == 0 and evidence['rewrite_peak_bytes'] == peak
            started = tool.start_rewrite(_query(worker), purge_ids, relation, evidence)
        assert started['start_event'] > 0
        recorded = connection.execute(
            'SELECT operational_payload FROM v3_meta.derived_generation_purge_event WHERE event_sequence=%s',
            (started['start_event'],)).fetchone()[0]
        assert recorded['rewrite_peak_bytes'] == peak and recorded['batch_peak_bytes'] == 0
        rolled_back = tool.resolve_rewrites(observer, purge_ids, relation, cancel=False)
        assert rolled_back['rolled_back_relations'] == [relation]
