"""Backend-lifetime watchdog for 016 rewrites and 019 copy long phases.

A root-owned transient systemd unit runs this independently of the controller.
It never holds the purge/backup locks and never sends an operating-system signal.
For a rewrite only 016's definer may cancel the recorded backend. For a copy
long phase (index build, VACUUM FREEZE, verify, FK validation, the opportunity
statistics count) 019 provides no cancel definer, so the unit cancels through
the owner session's authenticated cancel statement in ``v3_purge_copy``
(exact PID and backend_start, this database, the owner's active client backend
running one of the fixed phase statements) and records the condition beside
its config.
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


DETAIL_PATTERN = re.compile('(?:backend|observe):[A-Za-z0-9_]{1,64}')


def watch(backend_alive, observe, controller_alive, cancel, *, sleep=time.sleep, detail=None):
    """Keep cancelling on a latched breach until the authenticated backend exits.

    Every check that cannot complete cancels as ``wal_archiver_failure`` (the
    conditions 016's cancel definer accepts are fixed), so ``detail``, when
    given, receives the exception that latched the condition once, as
    ``<backend|observe>:<code>``; recording it never affects the watchdog.
    """
    condition = None
    while True:
        try:
            if not backend_alive():
                break
        except Exception as exc:
            if condition is None:
                _detail(detail, 'backend', exc)
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
                             'wal_ceiling' if code == 'wal_ceiling_exceeded' else
                             'wal_archiver_failure')
                _detail(detail, 'observe', exc)
        if condition is not None:
            try:
                cancel(condition)
            except Exception:
                # The backend may still be idle immediately before VACUUM or
                # may have completed. 016 authenticates activity/progress again.
                pass
        sleep(INTERVAL_SECONDS)
    return condition


def _detail(record, source, exc):
    if record is None:
        return
    code = str(exc)
    if re.fullmatch('[A-Za-z0-9_]{1,64}', code) is None:
        code = type(exc).__name__
    try:
        record(source + ':' + code)
    except Exception:
        pass


def secure_file(path):
    info = path.lstat()
    if not path.is_file() or path.is_symlink() or info.st_uid != 0 or info.st_mode & 0o077:
        raise ValueError('rewrite_monitor_state_unsafe')


def _sources(c):
    return [Path(__file__), Path(c.__file__) if hasattr(c, '__file__') else
            c.ROOT / 'scripts/operator/lib/v3_generation_purge.py',
            c.ROOT / 'scripts/operator/lib/v3_purge_rewrite.py',
            c.ROOT / 'scripts/operator/lib/v3_purge_rewrite_dispatch.py',
            c.ROOT / 'scripts/operator/lib/v3_purge_transactions.py',
            c.ROOT / 'scripts/operator/lib/v3_purge_delete.py',
            c.ROOT / 'scripts/operator/lib/v3_purge_state.py',
            c.ROOT / 'scripts/operator/lib/v3_purge_copy.py',
            c.ROOT / 'scripts/operator/lib/v3_purge_copy_dispatch.py',
            c.ROOT / 'scripts/operator/lib/f2d_evidence.py',
            c.ROOT / 'scripts/operator/v3_schema_identity.py']


def start_copy(c, runtime, phase, identity, report):
    """Watch one 019 long phase: same unit model as the rewrite, copy cancel path."""
    backend = phase['backend']
    if (type(backend.get('backend_pid')) is not int or backend['backend_pid'] <= 0
            or not isinstance(backend.get('backend_start'), str)
            or re.fullmatch('[a-z_]+', phase.get('phase', '')) is None
            or re.fullmatch('[a-z_]+', phase.get('relation', '')) is None
            or type(phase.get('required_free_bytes')) is not int or type(phase.get('wal_ceiling_bytes')) is not int):
        raise ValueError('copy_monitor_phase_invalid')
    unit = 'edfinder-v3-purge-copy-' + phase['relation'] + '-' + phase['phase'] + '-' + str(backend['backend_pid'])
    config = {'mode': 'copy', 'purge_ids': phase['purge_ids'], 'relation': phase['relation'], 'phase': phase['phase'],
              'backend': backend, 'required_free_bytes': phase['required_free_bytes'],
              'wal_ceiling_bytes': phase['wal_ceiling_bytes'],
              'data_directory': identity['data_directory'], 'data_mount': report['data_mount'],
              'wal_before': report['wal_before'], 'controller': report['runner_state'],
              'script_sha256': report['script_sha256']}
    _launch(c, runtime, unit, config, report, key='copy_monitor')
    return unit


def copy_condition(unit):
    """The condition a copy watchdog cancelled on, if it did; None otherwise."""
    path = DIRECTORY / (unit + '.json.condition')
    try:
        secure_file(path)
    except (OSError, ValueError):
        return None
    value = path.read_text()
    path.unlink(missing_ok=True)
    return value if re.fullmatch('[a-z_]+', value) else None


def copy_detail(unit):
    """What latched that condition (``<backend|observe>:<code>``); None otherwise."""
    path = DIRECTORY / (unit + '.json.detail')
    try:
        secure_file(path)
    except (OSError, ValueError):
        return None
    value = path.read_text()
    path.unlink(missing_ok=True)
    return value if DETAIL_PATTERN.fullmatch(value) else None


def start(c, runtime, ids, relation, backend, identity, report):
    """Admission is complete; establish the watchdog before sending VACUUM."""
    unit = 'edfinder-v3-purge-rewrite-' + str(backend['start_event'])
    config = {'purge_ids': ids, 'relation': relation, 'backend': backend,
              'data_directory': identity['data_directory'],
              'data_mount': report['data_mount'], 'wal_before': report['wal_before'],
              'controller': report['runner_state'], 'script_sha256': report['script_sha256']}
    _launch(c, runtime, unit, config, report, key='rewrite_monitor')
    return unit


def _launch(c, runtime, unit, config, report, *, key):
    if os.geteuid() != 0:
        raise ValueError('rewrite_monitor_requires_root')
    DIRECTORY.mkdir(mode=0o700, exist_ok=True)
    info = DIRECTORY.lstat()
    if DIRECTORY.is_symlink() or not DIRECTORY.is_dir() or info.st_uid != 0 or info.st_mode & 0o077:
        raise ValueError('rewrite_monitor_state_unsafe')
    # A service executing mutable, unprivileged source as root is unacceptable.
    for source in _sources(c):
        for item in (source, *source.parents):
            stat = item.lstat()
            if item.is_symlink() or stat.st_uid != 0 or stat.st_mode & 0o022:
                raise ValueError('rewrite_monitor_source_unsafe')
    container_id = runtime.docker('inspect', '-f', '{{.Id}}', c.CONTAINER)
    if re.fullmatch('[0-9a-f]{64}', container_id) is None:
        raise ValueError('rewrite_monitor_container_identity_invalid')
    path = DIRECTORY / (unit + '.json')
    config = {**config, 'container_id': container_id}
    backend = config['backend']
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
            report[key] = {'unit': unit, 'container_id': container_id,
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
    if path.parent != DIRECTORY or re.fullmatch(
            r'edfinder-v3-purge-(?:rewrite-[1-9][0-9]*|copy-[a-z_]+-[a-z_]+-[1-9][0-9]*)\.json', path.name) is None:
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
    copy = c._load('v3_purge_copy')
    copy_mode = config.get('mode') == 'copy'
    if copy_mode and (path.name.startswith('edfinder-v3-purge-rewrite-')
                      or type(config.get('required_free_bytes')) is not int
                      or type(config.get('wal_ceiling_bytes')) is not int):
        raise ValueError('rewrite_monitor_arguments_invalid')
    if not copy_mode and path.name.startswith('edfinder-v3-purge-copy-'):
        raise ValueError('rewrite_monitor_arguments_invalid')
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
        value = runtime.query(copy.BACKEND_ALIVE_SQL if copy_mode else rewrite.BACKEND_SQL,
                              {'backend_pid': str(config['backend']['backend_pid']),
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
        floor = config['required_free_bytes'] if copy_mode else c.FREE_FLOOR_BYTES
        if delete.free_space(config['data_mount']['source'])['free_bytes'] < floor:
            raise ValueError('filesystem_free_space_floor')
        if runtime.device(config['data_directory'] + '/pg_wal') != config['data_mount']['device']:
            raise ValueError('tablespace_or_wal_filesystem_mismatch')
        wal = c.measure_wal(runtime, config['data_directory'])
        c.wal_health(config['wal_before'], wal)
        if copy_mode and wal['bytes'] > config['wal_ceiling_bytes']:
            raise ValueError('wal_ceiling_exceeded')
    condition_path = Path(str(path) + '.condition')
    detail_path = Path(str(path) + '.detail')
    def detail(text):
        # The unit's journal keeps it for either mode; a copy also leaves it
        # beside its condition for the dispatch receipt.
        print('watchdog_detail ' + text, file=sys.stderr, flush=True)
        if copy_mode and not detail_path.exists():
            with detail_path.open('x') as stream:
                os.chmod(detail_path, 0o600)
                stream.write(text)
    def cancel(condition):
        if not pinned():
            return
        if copy_mode:
            if not condition_path.exists():
                with condition_path.open('x') as stream:
                    os.chmod(condition_path, 0o600)
                    stream.write(condition)
            runtime.query(copy.CANCEL_SQL, {'backend_pid': str(config['backend']['backend_pid']),
                                            'backend_start': config['backend']['backend_start']}, write=True)
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
        watch(alive, observe, controller, cancel, detail=detail)
    finally:
        ready.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
