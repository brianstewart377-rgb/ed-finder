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


# A killed client is noticed by its backend only when the injected sleep ends,
# so an interrupted fixture never leaves a phase running for longer than this.
# The copy route's chunk statement timeout (300 s) and the crash driver's wait
# for the orphaned backend to exit both exceed it with margin.
PAUSE_SECONDS = 40
# Crash points inside one phase statement (pause after the 019 call, before the
# transaction commits) and after a committed swap/swap-back/drop transaction.
STATEMENT_FAULTS = {
    'copy_chunk_client_killed': 'CHUNK_SQL', 'copy_postgres_restart': 'CHUNK_SQL',
    'index_build_backend_terminated': 'BUILD_INDEXES_SQL', 'verify_watchdog_cancel': 'VERIFY_SQL',
}
COMMITTED_FAULTS = {
    'swap_committed_client_killed': ('SWAP_SQL',),
    'swap_back_committed_client_killed': ('SWAP_BACK_SQL', 'SWAP_BACK_OPPORTUNITY_SQL'),
    'drop_committed_client_killed': ('DROP_SQL',),
}
# The chunk fault waits for the second chunk of the dispatch so the ledger holds
# a committed chunk before the interrupted one.
FAULT_CHUNK = 2
PAUSE_ANCHORS = {
    'CHUNK_SQL': '%(max_rows)s::integer),',
    'BUILD_INDEXES_SQL': '%(purge_id)s::uuid,%(relation)s))',
    'VERIFY_SQL': '%(purge_id)s::uuid,%(relation)s))',
}
# Read-only Finder smoke over the application views (the disposable fixture
# runs no API): one ranked row per product and per economy view.
SMOKE_SQL = """BEGIN READ ONLY;
SET LOCAL statement_timeout='15s'; SET LOCAL lock_timeout='15s';
SELECT jsonb_build_object(
 'system_search',(SELECT count(*) FROM (SELECT system_id64 FROM v3_app.system_search ORDER BY system_id64 LIMIT 1) s),
 'system_archetype',(SELECT count(*) FROM (SELECT system_id64 FROM v3_app.system_archetype ORDER BY system_id64 LIMIT 1) a),
 'system_economy_rating',(SELECT count(*) FROM (SELECT system_id64 FROM v3_app.system_economy_rating LIMIT 1) e),
 'economy_opportunity',(SELECT count(*) FROM (SELECT system_id64 FROM v3_derived.economy_opportunity
   WHERE derived_generation_id='cfc25d36-3bc7-4011-a465-d6460eaaf826' LIMIT 1) o),
 'body_mechanics',(SELECT count(*) FROM (SELECT system_id64 FROM v3_derived.body_mechanics
   WHERE derived_generation_id='cfc25d36-3bc7-4011-a465-d6460eaaf826' LIMIT 1) b));
COMMIT;"""


def pause_statement(name, sql):
    """Insert the fixed pause after the phase's 019 call, inside its statement."""
    anchor = PAUSE_ANCHORS[name]
    if sql.count(anchor) != 1:
        raise ValueError('rehearsal_fault_anchor_changed')
    pause = ",'rehearsal_pause',(pg_sleep(" + str(PAUSE_SECONDS) + ') IS NULL)'
    if anchor.endswith('),'):
        return sql.replace(anchor, anchor[:-1] + pause + ',')
    return sql.replace(anchor, anchor[:-1] + pause + ')')


def pause_after_commit(sql):
    if not sql.rstrip().endswith('COMMIT;'):
        raise ValueError('rehearsal_fault_anchor_changed')
    return (sql + '\nDO $purge_rehearsal$ BEGIN PERFORM pg_sleep(' + str(PAUSE_SECONDS)
            + '); END $purge_rehearsal$;\n')


@contextmanager
def faulted_phase_backend(runtime, copy, chunk_calls, original, c_, runtime_, statement_timeout_ms, *, on_wait=None):
    """Insert a named mid-statement pause into a real phase backend's query."""
    scenario = os.environ.get('ED_PURGE_REHEARSAL_FAULT')
    with original(c_, runtime_, statement_timeout_ms, on_wait=on_wait) as backend:
        target = STATEMENT_FAULTS.get(scenario)
        if target is not None:
            query = backend.query
            def faulted(sql, params=None, **kwargs):
                if sql == getattr(copy, target):
                    if target == 'CHUNK_SQL':
                        chunk_calls[0] += 1
                    if target != 'CHUNK_SQL' or chunk_calls[0] == FAULT_CHUNK:
                        runtime.fault(scenario, pause=False)
                        sql = pause_statement(target, sql)
                return query(sql, params, **kwargs)
            backend.query = faulted
        yield backend


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

        def fault(self, scenario, *, pause=True, proof=None):
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
                json.dump({'scenario': scenario, 'pid': os.getpid(), **(proof or {})}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            if pause:
                time.sleep(120)
                raise ValueError('rehearsal_fault_not_interrupted')

        def query(self, sql, params=None, *, write=False):
            copy = c._load('v3_purge_copy')
            scenario = os.environ.get('ED_PURGE_REHEARSAL_FAULT')
            # Only the named committed-transaction faults change an input, and
            # only for their own fixed statement; production SQL is unchanged.
            self._rehearsal_commit_fault = scenario if any(
                sql == getattr(copy, name) for name in COMMITTED_FAULTS.get(scenario, ())) else None
            started = time.monotonic()
            try:
                result = super().query(sql, params, write=write)
            finally:
                self._rehearsal_commit_fault = None
                self.report.setdefault('statement_durations', []).append({
                    'statement_sha256': c.hashlib.sha256(sql.encode()).hexdigest(),
                    'kind': 'query', 'duration_seconds': time.monotonic() - started})
            return result

        def docker(self, *argv, **kwargs):
            scenario = getattr(self, '_rehearsal_commit_fault', None)
            if scenario is not None and 'input' in kwargs:
                # The transaction commits first; the client then sleeps in the
                # same session so the crash driver can kill it after COMMIT.
                self._rehearsal_commit_fault = None
                self.fault(scenario, pause=False)
                kwargs['input'] = pause_after_commit(kwargs['input'])
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
            # The copy route's free-space admission for a disposable measurement
            # only: the 100 GB floor with no measured peak, explicitly marked
            # unmeasured. It must never be consumed as production evidence.
            copy = c._load('v3_purge_copy')
            reviewed['copy'] = copy.plan_block(None, copy.BOOTSTRAP_SOURCE)
            reviewed['disposable_rehearsal_only'] = True

        def finder_smoke(self, *_args, **_kwargs):
            observed = self.query(SMOKE_SQL)
            if not isinstance(observed, dict) or any(observed.get(key) != 1 for key in (
                    'system_search', 'system_archetype', 'system_economy_rating',
                    'economy_opportunity', 'body_mechanics')):
                raise ValueError('finder_smoke_failed')
            return {'origin': 'disposable_database_views', 'passed': True, 'requests': observed}

    runtime = Runtime(report)
    chunk_calls = [0]

    def save(value, path=None, **_kwargs):
        # Host recovery evidence stays in this run's private directory.
        target = temporary / (Path(path).name if path is not None else 'writer-state.json')
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())

    def launch(config, output, key):
        process = subprocess.Popen([sys.executable, '-I', str(Path(__file__).resolve())],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=runtime.env, start_new_session=True, text=True)
        process.stdin.write(json.dumps(config) + '\n')
        process.stdin.close()
        if not c.select.select([process.stdout], [], [], 15)[0] or process.stdout.readline().strip() != 'ready':
            process.terminate()
            process.wait(timeout=10)
            raise ValueError('rehearsal_monitor_start_failed')
        process.stdout.close()
        output[key] = {'pid': process.pid, 'kind': 'disposable_backend_watchdog'}
        return process.pid

    def rehearsal_load(module, path=None):
        if module not in cache:
            value = load(module, path)
            if module == 'v3_purge_delete':
                value.free_space = runtime.filesystem
                value.running_services = lambda *_: []
                value.save_host_state = save
                value.backup_skips = lambda _runtime, output: output.update(
                    skipped_scheduled_backups={'records': [], 'reason': 'disposable_no_backup_scheduler'})
            elif module == 'v3_purge_copy':
                value.finder_smoke = runtime.finder_smoke
            elif module == 'v3_purge_copy_dispatch':
                original = value.phase_backend
                value.phase_backend = lambda *args, **kwargs: faulted_phase_backend(
                    runtime, rehearsal_load('v3_purge_copy'), chunk_calls, original, *args, **kwargs)
            elif module == 'v3_purge_rewrite_monitor':
                def start(_c, _runtime, ids, relation, backend, identity, output):
                    config = {'name': name, 'token': token, 'ids': ids, 'relation': relation,
                              'backend': backend, 'controller': output['runner_state']}
                    return launch(config, output, 'rewrite_monitor')
                def start_copy(_c, _runtime, phase, identity, output):
                    unit = ('copy-' + phase['relation'] + '-' + phase['phase'] + '-'
                            + str(phase['backend']['backend_pid']))
                    if re.fullmatch('copy-[a-z_]+-[a-z_]+-[1-9][0-9]*', unit) is None:
                        raise ValueError('copy_monitor_phase_invalid')
                    config = {'mode': 'copy', 'name': name, 'token': token, 'unit': unit,
                              'relation': phase['relation'], 'phase': phase['phase'],
                              'backend': phase['backend'], 'required_free_bytes': phase['required_free_bytes'],
                              'wal_ceiling_bytes': phase['wal_ceiling_bytes'],
                              'data_directory': identity['data_directory'], 'wal_before': output['wal_before'],
                              'controller': output['runner_state']}
                    launch(config, output, 'copy_monitor')
                    return unit
                def copy_condition(unit):
                    path = temporary / (unit + '.condition')
                    try:
                        text = path.read_text()
                    except OSError:
                        return None
                    path.unlink(missing_ok=True)
                    return text if re.fullmatch('[a-z_]+', text) else None
                def copy_detail(unit):
                    path = temporary / (unit + '.detail')
                    try:
                        text = path.read_text()
                    except OSError:
                        return None
                    path.unlink(missing_ok=True)
                    return text if value.DETAIL_PATTERN.fullmatch(text) else None
                value.start = start
                value.start_copy = start_copy
                value.copy_condition = copy_condition
                value.copy_detail = copy_detail
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
    copy = c._load('v3_purge_copy')
    copy_mode = configuration.get('mode') == 'copy'
    backend = configuration['backend']
    params = {'backend_pid': str(backend['backend_pid']), 'backend_start': backend['backend_start']}
    temporary = Path(tempfile.gettempdir()) / configuration['name']
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
            return runtime.query(copy.BACKEND_ALIVE_SQL if copy_mode else rewrite.BACKEND_SQL, params)['alive']
        finally:
            runtime.deadline = float('inf')
    def controller():
        # The crash driver creates this trigger only after observing the
        # phase's own statement active, proving cancellation was mid-phase.
        if os.environ.get('ED_PURGE_REHEARSAL_FAULT') == 'verify_watchdog_cancel':
            trigger = Path(os.environ.get('ED_PURGE_REHEARSAL_FAULT_FILE', '') + '.trigger')
            if trigger.is_file():
                raise ValueError('controller_lost')
        state = configuration['controller']
        for prefix in ('controller', 'launcher'):
            if delete.controller_identity(state[prefix + '_pid'], state['controller_run_id']) != state[prefix + '_start_ticks']:
                raise ValueError('controller_lost')
    def observe():
        floor = configuration['required_free_bytes'] if copy_mode else c.FREE_FLOOR_BYTES
        if runtime.filesystem()['free_bytes'] < floor:
            raise ValueError('filesystem_free_space_floor')
        if copy_mode:
            wal = c.measure_wal(runtime, configuration['data_directory'])
            c.wal_health(configuration['wal_before'], wal)
            if wal['bytes'] > configuration['wal_ceiling_bytes']:
                raise ValueError('wal_ceiling_exceeded')
    def cancel(condition):
        if copy_mode:
            # The breach is latched: record the first condition once, then
            # repeat the authenticated cancel until the backend has gone.
            path = temporary / (configuration['unit'] + '.condition')
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(fd, 'w') as stream:
                    stream.write(condition)
            runtime.deadline = time.monotonic() + 10
            try:
                runtime.query(copy.CANCEL_SQL, params, write=True)
            finally:
                runtime.deadline = float('inf')
            return
        rewrite.cancel_rewrite(runtime.query, configuration['ids'][0], configuration['relation'], condition)
    def detail(text):
        # What latched the condition, beside it for the dispatch receipt.
        if copy_mode:
            path = temporary / (configuration['unit'] + '.detail')
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            except FileExistsError:
                return
            with os.fdopen(fd, 'w') as stream:
                stream.write(text)
    print('ready', flush=True)
    c._load('v3_purge_rewrite_monitor').watch(alive, observe, controller, cancel, detail=detail)


if __name__ == '__main__':
    monitor_main()
