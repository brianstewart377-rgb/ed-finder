"""Exercise persistent binary pipes and inherited lock lifetimes locally."""
import fcntl
import os
import sys

import pytest

from tests.test_v3_purge_delete_dispatch import load


CHILD = '''
import json, os, sys
for line in sys.stdin:
    if line.strip() == 'SELECT marker;':
        print(41, flush=True)
        print(json.dumps({'start_event': 41, 'backend_pid': os.getpid()}), flush=True)
    elif line.strip() == 'SELECT fail;':
        sys.exit(3)
    elif line.startswith("SELECT jsonb_build_object('command_completed'"):
        print(json.dumps({'command_completed': True}), flush=True)
'''


def runtime_with_child(monkeypatch):
    module = load('v3_generation_purge')
    actual = module.subprocess.Popen
    children = []
    def local_popen(argv, **kwargs):
        assert argv[:3] == ['docker', '--context', 'default']
        child = actual([sys.executable, '-u', '-c', CHILD], **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(module.subprocess, 'Popen', local_popen)
    return module.Runtime({}), children


def test_persistent_backend_reads_post_commit_marker_and_joins_child(monkeypatch):
    runtime, children = runtime_with_child(monkeypatch)
    waits = []
    with runtime.rewrite_backend(5000, on_wait=lambda: waits.append(True)) as backend:
        first = backend.query('SELECT marker;', write=True)
        second = backend.query('SELECT marker;', write=True)
        assert first == second and first['start_event'] == 41
        assert first['backend_pid'] == children[0].pid
        assert children[0].poll() is None
    assert waits and children[0].poll() == 0
    assert runtime.report['transaction_outcome'] == 'committed'


def test_backend_client_retains_both_locks_after_controller_fds_close(monkeypatch, tmp_path):
    runtime, children = runtime_with_child(monkeypatch)
    paths = [tmp_path / 'purge.lock', tmp_path / 'schedule.lock']
    fds = [os.open(path, os.O_CREAT | os.O_RDWR, 0o600) for path in paths]
    for fd in fds:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    runtime.lease_fd, runtime.backup_lock_fd = fds
    contenders = [os.open(path, os.O_RDWR) for path in paths]
    try:
        with runtime.rewrite_backend(5000) as backend:
            assert backend.query('SELECT marker;')['backend_pid'] == children[0].pid
            for fd in fds:
                os.close(fd)
            fds.clear()
            # Simulate loss of the wrapper. The independent maintenance client
            # keeps both flock descriptions alive until its backend work exits.
            for fd in contenders:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for fd in contenders:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        for fd in (*fds, *contenders):
            os.close(fd)
    assert children[0].poll() == 0


def test_failed_backend_is_joined_and_write_outcome_stays_unknown(monkeypatch):
    runtime, children = runtime_with_child(monkeypatch)
    with pytest.raises(ValueError, match='rewrite_backend_failed'):
        with runtime.rewrite_backend(5000) as backend:
            backend.query('SELECT fail;', write=True)
    assert children[0].poll() == 3
    assert runtime.report['transaction_outcome'] is None
    assert runtime.report['db_writes_performed'] is None
