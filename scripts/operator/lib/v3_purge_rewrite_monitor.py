"""Backend-lifetime rewrite watchdog; only 016 may cancel the recorded backend.

A root-owned transient systemd unit runs this independently of the controller.
It never holds the purge/backup locks and never sends an operating-system signal.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import time

INTERVAL_SECONDS = 0.25
STARTUP_SECONDS = 15
DIRECTORY = Path('/run/edfinder-v3-purge-monitors')


def watch(backend_alive, observe, controller_alive, cancel, *, sleep=time.sleep):
    """Keep cancelling on a latched breach until the authenticated backend exits."""
    condition = None
    while True:
        try:
            if not backend_alive():
                break
        except Exception:
            condition = condition or 'wal_archiver_failure'
        if condition is None:
            try:
                controller_alive()
                observe()
            except Exception as exc:
                code = str(exc)
                condition = ('controller_loss' if code == 'controller_lost' else
                             'free_space_floor' if code == 'filesystem_free_space_floor' else
                             'wal_retention' if code == 'wal_retention_unhealthy' else
                             'wal_filesystem' if code == 'tablespace_or_wal_filesystem_mismatch' else
                             'wal_archiver_failure')
        if condition is not None:
            try:
                cancel(condition)
            except Exception:
                # The backend may still be idle immediately before VACUUM or
                # may have completed. 016 authenticates activity/progress again.
                pass
        sleep(INTERVAL_SECONDS)
    return condition


def secure_file(path):
    info = path.lstat()
    if not path.is_file() or path.is_symlink() or info.st_uid != 0 or info.st_mode & 0o077:
        raise ValueError('rewrite_monitor_state_unsafe')


def start(c, runtime, ids, relation, backend, identity, report):
    """Admission is complete; establish the watchdog before sending VACUUM."""
    if os.geteuid() != 0:
        raise ValueError('rewrite_monitor_requires_root')
    DIRECTORY.mkdir(mode=0o700, exist_ok=True)
    info = DIRECTORY.lstat()
    if DIRECTORY.is_symlink() or not DIRECTORY.is_dir() or info.st_uid != 0 or info.st_mode & 0o077:
        raise ValueError('rewrite_monitor_state_unsafe')
    # A service executing mutable, unprivileged source as root is unacceptable.
    sources = [Path(__file__), Path(c.__file__) if hasattr(c, '__file__') else
               c.ROOT / 'scripts/operator/lib/v3_generation_purge.py',
               c.ROOT / 'scripts/operator/lib/v3_purge_rewrite.py',
               c.ROOT / 'scripts/operator/lib/v3_purge_rewrite_dispatch.py',
               c.ROOT / 'scripts/operator/lib/v3_purge_transactions.py',
               c.ROOT / 'scripts/operator/lib/v3_purge_delete.py',
               c.ROOT / 'scripts/operator/lib/v3_purge_state.py',
               c.ROOT / 'scripts/operator/lib/f2d_evidence.py',
               c.ROOT / 'scripts/operator/v3_schema_identity.py']
    for source in sources:
        for item in (source, *source.parents):
            stat = item.lstat()
            if item.is_symlink() or stat.st_uid != 0 or stat.st_mode & 0o022:
                raise ValueError('rewrite_monitor_source_unsafe')
    container_id = runtime.docker('inspect', '-f', '{{.Id}}', c.CONTAINER)
    if re.fullmatch('[0-9a-f]{64}', container_id) is None:
        raise ValueError('rewrite_monitor_container_identity_invalid')
    unit = 'edfinder-v3-purge-rewrite-' + str(backend['start_event'])
    path = DIRECTORY / (unit + '.json')
    config = {'purge_ids': ids, 'relation': relation, 'backend': backend,
              'container_id': container_id, 'data_directory': identity['data_directory'],
              'data_mount': report['data_mount'], 'wal_before': report['wal_before'],
              'controller': report['runner_state'], 'script_sha256': report['script_sha256']}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(config, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    runtime.run(['systemd-run', '--quiet', '--collect', '--unit=' + unit,
                 '--uid=0', '--property=Type=exec', '--property=Restart=no',
                 '--property=KillMode=process', '--property=UMask=0077',
                 '--setenv=GITHUB_RUN_ID=' + report['runner_state']['controller_run_id'],
                 '--', sys.executable, '-I', str(Path(__file__).resolve()), str(path)])
    ready = Path(str(path) + '.ready')
    deadline = time.monotonic() + STARTUP_SECONDS
    while time.monotonic() < deadline:
        if ready.exists():
            secure_file(ready)
            if ready.read_text() != 'ready':
                raise ValueError('rewrite_monitor_start_failed')
            report['rewrite_monitor'] = {'unit': unit, 'container_id': container_id,
                                          'backend_pid': backend['backend_pid'],
                                          'backend_start': backend['backend_start']}
            return unit
        time.sleep(0.05)
    raise ValueError('rewrite_monitor_start_timeout')


def main(argv=None):
    import importlib.util
    args = sys.argv[1:] if argv is None else argv
    if sys.implementation.name != 'cpython' or sys.version_info[:2] != (3, 14):
        raise ValueError('python314_required')
    if len(args) != 1 or os.geteuid() != 0:
        raise ValueError('rewrite_monitor_arguments_invalid')
    path = Path(args[0])
    if path.parent != DIRECTORY or re.fullmatch(r'edfinder-v3-purge-rewrite-[1-9][0-9]*\.json', path.name) is None:
        raise ValueError('rewrite_monitor_arguments_invalid')
    secure_file(path)
    config = json.loads(path.read_text())
    spec = importlib.util.spec_from_file_location('purge_controller', Path(__file__).with_name('v3_generation_purge.py'))
    c = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(c)
    if c.script_identity() != config['script_sha256']:
        raise ValueError('rewrite_monitor_script_identity_changed')
    rewrite = c._load('v3_purge_rewrite')
    delete = c._load('v3_purge_delete')
    runtime = c.Runtime(c.receipt('rewrite-monitor'))
    # No controller deadline: lifetime is the recorded PostgreSQL backend's.
    runtime.deadline = float('inf')
    original_docker = runtime.docker
    def pinned_docker(*args, **kwargs):
        if args and args[0] == 'exec':
            args = tuple(config['container_id'] if arg == c.CONTAINER else arg for arg in args)
        return original_docker(*args, **kwargs)
    runtime.docker = pinned_docker
    original_query = runtime.query
    def bounded_query(sql, params=None, *, write=False):
        # No long controller allowance in a short-interval watchdog probe.
        runtime.deadline = time.monotonic() + 10
        try:
            return original_query(sql, params, write=write)
        finally:
            runtime.deadline = float('inf')
    runtime.query = bounded_query
    ready = Path(str(path) + '.ready')
    def pinned():
        # Continue following the original container even if its name is reused.
        result = runtime.docker('inspect', '-f', '{{.Id}}', config['container_id'],
                                allow_failure=True, return_result=True)
        if result.returncode:
            if (result.returncode == 1 and not result.stdout.strip()
                    and result.stderr.strip() == 'Error: No such object: ' + config['container_id']):
                return False
            raise ValueError('rewrite_monitor_container_unknown')
        if result.stdout.strip() != config['container_id']:
            raise ValueError('rewrite_monitor_container_changed')
        return True
    def alive():
        if not pinned():
            return False
        value = runtime.query(rewrite.BACKEND_SQL, {'backend_pid': str(config['backend']['backend_pid']),
                                                   'backend_start': config['backend']['backend_start']})
        if type(value.get('alive')) is not bool:
            raise ValueError('rewrite_monitor_backend_unknown')
        return value['alive']
    def controller():
        state = config['controller']
        for prefix in ('controller', 'launcher'):
            if delete.controller_identity(state[prefix + '_pid'], state['controller_run_id']) != state[prefix + '_start_ticks']:
                raise ValueError('controller_lost')
    def observe():
        if delete.free_space(config['data_mount']['source'])['free_bytes'] < c.FREE_FLOOR_BYTES:
            raise ValueError('filesystem_free_space_floor')
        if runtime.device(config['data_directory'] + '/pg_wal') != config['data_mount']['device']:
            raise ValueError('tablespace_or_wal_filesystem_mismatch')
        c.wal_health(config['wal_before'], c.measure_wal(runtime, config['data_directory']))
    def cancel(condition):
        if not pinned():
            return
        rewrite.cancel_rewrite(runtime.query, config['purge_ids'][0], config['relation'], condition)
    try:
        pinned()
        # The handshake means the independent process can see the start backend.
        if not alive():
            raise ValueError('rewrite_monitor_backend_departed_before_start')
        with ready.open('x') as stream:
            os.chmod(ready, 0o600)
            stream.write('ready')
        watch(alive, observe, controller, cancel)
    finally:
        ready.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
