"""Crash-gate orchestration refuses unobserved or incompletely recovered states."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.rehearsal import v3_purge_crashes as tool

ORIGINAL, COPY = 1001, 2002


def _snapshot(events=(), *, tables=None, attoptions=('n_distinct=-0.13',), target_rows=100, rows_total=None,
              completed=False, postmaster='2026-10-16T00:00:00+00:00'):
    return {'published': {'economy_opportunity': {'rows': 100, 'fingerprint': '1234'}},
            'pointers': {'derived': 'published'},
            'relation': {'events': [{'kind': kind, 'sequence': index + 1,
                                     'abandoned': True if kind == 'FAILED_STOP' else None}
                                    for index, kind in enumerate(events)],
                         'completed': completed, 'rows_total': rows_total,
                         'tables': tables if tables is not None else {'v3_derived': ORIGINAL},
                         'invalid_indexes': 0, 'not_valid_foreign_keys': 0,
                         'live_attoptions': list(attoptions) if attoptions is not None else None,
                         'target_rows': target_rows, 'postmaster_started': postmaster}}


STAGED = {'v3_derived': ORIGINAL, 'v3_purge_staging': COPY}
SWAPPED = {'v3_derived': COPY, 'v3_retired': ORIGINAL}


@pytest.mark.parametrize(('events', 'tables', 'position'), [
    ((), {'v3_derived': ORIGINAL}, 'none'),
    (('COPY_STARTED', 'CHUNK_COPIED'), STAGED, 'staged'),
    (('COPY_STARTED', 'VERIFIED', 'SWAPPED'), SWAPPED, 'swapped'),
    (('COPY_STARTED', 'VERIFIED', 'SWAPPED', 'FK_VALIDATED', 'SWAPPED_BACK'), STAGED, 'staged'),
    (('COPY_STARTED', 'VERIFIED', 'SWAPPED', 'FK_VALIDATED', 'DROPPED'), {'v3_derived': COPY}, 'dropped'),
    (('COPY_STARTED', 'VERIFIED', 'FAILED_STOP'), {'v3_derived': ORIGINAL}, 'none'),
])
def test_catalog_must_agree_with_the_ledger_position(events, tables, position):
    assert tool.assert_intact(_snapshot(), _snapshot(events, tables=tables)) == position


@pytest.mark.parametrize(('events', 'tables'), [
    (('COPY_STARTED',), {'v3_derived': ORIGINAL}),                       # staging lost
    (('COPY_STARTED', 'VERIFIED', 'SWAPPED'), STAGED),                    # half swapped
    (('COPY_STARTED', 'VERIFIED', 'SWAPPED', 'DROPPED'), SWAPPED),         # retired left behind
    ((), STAGED),                                                         # unledgered staging
])
def test_ledger_and_catalog_disagreement_refuses_the_gate(events, tables):
    with pytest.raises(ValueError, match='crash_ledger_and_catalog_disagree'):
        tool.assert_intact(_snapshot(), _snapshot(events, tables=tables))


def test_invalid_index_or_unabandoned_failed_stop_refuses():
    damaged = _snapshot()
    damaged['relation']['invalid_indexes'] = 1
    with pytest.raises(ValueError, match='crash_ledger_and_catalog_disagree'):
        tool.assert_intact(_snapshot(), damaged)
    failed = _snapshot(('COPY_STARTED', 'FAILED_STOP'), tables={'v3_derived': ORIGINAL})
    failed['relation']['events'][-1]['abandoned'] = None
    with pytest.raises(ValueError, match='crash_unexpected_failed_stop'):
        tool.assert_intact(_snapshot(), failed)


@pytest.mark.parametrize('field', ['published', 'pointers'])
def test_survivor_fingerprint_and_pointer_changes_refuse_gate(field):
    after = _snapshot()
    after[field] = {'changed': True}
    with pytest.raises(ValueError, match='published_payload_or_pointer_changed'):
        tool.assert_intact(_snapshot(), after)


def test_wait_refuses_action_that_exits_before_progress_is_observed():
    with pytest.raises(RuntimeError, match='not_observed'):
        tool._wait(lambda: False, SimpleNamespace(poll=lambda: 0), reason='not_observed')


def test_wait_requires_real_observation_before_returning():
    result = tool._wait(lambda: {'pid': 42}, SimpleNamespace(poll=lambda: None), reason='not_observed')
    assert result['pid'] == 42


def test_prepare_runs_the_real_route_for_search_before_the_scenario_relation():
    calls = []
    class Harness:
        def start(self): calls.append('start')
        def migrate(self): calls.append('migrate')
        def seed(self): calls.append('seed')
        def authorize(self): calls.append('authorize')
        def action(self, mode): calls.append(mode)
        def copy_until_verified(self, name): calls.append('copy-until-verified-' + name)
    tool._prepare(Harness())
    assert calls == ['start', 'migrate', 'seed', 'authorize', 'preflight-system-search',
                     'copy-until-verified-system-search', 'swap-system-search', 'drop-system-search']


def _owned_marker(tmp_path, monkeypatch, scenario):
    marker = tmp_path / 'fault.json'
    marker.write_text(json.dumps({'scenario': scenario, 'pid': 456}))
    monkeypatch.setattr(tool.os, 'getpgid', lambda pid: 123)
    return marker


@pytest.mark.parametrize('scenario', tool.KILLED)
def test_killed_clients_require_the_owned_fault_point_and_the_observed_pause(tmp_path, monkeypatch, scenario):
    marker = _owned_marker(tmp_path, monkeypatch, scenario)
    calls, probes = [], []
    def observe(harness, sql, parameters=None):
        probes.append((sql, parameters))
        if sql == tool.ORPHAN_SQL:
            return {'backends': 0}
        return {'pid': 77} if sql == tool.PAUSED_SQL else {'sleeping': True}
    monkeypatch.setattr(tool, '_json', observe)
    monkeypatch.setattr(tool, '_kill', lambda process: calls.append('kill-wrapper-group'))
    def docker(*args, **kwargs):
        calls.append((args, kwargs))
        return 'PID COMMAND\n7 postgres\n' if args[0] == 'top' else ''
    harness = SimpleNamespace(container='disposable', docker=docker)
    result = tool._interrupt(harness, scenario, SimpleNamespace(pid=123, poll=lambda: 1, returncode=-9), marker)
    assert result['client_state'] == ('killed_before_commit' if scenario == 'copy_chunk_client_killed'
                                      else 'killed_after_commit')
    assert calls == ['kill-wrapper-group',
                     (('exec', 'disposable', 'killall', '-KILL', 'psql'), {'check': False}),
                     (('top', 'disposable', '-eo', 'pid,args'), {})]
    # The pause observed is the phase statement's own, or the post-commit sleep.
    expected = tool.PAUSED_SQL if scenario == 'copy_chunk_client_killed' else tool.COMMITTED_SLEEP_SQL
    assert probes[0][0] == expected and probes[-1][0] == tool.ORPHAN_SQL
    if scenario == 'copy_chunk_client_killed':
        assert probes[0][1] == {'function': 'v3_meta[.]purge_copy_chunk[(]'}


@pytest.mark.parametrize('scenario', ['copy_postgres_restart', 'index_build_backend_terminated', 'verify_watchdog_cancel'])
def test_external_interruptions_target_only_the_observed_phase_backend(tmp_path, monkeypatch, scenario):
    marker = _owned_marker(tmp_path, monkeypatch, scenario)
    calls = []
    monkeypatch.setattr(tool, '_json', lambda harness, sql, parameters=None: (
        {'backends': 0} if sql == tool.ORPHAN_SQL else {'pid': 321}))
    monkeypatch.setattr(tool, '_ready', lambda harness: calls.append('ready'))
    harness = SimpleNamespace(container='disposable', sql=lambda sql, params=None: calls.append((sql, params)) or 't',
                              docker=lambda *args: calls.append(args))
    process = SimpleNamespace(pid=123, poll=lambda: None, wait=lambda timeout: calls.append(('wait', timeout)),
                              returncode=1)
    result = tool._interrupt(harness, scenario, process, marker)
    assert result['observed_fault_point'] == scenario and result['wrapper_returncode'] == 1
    if scenario == 'copy_postgres_restart':
        assert calls == [('restart', '--time', '0', 'disposable'), ('wait', 240), 'ready']
    elif scenario == 'index_build_backend_terminated':
        statement, params = calls[0]
        assert statement == tool.TERMINATE_SQL and params == {'pid': 321}
        assert 'purge_copy_build_indexes' in statement and 'pg_terminate_backend(pid)' in statement
    else:
        assert Path(str(marker) + '.trigger').read_text() == 'observed-active-verify\n'
        assert calls == [('wait', 240)]


def test_unrelated_hook_pid_is_not_accepted(tmp_path, monkeypatch):
    marker = tmp_path / 'fault.json'
    marker.write_text(json.dumps({'scenario': 'swap_committed_client_killed', 'pid': 456}))
    monkeypatch.setattr(tool.os, 'getpgid', lambda pid: 999)
    with pytest.raises(RuntimeError, match='fault_point_not_observed'):
        tool._interrupt(SimpleNamespace(), 'swap_committed_client_killed',
                        SimpleNamespace(pid=123, poll=lambda: 1), marker)


def test_orphaned_backend_must_exit_before_any_redispatch(monkeypatch):
    clock = iter(range(0, 10_000, 30))
    monkeypatch.setattr(tool.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(tool.time, 'sleep', lambda _seconds: None)
    monkeypatch.setattr(tool, '_json', lambda harness, sql, parameters=None: {'backends': 1})
    with pytest.raises(RuntimeError, match='crash_orphaned_backend_survived'):
        tool._wait_no_orphan(SimpleNamespace())


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
    assert len(fixtures) == len({fixture.output for fixture in fixtures}) == len(tool.CRASH_SCENARIOS)
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


class _Fixture:
    """A fake harness whose economy_opportunity ledger follows 019's rules."""

    def __init__(self, tmp_path, scenario, *, damage=None):
        self.output = tmp_path
        self.environment = {}
        self.scale = 'smoke'
        self.counts = {tool.RELATION: {tool.controller.PUBLISHED_KEY: 100}}
        self.scenario, self.damage = scenario, damage
        self.events, self.tables = [], {'v3_derived': ORIGINAL}
        self.attoptions, self.completed, self.rows_total = ['n_distinct=-0.13'], False, None
        self.postmaster = '2026-10-16T00:00:00+00:00'
        self.modes = []
        self.refused_action = None
        # A crash restart leaves pg_stat_archiver empty until a segment is archived.
        self.archive_known = scenario != 'copy_postgres_restart' or damage == 'archive_known'

    def archived(self):
        self.modes.append('archived')
        self.archive_known = True

    def snapshot(self):
        return _snapshot(self.events, tables=dict(self.tables), attoptions=self.attoptions,
                         target_rows=0 if 'DROPPED' in self.events else 100, rows_total=self.rows_total,
                         completed=self.completed, postmaster=self.postmaster)

    def copy_until_verified(self, name):
        self.modes.append('copy-until-verified-' + name)
        if name != tool.MODE:
            return
        positional = [kind for kind in self.events if kind != 'FK_VALIDATED']
        last = positional[-1] if positional else None
        if last in (None, 'FAILED_STOP'):
            self.events += ['COPY_STARTED', 'CHUNK_COPIED', 'INDEXES_BUILT']
        elif last != 'SWAPPED_BACK':
            started = len(self.events) - 1 - self.events[::-1].index('COPY_STARTED')
            if 'INDEXES_BUILT' not in self.events[started:]:
                self.events += ['CHUNK_COPIED', 'INDEXES_BUILT']
        self.events.append('VERIFIED')
        self.tables = dict(STAGED)
        self.rows_total = 100

    def action(self, mode):
        self.modes.append(mode)
        report = {'status': 'success'}
        if mode == 'copy-' + tool.MODE and not self.archive_known:
            failures = ['wal_gate_unknown'] if self.damage == 'other_refusal' else ['wal_archive_lag_unknown']
            self.refused_action = {'mode': mode, 'report': 'x.json', 'failures': failures}
            raise RuntimeError('real_action_refused_copy_economy_opportunity')
        if mode == 'swap-' + tool.MODE:
            if self.events[-1] == 'SWAPPED':
                report['swap_resumed'] = True
            else:
                self.events.append('SWAPPED')
            self.events.append('FK_VALIDATED')
            self.tables, self.attoptions = dict(SWAPPED), ['n_distinct=-0.270000']
        elif mode == 'swap-back-' + tool.MODE:
            if self.events[-1] == 'SWAPPED_BACK':
                report['swap_back_resumed'] = True
            else:
                self.events.append('SWAPPED_BACK')
            self.events.append('FK_VALIDATED')
            report['result'] = 'swapped_back_live_restored'
            self.tables, self.attoptions = dict(STAGED), ['n_distinct=-0.13']
        elif mode == 'drop-' + tool.MODE:
            if 'DROPPED' in self.events:
                report['result'] = 'retired_relation_already_dropped'
            else:
                self.events.append('DROPPED')
            self.tables = {'v3_derived': COPY}
        elif mode == 'abandon-' + tool.MODE:
            self.events.append('FAILED_STOP')
            self.tables = {'v3_derived': ORIGINAL}
        elif mode == 'status':
            pending = {'SWAPPED': 'swap-', 'SWAPPED_BACK': 'swap-back-'}.get(self.events[-1])
            report['next_admissible_mode'] = {'mode': (pending or 'copy-') + tool.MODE}
        elif mode == 'complete':
            self.completed = True
        return {'report': report}

    def number(self, statement):
        return 0

    def faulted(self, harness, scenario):
        """What each real interruption leaves behind, committed or not."""
        if scenario in ('copy_chunk_client_killed', 'copy_postgres_restart'):
            self.events += ['COPY_STARTED', 'CHUNK_COPIED']
            self.tables = dict(STAGED)
            if scenario == 'copy_postgres_restart':
                self.postmaster = '2026-10-16T00:05:00+00:00'
        elif scenario == 'index_build_backend_terminated':
            self.events += ['COPY_STARTED', 'CHUNK_COPIED']
            self.tables = dict(STAGED)
        elif scenario == 'verify_watchdog_cancel':
            self.events += ['COPY_STARTED', 'CHUNK_COPIED', 'INDEXES_BUILT']
            self.tables = dict(STAGED)
            return {'observed_fault_point': scenario}, {
                'failures': ['copy_verify_interrupted'],
                'copy_phase_failures': [{'monitor_condition': 'controller_loss',
                                         'sqlstate': 'XX000' if self.damage == 'sqlstate' else '57014'}]}
        elif scenario == 'swap_committed_client_killed':
            self.events.append('SWAPPED')
            self.tables, self.attoptions = dict(SWAPPED), ['n_distinct=-0.13']
        elif scenario == 'swap_back_committed_client_killed':
            self.events.append('SWAPPED_BACK')
            self.tables = dict(STAGED)
            self.attoptions = ['n_distinct=-0.270000'] if self.damage == 'statistics' else ['n_distinct=-0.13']
        elif scenario == 'drop_committed_client_killed':
            self.events.append('DROPPED')
            self.tables = {'v3_derived': COPY}
        return {'observed_fault_point': scenario}, None


def _run(tmp_path, monkeypatch, scenario, *, damage=None):
    fixture = _Fixture(tmp_path, scenario, damage=damage)
    monkeypatch.setattr(tool, '_prepare', lambda harness: harness.modes.append('prepare'))
    monkeypatch.setattr(tool, 'snapshot', lambda harness: harness.snapshot())
    monkeypatch.setattr(tool, '_faulted', fixture.faulted)
    return fixture, tool.run_scenario(fixture, scenario)


@pytest.mark.parametrize('scenario', tool.CRASH_SCENARIOS)
def test_every_scenario_resumes_through_the_real_modes_and_completes(tmp_path, monkeypatch, scenario):
    fixture, result = _run(tmp_path, monkeypatch, scenario)
    assert result['passed'] is True and result['published_fingerprints_unchanged'] is True
    assert fixture.modes[:2] == ['prepare', 'preflight-' + tool.MODE]
    # Every remaining relation finishes through drop, then 019's COMPLETED.
    assert fixture.modes[-9:] == ['preflight-body-mechanics', 'copy-until-verified-body-mechanics',
                                  'swap-body-mechanics', 'drop-body-mechanics',
                                  'preflight-system-rating-vector', 'copy-until-verified-system-rating-vector',
                                  'swap-system-rating-vector', 'drop-system-rating-vector', 'complete']
    assert fixture.events.count('DROPPED') == 1 and fixture.completed is True
    if scenario == 'swap_committed_client_killed':
        assert result['status_next_mode'] == {'mode': 'swap-' + tool.MODE}
    if scenario == 'swap_back_committed_client_killed':
        assert result['status_next_mode'] == {'mode': 'swap-back-' + tool.MODE}
    if scenario == 'abandon_and_recopy':
        assert fixture.events.count('COPY_STARTED') == 2
    if scenario == 'drop_committed_client_killed':
        assert fixture.modes.count('drop-' + tool.MODE) == 1
    if scenario == 'copy_postgres_restart':
        # The restart's archiver refusal is proven, then one segment completes
        # before the copy resumes from the ledger.
        assert result['restart_archive_refusal'] == 'wal_archive_lag_unknown'
        assert fixture.refused_action is None
        index = fixture.modes.index('copy-' + tool.MODE)
        assert fixture.modes[index:index + 3] == ['copy-' + tool.MODE, 'archived',
                                                  'copy-until-verified-' + tool.MODE]


def test_a_restart_whose_archiver_state_survived_still_resumes(tmp_path, monkeypatch):
    fixture, result = _run(tmp_path, monkeypatch, 'copy_postgres_restart', damage='archive_known')
    assert result['passed'] is True and result['restart_archive_refusal'] is None
    assert 'archived' in fixture.modes


def test_a_restart_refused_for_any_other_reason_fails(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match='crash_restart_refusal_unexpected'):
        _run(tmp_path, monkeypatch, 'copy_postgres_restart', damage='other_refusal')


@pytest.mark.parametrize(('scenario', 'damage', 'code'), [
    ('verify_watchdog_cancel', 'sqlstate', 'crash_watchdog_did_not_cancel_verify'),
    ('swap_back_committed_client_killed', 'statistics', 'crash_committed_swap_back_not_observed'),
])
def test_a_scenario_that_does_not_show_its_exact_fault_effect_fails(tmp_path, monkeypatch, scenario, damage, code):
    with pytest.raises(ValueError, match=code):
        _run(tmp_path, monkeypatch, scenario, damage=damage)


def test_a_restart_that_did_not_restart_postgres_fails(tmp_path, monkeypatch):
    fixture = _Fixture(tmp_path, 'copy_postgres_restart')
    original = fixture.faulted
    def faulted(harness, scenario):
        result = original(harness, scenario)
        fixture.postmaster = '2026-10-16T00:00:00+00:00'
        return result
    monkeypatch.setattr(tool, '_prepare', lambda harness: None)
    monkeypatch.setattr(tool, 'snapshot', lambda harness: harness.snapshot())
    monkeypatch.setattr(tool, '_faulted', faulted)
    with pytest.raises(ValueError, match='crash_postgres_not_restarted'):
        tool.run_scenario(fixture, 'copy_postgres_restart')


def test_unknown_scenario_is_refused_before_any_fixture_work(tmp_path):
    with pytest.raises(ValueError, match='unknown_crash_scenario'):
        tool.run_scenario(SimpleNamespace(), 'rewrite_monitor_cancel')


def test_configure_fixture_never_changes_the_crash_scale_counts():
    counts = {tool.RELATION: {tool.controller.PUBLISHED_KEY: 200}}
    fixture = SimpleNamespace(counts=counts, scale='smoke')
    assert tool.configure_fixture(fixture, 'copy_postgres_restart') == counts
    assert fixture.counts is not counts


def test_fault_modes_name_only_fixed_copy_modes_and_scenarios():
    assert set(tool.FAULT_MODES) == set(tool.MARKED)
    assert set(tool.MARKED) | {'swap_back_and_reswap', 'abandon_and_recopy'} == set(tool.CRASH_SCENARIOS)
    from scripts.operator.lib import v3_purge_rehearsal as adapter
    assert set(adapter.STATEMENT_FAULTS) | set(adapter.COMMITTED_FAULTS) == set(tool.MARKED)


def test_idle_client_already_gone_is_accepted_but_a_survivor_is_not(monkeypatch):
    listings = iter(['PID COMMAND\n7 postgres\n9 psql -X --no-psqlrc\n', 'PID COMMAND\n7 postgres\n'])
    calls = []
    def docker(*args, **kwargs):
        calls.append((args, kwargs))
        return next(listings) if args[0] == 'top' else ''
    fixture = SimpleNamespace(container='c', docker=docker)
    monkeypatch.setattr(tool.time, 'sleep', lambda _seconds: None)
    tool._wait_no_psql_client(fixture)
    assert all(args[:2] == ('top', 'c') and args[2:] == ('-eo', 'pid,args') for args, _ in calls)
    survivor = SimpleNamespace(container='c', docker=lambda *a, **k: 'PID COMMAND\n9 /usr/local/bin/psql\n')
    clock = iter(range(0, 100, 10))
    monkeypatch.setattr(tool.time, 'monotonic', lambda: next(clock))
    with pytest.raises(RuntimeError, match='crash_psql_client_survived'):
        tool._wait_no_psql_client(survivor)
    with pytest.raises(RuntimeError, match='crash_container_process_listing_unknown'):
        tool._psql_clients(SimpleNamespace(container='c', docker=lambda *a, **k: ''))


def test_snapshot_queries_are_observer_reads_with_bound_generation():
    assert 'SET ROLE' not in tool.POINTER_OBSERVATION_SQL and 'SET ROLE' not in tool.STATE_SQL
    assert "derived_generation_id<>%(published)s::uuid" in tool.STATE_SQL
    assert tool.STATE_SQL.count("'economy_opportunity'") >= 3
    assert all(statement.rstrip().endswith(';') for statement in (
        tool.STATE_SQL, tool.ORPHAN_SQL, tool.PAUSED_SQL, tool.COMMITTED_SLEEP_SQL, tool.TERMINATE_SQL))
    assert deepcopy(tool.RELATIONS) == ('system_search', 'economy_opportunity', 'body_mechanics', 'system_rating_vector')
