"""Delete lifecycle tests use only in-memory state and temporary host leases."""
import fcntl
import json
import os
from pathlib import Path
import signal
from types import SimpleNamespace
import threading

import pytest

from scripts.operator.lib import v3_purge_delete as purge


@pytest.mark.parametrize('condition', ('filesystem_free_space_floor', 'archiver_failed_count_increased'))
def test_delete_loop_stops_before_next_batch_and_later_resumes_from_counts(condition):
    state = {'remaining': 9, 'gates': 0, 'batches': 0}
    failures = []
    def gates():
        state['gates'] += 1
        if state['gates'] == 2:
            raise ValueError(condition)
        return {'free_bytes': 200_000_000_000}
    def batch(measured):
        assert measured['free_bytes'] == 200_000_000_000
        state['batches'] += 1
        state['remaining'] -= 3
        return 3
    with pytest.raises(ValueError, match=condition):
        purge.delete_loop(gates, batch, lambda: state['remaining'], failures.append, lambda: False)
    assert state == {'remaining': 6, 'gates': 2, 'batches': 1}
    assert [str(error) for error in failures] == [condition]
    # The second invocation has no Python cursor from the first dispatch.
    assert purge.delete_loop(lambda: {'free_bytes': 200_000_000_000}, batch,
                             lambda: state['remaining'], failures.append, lambda: False) == 6
    assert state['remaining'] == 0 and state['batches'] == 3


def test_lost_controller_stops_after_at_most_current_batch():
    controller_alive = True
    batches = []
    failures = []
    def gates():
        if not controller_alive:
            raise ValueError('controller_lost')
        return {}
    def batch(_measured):
        nonlocal controller_alive
        batches.append('committed')
        controller_alive = False
        return 1
    with pytest.raises(ValueError, match='controller_lost'):
        purge.delete_loop(gates, batch, lambda: 10 - len(batches), failures.append, lambda: False)
    assert batches == ['committed']
    assert [str(error) for error in failures] == ['controller_lost']


def test_budget_or_signal_starts_no_more_batch():
    for signalled in (False, True):
        failures = []
        ticks = iter((0, 2))
        with pytest.raises(ValueError, match='delete_stop_requested' if signalled else 'budget_exhausted'):
            purge.delete_loop(lambda: pytest.fail('gate after stop'),
                              lambda _: pytest.fail('batch after stop'), lambda: 1,
                              failures.append, lambda: signalled,
                              budget_seconds=1, clock=lambda: next(ticks))
        assert len(failures) == 1


@pytest.mark.parametrize('monitor_failure', (False, True))
def test_launcher_joins_writer_before_cleanup_and_releasing_lease(tmp_path, monitor_failure):
    lease = tmp_path / 'purge.lock'
    entered = threading.Event()
    finish = threading.Event()
    monitor_seen = threading.Event()
    completed = threading.Event()
    trace = []
    errors = []
    def batch():
        entered.set()
        assert finish.wait(5)
        trace.append('writer_exited')
        return 3
    def monitor():
        monitor_seen.set()
        if monitor_failure:
            raise ValueError('filesystem_free_space_floor_mid_batch')
    def cancel():
        trace.append('cancel_requested')
        # Deliberately leave the writer alive until the test permits completion.
    def launch():
        try:
            with lease.open('w') as held:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                try:
                    purge.monitored_batch(batch, monitor, cancel, interval=0.001)
                finally:
                    trace.append('restore_writer_fence')
                fcntl.flock(held, fcntl.LOCK_UN)
        except BaseException as exc:
            errors.append(exc)
        finally:
            completed.set()
    launcher = threading.Thread(target=launch)
    launcher.start()
    try:
        assert entered.wait(5) and monitor_seen.wait(5)
        assert not completed.is_set()
        assert 'restore_writer_fence' not in trace
        with lease.open('w') as contender:
            with pytest.raises(BlockingIOError):
                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        finish.set()
        launcher.join(5)
    assert not launcher.is_alive()
    assert trace.index('writer_exited') < trace.index('restore_writer_fence')
    assert [str(error) for error in errors] == (
        ['filesystem_free_space_floor_mid_batch'] if monitor_failure else [])
    with lease.open('w') as contender:
        fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_admission_adopts_only_matching_relation_and_keeps_rewrite_refused():
    opened = {'purge_id': 'one', 'relation_code': 'system_search',
              'event_kind': 'AUTOVACUUM_DISABLED'}
    purge.admission('delete-system-search', [opened], ['one', 'two'], 'system_search')
    with pytest.raises(ValueError, match='different_relation_fence_open'):
        purge.admission('delete-body-mechanics', [opened], ['one', 'two'], 'body_mechanics')
    with pytest.raises(ValueError, match='rewrite_resolution_requires_p2b2b'):
        purge.admission('restore-services', [{**opened, 'event_kind': 'REWRITE_STARTED'}],
                        ['one', 'two'], None)


@pytest.mark.parametrize('mode', ('delete-system-search', 'abort-relation-system-search',
                                  'authorize', 'complete', 'rewrite-system-search'))
@pytest.mark.parametrize('kind', ('WRITER_FENCE_ENABLED', 'SERVICES_QUIESCED'))
@pytest.mark.parametrize('open_batch', (False, True))
def test_prior_dispatch_writer_or_service_fence_always_requires_restoration(mode, kind, open_batch):
    events = [{'purge_id': 'one', 'relation_code': None, 'event_kind': kind}]
    if open_batch:
        events.append({'purge_id': 'one', 'relation_code': 'system_search', 'event_kind': 'BATCH_STARTED'})
    with pytest.raises(ValueError, match='orphaned_writer_fence_requires_restore_services'):
        purge.admission(mode, events, ['one', 'two'], 'system_search')


def test_restore_resolves_batch_before_restoring_writer_and_is_idempotent():
    trace = []
    restored = set()
    runtime = SimpleNamespace(state=lambda **_: {'unresolved': []}, query=object())
    def writer_fence(query, purge_id, enabled, probe, **kwargs):
        assert query is runtime.query and enabled is False
        assert trace[-1] == 'resolved_batch' or trace[-1].startswith('restore:')
        if purge_id not in restored:
            trace.append('restore:' + purge_id)
            restored.add(purge_id)
        return {'enabled': False, 'verified': True, 'sessions_recycled': 3}
    tx = SimpleNamespace(resolve_batches=lambda *_: trace.append('resolved_batch'), writer_fence=writer_fence)
    report = {'wal_before': {}, 'writer_fence': {'application_role': 'edfinder_v3',
                                               'enabled': True, 'verified': True}}
    purge.restore(SimpleNamespace(), tx, runtime, report, ['one', 'two'], None)
    purge.restore(SimpleNamespace(), tx, runtime, report, ['one', 'two'], None)
    assert trace == ['resolved_batch', 'restore:one', 'restore:two', 'resolved_batch']
    assert report['writer_restore']['verified'] is True
    assert report['writer_fence'] == {'application_role': 'edfinder_v3', 'enabled': False,
                                      'verified': True, 'sessions_recycled': 3}


def test_integrity_failure_never_auto_restores_and_requires_exact_acknowledgement():
    failure = {'event_kind': 'FAILED_STOP', 'event_sequence': 17}
    trace = []
    runtime = SimpleNamespace(state=lambda **_: {'unresolved': [failure]}, query=object())
    tx = SimpleNamespace(
        resolve_batches=lambda *_: trace.append('resolved_batch'),
        writer_fence=lambda *_, **kwargs: trace.append('restored'),
        record_failed_stop=lambda *args: trace.append(args[-1]),
    )
    report = {'wal_before': {}}
    purge.restore(SimpleNamespace(), tx, runtime, report, ['one'], None, automatic=True)
    assert trace == [] and report['writer_restore'] == 'refused_integrity_failed_stop'
    for acknowledgement in (None, 16, 18):
        with pytest.raises(ValueError, match='acknowledgement_required'):
            purge.restore(SimpleNamespace(), tx, runtime, report, ['one'], acknowledgement)
    assert trace == []
    with pytest.raises(ValueError, match='integrity_failed_stop_acknowledgement_payload_unsupported_016'):
        purge.restore(SimpleNamespace(), tx, runtime, report, ['one'], 17)
    assert trace == []
    assert runtime.state()['unresolved'] == [failure]


@pytest.mark.parametrize('relation', ('system_search', 'economy_opportunity', 'body_mechanics', 'system_rating_vector'))
def test_plan_bounds_and_conservative_reservation_are_recordable(relation):
    limit, peak, source = purge.batch_bounds({'delete': {relation: {'batch_limit': 1000}}}, relation)
    assert 1 <= limit <= 100000 and 0 < peak < 1_000_000_000
    assert source == 'conservative_fixed_reservation'
    assert purge.batch_bounds({'delete': {relation: {'batch_limit': 7, 'batch_peak_bytes': 30}}}, relation) == (
        7, 30, 'reviewed_plan')


@pytest.mark.parametrize('config', ({}, {'batch_limit': 100001}, {'batch_limit': True}, {'batch_limit': 0},
                                   {'batch_limit': 1, 'batch_peak_bytes': 1_000_000_000},
                                   {'batch_limit': 1, 'batch_peak_bytes': -1}))
def test_invalid_plan_batch_bounds_fail_closed(config):
    with pytest.raises(ValueError, match='delete_plan_batch_'):
        purge.batch_bounds({'delete': {'system_search': config}}, 'system_search')


@pytest.mark.parametrize(('pid', 'run_id', 'environment'), (
    (None, '123', '123'), (True, '123', '123'), (1, '123', '123'),
    (10, None, '123'), (10, 'abc', 'abc'), (10, '123', '124'),
))
def test_controller_identity_requires_exact_run_binding_before_process_access(monkeypatch, pid, run_id, environment):
    monkeypatch.setenv('GITHUB_RUN_ID', environment)
    monkeypatch.setattr(purge.os, 'kill', lambda *_: pytest.fail('invalid controller accessed process'))
    with pytest.raises(ValueError, match='controller_identity_required'):
        purge.controller_identity(pid, run_id)


def test_controller_identity_records_start_ticks_and_detects_dead_or_reused_process(monkeypatch):
    monkeypatch.setenv('GITHUB_RUN_ID', '123')
    calls = []
    monkeypatch.setattr(purge.os, 'kill', lambda *args: calls.append(args))
    fields = ['S', *['0'] * 18, '98765']
    monkeypatch.setattr(Path, 'read_text', lambda _: '10 (controller with spaces) ' + ' '.join(fields))
    assert purge.controller_identity(10, '123') == '98765'
    fields[19] = '98766'
    assert purge.controller_identity(10, '123') != '98765'
    fields[0] = 'Z'
    with pytest.raises(ValueError, match='controller_lost'):
        purge.controller_identity(10, '123')
    def missing(*_):
        raise ProcessLookupError()
    monkeypatch.setattr(purge.os, 'kill', missing)
    with pytest.raises(ValueError, match='controller_lost'):
        purge.controller_identity(10, '123')
    assert calls == [(10, 0)] * 3


@pytest.mark.parametrize('sig', (signal.SIGINT, signal.SIGTERM, signal.SIGHUP))
def test_signal_handler_requests_stop_and_restores_prior_handlers(monkeypatch, sig):
    prior = {value: object() for value in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
    handlers = dict(prior)
    def install(number, handler):
        previous = handlers[number]
        handlers[number] = handler
        return previous
    monkeypatch.setattr(purge.signal, 'signal', install)
    stop = threading.Event()
    with purge.stop_signals(stop):
        handlers[sig](sig, None)
        assert stop.is_set()
    assert handlers == prior


def test_host_state_requires_root_before_any_filesystem_write(tmp_path, monkeypatch):
    path = tmp_path / 'state.json'
    monkeypatch.setattr(purge.os, 'geteuid', lambda: 1000)
    with pytest.raises(ValueError, match='writer_state_requires_root'):
        purge.save_host_state({'containers': []}, path)
    assert not path.exists()


def test_host_state_refuses_unsafe_directory_without_creating_file(tmp_path, monkeypatch):
    path = tmp_path / 'state.json'
    tmp_path.chmod(0o777)
    monkeypatch.setattr(purge.os, 'geteuid', lambda: 0)
    with pytest.raises(ValueError, match='writer_state_directory_unsafe'):
        purge.save_host_state({'containers': []}, path)
    assert not path.exists()


def test_host_state_refuses_file_mode_or_symlink_without_changing_evidence(tmp_path, monkeypatch):
    path = tmp_path / 'state.json'
    original = json.dumps({'containers': [{'name': 'authority-writer', 'id': 'old'}]})
    path.write_text(original)
    path.chmod(0o644)
    monkeypatch.setattr(purge.os, 'geteuid', lambda: 0)
    real_stat = Path.stat
    def root_stat(self, **kwargs):
        values = list(real_stat(self, **kwargs))
        values[4] = 0
        return os.stat_result(values)
    monkeypatch.setattr(Path, 'stat', root_stat)
    with pytest.raises(ValueError, match='writer_state_file_unsafe'):
        purge.save_host_state({'containers': []}, path)
    assert path.read_text() == original
    linked = tmp_path / 'symlink.json'
    linked.symlink_to(path)
    with pytest.raises(OSError):
        purge.save_host_state({'containers': []}, linked)
    assert path.read_text() == original


@pytest.mark.parametrize('signalled', (False, True))
def test_real_loop_process_is_joined_before_restoration_or_lease_release(tmp_path, signalled):
    context = purge.multiprocessing.get_context('fork')
    stop = context.Event()
    entered = context.Event()
    release = context.Event()
    returned = threading.Event()
    observer_errors = []
    lease = tmp_path / 'process-purge.lock'
    report = {}
    parent_pid = os.getpid()
    def work():
        assert os.getpid() != parent_pid
        assert report['runner_state']['loop_pid'] == os.getpid()
        entered.set()
        assert (stop if signalled else release).wait(5)
        report['writer_exited'] = True
        report['rows_affected_this_run'] = 3
    def observe():
        try:
            assert entered.wait(5)
            assert not returned.is_set()
            assert report['runner_state']['loop_pid'] != parent_pid
            with lease.open('w') as contender:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException as exc:
            observer_errors.append(exc)
        finally:
            (stop if signalled else release).set()
    with lease.open('w') as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        observer = threading.Thread(target=observe)
        observer.start()
        try:
            purge.run_loop_process(work, report, stop)
            returned.set()
            assert report['writer_exited'] is True
            assert report['runner_state']['loop_exited'] is True
            assert report['rows_affected_this_run'] == 3
            with pytest.raises(ProcessLookupError):
                os.kill(report['runner_state']['loop_pid'], 0)
            # The caller can restore fences only at this joined boundary.
            report['writer_fence_restored'] = True
        finally:
            release.set()
            stop.set()
            observer.join(5)
        assert not observer.is_alive()
        assert observer_errors == []
        fcntl.flock(held, fcntl.LOCK_UN)
    with lease.open('w') as contender:
        fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)


@pytest.mark.parametrize(('condition', 'expected'), (
    ('controller_lost', 'controller_lost'),
    ('private diagnostics that must not escape', 'delete_loop_failed'),
))
def test_real_loop_process_propagates_safe_failure_only_after_exit(condition, expected):
    context = purge.multiprocessing.get_context('fork')
    report = {}
    def work():
        report['failed_stop_recorded'] = True
        raise ValueError(condition)
    with pytest.raises(purge.LoopFailure, match='^' + expected + '$'):
        purge.run_loop_process(work, report, context.Event())
    assert report['failed_stop_recorded'] is True
    assert report['runner_state']['loop_exited'] is True
    with pytest.raises(ProcessLookupError):
        os.kill(report['runner_state']['loop_pid'], 0)


def test_real_loop_process_hard_exit_reports_unknown_outcome_after_join():
    context = purge.multiprocessing.get_context('fork')
    report = {}
    with pytest.raises(purge.LoopFailure, match='delete_loop_process_outcome_unknown'):
        purge.run_loop_process(lambda: os._exit(7), report, context.Event())
    assert report['runner_state']['loop_exited'] is True
    with pytest.raises(ProcessLookupError):
        os.kill(report['runner_state']['loop_pid'], 0)
