"""Explicit disposable transport for the real purge controller.

Nothing here changes migration 016, payload SQL, transaction recovery or the
100 GB database floor. The adapter substitutes only host facilities (local
locks, absent application services and an unprivileged watchdog). Its marker is
checked before changing any controller identity. Production hosts are denied
independently of the marker, including a marker accidentally copied to them.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

DATABASE = 'edfinder_purge_rehearsal'
LABEL = 'edfinder.purge-rehearsal'
MARKER_PREFIX = 'edfinder-disposable-purge-rehearsal:'
NAME_PATTERN = r'edfinder-purge-rehearsal-[a-f0-9]{32}'
PRODUCTION_HOSTS = frozenset(('ed-finder-prod', 'nb79a3d', 'nb79a3d.mevnode.com'))
PRODUCTION_CONTAINER = 'edfinder-v3-phase4c-full-20260827_r5-postgres'
PRODUCTION_DATABASE = 'edfinder_v3_phase4c_full_20260827_r5'


def validate_target(name, token, short_host, full_host, inspection, volume, marker):
    """Pure, fail-closed admission; every independent identity must agree."""
    if (short_host in PRODUCTION_HOSTS or full_host in PRODUCTION_HOSTS
            or name == PRODUCTION_CONTAINER or not isinstance(name, str)
            or re.fullmatch(NAME_PATTERN, name) is None
            or not isinstance(token, str) or re.fullmatch('[a-f0-9]{64}', token) is None):
        raise ValueError('rehearsal_production_or_invalid_identity')
    if not isinstance(inspection, dict) or not isinstance(volume, dict):
        raise ValueError('rehearsal_container_not_disposable')
    config = inspection.get('Config', {})
    host = inspection.get('HostConfig', {})
    mounts = inspection.get('Mounts')
    if (inspection.get('Name') != '/' + name
            or re.fullmatch('[a-f0-9]{64}', inspection.get('Id', '')) is None
            or inspection.get('State', {}).get('Running') is not True
            or config.get('Labels', {}).get(LABEL) != token
            or config.get('Hostname') != name
            or host.get('NetworkMode') != 'none'
            or host.get('Privileged') is not False
            or host.get('Binds') or host.get('PortBindings')
            or host.get('VolumesFrom') or host.get('Devices')
            or host.get('PidMode') or host.get('IpcMode') == 'host'
            or not isinstance(mounts, list) or len(mounts) != 1):
        raise ValueError('rehearsal_container_not_disposable')
    mount = mounts[0]
    if (mount.get('Type') != 'volume' or mount.get('Name') != name + '-data'
            or mount.get('Destination') != '/var/lib/postgresql' or mount.get('RW') is not True
            or volume.get('Name') != name + '-data'
            or volume.get('Labels', {}).get(LABEL) != token
            or volume.get('Driver') != 'local' or volume.get('Options')):
        raise ValueError('rehearsal_volume_not_disposable')
    if marker != {'database': DATABASE, 'marker': MARKER_PREFIX + token}:
        raise ValueError('rehearsal_database_marker_missing')
    return inspection['Id']


def install(c, report, name, token):
    """Admit the target first, then return a container-pinned Runtime subclass.

    Called only by the explicit pair of CLI arguments. No environment variable
    or DSN can activate the adapter. Each action is a separate interpreter.
    """
    if not name or not token:
        raise ValueError('rehearsal_arguments_require_pair')
    # Validate request and host before issuing even a Docker inspect or DB read.
    probe = c.Runtime(report)
    short = probe.run(['hostname', '-s'])
    full = probe.run(['hostname', '-f'])
    if (short in PRODUCTION_HOSTS or full in PRODUCTION_HOSTS
            or re.fullmatch(NAME_PATTERN, name) is None
            or re.fullmatch('[a-f0-9]{64}', token) is None):
        raise ValueError('rehearsal_production_or_invalid_identity')
    if probe.run(['docker', 'context', 'show']) != 'default':
        raise ValueError('unexpected_docker_context')
    context = json.loads(probe.docker('context', 'inspect', 'default'))
    if len(context) != 1 or context[0]['Endpoints']['docker']['Host'] != 'unix:///var/run/docker.sock':
        raise ValueError('unexpected_docker_endpoint')
    inspection = json.loads(probe.docker('inspect', name))
    volume = json.loads(probe.docker('volume', 'inspect', name + '-data'))
    if len(inspection) != 1 or len(volume) != 1:
        raise ValueError('rehearsal_inspection_invalid')
    # Admit topology before even the fixed marker read; then check the actual
    # marker separately. The expected value here is never evidence of admission.
    validate_target(name, token, short, full, inspection[0], volume[0],
                    {'database': DATABASE, 'marker': MARKER_PREFIX + token})
    # Query fixed DB over the container's Unix socket; no caller-selected URL.
    marker_sql = "SELECT json_build_object('database',current_database(),'marker',shobj_description(oid,'pg_database')) FROM pg_database WHERE datname=current_database()"
    marker = json.loads(probe.docker('exec', name, 'psql', '-X', '--no-password',
        '--username', 'edfinder_v3', '--dbname', DATABASE, '--host', '/var/run/postgresql',
        '--tuples-only', '--no-align', '--set', 'ON_ERROR_STOP=1', '--command', marker_sql))
    container_id = validate_target(name, token, short, full, inspection[0], volume[0], marker)
    # Constants are private to this invocation. All subsequent execs use ID,
    # preventing name reuse from redirecting a previously admitted connection.
    c.CONTAINER = container_id
    c.DATABASE = DATABASE
    c.INSTALLED_WRAPPER = c.WRAPPER
    c.check_wrapper = lambda: (c.hashlib.sha256(c.WRAPPER.read_bytes()).hexdigest(),) * 2
    cache = {}
    load = c._load
    temporary = Path(tempfile.gettempdir()) / name
    temporary.mkdir(mode=0o700, exist_ok=True)
    if temporary.is_symlink() or temporary.stat().st_uid != os.getuid() or temporary.stat().st_mode & 0o077:
        raise ValueError('rehearsal_lock_directory_unsafe')
    state = c.purge_state
    state.DATABASE_NAME = DATABASE
    lease_probe = state.lease_state
    state.lease_state = lambda: lease_probe(temporary / 'purge.lock')

    class Runtime(c.Runtime):
        rehearsal = True

        def guard(self):
            self.report.update(host=short, fqdn=full, container=name, database=DATABASE,
                               rehearsal=True, production_authority=False,
                               rehearsal_container_id=container_id,
                               workflow_run_id=os.environ.get('GITHUB_RUN_ID'),
                               source_git_sha=self.run(['git', '-C', str(c.ROOT), 'rev-parse', 'HEAD']),
                               script_sha256=c.script_identity())

        def fault(self, scenario, *, pause=True):
            if os.environ.get('ED_PURGE_REHEARSAL_FAULT') != scenario:
                return
            raw = os.environ.get('ED_PURGE_REHEARSAL_FAULT_FILE', '')
            path = Path(raw)
            if (not path.is_absolute() or path.parent.is_symlink()
                    or path.parent.stat().st_uid != os.getuid()
                    or path.parent.stat().st_mode & 0o022):
                raise ValueError('rehearsal_fault_path_unsafe')
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'w') as stream:
                json.dump({'scenario': scenario, 'pid': os.getpid()}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            if pause:
                time.sleep(120)
                raise ValueError('rehearsal_fault_not_interrupted')

        def query(self, sql, params=None, *, write=False):
            is_batch = sql == c._load('v3_purge_transactions').BATCH_SQL
            self._rehearsal_batch = is_batch
            started = time.monotonic()
            try:
                result = super().query(sql, params, write=write)
            finally:
                self._rehearsal_batch = False
                self.report.setdefault('statement_durations', []).append({
                    'statement_sha256': c.hashlib.sha256(sql.encode()).hexdigest(),
                    'kind': 'payload_batch' if is_batch else 'query',
                    'duration_seconds': time.monotonic() - started})
            return result

        @contextmanager
        def rewrite_backend(self, timeout_ms, *, on_wait=None):
            active = self
            with super().rewrite_backend(timeout_ms, on_wait=on_wait) as backend:
                class Backend:
                    def query(self, *args, **kwargs):
                        return backend.query(*args, **kwargs)

                    def command(self, statement):
                        started = time.monotonic()
                        try:
                            result = backend.command(statement)
                        finally:
                            active.report.setdefault('statement_durations', []).append({
                                'statement_sha256': c.hashlib.sha256(statement.encode()).hexdigest(),
                                'kind': 'vacuum_full_analyze' if statement.startswith('VACUUM') else 'command',
                                'duration_seconds': time.monotonic() - started})
                        if statement.startswith('VACUUM'):
                            active.fault('wrapper_after_rewrite_commit')
                        return result
                yield Backend()

        def docker(self, *argv, **kwargs):
            scenario = os.environ.get('ED_PURGE_REHEARSAL_FAULT')
            if (getattr(self, '_rehearsal_batch', False) and 'input' in kwargs
                    and scenario in ('batch_client_before_commit', 'batch_client_after_commit')):
                self.fault(scenario, pause=False)
                before, final = kwargs['input'].rsplit('COMMIT;', 1)
                # No additional result row; production's two committed JSON
                # result parsing stays unchanged. The crash driver waits for
                # this backend's PgSleep wait before killing its psql client.
                pause = "DO $purge_rehearsal$ BEGIN PERFORM pg_sleep(120); END $purge_rehearsal$;\n"
                kwargs['input'] = (before + pause + 'COMMIT;' + final if scenario == 'batch_client_before_commit'
                                   else before + 'COMMIT;\n' + pause + final)
            # Alpine's du reports allocated KiB. Preserve the controller's byte
            # transport contract and disclose this resolution in the receipt.
            if (len(argv) == 8 and argv[:3] == ('exec', c.CONTAINER, 'du')
                    and argv[3:7] == ('--bytes', '--summarize', '--dereference', '--')):
                result = super().docker('exec', c.CONTAINER, 'du', '-skL', argv[7], **kwargs)
                fields = result.split()
                if len(fields) != 2 or not fields[0].isdecimal() or fields[1] != argv[7]:
                    raise ValueError('wal_directory_bytes_unavailable')
                self.report['wal_directory_accounting'] = 'allocated_bytes_1KiB_resolution'
                return str(int(fields[0]) * 1024) + ' ' + fields[1]
            return super().docker(*argv, **kwargs)

        def workers(self):
            # Network-none, no application processes; inspect only this target.
            self.report['workers'] = [{'name': name, 'running': False,
                                       'reason': 'isolated_database_no_application_workers'}]
            return True

        def status_workers(self):
            self.workers()

        @contextmanager
        def local_lock(self, filename, attribute):
            descriptor = os.open(temporary / filename, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                setattr(self, attribute, descriptor)
                yield
            finally:
                setattr(self, attribute, None)
                os.close(descriptor)

        def lease(self):
            return self.local_lock('purge.lock', 'lease_fd')

        def backup_lock(self):
            return self.local_lock('backup.lock', 'backup_lock_fd')

        def filesystem(self, _path=None):
            fields = self.docker('exec', c.CONTAINER, 'stat', '-f', '-c', '%S %b %f %a', '/var/lib/postgresql').split()
            if len(fields) != 4 or any(not field.isdecimal() for field in fields):
                raise ValueError('rehearsal_filesystem_unknown')
            size, blocks, free, available = map(int, fields)
            return {'total_bytes': size * blocks, 'used_bytes': size * (blocks - free),
                    'free_bytes': size * available}

        def storage(self, identity, objects):
            directory = identity['data_directory']
            if identity.get('temp_tablespaces') or any(item['location'] for item in identity['tablespaces']):
                raise ValueError('rehearsal_external_tablespace')
            device = self.device(directory)
            for item in objects:
                path = item.get('path')
                if not isinstance(path, str) or path.startswith('/') or '..' in path.split('/'):
                    raise ValueError('relation_path_invalid')
                item['device'] = self.device(directory + '/' + path)
            c.check_placement(device, objects, [device], self.device(directory + '/pg_wal'))
            self.report['data_mount'] = {'source': '/var/lib/postgresql', 'destination': directory,
                'device': device, 'temp_devices': [device], 'wal_device': device}
            return self.filesystem()

        def prepare_plan(self, reviewed):
            # Admission bounds for a disposable measurement only. These are
            # explicitly unmeasured and must never be consumed as prod evidence.
            for relation in c.RELATIONS.values():
                reviewed['delete'][relation].update(
                    batch_limit=10000, batch_peak_bytes=900_000_000,
                    rows_per_second=1, rows_per_second_source='disposable_bootstrap_unmeasured',
                    rewrite_allowance_seconds=3600,
                    autovacuum_budget_bytes=1)
            reviewed['rewrite'] = {relation: {'rewrite_peak_bytes': 1_000_000_000,
                'statement_timeout_ms': 3_600_000} for relation in c.RELATIONS.values()}
            reviewed['disposable_rehearsal_only'] = True

    runtime = Runtime(report)

    def rehearsal_load(module, path=None):
        if module not in cache:
            value = load(module, path)
            if module == 'v3_purge_delete':
                value.free_space = runtime.filesystem
                value.running_services = lambda *_: []
                def save(value, **_kwargs):
                    target = temporary / 'writer-state.json'
                    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
                    with os.fdopen(fd, 'w') as stream:
                        json.dump(value, stream)
                        stream.flush()
                        os.fsync(stream.fileno())
                value.save_host_state = save
                value.backup_skips = lambda _runtime, output: output.update(
                    skipped_scheduled_backups={'records': [], 'reason': 'disposable_no_backup_scheduler'})
            elif module == 'v3_purge_rewrite_monitor':
                def start(_c, active_runtime, ids, relation, backend, identity, output):
                    config = {'name': name, 'token': token, 'ids': ids, 'relation': relation,
                              'backend': backend, 'controller': output['runner_state']}
                    process = subprocess.Popen([sys.executable, '-I', str(Path(__file__).resolve())],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                        env=active_runtime.env, start_new_session=True, text=True)
                    process.stdin.write(json.dumps(config) + '\n')
                    process.stdin.close()
                    if not c.select.select([process.stdout], [], [], 15)[0] or process.stdout.readline().strip() != 'ready':
                        process.terminate()
                        process.wait(timeout=10)
                        raise ValueError('rehearsal_monitor_start_failed')
                    process.stdout.close()
                    output['rewrite_monitor'] = {'pid': process.pid, 'kind': 'disposable_backend_watchdog'}
                    return process.pid
                value.start = start
            cache[module] = value
        return cache[module]
    c._load = rehearsal_load
    return runtime


def monitor_main():
    """Unprivileged independent watchdog, re-admitted from its disposable marker."""
    import importlib.util
    configuration = json.loads(sys.stdin.readline())
    spec = importlib.util.spec_from_file_location('purge', Path(__file__).with_name('v3_generation_purge.py'))
    c = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(c)
    runtime = install(c, c.receipt('rehearsal-monitor'), configuration['name'], configuration['token'])
    runtime.deadline = float('inf')
    rewrite = c._load('v3_purge_rewrite')
    delete = c._load('v3_purge_delete')
    backend = configuration['backend']
    params = {'backend_pid': str(backend['backend_pid']), 'backend_start': backend['backend_start']}
    def alive():
        # A removed/restarted fixture ends its original backend's lifetime.
        # Without this check a failed Docker exec could leave the watchdog
        # retrying forever after the always-cleanup step removes the container.
        inspected = runtime.docker('inspect', '-f', '{{.State.Running}}', c.CONTAINER,
                                   allow_failure=True, return_result=True)
        if inspected.returncode:
            if (inspected.returncode == 1 and not inspected.stdout.strip()
                    and inspected.stderr.strip() == 'Error: No such object: ' + c.CONTAINER):
                return False
            raise ValueError('rehearsal_monitor_container_unknown')
        if inspected.stdout.strip() == 'false':
            return False
        if inspected.stdout.strip() != 'true':
            raise ValueError('rehearsal_monitor_container_unknown')
        runtime.deadline = time.monotonic() + 10
        try:
            return runtime.query(rewrite.BACKEND_SQL, params)['alive']
        finally:
            runtime.deadline = float('inf')
    def controller():
        # The driver creates this trigger only after observing a live
        # pg_stat_progress_cluster row, proving cancellation was mid-rewrite.
        if os.environ.get('ED_PURGE_REHEARSAL_FAULT') == 'rewrite_monitor_cancel':
            trigger = Path(os.environ.get('ED_PURGE_REHEARSAL_FAULT_FILE', '') + '.trigger')
            if trigger.is_file():
                raise ValueError('controller_lost')
        state = configuration['controller']
        for prefix in ('controller', 'launcher'):
            if delete.controller_identity(state[prefix + '_pid'], state['controller_run_id']) != state[prefix + '_start_ticks']:
                raise ValueError('controller_lost')
    def observe():
        if runtime.filesystem()['free_bytes'] < c.FREE_FLOOR_BYTES:
            raise ValueError('filesystem_free_space_floor')
    def cancel(condition):
        rewrite.cancel_rewrite(runtime.query, configuration['ids'][0], configuration['relation'], condition)
    print('ready', flush=True)
    c._load('v3_purge_rewrite_monitor').watch(alive, observe, controller, cancel)


if __name__ == '__main__':
    monitor_main()
