"""Independent watchdog conditions; no host, systemd or database access."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts/operator/lib' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('failure,condition', (
    ('filesystem_free_space_floor', 'free_space_floor'),
    ('archiver_failed_count_changed', 'wal_archiver_failure'),
    ('archiver_last_failure_newer_than_success', 'wal_archiver_failure'),
    ('wal_retention_unhealthy', 'wal_retention'),
    ('tablespace_or_wal_filesystem_mismatch', 'wal_filesystem'),
    ('controller_lost', 'controller_loss'),
))
def test_monitor_cancels_each_breach_even_when_parent_alive(failure, condition):
    monitor = load('v3_purge_rewrite_monitor')
    alive = iter((True, True, False))
    calls = []
    def controller():
        calls.append('controller-alive')
        if failure == 'controller_lost':
            raise ValueError(failure)
    def observe():
        calls.append('observe')
        raise ValueError(failure)
    def cancel(reason):
        calls.append(('cancel-recorded-backend', reason))
    assert monitor.watch(lambda: next(alive), observe, controller, cancel, sleep=lambda _: None) == condition
    assert calls.count(('cancel-recorded-backend', condition)) == 2
    assert 'controller-alive' in calls
    if failure != 'controller_lost':
        assert 'observe' in calls


def test_monitor_exits_immediately_when_exact_backend_is_gone():
    monitor = load('v3_purge_rewrite_monitor')
    def forbidden(*_):
        pytest.fail('departed backend must neither be probed nor cancelled')
    assert monitor.watch(lambda: False, forbidden, forbidden, forbidden) is None


def test_monitor_retries_authenticated_cancel_when_backend_initially_idle():
    monitor = load('v3_purge_rewrite_monitor')
    alive = iter((True, True, False))
    reasons = []
    def cancel(condition):
        reasons.append(condition)
        if len(reasons) == 1:
            raise ValueError('no_authenticated_live_purge_backend')
    def lost():
        raise ValueError('controller_lost')
    monitor.watch(lambda: next(alive), lambda: None, lost, cancel, sleep=lambda _: None)
    assert reasons == ['controller_loss', 'controller_loss']


def test_monitor_does_not_exit_on_unknown_backend_observation():
    monitor = load('v3_purge_rewrite_monitor')
    values = iter((None, True, False))
    reasons = []
    def backend():
        value = next(values)
        if value is None:
            raise ValueError('database_unavailable')
        return value
    monitor.watch(backend, lambda: None, lambda: None, reasons.append, sleep=lambda _: None)
    assert reasons == ['wal_archiver_failure', 'wal_archiver_failure']


@pytest.mark.parametrize('failure', ('count', 'timestamp'))
def test_watchdog_uses_both_actual_archiver_tests(failure):
    monitor = load('v3_purge_rewrite_monitor')
    controller = load('v3_generation_purge')
    before = {'archive_mode': 'on', 'archiver': {'failed_count': 4,
              'last_archived_time': '2026-10-16T10:00:00+00:00', 'last_failed_time': None}, 'slots': []}
    after = deepcopy(before)
    if failure == 'count':
        # A later successful archive does not excuse a new failed_count.
        after['archiver']['failed_count'] += 1
    else:
        after['archiver']['last_failed_time'] = '2026-10-16T10:01:00+00:00'
    alive = iter((True, False))
    calls = []
    monitor.watch(lambda: next(alive), lambda: controller.wal_health(before, after),
                  lambda: calls.append('controller-alive'), calls.append, sleep=lambda _: None)
    assert calls == ['controller-alive', 'wal_archiver_failure']


def test_watchdog_source_has_only_dedicated_cancel_capability():
    source = (ROOT / 'scripts/operator/lib/v3_purge_rewrite_monitor.py').read_text()
    assert 'rewrite.cancel_rewrite(' in source
    assert 'systemd-run' in source and "'--uid=0'" in source
    assert "config['container_id'] if arg == c.CONTAINER" in source
    assert "config['backend']['backend_start']" in source
    assert 'os.kill' not in source and 'pg_cancel_backend' not in source
    assert 'runtime.lease(' not in source and 'runtime.backup_lock(' not in source
    assert 'script_identity()' in source
