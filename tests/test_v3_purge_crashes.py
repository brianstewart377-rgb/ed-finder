"""Crash-gate orchestration refuses unobserved or incompletely recovered states."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.rehearsal import v3_purge_crashes as tool


def _snapshot(*, node=10, target_rows=0, verified=0, starts=0):
    return {'published': {'system_rating_vector': {'rows': 100, 'fingerprint': '1234'}},
            'pointers': {'derived': 'published'}, 'relation': {
                'oid': 123, 'relfilenode': node, 'kind': 'r', 'catalog_relations': 1,
                'target_rows': target_rows, 'invalid_indexes': 0, 'invalid_foreign_keys': 0,
                'invalid_triggers': 0, 'rewrite_verifications': verified, 'rewrite_starts': starts,
                'last_analyze': '2026-10-16T00:00:02+00:00',
                'last_rewrite_start': '2026-10-16T00:00:01+00:00',
                'monitor_cancellations': 0, 'committed_rows': 100,
                'postmaster_started': '2026-10-16T00:00:00+00:00'}}


@pytest.mark.parametrize(('node', 'expected'), [(10, 'old'), (11, 'new')])
def test_relation_accepts_one_complete_old_or_new_catalog(node, expected):
    assert tool.assert_intact(_snapshot(), _snapshot(node=node)) == expected


@pytest.mark.parametrize(('key', 'value'), [
    ('oid', 124), ('catalog_relations', 2), ('kind', 'i'), ('relfilenode', 0),
    ('invalid_indexes', 1), ('invalid_foreign_keys', 1), ('invalid_triggers', 1),
])
def test_relation_rejects_half_swap_or_invalid_catalog(key, value):
    damaged = _snapshot(node=11)
    damaged['relation'][key] = value
    with pytest.raises(ValueError, match='half_swapped_or_invalid_relation'):
        tool.assert_intact(_snapshot(), damaged)


@pytest.mark.parametrize('field', ['published', 'pointers'])
def test_survivor_fingerprint_and_pointer_changes_refuse_gate(field):
    after = _snapshot(node=11)
    after[field] = {'changed': True}
    with pytest.raises(ValueError, match='published_payload_or_pointer_changed'):
        tool.assert_intact(_snapshot(), after)


def test_verified_recovery_and_same_node_retry_pass():
    recovered = _snapshot(node=11, verified=1, starts=2)
    tool.assert_recovered(_snapshot(), recovered, deepcopy(recovered))


@pytest.mark.parametrize(('key', 'value'), [
    ('target_rows', 1), ('rewrite_verifications', 0), ('relfilenode', 10),
    ('last_analyze', None), ('last_analyze', '2026-10-16T00:00:00+00:00'),
])
def test_unverified_or_unanalyzed_recovery_refuses_gate(key, value):
    recovered = _snapshot(node=11, verified=1, starts=2)
    recovered['relation'][key] = value
    with pytest.raises(ValueError, match='not_verified_or_analyzed'):
        tool.assert_recovered(_snapshot(), recovered, deepcopy(recovered))


@pytest.mark.parametrize(('key', 'value'), [('relfilenode', 12), ('rewrite_starts', 3), ('rewrite_verifications', 2)])
def test_second_redispatch_cannot_repeat_rewrite(key, value):
    recovered = _snapshot(node=11, verified=1, starts=2)
    repeated = deepcopy(recovered)
    repeated['relation'][key] = value
    with pytest.raises(ValueError, match='double_rewrite'):
        tool.assert_recovered(_snapshot(), recovered, repeated)


def test_wait_refuses_action_that_exits_before_progress_is_observed():
    with pytest.raises(RuntimeError, match='not_observed'):
        tool._wait(lambda: False, SimpleNamespace(poll=lambda: 0), reason='not_observed')


def test_wait_requires_real_observation_before_returning():
    result = tool._wait(lambda: {'pid': 42, 'phase': 'seq scanning heap'},
                        SimpleNamespace(poll=lambda: None), reason='not_observed')
    assert result['pid'] == 42


def test_prepare_uses_real_action_order_and_child_relations_before_vector():
    calls = []
    class Harness:
        def start(self): calls.append('start')
        def migrate(self): calls.append('migrate')
        def seed(self): calls.append('seed')
        def action(self, mode):
            calls.append(mode)
            return {'content_sha256': 'a' * 64}, Path('/proof'), 0, 0, 0
        def sql(self, statement, params):
            assert params['published']
            return '0'
    fixture = Harness()
    tool._prepare(fixture, delete_vector=True)
    assert calls == ['start', 'migrate', 'seed', 'plan', 'authorize', 'verify-system-archetype-empty',
                     'delete-system-search', 'rewrite-system-search', 'delete-economy-opportunity',
                     'rewrite-economy-opportunity', 'delete-body-mechanics', 'rewrite-body-mechanics',
                     'delete-system-rating-vector']
    assert fixture.plan == fixture.verification == (Path('/proof'), 'a' * 64)


@pytest.mark.parametrize('scenario', ['rewrite_monitor_cancel', 'rewrite_terminate_backend', 'rewrite_postgres_restart'])
def test_external_interruptions_require_progress_and_target_only_observed_backend(tmp_path, monkeypatch, scenario):
    calls = []
    progress = {'pid': 321, 'phase': 'seq scanning heap'}
    monkeypatch.setattr(tool, '_wait', lambda probe, process, **kwargs: progress)
    harness = SimpleNamespace(container='disposable', sql=lambda sql, params=None: calls.append((sql, params)) or 't',
                              docker=lambda *args: calls.append(args))
    process = SimpleNamespace(wait=lambda timeout: calls.append(('wait', timeout)), returncode=1)
    marker = tmp_path / 'ready'
    result = tool._interrupt(harness, scenario, process, marker)
    assert result['observed_active_rewrite'] == progress
    if scenario == 'rewrite_monitor_cancel':
        assert Path(str(marker) + '.trigger').read_text() == 'observed-active-rewrite\n'
    elif scenario == 'rewrite_terminate_backend':
        statement, params = calls[0]
        assert 'pg_stat_progress_cluster' in statement
        assert 'pg_terminate_backend(pid)' in statement
        assert params == {'pid': 321}
    else:
        assert calls[0] == ('restart', '--time', '0', 'disposable')


@pytest.mark.parametrize('scenario', ['batch_client_before_commit', 'batch_client_after_commit'])
def test_batch_client_kill_requires_authenticated_hook_and_commit_boundary_sleep(tmp_path, monkeypatch, scenario):
    marker = tmp_path / 'fault.json'
    marker.write_text(json.dumps({'scenario': scenario, 'pid': 456}))
    calls = []
    monkeypatch.setattr(tool.os, 'getpgid', lambda pid: 123)
    monkeypatch.setattr(tool, '_json', lambda harness, sql: {'sleeping': True})
    monkeypatch.setattr(tool, '_kill', lambda process: calls.append('kill-wrapper-group'))
    harness = SimpleNamespace(container='disposable', docker=lambda *args: calls.append(args))
    result = tool._interrupt(harness, scenario,
                             SimpleNamespace(pid=123, poll=lambda: None), marker)
    assert result['batch_client_state'] == ('killed_before_commit' if scenario.endswith('before_commit') else 'killed_after_commit')
    assert calls == ['kill-wrapper-group', ('exec', 'disposable', 'killall', '-KILL', 'psql')]


def test_unrelated_hook_pid_is_not_accepted(tmp_path, monkeypatch):
    marker = tmp_path / 'fault.json'
    marker.write_text(json.dumps({'scenario': 'batch_client_after_commit', 'pid': 456}))
    monkeypatch.setattr(tool.os, 'getpgid', lambda pid: 999)
    with pytest.raises(RuntimeError, match='fault_point_not_observed'):
        tool._interrupt(SimpleNamespace(), 'batch_client_after_commit',
                        SimpleNamespace(pid=123, poll=lambda: 1), marker)


@pytest.mark.parametrize('scale,expected', [('tiny', 'tiny'), ('smoke', 'smoke'), ('one_percent', 'smoke')])
def test_suite_uses_fresh_fixture_for_every_scenario_and_records_all_failures(tmp_path, monkeypatch, scale, expected):
    fixtures = []
    def factory(scale, run_id, output):
        output.mkdir(parents=True)
        result = SimpleNamespace(scale=scale, run_id=run_id, output=output, cleanup=lambda: None)
        fixtures.append(result)
        return result
    def fail(fixture, scenario):
        raise RuntimeError('not_observed')
    monkeypatch.setattr(tool, 'run_scenario', fail)
    results = tool.run_crashes(factory, scale, '123-1', tmp_path)
    assert set(results) == set(tool.CRASH_SCENARIOS)
    assert len(fixtures) == len({fixture.output for fixture in fixtures}) == 6
    assert all(fixture.scale == expected for fixture in fixtures)
    assert all(result['passed'] is False and result['cleanup_verified'] is True for result in results.values())
    assert all((fixture.output / 'crash-result.json').is_file() for fixture in fixtures)


def test_cleanup_failure_revokes_an_otherwise_successful_crash(tmp_path, monkeypatch):
    def factory(scale, run_id, output):
        output.mkdir(parents=True)
        def fail_cleanup(): raise RuntimeError('cleanup')
        return SimpleNamespace(output=output, cleanup=fail_cleanup)
    monkeypatch.setattr(tool, 'run_scenario', lambda fixture, scenario: {'passed': True})
    result = tool.run_crashes(factory, 'smoke', '123-1', tmp_path)
    assert all(not entry['passed'] and not entry['cleanup_verified'] for entry in result.values())


@pytest.mark.parametrize('scenario', tool.CRASH_SCENARIOS)
def test_scenario_uses_dispatch_recovery_and_verified_noop_retry(tmp_path, monkeypatch, scenario):
    calls = []
    is_batch = scenario.startswith('batch_client_')
    before = _snapshot(target_rows=100 if is_batch else 0)
    interrupted = deepcopy(before)
    interrupted['relation']['monitor_cancellations'] = 1
    if scenario == 'batch_client_after_commit':
        interrupted['relation']['target_rows'] = 90
    if scenario == 'rewrite_postgres_restart':
        interrupted['relation']['postmaster_started'] = '2026-10-16T00:01:00+00:00'
    if scenario == 'wrapper_after_rewrite_commit':
        interrupted['relation']['relfilenode'] = 11
    recovered = _snapshot(node=11, verified=1, starts=1)
    observed = iter([before, interrupted, recovered, deepcopy(recovered)])
    monkeypatch.setattr(tool, 'snapshot', lambda harness: next(observed))
    monkeypatch.setattr(tool, '_prepare', lambda harness, **kwargs: calls.append(('prepare', kwargs)))
    monkeypatch.setattr(tool, '_interrupt', lambda *args: {'observed_fault_point': scenario})
    process = SimpleNamespace(poll=lambda: 1)
    monkeypatch.setattr(tool.subprocess, 'Popen', lambda *args, **kwargs: process)
    harness = SimpleNamespace(output=tmp_path, environment={}, scale='smoke',
                              counts={tool.RELATION: {tool.controller.PUBLISHED_KEY: 100}},
                              action_argv=lambda mode: ['real-purge-action', mode],
                              action=lambda mode: calls.append(mode), sql=lambda *args: '0',
                              plan_batch_limit=lambda relation: 10)
    result = tool.run_scenario(harness, scenario)
    assert result['passed'] is True
    assert result['recovered_analyze_verified'] is True
    assert result['no_double_rewrite'] is True
    assert calls[0] == ('prepare', {'delete_vector': not is_batch})
    assert calls[1] == 'restore-services'
    assert calls[-3:] == ['rewrite-system-rating-vector', 'rewrite-system-rating-vector', 'complete']
    assert ('delete-system-rating-vector' in calls) is is_batch


@pytest.mark.parametrize('progress,active', [
    ({}, False), ({'pid': 42, 'heap_tuples_written': 0}, False),
    ({'pid': 42, 'heap_tuples_written': 1}, True),
])
def test_mid_rewrite_requires_tuples_already_physically_copied(monkeypatch, progress, active):
    monkeypatch.setattr(tool, '_json', lambda harness, statement: progress)
    assert bool(tool._active_rewrite(SimpleNamespace())) is active


@pytest.mark.parametrize('scenario', tool.CRASH_SCENARIOS)
def test_only_external_crash_survivor_vectors_augmented_and_measurement_untouched(scenario):
    counts = {relation: {tool.controller.PUBLISHED_KEY: 100, 'target': 200} for relation in tool.RELATIONS}
    measurement = SimpleNamespace(counts=counts)
    crash = SimpleNamespace(counts=counts, scale='smoke')
    actual = tool.configure_fixture(crash, scenario)
    assert measurement.counts is counts
    assert counts[tool.RELATION][tool.controller.PUBLISHED_KEY] == 100
    expected = deepcopy(counts)
    if scenario.startswith('rewrite_'):
        expected[tool.RELATION][tool.controller.PUBLISHED_KEY] = 2_000_000
    assert actual == expected
    assert crash.counts is not counts


def test_tiny_crash_fixture_is_never_augmented():
    counts = {tool.RELATION: {tool.controller.PUBLISHED_KEY: 200}}
    fixture = SimpleNamespace(counts=counts, scale='tiny')
    assert tool.configure_fixture(fixture, 'rewrite_postgres_restart') == counts
