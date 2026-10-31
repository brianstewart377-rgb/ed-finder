"""Writer restoration acknowledgements using the disposable canonical_database PG18 fixture."""
from psycopg.types.json import Jsonb
import psycopg
import pytest

from tests.test_v3_governed_derived_purge import (
    TARGETS, _application_worker, _authorize, _batch, _fence_sql_rows,
    _fresh_purge_controller, _receipt, _running_operation, _wait_for_database_operation,
    _wait_for_fixture_maintenance, _writer_fence,
    database as database,
)


def _failed_stop(connection, purge_id, integrity_failed):
    return connection.execute(
        "SELECT v3_meta.purge_record_event(%s,'FAILED_STOP',NULL,%s)",
        (purge_id, Jsonb({'integrity_failed': integrity_failed})),
    ).fetchone()[0]


def test_writer_restore_persists_exact_integrity_acknowledgement(database):
    connection = database[0]
    ids = _authorize(database)
    first, second = (ids[identifier] for _, identifier in TARGETS)
    _writer_fence(connection, first)
    sequence = _failed_stop(connection, second, True)
    with pytest.raises(psycopg.errors.RaiseException, match='separately acknowledged recovery'):
        with connection.transaction():
            connection.execute('SELECT v3_meta.purge_set_writer_fence(%s,false)', (first,))
    connection.execute('SELECT v3_meta.purge_set_writer_fence(%s,false,%s)', (first, sequence))
    connection.execute('SELECT v3_meta.purge_recycle_writer_sessions(%s,false)', (second,))
    connection.execute('SELECT v3_meta.purge_verify_writer_fence(%s,false,%s)', (second, 'off'))
    payloads = connection.execute(
        """SELECT operational_payload FROM v3_meta.derived_generation_purge_event
           WHERE event_kind='WRITER_FENCE_RESTORED' ORDER BY event_sequence""",
    ).fetchall()
    assert len(payloads) == 3
    assert all(payload['acknowledge_failed_stop'] == sequence for payload, in payloads)
    assert payloads[-1][0]['verified'] is True
    assert connection.execute(
        """SELECT failure_evidence FROM v3_meta.derived_generation_purge_event
           WHERE event_sequence=%s""", (sequence,),
    ).fetchone()[0] == {'integrity_failed': True}
    # Recovery may recheck the durable acknowledgement without inventing a
    # FAILED_STOP; ordinary mutators retain the independent integrity fence.
    connection.execute('SELECT v3_meta.purge_set_writer_fence(%s,false)', (first,))
    _writer_fence(connection, first)
    connection.execute('RESET ROLE')
    with pytest.raises(psycopg.errors.RaiseException, match='integrity failure stops purge'):
        with connection.transaction():
            connection.execute('SELECT v3_meta.purge_assert_fences(%s,%s)', (first, 'system_search'))


def test_writer_restore_rejects_invalid_or_wrong_plan_acknowledgements(database):
    connection = database[0]
    ids = _authorize(database)
    first, second = (ids[identifier] for _, identifier in TARGETS)
    _writer_fence(connection, first)
    non_integrity = _failed_stop(connection, first, False)
    authorized = connection.execute(
        "SELECT min(event_sequence) FROM v3_meta.derived_generation_purge_event WHERE event_kind='AUTHORIZED'",
    ).fetchone()[0]
    for sequence in (-1, 0, 9223372036854775807, authorized, non_integrity):
        with pytest.raises(psycopg.errors.RaiseException, match='exact integrity failure'):
            with connection.transaction():
                connection.execute('SELECT v3_meta.purge_set_writer_fence(%s,false,%s)', (first, sequence))
    integrity = _failed_stop(connection, second, True)
    with pytest.raises(psycopg.errors.RaiseException, match='only valid for writer restoration'):
        with connection.transaction():
            connection.execute('SELECT v3_meta.purge_set_writer_fence(%s,true,%s)', (first, integrity))
    # Deliberately corrupt only the second request in this disposable fixture
    # to prove a valid event from another plan cannot authorize restoration.
    connection.execute('RESET ROLE')
    connection.execute('ALTER TABLE v3_meta.derived_generation_purge_request DISABLE TRIGGER retained_purge_request')
    try:
        connection.execute('UPDATE v3_meta.derived_generation_purge_request SET plan_sha256=%s WHERE purge_id=%s',
                           ('f' * 64, second))
    finally:
        connection.execute('ALTER TABLE v3_meta.derived_generation_purge_request ENABLE TRIGGER retained_purge_request')
    connection.execute('SET ROLE v3_derived_purge_executor')
    with pytest.raises(psycopg.errors.RaiseException, match='exact integrity failure'):
        with connection.transaction():
            connection.execute('SELECT v3_meta.purge_set_writer_fence(%s,false,%s)', (first, integrity))
    assert not connection.execute(
        "SELECT 1 FROM v3_meta.derived_generation_purge_event WHERE event_kind='WRITER_FENCE_RESTORED'",
    ).fetchone()


def test_committed_integrity_failed_rewrite_acknowledgement_requires_departed_backend(database):
    # This fixture installs 016 only. The fence's copy-aware STATE_SQL also reads
    # 019's functions (proved in tests/test_v3_purge_copy_operator_pg18.py); the
    # 016 semantics under test are the shared part, LEGACY_STATE_SQL.
    from scripts.operator.lib.v3_purge_state import LEGACY_STATE_SQL as STATE_SQL

    connection = database[0]
    ids = _authorize(database)
    purge_id = ids[TARGETS[0][1]]
    _writer_fence(connection, purge_id)
    with _fresh_purge_controller(connection) as connection:
        connection.execute('SELECT v3_meta.purge_set_relation_autovacuum(%s,%s,false)',
                           (purge_id, 'system_search'))
        for request_id in ids.values():
            assert _batch(connection, request_id, 'system_search') == 12
        # The phase check refuses any other writing backend; let the batch's
        # maintenance finish first, as the other purge PG18 tests do.
        _wait_for_fixture_maintenance(connection)
        connection.execute('SELECT v3_meta.complete_derived_payload_relation(%s,%s,%s)',
                           (purge_id, 'system_search', Jsonb(_receipt())))
        with _application_worker(connection) as worker:
            started = worker.execute(
                "SELECT v3_meta.purge_record_event(%s,'REWRITE_STARTED','system_search',%s)",
                (purge_id, Jsonb(_receipt())),
            ).fetchone()[0]
            before = worker.execute("SELECT pg_relation_filenode('v3_derived.system_search')").fetchone()[0]
            worker.execute('VACUUM (FULL, ANALYZE) v3_derived.system_search')
            assert worker.execute("SELECT pg_relation_filenode('v3_derived.system_search')").fetchone()[0] != before
            failure = connection.execute(
                "SELECT v3_meta.purge_record_event(%s,'FAILED_STOP','system_search',%s)",
                (purge_id, Jsonb({'integrity_failed': True, 'rewrite_committed': True,
                                 'start_event': started})),
            ).fetchone()[0]
            # A terminal failure does not excuse a live recorded backend,
            # even after its VACUUM has committed and it is merely idle.
            with pytest.raises(psycopg.errors.RaiseException, match='resolve open destructive operation'):
                with connection.transaction():
                    connection.execute('SELECT v3_meta.purge_set_writer_fence(%s,false,%s)',
                                       (purge_id, failure))
        with pytest.raises(psycopg.errors.RaiseException, match='resolve open destructive operation'):
            with connection.transaction():
                connection.execute('SELECT v3_meta.purge_set_writer_fence(%s,false)', (purge_id,))
        with pytest.raises(psycopg.errors.RaiseException, match='exact integrity failure'):
            with connection.transaction():
                connection.execute('SELECT v3_meta.purge_set_writer_fence(%s,false,%s)',
                                   (purge_id, failure + 1000))
        # Another genuine integrity failure for this plan cannot acknowledge
        # the failed rewrite: relation/start-event/commit proof must match.
        with pytest.raises(psycopg.errors.RaiseException, match='resolve open destructive operation'):
            with connection.transaction():
                unrelated = _failed_stop(connection, purge_id, True)
                connection.execute('SELECT v3_meta.purge_set_writer_fence(%s,false,%s)',
                                   (purge_id, unrelated))
        # A different maintenance backend cannot be ignored merely because
        # the original recorded backend has gone. Slow a tiny expression index
        # so both real progress views can be observed deterministically.
        connection.execute('RESET ROLE')
        connection.execute('''CREATE FUNCTION v3_meta.test_ack_progress_key(value_ bigint) RETURNS bigint
            LANGUAGE plpgsql IMMUTABLE AS $$ BEGIN PERFORM pg_sleep(0.1); RETURN value_; END $$''')
        connection.execute('''CREATE INDEX test_ack_progress_key ON v3_derived.system_search
            (v3_meta.test_ack_progress_key(system_id64))''')
        connection.execute('SET ROLE v3_derived_purge_executor')
        for operation, command in (
            ('rewrite', 'VACUUM (FULL) v3_derived.system_search'),
            ('analyze', 'ANALYZE v3_derived.system_search'),
        ):
            with _application_worker(connection) as maintenance:
                with _running_operation(maintenance, command) as future:
                    _wait_for_database_operation(connection, maintenance, future, operation)
                    with pytest.raises(psycopg.errors.RaiseException, match='resolve open destructive operation'):
                        with connection.transaction():
                            connection.execute('SELECT v3_meta.purge_set_writer_fence(%s,false,%s)',
                                               (purge_id, failure))
        _wait_for_fixture_maintenance(connection)
        connection.execute('SELECT v3_meta.purge_set_writer_fence(%s,false,%s)', (purge_id, failure))
        connection.execute('SELECT v3_meta.purge_recycle_writer_sessions(%s,false)', (purge_id,))
        connection.execute('SELECT v3_meta.purge_verify_writer_fence(%s,false,%s)', (purge_id, 'off'))
        assert connection.execute(
            """SELECT operational_payload->>'acknowledge_failed_stop',operational_payload->'verified'
               FROM v3_meta.derived_generation_purge_event WHERE event_kind='WRITER_FENCE_RESTORED'
               ORDER BY event_sequence DESC LIMIT 1""",
        ).fetchone() == (str(failure), True)
        assert not connection.execute(
            """SELECT 1 FROM v3_meta.derived_generation_purge_event
               WHERE event_kind IN ('REWRITE_VERIFIED','AUTOVACUUM_RESTORED')""",
        ).fetchone()
        assert connection.execute(
            "SELECT failure_evidence->'integrity_failed' FROM v3_meta.derived_generation_purge_event WHERE event_sequence=%s",
            (failure,),
        ).fetchone()[0] is True
        # P2a uses the authenticated owner login for metadata-only state.
        # It keeps ordinary mutators fenced after owner acknowledgement.
        connection.execute('RESET ROLE')
        observed = _fence_sql_rows(connection, STATE_SQL)[0][0]
        assert any(event['event_kind'] == 'FAILED_STOP' and event['event_sequence'] == failure
                   for event in observed['unresolved'])
