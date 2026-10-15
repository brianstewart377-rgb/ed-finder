"""Delete-phase transaction boundaries; all doubles are local and deterministic."""
from copy import deepcopy
import json

import pytest

from scripts.operator.lib import v3_purge_transactions as tool

IDS = list(tool.TARGET_IDS)


def state():
    return {'open_events': [], 'writer_fence': None, 'integrity_failures': [],
            'target_counts': dict.fromkeys(IDS, 2), 'relation_bytes': 4096,
            'vacuum_running': False,
            'ages': [{'scope': 'heap', 'xid_age': 10, 'mxid_age': 10}]}


def test_writer_fence_commits_before_recycle_and_fresh_probe_before_verification():
    calls = []
    def query(sql, params=None, *, write=False):
        assert write
        calls.append(sql)
        return {'sessions_recycled': 2} if sql == tool.WRITER_RECYCLE_SQL else {'verified': True}
    def probe():
        assert calls == [tool.WRITER_SET_SQL, tool.WRITER_RECYCLE_SQL]
        calls.append('fresh_login')
        return 'off'
    result = tool.writer_fence(query, IDS[0], False, probe)
    assert result['verified'] is True
    assert calls == [tool.WRITER_SET_SQL, tool.WRITER_RECYCLE_SQL, 'fresh_login', tool.WRITER_VERIFY_SQL]
    assert 'purge_set_writer_fence' in calls[0]
    assert 'purge_recycle_writer_sessions' in calls[1]


def test_wrong_fresh_writer_probe_never_records_verification():
    calls = []
    def query(sql, *_args, **_kwargs):
        calls.append(sql)
        return {}
    with pytest.raises(tool.PurgeTransactionError, match='fresh_probe_failed'):
        tool.writer_fence(query, IDS[0], False, lambda: 'on')
    assert calls == [tool.WRITER_SET_SQL, tool.WRITER_RECYCLE_SQL]


def test_verified_writer_fence_adoption_and_restore_idempotence_do_not_mutate():
    for enabled in (True, False):
        observed = state()
        observed['writer_fence'] = {
            'event_kind': 'WRITER_FENCE_ENABLED' if enabled else 'WRITER_FENCE_RESTORED',
            'operational_payload': {'verified': True},
        }
        def query(sql, *_args, write=False):
            assert sql in (tool.PHASE_STATE_SQL, tool._RECOVERY_STATE_READ) and not write
            return deepcopy(observed)
        assert tool.writer_fence(query, IDS[0], enabled, lambda: pytest.fail('no probe'),
                                 purge_ids=IDS)['adopted'] is True


@pytest.mark.parametrize('failure', ('different_relation', 'xid', 'mxid', 'vacuum'))
def test_autovacuum_adoption_checks_ledgered_ceiling_before_any_mutation(failure):
    observed = state()
    observed['open_events'] = [{'event_kind': 'AUTOVACUUM_DISABLED', 'relation_code': 'system_search',
                               'operational_payload': {'heap': {'xid_ceiling': 100, 'mxid_ceiling': 100}}}]
    if failure == 'different_relation':
        observed['open_events'][0]['relation_code'] = 'body_mechanics'
    elif failure == 'vacuum':
        observed['vacuum_running'] = True
    else:
        observed['ages'][0][failure + '_age'] = 100
    def query(sql, *_args, write=False):
        assert sql in (tool.PHASE_STATE_SQL, tool._RECOVERY_STATE_READ) and not write
        return deepcopy(observed)
    with pytest.raises(tool.PurgeTransactionError):
        tool.autovacuum_fence(query, IDS, 'system_search')


def test_same_relation_autovacuum_fence_is_adopted_after_age_observation():
    observed = state()
    observed['open_events'] = [{'event_kind': 'AUTOVACUUM_DISABLED', 'relation_code': 'system_search',
                               'operational_payload': {'heap': {'xid_ceiling': 100, 'mxid_ceiling': 100}}}]
    def query(sql, *_args, write=False):
        assert sql in (tool.PHASE_STATE_SQL, tool._RECOVERY_STATE_READ) and not write
        return deepcopy(observed)
    assert tool.autovacuum_fence(query, IDS, 'system_search')['adopted'] is True


def test_departed_open_batch_is_resolved_before_any_fence_restore():
    observed = state()
    observed['open_events'] = [{'event_kind': 'BATCH_STARTED', 'event_sequence': 7,
                               'purge_id': IDS[0], 'relation_code': 'system_search',
                               'backend_alive': False,
                               'operational_payload': {'low': [1], 'high': [2]}}]
    calls = []
    def query(sql, params=None, *, write=False):
        calls.append(sql)
        if sql in (tool.PHASE_STATE_SQL, tool._RECOVERY_STATE_READ):
            assert not write
            return deepcopy(observed)
        if sql == tool.BATCH_RANGE_SQL:
            assert not write and params['start_event'] == '7'
            return {'selected': 2, 'range_rows': 2}
        assert sql == tool.ROLLBACK_BATCH_SQL and write
        assert json.loads(params['evidence']) == {
            'recovered': True, 'start_event': 7, 'low': [1], 'high': [2], 'backend_departed': True,
            'selected': 2, 'range_rows': 2,
            'resolution_evidence': 'departed_backend_atomic_commit_receipt_and_intact_key_range'}
        return {'event_sequence': 8}
    assert tool.resolve_batches(query, IDS)['resolved_batch_events'] == [8]
    assert calls == [tool._RECOVERY_STATE_READ, tool.BATCH_RANGE_SQL, tool.ROLLBACK_BATCH_SQL]


def test_open_batch_still_live_after_cancel_never_records_rollback():
    observed = state()
    observed['open_events'] = [{'event_kind': 'BATCH_STARTED', 'event_sequence': 7,
                               'purge_id': IDS[0], 'relation_code': 'system_search',
                               'backend_alive': True, 'operational_payload': {}}]
    now = [0]
    calls = []
    def query(sql, *_args, write=False):
        calls.append(sql)
        if sql in (tool.PHASE_STATE_SQL, tool._RECOVERY_STATE_READ):
            return deepcopy(observed)
        assert sql == tool.CANCEL_BATCH_SQL and write
        return {'cancelled': True}
    def sleep(duration):
        now[0] += duration
    with pytest.raises(tool.PurgeTransactionError, match='backend_did_not_exit'):
        tool.resolve_batches(query, IDS, clock=lambda: now[0], sleep=sleep, maximum_seconds=1)
    assert calls.count(tool.CANCEL_BATCH_SQL) == 1
    assert tool.ROLLBACK_BATCH_SQL not in calls


def test_abort_reports_shortfall_without_mutation():
    observed = state()
    observed['open_events'] = [{'event_kind': 'AUTOVACUUM_DISABLED', 'relation_code': 'system_search'}]
    def query(sql, *_args, write=False):
        assert sql in (tool.RELATION_BYTES_SQL, tool._RECOVERY_STATE_READ) and not write
        if sql == tool.RELATION_BYTES_SQL:
            return {'relation_bytes': 4096}
        return deepcopy(observed)
    with pytest.raises(tool.PurgeTransactionError, match='headroom_insufficient') as exc:
        tool.abort_relation(query, IDS, 'system_search', {'autovacuum_budget_bytes': 4096,
                                                        'filesystem_free_bytes': 100_000_000_000})
    assert exc.value.evidence['shortfall_bytes'] == 4096


def test_payload_batch_waits_before_every_committed_start_and_calls_only_016():
    calls = []
    def query(sql, params=None, *, write=False):
        calls.append(sql)
        if sql == tool.COMPETING_WRITER_SQL:
            assert not write
            return {'competing_writers': 0, 'background_writers': 0}
        assert sql == tool.BATCH_SQL and write
        assert json.loads(params['evidence'])['competing_writer_wait']['attempts'] == 1
        return {'rows_affected': 1}
    for _ in range(2):
        assert tool.payload_batch(query, IDS[0], 'system_search', 1, {})['rows_affected'] == 1
    assert calls == [tool.COMPETING_WRITER_SQL, tool.BATCH_SQL] * 2
    assert tool.BATCH_SQL.index('purge_start_payload_batch') < tool.BATCH_SQL.index('COMMIT;')
    assert tool.BATCH_SQL.index('COMMIT;') < tool.BATCH_SQL.index('purge_derived_payload_batch')


def test_unscoped_failed_stop_uses_sql_null_relation():
    def query(sql, params=None, *, write=False):
        assert sql == tool.FAILED_STOP_SQL and write
        assert 'relation' not in params
        return {'failed_stop_events': [1, 2]}
    assert tool.record_failed_stop(query, IDS, {'integrity_failed': False})['failed_stop_events'] == [1, 2]


def test_payload_batch_uses_wait_before_fresh_host_measurements_without_waiting_again():
    waited = {'maximum_seconds': 30, 'elapsed_seconds': 2, 'attempts': 3,
              'background_writer_observed': True, 'remaining_competing_writers': 0}
    def query(sql, params=None, *, write=False):
        assert sql == tool.BATCH_SQL and write
        assert json.loads(params['evidence'])['competing_writer_wait'] == waited
        return {'rows_affected': 1}
    assert tool.payload_batch(query, IDS[0], 'system_search', 1,
                               {'competing_writer_wait': waited})['rows_affected'] == 1


def test_payload_batch_rejects_invalid_supplied_wait_without_mutation():
    def query(*_args, **_kwargs):
        pytest.fail('invalid evidence cannot reach the database')
    with pytest.raises(tool.PurgeTransactionError, match='competing_writer_wait_invalid'):
        tool.payload_batch(query, IDS[0], 'system_search', 1, {'competing_writer_wait': {}})


def test_recovery_metadata_never_scans_payload_or_acquires_a_write_transaction():
    sql = tool._RECOVERY_STATE_READ
    assert sql.startswith('BEGIN READ ONLY;')
    assert 'v3_derived.' not in sql
    assert 'pg_stat_activity' in sql and 'a.backend_start=e.backend_start' in sql
    assert 'SET ROLE' not in sql


def test_shared_plan_failure_has_one_exact_acknowledgement_sequence():
    calls = []
    def query(sql, params=None, *, write=False):
        assert write and sql == tool.FAILED_STOP_SQL
        assert json.loads(params['purge_ids']) == [IDS[0]]
        calls.append(json.loads(params['evidence']))
        return {'failed_stop_events': [17 if len(calls) == 1 else 18]}
    assert tool.record_failed_stop(query, IDS, {'integrity_failed': True})['failed_stop_events'] == [17]
    tool.acknowledge_failure(query, IDS, 17)
    assert calls[1]['acknowledge_failed_stop'] == 17
    assert calls[1]['integrity_failed'] is False


def test_budgeted_abort_records_measured_evidence_before_dedicated_restoration():
    observed = state()
    observed['open_events'] = [{'event_kind': 'AUTOVACUUM_DISABLED', 'relation_code': 'system_search'}]
    calls = []
    def query(sql, params=None, *, write=False):
        if sql == tool._RECOVERY_STATE_READ:
            assert not write
            return deepcopy(observed)
        if sql == tool.RELATION_BYTES_SQL:
            assert not write and params == {'relation': 'system_search'}
            return {'relation_bytes': 4096}
        assert write
        calls.append(sql)
        if sql == tool.RELATION_FAILURE_SQL:
            payload = json.loads(params['evidence'])
            assert payload['aborted'] is True
            assert payload['autovacuum_budget_bytes'] == 4096
            assert payload['filesystem_free_bytes'] == 100_000_004_096
            return {'failed_stop_events': [19]}
        assert sql == tool.AUTOVACUUM_SQL and params['enabled'] == 'true'
        return {'autovacuum_enabled': True}
    result = tool.abort_relation(query, IDS, 'system_search', {
        'autovacuum_budget_bytes': 4096, 'filesystem_free_bytes': 100_000_004_096})
    assert result['waiting_for_rewrite'] is True
    assert calls == [tool.RELATION_FAILURE_SQL, tool.AUTOVACUUM_SQL]


@pytest.mark.parametrize('remaining', (0, 1, 3, None))
def test_departed_batch_range_mismatch_records_nonintegrity_stop_and_leaves_start_open(remaining):
    observed = state()
    observed['open_events'] = [{'event_kind': 'BATCH_STARTED', 'event_sequence': 7,
                               'purge_id': IDS[0], 'relation_code': 'system_search',
                               'backend_alive': False,
                               'operational_payload': {'low': [1], 'high': [2], 'selected': 2}}]
    calls = []
    def query(sql, params=None, *, write=False):
        calls.append(sql)
        if sql == tool._RECOVERY_STATE_READ:
            assert not write
            return deepcopy(observed)
        if sql == tool.BATCH_RANGE_SQL:
            assert not write
            return {'selected': 2, 'range_rows': remaining}
        assert sql == tool.RELATION_FAILURE_SQL and write
        evidence = json.loads(params['evidence'])
        assert evidence['condition'] == 'batch_range_evidence_inconsistent'
        assert evidence['integrity_failed'] is False
        assert evidence['recorded_key_range'] == {'low': [1], 'high': [2]}
        return {'failed_stop_events': [8]}
    with pytest.raises(tool.PurgeTransactionError, match='batch_range_evidence_inconsistent'):
        tool.resolve_batches(query, IDS)
    assert calls == [tool._RECOVERY_STATE_READ, tool.BATCH_RANGE_SQL, tool.RELATION_FAILURE_SQL]
    assert tool.ROLLBACK_BATCH_SQL not in calls


def test_recorded_range_observation_uses_only_closed_relation_mapping_and_bound_identity():
    sql = tool.BATCH_RANGE_SQL
    assert sql.startswith('SET ROLE v3_derived_purge_executor;')
    assert '%(start_event)s::bigint' in sql and '%(purge_id)s::uuid' in sql
    assert 'x.economy_ordinal' in sql and 'b.low[3]::smallint' in sql
    for relation in tool.RELATIONS:
        assert 'FROM v3_derived.' + relation in sql
    assert 'DELETE FROM' not in sql and 'UPDATE ' not in sql


def test_abort_relation_size_observation_uses_catalog_size_without_exact_row_scans():
    assert 'pg_total_relation_size(' in tool.RELATION_BYTES_SQL
    assert 'count(*)' not in tool.RELATION_BYTES_SQL
    for relation in tool.RELATIONS:
        assert "'v3_derived." + relation + "'::regclass" in tool.RELATION_BYTES_SQL
