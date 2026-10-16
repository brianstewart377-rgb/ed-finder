"""Real watchdog cancellation, kept separate from the large canonical_database lane module.

Host floor/archiver/controller observations are injected; the backend identity,
blocked VACUUM, dedicated cancellation function and ledger are real PostgreSQL 18.
"""
from copy import deepcopy
from datetime import datetime
from time import monotonic, sleep

import psycopg
from psycopg.types.json import Jsonb
import pytest

from scripts.operator.lib import v3_generation_purge as controller
from scripts.operator.lib import v3_purge_rewrite as rewrite
from scripts.operator.lib import v3_purge_rewrite_monitor as monitor
from tests.ratings_v4_pg_fixture import canonical_database  # noqa: F401
from tests.test_v3_governed_derived_purge import (
    TARGETS, _application_worker, _authorize, _batch, _fresh_purge_controller,
    _receipt, _running_operation, _wait_for_database_operation,
    _wait_for_fixture_maintenance, _writer_fence,
    database,  # noqa: F401
)
from tests.test_v3_purge_rewrite_pg18 import _query


def test_watchdog_cancels_only_recorded_backend_for_each_breach_then_exits(database):  # noqa: F811
    connection = database[0]
    ids = _authorize(database)
    purge_ids = [str(value) for value in ids.values()]
    purge_id = ids[TARGETS[0][1]]
    _writer_fence(connection, purge_id)
    with _fresh_purge_controller(connection) as connection:
        connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)',
                           (purge_id, 'system_search'))
        for request_id in ids.values():
            assert _batch(connection, request_id, 'system_search') == 12
        connection.execute('SELECT v3_meta.complete_derived_payload_relation(%s,%s,%s)',
                           (purge_id, 'system_search', Jsonb(_receipt())))
        query = _query(connection)
        original_node = connection.execute("SELECT pg_relation_filenode('v3_derived.system_search')").fetchone()[0]
        for failure, expected in (('floor', 'free_space_floor'), ('count', 'wal_archiver_failure'),
                                  ('timestamp', 'wal_archiver_failure'), ('controller', 'controller_loss')):
            _wait_for_fixture_maintenance(connection)
            with _application_worker(connection) as worker:
                started = rewrite.start_rewrite(_query(worker), purge_ids, 'system_search', _receipt())
                with _application_worker(connection) as blocker, _application_worker(connection) as unrelated:
                    with blocker.transaction():
                        blocker.execute('LOCK TABLE v3_derived.system_search IN ACCESS SHARE MODE')
                        with _running_operation(unrelated, 'SELECT pg_sleep(20)') as other:
                            with _running_operation(worker, rewrite.rewrite_command('system_search')) as future:
                                _wait_for_database_operation(connection, worker, future, 'waiting_rewrite')
                                before = {'archive_mode': 'on', 'archiver': {'failed_count': 0,
                                          'last_archived_time': '2026-10-16T10:00:00+00:00',
                                          'last_failed_time': None}, 'slots': []}
                                after = deepcopy(before)
                                if failure == 'count':
                                    after['archiver']['failed_count'] = 1
                                elif failure == 'timestamp':
                                    after['archiver']['last_failed_time'] = '2026-10-16T10:01:00+00:00'
                                controller_checks = []
                                def controller_alive():
                                    controller_checks.append(True)
                                    if failure == 'controller':
                                        raise ValueError('controller_lost')
                                def observe():
                                    if failure == 'floor':
                                        raise ValueError('filesystem_free_space_floor')
                                    controller.wal_health(before, after)
                                identity = {'backend_pid': str(started['backend_pid']),
                                            'backend_start': started['backend_start']}
                                def backend_alive():
                                    return query(rewrite.BACKEND_SQL, identity)['alive']
                                assert backend_alive()
                                deadline = monotonic() + 10
                                def wait_for_departure(_):
                                    if future.done():
                                        with pytest.raises(psycopg.errors.QueryCanceled):
                                            future.result(timeout=1)
                                        # The real wrapper closes its canceled backend;
                                        # the watchdog must outlive it until that exit.
                                        worker.close()
                                    assert monotonic() < deadline, 'watchdog did not cancel recorded rewrite'
                                    sleep(.01)
                                assert monitor.watch(backend_alive, observe, controller_alive,
                                                     lambda reason: rewrite.cancel_rewrite(
                                                         query, str(purge_id), 'system_search', reason),
                                                     sleep=wait_for_departure) == expected
                                assert controller_checks
                                assert not other.done(), 'watchdog signalled an unrelated backend'
                                assert unrelated.info.backend_pid != started['backend_pid']
                                def forbidden(*_):
                                    pytest.fail('departed backend must not be observed or cancelled again')
                                assert monitor.watch(backend_alive, forbidden, forbidden, forbidden) is None
            resolved = rewrite.resolve_rewrites(query, purge_ids, 'system_search', cancel=False)
            assert resolved['rolled_back_relations'] == ['system_search']
            assert connection.execute("SELECT pg_relation_filenode('v3_derived.system_search')").fetchone()[0] == original_node
            rows = connection.execute(
                '''SELECT backend_pid,backend_start,operational_payload FROM v3_meta.derived_generation_purge_event
                   WHERE event_kind='REWRITE_CANCEL_REQUESTED' AND event_sequence>%s ORDER BY event_sequence''',
                (started['start_event'],),
            ).fetchall()
            assert rows
            for pid, backend_start, payload in rows:
                assert pid == started['backend_pid']
                assert backend_start == datetime.fromisoformat(started['backend_start'])
                assert payload == {'condition': expected, 'signalled': True}
