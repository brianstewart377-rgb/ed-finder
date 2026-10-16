"""Deterministic contracts for the three separate rewrite transactions."""
from copy import deepcopy
import json

import pytest

from scripts.operator.lib import v3_purge_rewrite as tool

IDS = list(tool.tx.TARGET_IDS)
RELATION = 'system_search'


def opened():
    return {'purge_id': IDS[0], 'relation_code': RELATION, 'event_sequence': 7,
            'event_kind': 'REWRITE_STARTED', 'backend_pid': 123, 'backend_start': '2026-10-15T10:00:00Z'}


def state(**overrides):
    return {'relation_oid': 42, 'identity_matches': True, 'backend_alive': False,
            'rewrite_running': False, 'analyze_running': False,
            'relfilenode': 101, 'relfilenode_before': 100, **overrides}


def verified(**overrides):
    return {'relation_oid': 42, 'identity_matches': True, 'relfilenode': 101,
            'relfilenode_before': 100, 'analyze_verified': True, 'snapshot_verified': True, 'target_counts_zero': True,
            'invalid_foreign_keys': 0, 'invalid_indexes': 0, 'invalid_triggers': 0,
            'heap_bytes': 100, 'index_bytes': 200, 'relation_bytes': 300, **overrides}


def receipt():
    return {'filesystem_free_bytes': tool.FLOOR_BYTES + 1500, 'wal_bytes': 0,
            'rewrite_peak_bytes': 1000, 'receipt_sha256': 'a' * 64}


@pytest.mark.parametrize('relation', tool.tx.RELATIONS)
def test_closed_command_mapping_never_accepts_an_identifier_from_input(relation):
    assert tool.rewrite_command(relation) == 'VACUUM (FULL, ANALYZE) v3_derived.' + relation + ';'
    assert tool.analyze_command(relation) == 'ANALYZE v3_derived.' + relation + ';'
    with pytest.raises(ValueError, match='purge_relation_invalid'):
        tool.rewrite_command(relation + '; SELECT 1')


def test_three_step_sql_commits_start_before_marker_and_vacuum_is_standalone():
    assert tool.START_SQL.index('purge_record_event') < tool.START_SQL.index('COMMIT;')
    assert tool.START_SQL.index('COMMIT;') < tool.START_SQL.index("'start_event'")
    assert 'VACUUM' not in tool.START_SQL
    assert tool.rewrite_command(RELATION).count(';') == 1
    assert 'BEGIN' not in tool.rewrite_command(RELATION)
    assert tool.session_setup(120_000).startswith('SET ROLE v3_derived_purge_executor;')
    assert "SET lock_timeout='5s'" in tool.session_setup(120_000)
    assert "statement_timeout='120000ms'" in tool.session_setup(120_000)
    assert 'REWRITE_VERIFIED' not in tool.START_SQL
    assert 'purge_record_event' in tool.EVENT_SQL


@pytest.mark.parametrize('peak', (None, False, -1, 1.5, '1000', 2**63))
def test_missing_or_invalid_rehearsal_peak_refuses_before_database_or_timeout(peak):
    plan = {'rewrite': {RELATION: {'rewrite_peak_bytes': peak, 'statement_timeout_ms': 1000}}}
    with pytest.raises(ValueError, match='rewrite_peak_not_measured'):
        tool.rewrite_configuration(plan, RELATION)
    def query(*_args, **_kwargs):
        pytest.fail('unmeasured rewrite must not reach database')
    with pytest.raises(ValueError, match='rewrite_peak_not_measured'):
        tool.start_rewrite(query, IDS, RELATION, {**receipt(), 'rewrite_peak_bytes': peak})


@pytest.mark.parametrize('timeout', (None, False, 0, -1, 1.5, '1000', 2**31))
def test_per_relation_timeout_requires_explicit_bounded_integer(timeout):
    with pytest.raises(ValueError, match='rewrite_statement_timeout_not_measured'):
        tool.rewrite_configuration({'rewrite': {RELATION: {'rewrite_peak_bytes': 1000,
                                                          'statement_timeout_ms': timeout}}}, RELATION)
    with pytest.raises(ValueError, match='rewrite_statement_timeout_not_measured'):
        tool.session_setup(timeout)


def test_valid_rehearsal_configuration_preserves_exact_values():
    config = {'rewrite_peak_bytes': 1000, 'statement_timeout_ms': 120_000}
    assert tool.rewrite_configuration({'rewrite': {RELATION: config}}, RELATION) == config


def test_projected_peak_factor_uses_exact_integer_rounding_and_inclusive_floor():
    def query(sql, params=None, *, write=False):
        assert sql == tool.START_SQL and write
        assert json.loads(params['evidence'])['rewrite_peak_bytes'] == 1001
        return {'start_event': 7, 'backend_pid': 123, 'backend_start': '2026-10-15T10:00:00Z',
                'relfilenode_before': 100}
    with pytest.raises(ValueError, match='rewrite_projected_headroom_insufficient'):
        tool.start_rewrite(query, IDS, RELATION, {**receipt(), 'rewrite_peak_bytes': 1001})
    tool.start_rewrite(query, IDS, RELATION, {**receipt(), 'rewrite_peak_bytes': 1001,
                                            'filesystem_free_bytes': tool.FLOOR_BYTES + 1502})


def test_recovery_catalog_reads_never_touch_payload_or_observe_pid_without_start():
    assert 'FROM v3_derived.' not in tool.STATE_SQL
    assert 'pg_stat_progress_cluster' in tool.STATE_SQL
    assert 'pg_stat_progress_analyze' in tool.STATE_SQL
    assert 'a.pid=e.backend_pid AND a.backend_start=e.backend_start' in tool.STATE_SQL
    assert 'pid=%(backend_pid)s::integer AND backend_start=%(backend_start)s::timestamptz' in tool.BACKEND_SQL
    for sql in (tool.STATE_SQL, tool.BACKEND_SQL):
        assert sql.startswith('BEGIN READ ONLY;')
        assert 'SET ROLE' not in sql


def test_changed_filenode_recovery_analyzes_then_verifies_without_second_vacuum():
    calls = []
    def query(sql, params=None, *, write=False):
        calls.append(sql)
        if sql == tool.tx._RECOVERY_STATE_READ:
            return {'open_events': [opened()], 'integrity_failures': []}
        if sql == tool.STATE_SQL:
            return state()
        if sql == tool.VERIFY_SQL:
            assert calls[-2] == 'ANALYZE'
            return verified()
        assert sql == tool.EVENT_SQL and write
        assert params['kind'] == 'REWRITE_VERIFIED'
        evidence = json.loads(params['evidence'])
        assert evidence['recovered'] is True and evidence['start_event'] == 7
        return {'event_sequence': 8}
    def analyze(sql):
        assert sql == tool.analyze_command(RELATION)
        calls.append('ANALYZE')
    result = tool.resolve_rewrites(query, IDS, RELATION, analyze=analyze, receipt=receipt)
    assert result == {'resolved_rewrite_events': [8], 'verified_relations': [RELATION],
                      'rolled_back_relations': []}
    assert all('VACUUM (FULL' not in sql for sql in calls)


def test_unchanged_filenode_recovery_closes_record_and_leaves_relation_available_for_fresh_rewrite():
    calls = []
    def query(sql, params=None, *, write=False):
        calls.append(sql)
        if sql == tool.tx._RECOVERY_STATE_READ:
            return {'open_events': [opened()], 'integrity_failures': []}
        if sql == tool.STATE_SQL:
            return state(relfilenode=100)
        assert sql == tool.EVENT_SQL and write
        assert params['kind'] == 'REWRITE_ROLLED_BACK'
        assert json.loads(params['evidence'])['relfilenode_unchanged'] is True
        return {'event_sequence': 8}
    result = tool.resolve_rewrites(query, IDS, RELATION)
    assert result['verified_relations'] == [] and result['rolled_back_relations'] == [RELATION]
    assert calls == [tool.tx._RECOVERY_STATE_READ, tool.STATE_SQL, tool.EVENT_SQL]


@pytest.mark.parametrize('failure', ('analyze_verified', 'snapshot_verified', 'target_counts_zero', 'identity_matches',
                                    'invalid_foreign_keys', 'invalid_indexes', 'invalid_triggers'))
def test_failed_verification_of_committed_rewrite_records_integrity_stop(failure):
    calls = []
    def query(sql, params=None, *, write=False):
        calls.append(sql)
        if sql == tool.VERIFY_SQL:
            return verified(**{failure: 1 if failure.startswith('invalid_') else False})
        assert sql == tool.tx.RELATION_FAILURE_SQL and write
        evidence = json.loads(params['evidence'])
        assert evidence['rewrite_committed'] is True and evidence['integrity_failed'] is True
        return {'failed_stop_events': [9]}
    with pytest.raises(ValueError, match='rewrite_verification_failed'):
        tool.verify_rewrite(query, IDS, RELATION, receipt(), event=opened())
    assert calls == [tool.VERIFY_SQL, tool.tx.RELATION_FAILURE_SQL]


@pytest.mark.parametrize('progress', ('backend_alive', 'rewrite_running', 'analyze_running'))
def test_redispatch_refuses_running_relation_without_signalling_any_backend(progress):
    def query(sql, *_args, write=False):
        assert not write
        if sql == tool.tx._RECOVERY_STATE_READ:
            return {'open_events': [opened()], 'integrity_failures': []}
        assert sql == tool.STATE_SQL
        return state(**{progress: True})
    with pytest.raises(ValueError, match='purge_rewrite_backend_still_active'):
        tool.resolve_rewrites(query, IDS, RELATION, cancel=False)


def test_cancellation_waits_for_identity_and_both_progress_views_before_resolution():
    observations = [state(backend_alive=True, rewrite_running=True),
                    state(analyze_running=True), state(relfilenode=100)]
    calls, now = [], [0.0]
    def query(sql, params=None, *, write=False):
        calls.append(sql)
        if sql == tool.tx._RECOVERY_STATE_READ:
            return {'open_events': [opened()], 'integrity_failures': []}
        if sql == tool.STATE_SQL:
            return deepcopy(observations.pop(0))
        if sql == tool.CANCEL_SQL:
            assert write and params['purge_id'] == IDS[0] and params['relation'] == RELATION
            return {'cancelled': True}
        assert not observations and sql == tool.EVENT_SQL and write
        assert params['kind'] == 'REWRITE_ROLLED_BACK'
        return {'event_sequence': 8}
    def sleep(seconds):
        now[0] += seconds
    tool.resolve_rewrites(query, IDS, clock=lambda: now[0], sleep=sleep)
    assert calls.count(tool.CANCEL_SQL) == 1
    assert calls[-2:] == [tool.STATE_SQL, tool.EVENT_SQL]
    assert 'pg_cancel_backend' not in tool.CANCEL_SQL
    assert 'cancel_purge_rewrite' in tool.CANCEL_SQL


def test_backend_that_survives_cancel_never_gets_a_resolution_event():
    now, calls = [0.0], []
    def query(sql, *_args, **_kwargs):
        calls.append(sql)
        if sql == tool.tx._RECOVERY_STATE_READ:
            return {'open_events': [opened()], 'integrity_failures': []}
        return state(backend_alive=True) if sql == tool.STATE_SQL else {'cancelled': True}
    def sleep(seconds):
        now[0] += seconds
    with pytest.raises(ValueError, match='purge_rewrite_backend_did_not_exit'):
        tool.resolve_rewrites(query, IDS, clock=lambda: now[0], sleep=sleep, maximum_seconds=1)
    assert calls.count(tool.CANCEL_SQL) == 1 and tool.EVENT_SQL not in calls


def test_failed_recovered_analyze_stops_integrity_and_never_closes_rewrite():
    def query(sql, params=None, *, write=False):
        if sql == tool.tx._RECOVERY_STATE_READ:
            return {'open_events': [opened()], 'integrity_failures': []}
        if sql == tool.STATE_SQL:
            return state()
        assert sql == tool.tx.RELATION_FAILURE_SQL and write
        evidence = json.loads(params['evidence'])
        assert evidence['integrity_failed'] is True and evidence['rewrite_committed'] is True
        return {'failed_stop_events': [9]}
    def analyze(_sql):
        raise RuntimeError('injected_analyze_failure')
    with pytest.raises(ValueError, match='rewrite_recovery_verification_failed'):
        tool.resolve_rewrites(query, IDS, analyze=analyze, receipt=receipt)


def test_successful_verification_retains_sizes_and_appends_dedicated_016_verifier():
    def query(sql, params=None, *, write=False):
        if sql == tool.VERIFY_SQL:
            return verified()
        assert sql == tool.EVENT_SQL and write and params['kind'] == 'REWRITE_VERIFIED'
        evidence = json.loads(params['evidence'])
        assert evidence['verification']['index_bytes'] == 200
        assert evidence['recovered'] is False
        return {'event_sequence': 8}
    assert tool.verify_rewrite(query, IDS, RELATION, receipt(), event=opened())['event_sequence'] == 8
