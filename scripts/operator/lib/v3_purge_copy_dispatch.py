"""Copy-and-drop dispatch (preflight/copy/swap/swap-back/drop/abandon/complete).

Runs under the caller's host purge lease and backup-schedule lock. Migration
019 owns every ledger and payload mutation; this module owns host gates, the
per-phase SET LOCAL bounds, the chunk loop, the long-phase backend with its
root-owned watchdog and progress polling, swap retry/backoff, the Finder smoke,
and the economy_opportunity planner-statistics recalibration. Resumability is
per phase: a long phase that is cancelled or times out rolls back and the next
``copy-R`` dispatch re-enters it from the ledger; only integrity failures
record ``FAILED_STOP`` through ``purge_copy_record_failure``.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import multiprocessing
import os
from pathlib import Path
import re
import select
import subprocess
import tempfile
import time

# 330 minutes: the 320-minute verify plus its 300 s start margin and the
# preflight before it; the 360-minute job keeps 30 minutes for set-up, cleanup
# and upload (owner decision 2026-10-30; it was 9,000 s inside a 180-minute job).
DISPATCH_BUDGET_SECONDS = 19_800
# Root-owned host evidence of the economy_opportunity statistics option before
# its recalibration (019's append-only ledger has no event for it).
STATISTICS_STATE_FILE = Path('/var/lib/ed-finder/v3-production/derived-purge-copy-statistics.json')
PROGRESS_INTERVAL_SECONDS = 10
MAX_PROGRESS_SAMPLES = 2_000


def _bucket(report, key, empty):
    """receipt() initialises every field to None; grow a dict/list in place."""
    if not isinstance(report.get(key), type(empty)):
        report[key] = empty
    return report[key]


class PhaseBackendError(ValueError):
    def __init__(self, code, sqlstate=None):
        super().__init__(code)
        self.sqlstate = sqlstate
        self.evidence = {'sqlstate': sqlstate}


def psql_argv(c):
    """The pinned container login; the only transport phase_backend uses."""
    return ['docker', '--context', 'default', 'exec', '-i', c.CONTAINER,
            'psql', '-X', '--no-psqlrc', '--no-password', '--username', c.USER,
            '--dbname', c.DATABASE, '--host', '/var/run/postgresql',
            '--tuples-only', '--no-align', '--quiet', '--set', 'ON_ERROR_STOP=1',
            '--set', 'VERBOSITY=sqlstate', '--file=-']


def _no_wait():
    """Session set-up runs before the caller's callback may see the backend."""


@contextmanager
def phase_backend(c, runtime, statement_timeout_ms, *, on_wait=None):
    """One persistent owner login: identity first, then the executor session.

    The identity is read before SET ROLE so the watchdog can pin PID and
    backend_start. SQLSTATE diagnostics stay in a private temporary file; only
    the five-character code reaches the receipt. The caller's ``on_wait``
    (progress polling, cancellation, controller liveness) is enabled only for
    queries issued after the backend is yielded: during set-up the callback
    could not yet know the backend it observes.
    """
    rewrite = c._load('v3_purge_rewrite')
    argv = psql_argv(c)
    with tempfile.TemporaryFile(mode='w+') as errors:
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=errors, bufsize=0, env=runtime.env,
                                   pass_fds=tuple(fd for fd in (runtime.lease_fd, runtime.backup_lock_fd) if fd is not None))

        class Backend:
            pending = b''
            identity = None
            sqlstate = None

            def _sqlstate(self):
                try:
                    errors.seek(0)
                    text = errors.read(65536)
                except (OSError, ValueError):
                    return None
                found = re.findall(r'\bERROR:\s+([0-9A-Z]{5})\b', text)
                return found[-1] if found else None

            def query(self, sql, params=None, *, write=False, wait=None):
                assignments = []
                for key, value in (params or {}).items():
                    if re.fullmatch('[a-z][a-z0-9_]*', key) is None:
                        raise ValueError('invalid_parameter_name')
                    value = c.evidence.canonical_json(value) if not isinstance(value, str) else value
                    assignments.append('\\set ' + key + " '" + value.encode().hex() + "'")
                    sql = sql.replace('%(' + key + ')s', "convert_from(decode(:'" + key + "','hex'),'UTF8')")
                if '%(' in sql:
                    raise ValueError('unbound_parameter')
                if write:
                    runtime.report.update(read_only=False, db_writes_performed=None, transaction_outcome=None)
                if process.poll() is not None:
                    self.sqlstate = self._sqlstate()
                    raise PhaseBackendError('copy_phase_backend_failed', self.sqlstate)
                try:
                    process.stdin.write(('\n'.join(assignments) + '\n' + sql + '\n').encode())
                    process.stdin.flush()
                except (BrokenPipeError, OSError):
                    self.sqlstate = self._sqlstate()
                    raise PhaseBackendError('copy_phase_backend_failed', self.sqlstate) from None
                waiter = wait or on_wait
                while True:
                    if waiter is not None:
                        waiter()
                    if time.monotonic() >= runtime.deadline:
                        raise ValueError('copy_controller_timeout')
                    if b'\n' not in self.pending and select.select([process.stdout], [], [], 0.2)[0]:
                        chunk = os.read(process.stdout.fileno(), 65536)
                        if not chunk:
                            self.sqlstate = self._sqlstate()
                            raise PhaseBackendError('copy_phase_backend_failed', self.sqlstate)
                        self.pending += chunk
                    if len(self.pending) > c.MAX_OUTPUT:
                        raise ValueError('command_output_bound_exceeded')
                    if b'\n' in self.pending:
                        raw, self.pending = self.pending.split(b'\n', 1)
                        line = raw.decode('utf-8')
                        if not line.lstrip().startswith('{'):
                            continue
                        try:
                            result = json.loads(line)
                        except ValueError:
                            raise ValueError('database_result_invalid') from None
                        if write:
                            runtime.report.update(db_writes_performed=True, transaction_outcome='committed')
                        return result
                    if process.poll() is not None:
                        self.sqlstate = self._sqlstate()
                        raise PhaseBackendError('copy_phase_backend_failed', self.sqlstate)
        try:
            backend = Backend()
            backend.identity = backend.query(c._load('v3_purge_copy').BACKEND_IDENTITY_SQL, wait=_no_wait)
            if (type(backend.identity.get('backend_pid')) is not int or backend.identity['backend_pid'] <= 0
                    or not isinstance(backend.identity.get('backend_start'), str)):
                raise ValueError('copy_backend_identity_invalid')
            backend.query(rewrite.session_setup(statement_timeout_ms) + "SELECT jsonb_build_object('session_ready',true);",
                          wait=_no_wait)
            yield backend
        finally:
            try:
                process.stdin.close()
            except OSError:
                pass
            deadline = time.monotonic() + 30
            while process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.1)
            if process.poll() is None:
                process.kill()
            process.stdout.close()
            process.wait()


def _controller(c, report, controller_pid, controller_run_id):
    delete = c._load('v3_purge_delete')
    controller_pid = controller_pid or os.getppid()
    controller_run_id = controller_run_id or os.environ.get('GITHUB_RUN_ID')
    controller_start = delete.controller_identity(controller_pid, controller_run_id)
    launcher_start = delete.controller_identity(os.getpid(), controller_run_id)
    report['runner_state'] = {'controller_pid': controller_pid, 'controller_run_id': controller_run_id,
                              'controller_start_ticks': controller_start, 'launcher_pid': os.getpid(),
                              'launcher_start_ticks': launcher_start}

    def alive():
        if (delete.controller_identity(controller_pid, controller_run_id) != controller_start
                or delete.controller_identity(os.getpid(), controller_run_id) != launcher_start):
            raise ValueError('controller_lost')
    return alive


def _state(c, copy, runtime, reviewed, relation):
    status = runtime.query(copy.STATUS_SQL)
    state = copy.relation_state(status, reviewed['plan_sha256'], relation)
    request = runtime.query(copy.REQUEST_SQL, {'plan_sha256': reviewed['plan_sha256']})
    if request is not None and not isinstance(request, dict):
        raise ValueError('purge_copy_request_invalid')
    frozen = None
    if request is not None:
        survivors = request.get('frozen_survivors')
        frozen = survivors.get(relation) if isinstance(survivors, dict) else None
        if type(frozen) is not int or frozen < 0:
            raise ValueError('copy_frozen_survivors_unknown')
    return status, state, request, frozen


def _light_workers(runtime):
    runtime.status_workers()
    if any(worker.get('running') is not False for worker in runtime.report.get('workers') or []):
        raise ValueError('named_workers_not_stopped')


def _measure(c, copy, runtime, identity, report, required_bytes):
    delete = c._load('v3_purge_delete')
    _light_workers(runtime)
    disk = delete.free_space(report['data_mount']['source'])
    report['filesystem_after'] = disk
    wal = c.measure_wal(runtime, identity['data_directory'])
    report['wal_after'] = wal
    c.wal_health(report['wal_before'], wal)
    if runtime.device(identity['data_directory'] + '/pg_wal') != report['data_mount']['device']:
        raise ValueError('tablespace_or_wal_filesystem_mismatch')
    gate = {'filesystem_free_bytes': disk['free_bytes'], 'required_bytes': required_bytes,
            'wal_bytes': wal['bytes'], 'observed_at': datetime.now(timezone.utc).isoformat()}
    report['copy_gate'] = gate
    if disk['free_bytes'] < required_bytes:
        raise ValueError('filesystem_free_space_floor')
    return gate


REDO_PATTERN = re.compile(r"^Latest checkpoint's REDO location:[ \t]+([0-9A-F]{1,8}/[0-9A-F]{1,8})[ \t]*$", re.M)


def _wal_since_checkpoint(c, copy, runtime, identity, current_lsn):
    """WAL written since the latest checkpoint's REDO point (the WAL a crash
    would replay and a checkpoint cannot yet recycle).

    The pg_wal directory itself is not this quantity: after a sustained write
    burst PostgreSQL keeps recycled, pre-allocated segments there up to about
    max_wal_size, and an idle server skips checkpoints, so a directory-size
    throttle could wait forever. The REDO location comes from the pinned
    container's control file, read as the server's own OS user (as the data
    directory is): no SQL capability is added to the executor.
    """
    text = runtime.docker('exec', '--user', 'postgres', '--env', 'LC_ALL=C', c.CONTAINER,
                          'pg_controldata', '-D', identity['data_directory'])
    found = REDO_PATTERN.findall(text if isinstance(text, str) else '')
    if len(found) != 1 or not isinstance(current_lsn, str):
        raise ValueError('wal_checkpoint_redo_unknown')
    delta = runtime.query(copy.WAL_DELTA_SQL, {'before_lsn': found[0], 'after_lsn': current_lsn}).get('bytes')
    if type(delta) is not int or delta < 0:
        raise ValueError('wal_checkpoint_redo_unknown')
    return delta


def _wait(c, copy, runtime, identity, report, *, controller_alive, stop, max_wal_size, lag_segments,
          clock=time.monotonic, sleep=time.sleep):
    """Throttle: WAL since the last checkpoint under the soft limit and the
    archiver within its lag bound. pg_wal health is re-checked every poll."""
    started = clock()
    while True:
        controller_alive()
        if stop.is_set():
            raise ValueError('copy_stop_requested')
        wal = c.measure_wal(runtime, identity['data_directory'])
        c.wal_health(report['wal_before'], wal)
        observed = runtime.query(copy.WAL_LAG_SQL)
        lag = copy.archive_lag_segments(observed)
        retained = _wal_since_checkpoint(c, copy, runtime, identity, observed.get('wal_lsn'))
        report['wal_throttle'] = {'wal_since_checkpoint_bytes': retained, 'wal_directory_bytes': wal['bytes'],
                                  'max_wal_size_bytes': max_wal_size,
                                  'archive_lag_segments': lag, 'lag_bound_segments': lag_segments,
                                  'waited_seconds': round(clock() - started, 1)}
        if not copy.wal_throttle_needed(retained, max_wal_size) and lag <= lag_segments:
            return report['wal_throttle']
        if clock() - started >= copy.ARCHIVE_WAIT_SECONDS:
            raise ValueError('wal_archive_lag_wait_exhausted')
        if clock() >= runtime.deadline - 60:
            raise ValueError('copy_controller_timeout')
        sleep(copy.THROTTLE_POLL_SECONDS)


def _record_failure(c, copy, runtime, report, ids, relation, evidence):
    report.update(failed_stop_attempted=True, failed_stop_recorded=None, integrity_failed=True,
                  failure_evidence=evidence)
    try:
        recorded = runtime.query(copy.RECORD_FAILURE_SQL, {'purge_id': ids[0], 'relation': relation,
                                                           'evidence': c.evidence.canonical_json(evidence)}, write=True)
        if type(recorded.get('event')) is not int:
            raise ValueError('purge_failed_stop_outcome_unknown')
    except Exception:
        report['failed_stop_recorded'] = None
        raise
    report['failed_stop_recorded'] = recorded['event']
    return recorded


def _long_phase(c, copy, runtime, report, *, phase, sql, params, relation, ids, identity,
                controller_alive, stop, required_bytes, max_wal_size, write=True):
    """One 019 call (or VACUUM) under the per-phase bounds, the watchdog and
    progress polling; the job stays attached until the backend answers."""
    monitor = c._load('v3_purge_rewrite_monitor')
    settings = copy.phase_settings(phase)
    report['copy_phase'] = phase
    _bucket(report, 'phase_timeouts', {})[phase] = settings
    if settings['temp_file_limit_kb'] is not None:
        privilege = runtime.query(copy.TEMP_FILE_LIMIT_PRIVILEGE_SQL)
        report['temp_file_limit_privilege'] = privilege
        if privilege.get('can_set_temp_file_limit') is not True:
            raise ValueError('temp_file_limit_privilege_missing')
    _wait(c, copy, runtime, identity, report, controller_alive=controller_alive, stop=stop,
          max_wal_size=max_wal_size, lag_segments=copy.ARCHIVE_LAG_PHASE_SEGMENTS)
    if runtime.workers() is not True:
        raise ValueError('named_workers_not_stopped')
    gate = _measure(c, copy, runtime, identity, report, required_bytes)
    _bucket(report, 'copy_phase_gates', {})[phase] = gate
    before = runtime.query(copy.WAL_LAG_SQL)['wal_lsn']
    timeout_seconds = settings['statement_timeout_ms'] / 1000
    runtime.deadline = max(runtime.deadline, time.monotonic() + timeout_seconds + copy.LONG_PHASE_MARGIN_SECONDS)
    samples = []
    last_sample = [0.0]
    cancelled = [False]
    # The callback never closes over the context variable: it observes only a
    # backend that phase_backend has finished setting up and yielded.
    active = {}

    def on_wait():
        backend = active.get('backend')
        if backend is None:
            return
        identity_params = {'backend_pid': str(backend.identity['backend_pid']),
                           'backend_start': backend.identity['backend_start']}
        if stop.is_set() and not cancelled[0]:
            cancelled[0] = True
            try:
                runtime.query(copy.CANCEL_SQL, identity_params, write=True)
            except Exception:
                pass
        controller_alive()
        now = time.monotonic()
        if now - last_sample[0] >= PROGRESS_INTERVAL_SECONDS and len(samples) < MAX_PROGRESS_SAMPLES:
            last_sample[0] = now
            try:
                samples.append({'at': datetime.now(timezone.utc).isoformat(),
                                **runtime.query(copy.PROGRESS_SQL, identity_params)})
            except (RuntimeError, ValueError):
                samples.append({'at': datetime.now(timezone.utc).isoformat(), 'unavailable': True})
            report['copy_progress'] = {'phase': phase, 'samples': len(samples), 'last': samples[-1]}
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    with phase_backend(c, runtime, settings['statement_timeout_ms'], on_wait=on_wait) as backend:
        active['backend'] = backend
        unit = monitor.start_copy(c, runtime, {
            'phase': phase, 'relation': relation, 'purge_ids': ids, 'backend': backend.identity,
            # Admission (above) required the full reservation: floor + growth
            # + temp + WAL. While running, the phase is meant to consume that
            # reservation, so the watchdog guards only the safety floor.
            'required_free_bytes': copy.FLOOR_BYTES,
            'wal_ceiling_bytes': max_wal_size * copy.WAL_CEILING_MULTIPLIER,
        }, identity, report)
        controller_alive()
        try:
            result = backend.query(sql, params, write=write)
        except PhaseBackendError as exc:
            condition = monitor.copy_condition(unit)
            detail = monitor.copy_detail(unit)
            kind = copy.classify_sqlstate(exc.sqlstate)
            _bucket(report, 'copy_phase_failures', []).append({
                'phase': phase, 'sqlstate': exc.sqlstate, 'classification': kind,
                'monitor_condition': condition, 'monitor_detail': detail, 'started_at': started_at})
            if kind == 'integrity':
                _record_failure(c, copy, runtime, report, ids, relation,
                                copy.failure_evidence('copy_' + phase + '_integrity_failed', phase, exc.sqlstate,
                                                      {'monitor_condition': condition, 'controller': report['runner_state']}))
                raise ValueError('copy_' + phase + '_integrity_failed') from None
            raise ValueError('copy_' + phase + '_interrupted') from None
    after = runtime.query(copy.WAL_LAG_SQL)['wal_lsn']
    delta = runtime.query(copy.WAL_DELTA_SQL, {'before_lsn': before, 'after_lsn': after}).get('bytes')
    if type(delta) is not int or delta < 0:
        raise ValueError('wal_byte_delta_unavailable')
    _bucket(report, 'wal_phase_bytes', {})[phase] = delta
    _bucket(report, 'copy_steps', []).append({'phase': phase, 'started_at': started_at,
                                                'completed_at': datetime.now(timezone.utc).isoformat(),
                                                'seconds': round(time.monotonic() - started, 6),
                                                'wal_bytes': delta, 'result': result})
    return result


def _retrying(c, copy, runtime, report, *, phase, sql, params, clock=time.monotonic, sleep=time.sleep):
    """Swap/swap-back/drop: bounded attempts, each capped by its statement
    timeout, retried only on lock or statement timeout; the stall is recorded."""
    attempts = []
    report['swap_attempts'] = attempts
    for index in range(copy.SWAP_MAX_ATTEMPTS):
        started = clock()
        try:
            result = runtime.query(sql, params, write=True)
        except RuntimeError as exc:
            code = str(exc)
            seconds = round(clock() - started, 3)
            retryable = code in ('database_lock_timeout', 'database_statement_timeout')
            attempts.append({'attempt': index + 1, 'seconds': seconds, 'outcome': code})
            if not retryable:
                raise ValueError(phase + '_failed') from None
            if index + 1 >= copy.SWAP_MAX_ATTEMPTS:
                raise ValueError(phase + '_lock_attempts_exhausted') from None
            sleep(copy.SWAP_BACKOFF_SECONDS[index])
            continue
        attempts.append({'attempt': index + 1, 'seconds': round(clock() - started, 3), 'outcome': 'committed'})
        report['measured_stall_seconds'] = max(a['seconds'] for a in attempts)
        return result
    raise ValueError(phase + '_lock_attempts_exhausted')


def _common(c, copy, mode, runtime, report, plan, verification, *, relation, need_proof=True):
    tx = c._load('v3_purge_transactions')
    # First observation is the P2a admission state, before any plan or host
    # access: an orphaned writer/service fence needs restore-services first.
    state = c.admission_state(runtime, report, allow_unresolved=True)
    if plan is None:
        raise ValueError('authenticated_plan_required')
    reviewed = plan['reviewed_plan']
    ids = tx.get_purge_ids(runtime.query, reviewed['plan_sha256'])
    requests = tx._requests(runtime.query, ids, reviewed)
    report.update(purge_id=ids, reviewed_plan_sha256=reviewed['plan_sha256'], relation=relation)
    if need_proof:
        proof = c.verification_gate(verification, requests)
        report['system_archetype_verification'] = proof
        if proof['status'] != 'proven':
            raise ValueError('sealed_verification_required')
    if state.get('copy_ledger_present') is not True:
        raise ValueError('purge_copy_ledger_absent')
    if state['unresolved']:
        # Any open 016 operation or integrity stop refuses the copy route: those
        # events hold the old relation OIDs (019 refuses too; refuse earlier here).
        kinds = sorted({event['event_kind'] for event in state['unresolved']})
        report['next_admissible_mode'] = {'mode': 'restore-services' if {'WRITER_FENCE_ENABLED', 'SERVICES_QUIESCED'} & set(kinds)
                                          else 'status', 'reason': 'open_016_event_' + '_'.join(kinds)}
        raise ValueError('open_governed_purge_event_refuses_copy')
    identity = runtime.query(c.IDENTITY_SQL)
    defaults = identity.get('role_defaults')
    if not isinstance(defaults, list) or any(v != 'default_transaction_read_only=off' for v in defaults):
        raise ValueError('application_role_already_read_only_or_unknown')
    entries = c.validate_identity(identity, report, runtime=runtime)
    report['postmaster_started_epoch'] = identity.get('postmaster_started_epoch')
    identity['data_directory'] = runtime.data_directory()
    report['wal_before'] = c.measure_wal(runtime, identity['data_directory'])
    if runtime.query(c.POINTER_IDENTITIES_SQL) != reviewed.get('pointer_identities'):
        raise ValueError('copy_pointer_identity_drift')
    c.survivor_gate(runtime, reviewed, report, 'published_survivors_before')
    objects = runtime.query(c.OBJECTS_SQL)
    if not objects or any(obj.get('valid') is not True for obj in objects):
        raise ValueError('relation_or_index_evidence_invalid')
    report['filesystem_before'] = runtime.storage(identity, objects)
    report['relation_bytes_before'] = objects
    expected, installed = c.check_wrapper()
    report.update(expected_wrapper_sha256=expected, installed_wrapper_sha256=installed)
    if expected != plan.get('expected_wrapper_sha256'):
        raise ValueError('plan_backup_wrapper_hash_changed')
    return reviewed, ids, identity, entries


def _require_no_competitor(copy, runtime, report):
    """Refuse, retryably, while another backend may still hold 019's copy lock."""
    observed = runtime.query(copy.COMPETING_COPY_SQL)
    report['competing_copy_backends'] = observed
    if (not isinstance(observed, dict) or type(observed.get('lock_holders')) is not int
            or type(observed.get('copy_statements')) is not int):
        raise ValueError('competing_copy_observation_invalid')
    if observed['lock_holders'] or observed['copy_statements']:
        report['next_admissible_mode'] = {'mode': 'status', 'reason': 'wait_for_the_earlier_copy_backend_to_exit'}
        raise ValueError('competing_purge_copy_backend_active')


def preflight(c, copy, runtime, report, relation, *, scan):
    observed = runtime.query(copy.PREFLIGHT_SQL, {'relation': relation})
    violations = None
    if relation == 'system_search' and scan:
        violations = runtime.query(copy.SEARCH_VIOLATIONS_SQL)
    result = copy.evaluate_preflight(observed, violations=violations, relation=relation)
    report['copy_preflight'] = result
    return result


def dispatch(c, mode, runtime, report, plan, verification, *, wall_clock_seconds=300,
             controller_pid=None, controller_run_id=None, acknowledge_failed_stop=None,
             writer_mode='read-only'):
    copy = c._load('v3_purge_copy')
    if writer_mode != 'read-only':
        raise ValueError('quiesce_mode_not_authorized_option_b_only')
    if acknowledge_failed_stop is not None:
        raise ValueError('acknowledgement_not_admitted')
    if mode == 'complete':
        return complete(c, copy, runtime, report, plan, verification)
    kind, relation = copy.relation_for_mode(mode)
    reviewed, ids, identity, entries = _common(c, copy, mode, runtime, report, plan, verification,
                                               relation=relation, need_proof=kind != 'preflight')
    if kind == 'preflight':
        report['read_only'] = True
        preflight(c, copy, runtime, report, relation, scan=True)
        report.update(result='copy_preflight_passed', status='success')
        return
    _require_no_competitor(copy, runtime, report)
    controller_alive = _controller(c, report, controller_pid, controller_run_id)
    stop = multiprocessing.get_context('fork').Event()
    delete = c._load('v3_purge_delete')
    status, state, request, frozen = _state(c, copy, runtime, reviewed, relation)
    report['copy_state'] = state
    staging = runtime.query(copy.STAGING_SQL, {'relation': relation})
    max_wal_size = staging.get('max_wal_size_bytes')
    if type(max_wal_size) is not int or max_wal_size <= 0:
        raise ValueError('wal_measurement_invalid')
    report['max_wal_size_bytes'] = max_wal_size
    with delete.stop_signals(stop):
        try:
            if kind == 'copy':
                _copy(c, copy, runtime, report, reviewed, ids, identity, entries, relation, state, frozen, staging,
                      controller_alive=controller_alive, stop=stop, max_wal_size=max_wal_size,
                      wall_clock_seconds=wall_clock_seconds)
            elif kind == 'swap':
                _swap(c, copy, runtime, report, ids, identity, relation, state,
                      controller_alive=controller_alive, stop=stop, max_wal_size=max_wal_size)
            elif kind == 'swap_back':
                _swap_back(c, copy, runtime, report, ids, identity, relation, state,
                           controller_alive=controller_alive, stop=stop, max_wal_size=max_wal_size)
            elif kind == 'drop':
                _drop(c, copy, runtime, report, ids, identity, relation, state,
                      controller_alive=controller_alive, stop=stop, max_wal_size=max_wal_size)
            elif kind == 'abandon':
                _abandon(c, copy, runtime, report, ids, relation, state)
            else:
                raise ValueError('unknown_mode')
        finally:
            stop.set()
            runtime.deadline = max(runtime.deadline, time.monotonic() + 180)
            try:
                after_status, after_state, _request, _frozen = _state(c, copy, runtime, reviewed, relation)
                report['copy_state_after'] = after_state
                report['copy_status'] = after_status
            except Exception:
                report['copy_state_after'] = None
            delete.backup_skips(runtime, report)
    c.finalize_wal_delta(runtime, report)
    report['status'] = 'success'


def _copy(c, copy, runtime, report, reviewed, ids, identity, entries, relation, state, frozen, staging, *,
          controller_alive, stop, max_wal_size, wall_clock_seconds):
    if type(wall_clock_seconds) is not int or not 1 <= wall_clock_seconds <= copy.MAX_WALL_CLOCK_SECONDS:
        raise ValueError('copy_wall_clock_budget_invalid')
    dispatch_started = time.monotonic()
    runtime.deadline = max(runtime.deadline, dispatch_started + DISPATCH_BUDGET_SECONDS + 600)
    report.update(wall_clock_timeout_seconds=wall_clock_seconds, batch_limit=copy.CHUNK_ROWS,
                  copy_dispatch_budget_seconds=DISPATCH_BUDGET_SECONDS)
    step = copy.next_step(state, frozen, staging)
    report['copy_next_step'] = step
    if step.startswith('refuse:'):
        raise ValueError(step.removeprefix('refuse:'))
    # Read-only preflight first. The payload scan runs only before prepare; a
    # resumed copy repeats the catalog checks every dispatch.
    preflight(c, copy, runtime, report, relation, scan=step == 'prepare')
    remaining_budget = lambda: DISPATCH_BUDGET_SECONDS - (time.monotonic() - dispatch_started)  # noqa: E731
    params = {'purge_id': ids[0], 'relation': relation}
    if step == 'prepare':
        _wait(c, copy, runtime, identity, report, controller_alive=controller_alive, stop=stop,
              max_wal_size=max_wal_size, lag_segments=copy.ARCHIVE_LAG_CHUNK_SEGMENTS)
        # Design 1.6: the whole relation's copy must fit before the first row
        # is copied (floor + 1.5 x the plan's reviewed peak proxy).
        required = max(copy.required_before_copy(reviewed, relation),
                       copy.chunk_gate_required(copy.DEFAULT_CHUNK_RESERVATION_BYTES))
        report['required_free_bytes_before_copy'] = required
        _measure(c, copy, runtime, identity, report, required)
        _bucket(report, 'phase_timeouts', {})['prepare'] = copy.phase_settings('prepare')
        result = runtime.query(copy.PREPARE_SQL, params, write=True)
        if type(result.get('event')) is not int:
            raise ValueError('copy_prepare_outcome_unknown')
        _bucket(report, 'copy_steps', []).append({'phase': 'prepare', 'result': result})
        _status, state, _request, frozen = _state(c, copy, runtime, reviewed, relation)
        staging = runtime.query(copy.STAGING_SQL, {'relation': relation})
        step = copy.next_step(state, frozen, staging)
    if step == 'chunk':
        _chunks(c, copy, runtime, report, ids, identity, entries, relation, state, frozen, staging,
                controller_alive=controller_alive, stop=stop, max_wal_size=max_wal_size,
                budget_seconds=min(wall_clock_seconds, max(1, int(remaining_budget()))))
        _status, state, _request, frozen = _state(c, copy, runtime, reviewed, relation)
        staging = runtime.query(copy.STAGING_SQL, {'relation': relation})
        step = copy.next_step(state, frozen, staging)
    while step in ('index_build', 'vacuum_freeze', 'verify'):
        settings = copy.phase_settings(step)
        if remaining_budget() < settings['statement_timeout_ms'] / 1000 + copy.LONG_PHASE_MARGIN_SECONDS:
            report.update(result='copy_long_phase_deferred_to_next_dispatch', copy_next_step=step,
                          next_admissible_mode={'mode': 'copy-' + relation.replace('_', '-'), 'implemented': True})
            return
        if stop.is_set():
            raise ValueError('copy_stop_requested')
        if step == 'index_build':
            index_bytes = copy.expected_index_bytes(staging['live_index_bytes'], staging['live_reltuples'], frozen)
            report['expected_index_bytes'] = index_bytes
            required = copy.long_phase_required('index_build', index_bytes=index_bytes, max_wal_size_bytes=max_wal_size)
            _long_phase(c, copy, runtime, report, phase='index_build', sql=copy.BUILD_INDEXES_SQL, params=params,
                        relation=relation, ids=ids, identity=identity, controller_alive=controller_alive, stop=stop,
                        required_bytes=required, max_wal_size=max_wal_size)
        elif step == 'vacuum_freeze':
            required = copy.long_phase_required('vacuum_freeze', max_wal_size_bytes=max_wal_size)
            xid_before = runtime.query(copy.STAGING_SQL, {'relation': relation}).get('xid_next')
            _long_phase(c, copy, runtime, report, phase='vacuum_freeze', sql=copy.vacuum_sql(relation), params=None,
                        relation=relation, ids=ids, identity=identity, controller_alive=controller_alive, stop=stop,
                        required_bytes=required, max_wal_size=max_wal_size)
            # F12: the VACUUM must have frozen the copy, not merely run.
            fresh = runtime.query(copy.STAGING_SQL, {'relation': relation})
            report['staging_freeze'] = {**copy.staging_frozen(fresh, xid_before=xid_before),
                                        'last_vacuum': fresh.get('last_vacuum'), 'last_analyze': fresh.get('last_analyze')}
        else:
            fresh = runtime.query(copy.STAGING_SQL, {'relation': relation})
            try:
                report['staging_freeze'] = {**copy.staging_frozen(fresh), 'last_vacuum': fresh.get('last_vacuum'),
                                            'last_analyze': fresh.get('last_analyze')}
            except ValueError:
                # A resumed dispatch whose earlier FREEZE has aged out of the
                # absolute bound freezes again rather than verifying stale ages.
                report['staging_freeze'] = {'refrozen': True, 'staging_xid_age': fresh.get('staging_xid_age')}
                step = 'vacuum_freeze'
                continue
            required = copy.long_phase_required('verify', max_wal_size_bytes=max_wal_size)
            _long_phase(c, copy, runtime, report, phase='verify', sql=copy.VERIFY_SQL, params=params,
                        relation=relation, ids=ids, identity=identity, controller_alive=controller_alive, stop=stop,
                        required_bytes=required, max_wal_size=max_wal_size)
            # 019 verifies the generation set and fingerprint under the executor;
            # the published products must also still hold the frozen rows.
            c.survivor_gate(runtime, reviewed, report, 'published_survivors_after')
        c.require_reviewed_migration_ledger(runtime, entries)
        _status, state, _request, frozen = _state(c, copy, runtime, reviewed, relation)
        staging = runtime.query(copy.STAGING_SQL, {'relation': relation})
        step = copy.next_step(state, frozen, staging)
    report['copy_next_step'] = step
    if step == 'done':
        report.update(result='copy_verified_ready_for_swap',
                      next_admissible_mode={'mode': 'swap-' + relation.replace('_', '-'), 'implemented': True})
    elif step == 'chunk':
        report.update(result='copy_in_progress',
                      next_admissible_mode={'mode': 'copy-' + relation.replace('_', '-'), 'implemented': True})
    elif step.startswith('refuse:'):
        raise ValueError(step.removeprefix('refuse:'))
    else:
        report.update(result='copy_phase_pending_' + step,
                      next_admissible_mode={'mode': 'copy-' + relation.replace('_', '-'), 'implemented': True})


def _chunks(c, copy, runtime, report, ids, identity, entries, relation, state, frozen, staging, *,
            controller_alive, stop, max_wal_size, budget_seconds, clock=time.monotonic):
    settings = copy.phase_settings('chunk')
    _bucket(report, 'phase_timeouts', {})['chunk'] = settings
    report['copy_phase'] = 'chunk'
    reservation = copy.DEFAULT_CHUNK_RESERVATION_BYTES
    params = {'purge_id': ids[0], 'relation': relation, 'max_rows': str(copy.CHUNK_ROWS)}
    started = clock()
    copied = 0
    chunks = 0
    total = state.get('rows_total') or 0
    report.update(rows_affected_this_run=0, rows_affected_cumulative=total,
                  rows_remaining={relation: frozen - total})
    previous_bytes = staging.get('staging_bytes')
    previous_lsn = staging.get('wal_lsn')
    outcome = 'copy_in_progress'
    with phase_backend(c, runtime, settings['statement_timeout_ms'], on_wait=controller_alive) as backend:
        while True:
            if stop.is_set():
                outcome = 'copy_stop_requested'
                break
            if clock() - started >= budget_seconds:
                outcome = 'copy_wall_clock_budget_exhausted'
                break
            controller_alive()
            # Gate 2 before EVERY chunk, then the WAL/archiver throttle.
            _measure(c, copy, runtime, identity, report, copy.chunk_gate_required(reservation))
            _wait(c, copy, runtime, identity, report, controller_alive=controller_alive, stop=stop,
                  max_wal_size=max_wal_size, lag_segments=copy.ARCHIVE_LAG_CHUNK_SEGMENTS)
            if chunks % 50 == 0:
                c.require_reviewed_migration_ledger(runtime, entries)
            if stop.is_set() or clock() - started >= budget_seconds:
                continue
            chunk_started = clock()
            try:
                result = backend.query(copy.CHUNK_SQL, params, write=True)
            except PhaseBackendError as exc:
                kind = copy.classify_sqlstate(exc.sqlstate)
                _bucket(report, 'copy_phase_failures', []).append({
                    'phase': 'chunk', 'sqlstate': exc.sqlstate, 'classification': kind, 'chunk_index': chunks + 1})
                if kind == 'integrity':
                    _record_failure(c, copy, runtime, report, ids, relation,
                                    copy.failure_evidence('copy_chunk_integrity_failed', 'chunk', exc.sqlstate,
                                                          {'chunk_index': chunks + 1, 'rows_total': total,
                                                           'controller': report['runner_state']}))
                    raise ValueError('copy_chunk_integrity_failed') from None
                raise ValueError('copy_chunk_interrupted') from None
            report['copy_chunk_statement_seconds'] = round(
                (report.get('copy_chunk_statement_seconds') or 0) + (clock() - chunk_started), 6)
            rows = result.get('rows')
            if type(rows) is not int or not 0 <= rows <= copy.CHUNK_ROWS:
                raise ValueError('copy_chunk_result_invalid')
            if rows == 0:
                outcome = 'copy_rows_complete'
                break
            chunks += 1
            copied += rows
            total += rows
            if total > frozen:
                raise ValueError('copy_exceeds_frozen_survivors')
            growth = 0
            if type(result.get('staging_bytes')) is int and type(previous_bytes) is int:
                growth += max(0, result['staging_bytes'] - previous_bytes)
            if isinstance(result.get('wal_lsn'), str) and isinstance(previous_lsn, str):
                delta = runtime.query(copy.WAL_DELTA_SQL, {'before_lsn': previous_lsn, 'after_lsn': result['wal_lsn']}).get('bytes')
                if type(delta) is int and delta >= 0:
                    growth += delta
                    wal_bytes = _bucket(report, 'wal_phase_bytes', {})
                    wal_bytes['chunk'] = (wal_bytes.get('chunk') or 0) + delta
            previous_bytes, previous_lsn = result.get('staging_bytes'), result.get('wal_lsn')
            reservation = max(reservation, growth)
            report.update(rows_affected_this_run=copied, rows_affected_cumulative=total,
                          rows_remaining={relation: frozen - total},
                          copy_chunk_reservation={'bytes': reservation, 'last_chunk_growth_bytes': growth,
                                                  'chunks_this_run': chunks, 'elapsed_seconds': round(clock() - started, 1)})
    report['copy_chunk_outcome'] = outcome
    if outcome == 'copy_stop_requested':
        raise ValueError('copy_stop_requested')


def _swap(c, copy, runtime, report, ids, identity, relation, state, *, controller_alive, stop, max_wal_size):
    if state is None or state['failed'] or state['copy_position'] not in ('staged', 'swapped'):
        raise ValueError('verified_staging_copy_required_for_swap')
    params = {'purge_id': ids[0], 'relation': relation}
    _bucket(report, 'phase_timeouts', {})['swap'] = copy.phase_settings('swap')
    if state['copy_position'] == 'staged':
        if state.get('phase') != 'VERIFIED':
            raise ValueError('verified_staging_copy_required_for_swap')
        _wait(c, copy, runtime, identity, report, controller_alive=controller_alive, stop=stop,
              max_wal_size=max_wal_size, lag_segments=copy.ARCHIVE_LAG_PHASE_SEGMENTS)
        _measure(c, copy, runtime, identity, report, copy.FLOOR_BYTES)
        result = _retrying(c, copy, runtime, report, phase='swap', sql=copy.SWAP_SQL, params=params)
        if type(result.get('event')) is not int:
            raise ValueError('swap_outcome_unknown')
        _bucket(report, 'copy_steps', []).append({'phase': 'swap', 'result': result})
        report['swapped_at'] = datetime.now(timezone.utc).isoformat()
    elif state.get('fk_validated') is None:
        report['swap_resumed'] = True
    else:
        report['swap_resumed'] = True
        report['result'] = 'swap_already_verified'
    fresh = _state(c, copy, runtime, {'plan_sha256': report['reviewed_plan_sha256']}, relation)[1]
    if fresh is None or fresh['copy_position'] != 'swapped':
        raise ValueError('swap_position_unverified')
    if fresh.get('fk_validated') is None:
        required = copy.long_phase_required('validate_fks', max_wal_size_bytes=max_wal_size)
        _long_phase(c, copy, runtime, report, phase='validate_fks', sql=copy.VALIDATE_FKS_SQL, params=params,
                    relation=relation, ids=ids, identity=identity, controller_alive=controller_alive, stop=stop,
                    required_bytes=required, max_wal_size=max_wal_size)
    report['finder_smoke'] = copy.finder_smoke()
    if relation == 'economy_opportunity':
        _recalibrate(c, copy, runtime, report, ids, identity, relation, controller_alive=controller_alive, stop=stop,
                     max_wal_size=max_wal_size)
    if report.get('result') is None:
        report['result'] = 'swap_verified'
    report['next_admissible_mode'] = {'mode': 'drop-' + relation.replace('_', '-'), 'implemented': True}


def _recalibrate(c, copy, runtime, report, ids, identity, relation, *, controller_alive, stop, max_wal_size):
    """F7: n_distinct for economy_opportunity.system_id64 from fresh counts, then
    ANALYZE and the chunk-read plan proof. Before/after travel in the receipt."""
    before = runtime.query(copy.RECALIBRATE_STATS_SQL)
    counts = _long_phase(c, copy, runtime, report, phase='recalibrate_count', sql=copy.RECALIBRATE_COUNT_SQL,
                         params=None, relation=relation, ids=ids, identity=identity, controller_alive=controller_alive,
                         stop=stop, required_bytes=copy.long_phase_required('recalibrate_count', max_wal_size_bytes=max_wal_size),
                         max_wal_size=max_wal_size, write=False)
    fraction = copy.n_distinct_fraction(counts.get('rows'), counts.get('distinct_systems'))
    wanted = copy.n_distinct_option(fraction)
    # Idempotent: a re-dispatched swap-R measures the same table and finds the
    # option already set; only ANALYZE and the plan proof run again.
    already = copy.attoptions_list(before.get('attoptions')) == [wanted]
    record = {'purge_ids': ids, 'relation': relation, 'column': 'system_id64',
              'live_attoptions_before': before.get('attoptions'),
              'retired_attoptions': before.get('retired_attoptions'),
              'n_distinct_target': -fraction, 'already_set': already,
              'recorded_at': datetime.now(timezone.utc).isoformat()}
    if not already:
        # The restore value survives in root-owned host state before the ALTER
        # (019's append-only ledger has no event for a statistics option), and
        # swap-back-R restores the retired table's option in its own transaction.
        c._load('v3_purge_delete').save_host_state(record, path=STATISTICS_STATE_FILE)
        # Owner session DDL (the application role owns the table; the executor
        # does not): the one planner-statistics write of the route.
        altered = runtime.query(copy.recalibrate_alter_sql(fraction), write=True)
    else:
        altered = {'n_distinct': -fraction, 'already_set': True}
    # PR #894 review 4383773090: ANALYZE is a long phase (its statement timeout
    # is the 7,200 s envelope), so it runs on the persistent long-phase backend
    # under the watchdog, not through the 2,760 s one-shot transport.
    analyzed = _long_phase(c, copy, runtime, report, phase='recalibrate_analyze', sql=copy.RECALIBRATE_ANALYZE_SQL,
                           params=None, relation=relation, ids=ids, identity=identity,
                           controller_alive=controller_alive, stop=stop,
                           required_bytes=copy.long_phase_required('recalibrate_analyze', max_wal_size_bytes=max_wal_size),
                           max_wal_size=max_wal_size)
    after = runtime.query(copy.RECALIBRATE_STATS_SQL)
    plan = runtime.query(copy.CHUNK_READ_PLAN_SQL)
    plan_ok = copy.chunk_read_plan_ok(plan)
    report['n_distinct_recalibration'] = {'before': before, 'counts': counts, 'n_distinct': -fraction,
                                          'altered': altered, 'analyzed': analyzed, 'after': after,
                                          'host_state': record if not already else None,
                                          'chunk_read_plan_nested_loop_on_pkey': plan_ok, 'chunk_read_plan': plan}
    if copy.attoptions_list(after.get('attoptions')) != [wanted]:
        raise ValueError('n_distinct_recalibration_not_applied')
    if analyzed.get('analyzed') is not True or not plan_ok:
        raise ValueError('n_distinct_recalibration_plan_unverified')


def _swap_back(c, copy, runtime, report, ids, identity, relation, state, *, controller_alive, stop, max_wal_size):
    """Undo a swap. Resumable: a committed swap-back whose FK validation was
    interrupted (staged, SWAPPED_BACK, child FKs NOT VALID) skips the physical
    swap-back and finishes validation and the smoke."""
    resumed = (state is not None and state['copy_position'] == 'staged'
               and state.get('phase') == 'SWAPPED_BACK')
    if state is None or not (resumed or state['copy_position'] == 'swapped'):
        raise ValueError('swapped_relation_required_for_swap_back')
    params = {'purge_id': ids[0], 'relation': relation}
    _bucket(report, 'phase_timeouts', {})['swap_back'] = copy.phase_settings('swap_back')
    if resumed:
        report['swap_back_resumed'] = True
    else:
        _measure(c, copy, runtime, identity, report, copy.FLOOR_BYTES)
        sql = copy.SWAP_BACK_SQL
        if relation == 'economy_opportunity':
            # 019's swap-back compares attribute options exactly with the
            # retired table; the forward swap recalibrated n_distinct on the
            # copy. Restore the retired value in the swap-back's own
            # transaction (owner DDL, then the executor call): both commit or
            # neither does.
            report['n_distinct_restore'] = {'before': runtime.query(copy.RECALIBRATE_STATS_SQL)}
            sql = copy.SWAP_BACK_OPPORTUNITY_SQL
        result = _retrying(c, copy, runtime, report, phase='swap_back', sql=sql, params=params)
        if type(result.get('event')) is not int:
            raise ValueError('swap_back_outcome_unknown')
        _bucket(report, 'copy_steps', []).append({'phase': 'swap_back', 'result': result})
        if relation == 'economy_opportunity':
            report['n_distinct_restore']['after'] = runtime.query(copy.RECALIBRATE_STATS_SQL)
    fresh = _state(c, copy, runtime, {'plan_sha256': report['reviewed_plan_sha256']}, relation)[1]
    if fresh is None or fresh['copy_position'] != 'staged' or fresh.get('phase') != 'SWAPPED_BACK':
        raise ValueError('swap_back_position_unverified')
    if fresh.get('fk_validated') is None:
        required = copy.long_phase_required('validate_fks', max_wal_size_bytes=max_wal_size)
        _long_phase(c, copy, runtime, report, phase='validate_fks', sql=copy.VALIDATE_FKS_SQL, params=params,
                    relation=relation, ids=ids, identity=identity, controller_alive=controller_alive, stop=stop,
                    required_bytes=required, max_wal_size=max_wal_size)
        result_code = 'swapped_back_live_restored'
    else:
        result_code = 'swap_back_already_verified'
    report['finder_smoke'] = copy.finder_smoke()
    report.update(result=result_code,
                  next_admissible_mode={'mode': 'status', 'reason': 'owner_chooses_copy_reverify_or_abandon'})


def _drop(c, copy, runtime, report, ids, identity, relation, state, *, controller_alive, stop, max_wal_size):
    order = list(copy.ORDER)
    following = order[order.index(relation) + 1:]
    next_mode = ({'mode': 'copy-' + following[0].replace('_', '-'), 'implemented': True}
                 if following else {'mode': 'complete', 'implemented': True})
    if state is not None and state['copy_position'] == 'dropped':
        # A drop whose response was lost has committed: report, change nothing.
        report.update(result='retired_relation_already_dropped', next_admissible_mode=next_mode)
        return
    if (state is None or state['failed'] or state['copy_position'] != 'swapped' or state.get('phase') != 'SWAPPED'
            or state.get('verified') is None or state.get('fk_validated') is None):
        raise ValueError('drop_requires_verified_swapped_and_fk_validated')
    _bucket(report, 'phase_timeouts', {})['drop'] = copy.phase_settings('drop')
    if relation == 'economy_opportunity':
        # PR #894 review 4382332411: swap-R may have been interrupted after FK
        # validation but before the n_distinct recalibration and its chunk-read
        # plan proof finished, and the ledger has no event for them. Re-run the
        # idempotent recalibration (fresh counts; the option is only altered if
        # it differs; ANALYZE and the plan proof always run) so the retired
        # table, the only undo, is never dropped behind unverified statistics.
        try:
            _recalibrate(c, copy, runtime, report, ids, identity, relation, controller_alive=controller_alive,
                         stop=stop, max_wal_size=max_wal_size)
        except ValueError:
            report['next_admissible_mode'] = {'mode': 'swap-economy-opportunity', 'implemented': True,
                                              'reason': 'statistics_recalibration_unverified'}
            raise
        report['drop_statistics_reverified'] = True
    # The owner's acceptance condition: the Finder answers before the retired
    # table (the only undo) is dropped.
    report['finder_smoke'] = copy.finder_smoke()
    _measure(c, copy, runtime, identity, report, copy.FLOOR_BYTES)
    before = runtime.query(copy.WAL_LAG_SQL)['wal_lsn']
    result = _retrying(c, copy, runtime, report, phase='drop', sql=copy.DROP_SQL,
                       params={'purge_id': ids[0], 'relation': relation})
    if type(result.get('event')) is not int:
        raise ValueError('drop_outcome_unknown')
    after = runtime.query(copy.WAL_LAG_SQL)['wal_lsn']
    delta = runtime.query(copy.WAL_DELTA_SQL, {'before_lsn': before, 'after_lsn': after}).get('bytes')
    _bucket(report, 'wal_phase_bytes', {})['drop'] = delta if type(delta) is int else None
    _bucket(report, 'copy_steps', []).append({'phase': 'drop', 'result': result})
    report['filesystem_reclamation_performed'] = True
    delete = c._load('v3_purge_delete')
    report['filesystem_after'] = delete.free_space(report['data_mount']['source'])
    report['relation_bytes_after'] = runtime.query(c.OBJECTS_SQL)
    report.update(result='retired_relation_dropped', next_admissible_mode=next_mode)


def _abandon(c, copy, runtime, report, ids, relation, state):
    if state is None or state['copy_position'] != 'staged':
        raise ValueError('only_an_unswapped_staging_copy_can_be_abandoned')
    _bucket(report, 'phase_timeouts', {})['abandon'] = copy.phase_settings('abandon')
    evidence = copy.abandon_evidence('owner_abandon', report['runner_state'].get('controller_run_id'), report['runner_state'])
    result = _retrying(c, copy, runtime, report, phase='abandon', sql=copy.ABANDON_SQL,
                       params={'purge_id': ids[0], 'relation': relation, 'evidence': c.evidence.canonical_json(evidence)})
    if type(result.get('event')) is not int:
        raise ValueError('abandon_outcome_unknown')
    _bucket(report, 'copy_steps', []).append({'phase': 'abandon', 'result': result})
    report.update(result='staging_copy_abandoned',
                  next_admissible_mode={'mode': 'copy-' + relation.replace('_', '-'), 'implemented': True})


def complete(c, copy, runtime, report, plan, verification):
    """019's COMPLETED: every relation dropped, nothing staged or retired, no
    target rows. 016's own ledger never reaches COMPLETED on this route."""
    reviewed, ids, identity, entries = _common(c, copy, 'complete', runtime, report, plan, verification, relation=None)
    _require_no_competitor(copy, runtime, report)
    status = runtime.query(copy.STATUS_SQL)
    report['copy_status'] = status
    for relation in copy.ORDER:
        state = copy.relation_state(status, reviewed['plan_sha256'], relation)
        if state is None or state['copy_position'] != 'dropped':
            raise ValueError('copy_relation_not_dropped')
    tx = c._load('v3_purge_transactions')
    tx.verify_empty(runtime.query, purge_ids=ids)
    observed = runtime.query(tx.PLAN_SQL)
    tx._targets(observed.get('targets'), failed=True)
    snapshot = observed['snapshot']
    pointers = {key: snapshot.get(key) for key in ('canonical', 'derived', 'spatial')}
    report.update(pointers_before=pointers, survivors_before=snapshot.get('survivors'), targets=observed['targets'])
    if (any(snapshot.get(k) != reviewed['snapshot'].get(k) for k in ('canonical', 'derived', 'spatial', 'retained', 'survivors'))
            or any(any(t['payload_counts'].values()) for t in observed['targets'])):
        raise ValueError('purge_completion_preconditions_failed')
    _bucket(report, 'phase_timeouts', {})['complete'] = copy.phase_settings('complete')
    c.require_reviewed_migration_ledger(runtime, entries)
    result = runtime.query(copy.COMPLETE_SQL, {'purge_id': ids[0]}, write=True)
    if type(result.get('event')) is not int:
        raise ValueError('copy_completion_outcome_unknown')
    c.survivor_gate(runtime, reviewed, report, 'published_survivors_after')
    report['copy_status'] = runtime.query(copy.STATUS_SQL)
    after = runtime.query(tx.PLAN_SQL)['snapshot']
    report.update(pointers_after={key: after.get(key) for key in ('canonical', 'derived', 'spatial')},
                  survivors_after=after.get('survivors'))
    if report['pointers_after'] != pointers or report['survivors_after'] != snapshot.get('survivors'):
        raise ValueError('purge_completion_postcondition_unknown')
    report['fk_check'] = True
    report.update(result={**result, 'copy_completed': True})
    c.finalize_wal_delta(runtime, report)
    report['status'] = 'success'
