"""P2b1 fixed SQL and preflight checks with no production access."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


PATH = Path(__file__).resolve().parents[1] / 'scripts/operator/lib/v3_purge_transactions.py'
SPEC = importlib.util.spec_from_file_location('purge_transactions_test', PATH)
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)


def plan():
    return {'snapshot': {'canonical': {}, 'derived': {'derived_generation_id': tool.PUBLISHED_ID},
                         'spatial': {}, 'retained': {}, 'survivors': {}},
            'targets': [{'id': identity, 'key': key, 'state': state, 'manifest_sha256': 'a' * 64,
                         'payload_counts': dict.fromkeys(tool.RELATIONS, 1)}
                        for identity, key, state in sorted(tool.TARGET_IDENTITIES)],
            'workers_stopped': True, 'plan_sha256': 'b' * 64}


def test_all_sessions_start_with_restricted_role_and_have_bounds():
    constants = [value for key, value in vars(tool).items() if key.endswith('_SQL')]
    assert constants
    for sql in constants:
        if sql == tool.COMPETING_WRITER_SQL:
            assert sql.startswith('BEGIN READ ONLY;')
            assert "SET LOCAL statement_timeout='1s';" in sql
        else:
            assert sql.startswith('SET ROLE v3_derived_purge_executor;')
            assert "SET LOCAL statement_timeout='45min';" in sql
        assert "SET LOCAL lock_timeout='5s';" in sql
        assert sql.endswith('COMMIT;')
        for forbidden in ('RESET ROLE', 'SET SESSION AUTHORIZATION', 'ALTER TABLE',
                          'DELETE FROM', 'UPDATE ', 'INSERT INTO', 'TRUNCATE ', ' CASCADE'):
            assert forbidden not in sql


def test_digest_is_obtained_from_postgres_and_kept_distinct_from_outer_seal():
    calls = []
    def query(sql, params=None, *, write=False):
        assert not write
        calls.append((sql, params))
        return plan() if sql == tool.PLAN_SQL else {'plan_sha256': 'c' * 64}
    result = tool.collect_plan(query, 'd' * 40, 'operator', 'owner-approved purge')
    assert result['plan_sha256'] == 'c' * 64
    assert result['source_git_sha'] == 'd' * 40
    assert 'plan_sha256' not in json.loads(calls[-1][1]['plan'])
    assert 'content_sha256' not in result
    assert '::text' in tool.PLAN_HASH_SQL


@pytest.mark.parametrize(('field', 'bound'), (('actor', 256), ('reason', 2048)))
@pytest.mark.parametrize('value', ('', ' leading', 'trailing ', '\toperator', 'operator\n',
                                 'over_bound', 'padded_to_over_bound'))
def test_plan_rejects_raw_unbounded_or_unstripped_attribution_before_query(field, bound, value):
    if value == 'over_bound':
        value = 'x' * (bound + 1)
    elif value == 'padded_to_over_bound':
        value = ' ' * bound + 'x'
    attribution = {'actor': 'operator', 'reason': 'reviewed purge', field: value}
    def query(*_args, **_kwargs):
        pytest.fail('invalid raw attribution must be rejected before SQL or sealing')
    with pytest.raises(tool.PurgeTransactionError, match='actor_source_or_reason_invalid'):
        tool.collect_plan(query, 'd' * 40, **attribution)


def test_plan_preserves_attribution_at_exact_raw_bounds_in_the_sealed_body():
    attribution = {'actor': 'a' * 256, 'reason': 'r' * 2048}
    def query(sql, params=None, *, write=False):
        assert not write
        if sql == tool.PLAN_SQL:
            return plan()
        assert sql == tool.PLAN_HASH_SQL
        body = json.loads(params['plan'])
        assert {field: body[field] for field in attribution} == attribution
        return {'plan_sha256': 'c' * 64}
    result = tool.collect_plan(query, 'd' * 40, **attribution)
    assert {field: result[field] for field in attribution} == attribution


def test_exclusions_check_direct_archetype_rows_without_ungranted_summary_view():
    assert ('FROM v3_derived.system_archetype WHERE derived_generation_id '
            'IN (SELECT id FROM targets)') in tool.EXCLUSIONS_SQL
    assert 'system_archetype_summary' not in tool.EXCLUSIONS_SQL
    assert 'v3_app.' not in tool.EXCLUSIONS_SQL
    counts = dict.fromkeys(('cluster_run', 'cluster', 'cluster_member', 'system_archetype'), 0)
    assert tool.verify_empty(lambda *_args, **_kwargs: counts) == {
        'empty': True, 'counts': counts, 'database_writes': False}


@pytest.mark.parametrize('failure', ('targets', 'snapshot', 'workers', 'digest'))
def test_authorize_preflight_failure_never_calls_write(failure):
    reviewed = plan()
    current = plan()
    current.pop('workers_stopped')
    current.pop('plan_sha256')
    if failure == 'targets':
        current['targets'][0]['manifest_sha256'] = 'f' * 64
    elif failure == 'snapshot':
        current['snapshot'] = {}
    elif failure == 'workers':
        reviewed['workers_stopped'] = False
    def query(sql, params=None, *, write=False):
        assert not write
        if sql == tool.PLAN_HASH_SQL:
            return {'plan_sha256': ('a' if failure == 'digest' else 'b') * 64}
        assert sql == tool.PLAN_SQL
        return current
    with pytest.raises(tool.PurgeTransactionError):
        tool.authorize(query, reviewed)


def test_competing_background_writer_wait_is_bounded_and_rechecks_without_writes():
    now = [0.0]
    observations = iter((1, 1, 0))
    def query(sql, params=None, *, write=False):
        assert not write and sql == tool.COMPETING_WRITER_SQL
        count = next(observations)
        return {'competing_writers': count, 'background_writers': count}
    def sleep(seconds):
        now[0] += seconds
    result = tool.wait_for_competing_writers(query, clock=lambda: now[0], sleep=sleep)
    assert result['attempts'] == 3
    assert result['elapsed_seconds'] == 2
    assert result['background_writer_observed'] is True
    assert result['maximum_seconds'] == 30
    def blocked(sql, params=None, *, write=False):
        assert not write
        return {'competing_writers': 1, 'background_writers': 0}
    with pytest.raises(tool.PurgeTransactionError, match='wait_exhausted') as exc:
        tool.wait_for_competing_writers(blocked, clock=lambda: now[0], sleep=sleep)
    assert exc.value.evidence['elapsed_seconds'] == 30
    assert exc.value.evidence['attempts'] == 31


def test_wait_retains_production_predicate_including_background_workers():
    assert 'backend_xid IS NOT NULL' in tool.COMPETING_WRITER_SQL
    assert "OR (backend_type='client backend' AND state IS NULL)" in tool.COMPETING_WRITER_SQL
    assert 'backend_xmin' not in tool.COMPETING_WRITER_SQL


@pytest.mark.parametrize('bad', (True, -1, None, '0'))
def test_unknown_competing_writer_observation_fails_closed(bad):
    with pytest.raises(tool.PurgeTransactionError, match='observation_invalid'):
        tool.wait_for_competing_writers(lambda *_args, **_kwargs:
                                        {'competing_writers': bad, 'background_writers': 0})


def test_exclusions_positive_count_fails_read_only_without_authorized_requests():
    def query(sql, params=None, *, write=False):
        assert not write
        return {'cluster_run': 0, 'cluster': 0, 'cluster_member': 0,
                'system_archetype': 1}
    with pytest.raises(tool.PurgeTransactionError, match='unexpected_excluded_payload') as exc:
        tool.verify_empty(query)
    assert exc.value.evidence['integrity_failed'] is True
    assert 'failed_stop_events' not in exc.value.evidence


def test_verify_empty_records_integrity_failure_only_for_two_authenticated_requests():
    ids = list(tool.TARGET_IDS)  # Shape-only mock; real request IDs are ledger UUIDs.
    calls = []
    def query(sql, params=None, *, write=False):
        calls.append((sql, write))
        if sql == tool.REQUESTS_SQL:
            assert not write
            return {'requests': [{'purge_id': identity, 'derived_generation_id': identity,
                                  'plan_sha256': 'a' * 64} for identity in ids]}
        if sql == tool.EXCLUSIONS_SQL:
            assert not write
            return {'cluster_run': 0, 'cluster': 0, 'cluster_member': 1,
                    'system_archetype': 0}
        assert sql == tool.FAILED_STOP_SQL and write
        evidence = json.loads(params['evidence'])
        assert evidence['integrity_failed'] is True
        return {'failed_stop_events': [4, 5]}
    with pytest.raises(tool.PurgeTransactionError) as exc:
        tool.verify_empty(query, purge_ids=ids)
    assert exc.value.evidence['failed_stop_events'] == [4, 5]
    assert [w for _, w in calls] == [False, False, True]


def test_completion_refuses_before_write_when_no_rewrite_evidence_exists():
    reviewed = plan()
    ids = list(tool.TARGET_IDS)
    def query(sql, params=None, *, write=False):
        assert not write
        if sql == tool.REQUESTS_SQL:
            return {'requests': [{'purge_id': identity, 'derived_generation_id': identity,
                                  'plan_sha256': reviewed['plan_sha256'],
                                  'frozen_snapshot': reviewed['snapshot']} for identity in ids]}
        if sql == tool.EXCLUSIONS_SQL:
            return dict.fromkeys(('cluster_run', 'cluster', 'cluster_member', 'system_archetype'), 0)
        assert sql == tool.COMPLETION_STATE_SQL
        return {'targets': [{**t, 'state': 'FAILED', 'payload_counts': dict.fromkeys(tool.RELATIONS, 0)}
                            for t in reviewed['targets']],
                'snapshot': reviewed['snapshot'], 'rewrites': [], 'invalid_foreign_keys': 0,
                'invalid_indexes': 0, 'invalid_triggers': 0}
    with pytest.raises(tool.PurgeTransactionError, match='completion_preconditions_failed'):
        tool.complete(query, reviewed, {}, purge_ids=ids)


@pytest.mark.parametrize('phase', ('authorization', 'completion'))
def test_transport_failure_preserves_wait_evidence_and_never_retries(phase):
    calls = []
    waited = {'maximum_seconds': 30, 'elapsed_seconds': 3, 'attempts': 4,
              'background_writer_observed': True, 'remaining_competing_writers': 0}
    def query(sql, params=None, *, write=False):
        calls.append((sql, params, write))
        raise RuntimeError('must not leak database diagnostics or credential')
    with pytest.raises(tool.PurgeTransactionError, match='write_outcome_unknown') as exc:
        tool._write_after_wait(query, tool.AUTHORIZE_SQL, {'plan': '{}'}, waited, phase)
    assert len(calls) == 1
    assert exc.value.evidence == {**waited, 'transaction_outcome': None}
    assert 'credential' not in str(exc.value)


def test_completion_sql_atomically_proves_snapshot_and_records_both_requests():
    assert 'v3_meta.complete_derived_generation_purge(' in tool.COMPLETE_SQL
    assert 'MATERIALIZED' in tool.COMPLETE_SQL
    assert 'snapshot_verified' in tool.COMPLETE_SQL
    assert "v3_meta.purge_snapshot()=%(snapshot)s::jsonb" in tool.COMPLETE_SQL


def test_wait_observation_transport_failure_preserves_bounds_and_unknown_count():
    def query(sql, params=None, *, write=False):
        assert not write
        raise RuntimeError('private database diagnostic')
    with pytest.raises(tool.PurgeTransactionError, match='observation_failed') as exc:
        tool.wait_for_competing_writers(query)
    assert exc.value.evidence['maximum_seconds'] == 30
    assert exc.value.evidence['attempts'] == 1
    assert exc.value.evidence['remaining_competing_writers'] is None
    assert 'private' not in str(exc.value)


@pytest.mark.parametrize('phase', ('authorize', 'complete'))
def test_late_host_gate_failure_precedes_wait_and_writes(phase):
    reviewed = plan()
    ids = list(tool.TARGET_IDS)
    queries = []
    gate_calls = []
    def query(sql, params=None, *, write=False):
        assert not write
        assert sql != tool.COMPETING_WRITER_SQL
        queries.append(sql)
        if sql == tool.PLAN_HASH_SQL:
            return {'plan_sha256': reviewed['plan_sha256']}
        if sql == tool.PLAN_SQL:
            return {'targets': reviewed['targets'], 'snapshot': reviewed['snapshot']}
        if sql == tool.REQUESTS_SQL:
            return {'requests': [{'purge_id': identity, 'derived_generation_id': identity,
                                  'plan_sha256': reviewed['plan_sha256'],
                                  'frozen_snapshot': reviewed['snapshot']} for identity in ids]}
        if sql == tool.EXCLUSIONS_SQL:
            return dict.fromkeys(('cluster_run', 'cluster', 'cluster_member', 'system_archetype'), 0)
        assert sql == tool.COMPLETION_STATE_SQL
        return {'targets': [{**t, 'state': 'FAILED', 'payload_counts': dict.fromkeys(tool.RELATIONS, 0)}
                            for t in reviewed['targets']],
                'snapshot': reviewed['snapshot'], 'rewrites': list(tool.RELATIONS),
                'invalid_foreign_keys': 0, 'invalid_indexes': 0, 'invalid_triggers': 0}
    def before_write():
        gate_calls.append(len(queries))
        assert queries[-1] == (tool.EXCLUSIONS_SQL if phase == 'authorize' else tool.COMPLETION_STATE_SQL)
        raise ValueError('late_worker_or_storage_gate_refused')
    with pytest.raises(ValueError, match='late_worker_or_storage_gate_refused'):
        if phase == 'authorize':
            tool.authorize(query, reviewed, before_write=before_write)
        else:
            tool.complete(query, reviewed, {'filesystem_free_bytes': 100_000_000_000,
                                           'wal_bytes': 0, 'receipt_sha256': 'a' * 64},
                          purge_ids=ids, before_write=before_write)
    assert gate_calls == [len(queries)]


def test_failed_stop_transport_failure_preserves_observed_integrity_evidence():
    ids = list(tool.TARGET_IDS)
    counts = {'cluster_run': 0, 'cluster': 0, 'cluster_member': 1,
              'system_archetype': 0}
    def query(sql, params=None, *, write=False):
        if sql == tool.REQUESTS_SQL:
            return {'requests': [{'purge_id': identity, 'derived_generation_id': identity,
                                  'plan_sha256': 'a' * 64} for identity in ids]}
        if sql == tool.EXCLUSIONS_SQL:
            return counts
        assert sql == tool.FAILED_STOP_SQL and write
        raise RuntimeError('transport interrupted; must not be disclosed')
    with pytest.raises(tool.PurgeTransactionError, match='purge_failed_stop_outcome_unknown') as exc:
        tool.verify_empty(query, purge_ids=ids)
    assert exc.value.evidence['integrity_failed'] is True
    assert exc.value.evidence['counts'] == counts
    assert exc.value.evidence['failed_stop_events'] is None
    assert 'transport' not in str(exc.value)
