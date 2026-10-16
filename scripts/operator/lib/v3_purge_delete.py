"""P2b2a bounded delete lifecycle; migration 016 owns every database mutation.

The synchronous launcher and its lease enclose the loop, batch monitor and
recovery. No detached writer is started. Rewrite recovery is deliberately a
separate branch for P2b2b.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
import multiprocessing
import os
from pathlib import Path
import re
import signal
import stat
import threading
import time

DEFAULT_BATCH_PEAK_BYTES = 900_000_000  # below 016's strict 1 GB bound
STATE_FILE = Path('/var/lib/ed-finder/v3-production/derived-purge-writer-state.json')
INTEGRITY_FAILURES = frozenset((
    'delete_pointer_changed', 'delete_published_survivor_count_drift',
    'delete_retained_metadata_drift', 'delete_fk_or_index_failure',
    'delete_loop_process_outcome_unknown', 'relation_or_index_evidence_invalid',
))


def delete_loop(gates, batch, remaining, failed_stop, stop_requested, *,
                budget_seconds=300, clock=time.monotonic, controller_alive=None):
    """Gate each transaction and resume only from fresh database counts."""
    started = clock()
    affected = 0
    try:
        while remaining() > 0:
            if stop_requested():
                raise ValueError('delete_stop_requested')
            if clock() - started >= budget_seconds:
                raise ValueError('delete_wall_clock_budget_exhausted')
            measured = gates()
            # gates() can take minutes (worker probe, competing-writer wait).
            # Re-check every stop condition immediately before the batch so a
            # lost controller or spent budget never starts one more delete.
            if stop_requested():
                raise ValueError('delete_stop_requested')
            if clock() - started >= budget_seconds:
                raise ValueError('delete_wall_clock_budget_exhausted')
            if controller_alive is not None:
                controller_alive()
            count = batch(measured)
            if type(count) is not int or count <= 0:
                raise ValueError('delete_batch_progress_invalid')
            affected += count
        return affected
    except Exception as exc:
        failed_stop(exc)
        raise


@contextmanager
def stop_signals(stop):
    previous = {}
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        previous[sig] = signal.signal(sig, lambda *_: stop.set())
    try:
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def controller_identity(pid, run_id):
    if (type(pid) is not int or pid <= 1 or not isinstance(run_id, str)
            or re.fullmatch('[1-9][0-9]{0,19}', run_id) is None
            or os.environ.get('GITHUB_RUN_ID') != run_id):
        raise ValueError('controller_identity_required')
    try:
        os.kill(pid, 0)
        # Include start ticks so PID reuse cannot adopt a different controller.
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        if fields[0] == 'Z':
            raise ValueError('controller_lost')
        return fields[19]
    except (OSError, IndexError):
        raise ValueError('controller_lost') from None


def running_services(runtime, authority_path):
    authority = json.loads(authority_path.read_text())
    contract = authority['application_contract']
    services = contract['services']
    containers = contract['containers']
    if (not isinstance(services, list) or not isinstance(containers, list)
            or len(services) != len(containers)
            or any(not isinstance(service, str) for service in services)
            or any(not isinstance(name, str) for name in containers)
            or len(set(services)) != len(services) or len(set(containers)) != len(containers)
            or contract.get('compose_project') != 'edfinder-v3-production'):
        raise ValueError('writer_container_authority_invalid')
    names = [name for service, name in zip(services, containers, strict=True) if service.startswith('api-')]
    if (not names or any(re.fullmatch('edfinder-v3-production-api-(blue|green)', n) is None for n in names)
            or any(name != 'edfinder-v3-production-' + service
                   for service, name in zip(services, containers, strict=True) if service.startswith('api-'))):
        raise ValueError('writer_container_authority_invalid')
    # Inspect only the authority's writers, but also refuse an unlisted API or
    # application-project container. Unrelated host containers are preserved.
    listed = runtime.docker('container', 'ls', '--format', '{{json .}}')
    observed = set()
    for row in listed.splitlines():
        try:
            value = json.loads(row)
            name, labels = value['Names'], value['Labels']
            if (not isinstance(name, str) or re.fullmatch('[a-zA-Z0-9][a-zA-Z0-9_.-]*', name) is None
                    or not isinstance(labels, str) or name in observed):
                raise ValueError()
            projects = [label.removeprefix('com.docker.compose.project=')
                        for label in labels.split(',') if label.startswith('com.docker.compose.project=')]
            if len(projects) > 1:
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise ValueError('writer_container_inventory_invalid') from None
        observed.add(name)
        if ((name.startswith('edfinder-v3-production-api-') or projects == [contract['compose_project']])
                and name not in containers):
            raise ValueError('writer_container_outside_authority')
    result = []
    for name in names:
        inspected = runtime.docker('inspect', '-f', '{{json .}}', name,
                                   allow_failure=True, return_result=True)
        if inspected.returncode:
            # The deployer removes the prior slot; bootstrap may never create
            # it. Only Docker's exact name-specific not-found exit proves that
            # absence. Daemon, permission, transport and other errors stop us.
            if (inspected.returncode == 1 and not inspected.stdout.strip()
                    and inspected.stderr.strip() == 'Error: No such object: ' + name):
                if name in observed:
                    raise ValueError('writer_container_inventory_changed')
                continue
            raise ValueError('writer_container_inspect_failed')
        try:
            value = json.loads(inspected.stdout)
            if (value['Name'] != '/' + name or type(value['State']['Running']) is not bool
                    or not isinstance(value['Id'], str) or re.fullmatch('[0-9a-f]{64}', value['Id']) is None):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise ValueError('writer_container_inspect_invalid') from None
        if (name in observed) != value['State']['Running']:
            raise ValueError('writer_container_inventory_changed')
        if value['State']['Running'] is True:
            result.append({'name': name, 'id': value['Id']})
    return result


def save_host_state(value, path=STATE_FILE):
    """Fixed root-owned recovery evidence; never contains environment values."""
    if os.geteuid() != 0:
        raise ValueError('writer_state_requires_root')
    parent = path.parent
    if parent.is_symlink() or parent.stat().st_uid != 0 or parent.stat().st_mode & 0o022:
        raise ValueError('writer_state_directory_unsafe')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
            raise ValueError('writer_state_file_unsafe')
        os.ftruncate(fd, 0)
        with os.fdopen(os.dup(fd), 'w') as stream:
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.close(fd)


def batch_bounds(reviewed, relation):
    config = reviewed.get('delete', {}).get(relation, {})
    limit = config.get('batch_limit')
    peak = config.get('batch_peak_bytes', DEFAULT_BATCH_PEAK_BYTES)
    if type(limit) is not int or not 1 <= limit <= 100000:
        raise ValueError('delete_plan_batch_limit_invalid')
    if type(peak) is not int or not 0 <= peak < 1_000_000_000:
        raise ValueError('delete_plan_batch_peak_invalid')
    return limit, peak, 'reviewed_plan' if 'batch_peak_bytes' in config else 'conservative_fixed_reservation'


def monitored_batch(batch, monitor, cancel, *, interval=0.2):
    """Join the writer before returning or raising, including on signals/errors."""
    result = []
    errors = []
    done = threading.Event()
    def write():
        try:
            result.append(batch())
        except BaseException as exc:
            errors.append(exc)
        finally:
            done.set()
    worker = threading.Thread(target=write, name='purge-batch', daemon=False)
    worker.start()
    failure = None
    try:
        while not done.wait(interval):
            try:
                monitor()
            except Exception as exc:
                if failure is None:
                    failure = exc
                try:
                    cancel()
                except Exception:
                    # Start may still be uncommitted. Retry against the exact
                    # ledgered identity until the bounded batch has exited.
                    pass
    finally:
        # Never restore a fence or leave the lease while a write is in flight.
        worker.join()
    if failure is not None:
        raise failure
    if errors:
        raise errors[0]
    return result[0]


class LoopFailure(ValueError):
    def __init__(self, code, evidence=None):
        super().__init__(code)
        self.evidence = evidence or {}


def run_loop_process(work, report, stop):
    """The launcher waits for a distinct loop PID before returning to cleanup.

    Linux fork retains the host lease descriptor throughout the child loop.
    The parent also holds it, and never unlocks it before join() completes.
    The shared event is the parent's stop-after-current-batch signal.
    """
    context = multiprocessing.get_context('fork')
    reader, sender = context.Pipe(duplex=False)
    def loop():
        reader.close()
        report.setdefault('runner_state', {})['loop_pid'] = os.getpid()
        try:
            work()
            sender.send({'report': report, 'error': None})
        except Exception as exc:
            code = str(exc)
            if re.fullmatch('[a-zA-Z0-9_]+', code) is None:
                code = 'delete_loop_failed'
            sender.send({'report': report, 'error': code, 'evidence': getattr(exc, 'evidence', None)})
        finally:
            sender.close()
    child = context.Process(target=loop, name='derived-purge-delete-loop', daemon=False)
    child.start()
    sender.close()
    report.setdefault('runner_state', {})['loop_pid'] = child.pid
    message = None
    try:
        while child.is_alive() or reader.poll():
            if reader.poll(0.2):
                message = reader.recv()
                break
    except (EOFError, OSError):
        stop.set()
    finally:
        # EXIT/INT/TERM/HUP may request a stop, but cannot skip this wait.
        child.join()
        reader.close()
    report['runner_state']['loop_exited'] = True
    if not isinstance(message, dict) or child.exitcode != 0:
        raise LoopFailure('delete_loop_process_outcome_unknown')
    report.update(message['report'])
    report['runner_state']['loop_exited'] = True
    if message['error'] is not None:
        raise LoopFailure(message['error'], message.get('evidence'))


def admission(mode, unresolved, ids, relation):
    kinds = {event['event_kind'] for event in unresolved}
    # Admission runs before this dispatch opens any fence. A prior dispatch's
    # writer fence is recovery work even if its final batch already committed.
    if mode != 'restore-services' and kinds & {'WRITER_FENCE_ENABLED', 'SERVICES_QUIESCED'}:
        raise ValueError('orphaned_writer_fence_requires_restore_services')
    for event in unresolved:
        if event['purge_id'] not in ids:
            raise ValueError('different_purge_fence_open')
        kind = event['event_kind']
        if kind == 'REWRITE_STARTED' and mode != 'restore-services':
            if not mode.startswith('rewrite-') or event['relation_code'] != relation:
                raise ValueError('different_relation_rewrite_open')
        if kind == 'SERVICES_QUIESCED':
            raise ValueError('quiesce_mode_not_authorized_option_b_only')
        if mode == 'restore-services':
            continue
        if kind == 'FAILED_STOP':
            raise ValueError('integrity_failed_stop_requires_restore_services_acknowledgement')
        if kind in ('AUTOVACUUM_DISABLED', 'BATCH_STARTED') and event['relation_code'] != relation:
            raise ValueError('different_relation_fence_open')


def dispatch(c, mode, runtime, report, plan, verification, *, wall_clock_seconds=300,
             controller_pid=None, controller_run_id=None, acknowledge_failed_stop=None,
             writer_mode='read-only'):
    """Run under the caller's host lease; restore only after every batch exits."""
    tx = c._load('v3_purge_transactions')
    if writer_mode != 'read-only':
        raise ValueError('quiesce_mode_not_authorized_option_b_only')
    if type(wall_clock_seconds) is not int or not 1 <= wall_clock_seconds <= 1800:
        raise ValueError('delete_wall_clock_budget_invalid')
    if plan is None:
        raise ValueError('authenticated_plan_required')
    reviewed = plan['reviewed_plan']
    relation = None if mode == 'restore-services' else c.RELATIONS[
        mode.removeprefix('delete-').removeprefix('abort-relation-')]
    ids = tx.get_purge_ids(runtime.query, reviewed['plan_sha256'])
    requests = tx._requests(runtime.query, ids, reviewed)
    report.update(purge_id=ids, reviewed_plan_sha256=reviewed['plan_sha256'])
    proof = c.verification_gate(verification, requests)
    if proof['status'] != 'proven':
        raise ValueError('sealed_verification_required')
    report['system_archetype_verification'] = proof
    report['relation'] = relation
    state = runtime.state(allow_unresolved=True)
    if mode != 'restore-services' and any(e['event_kind'] in ('WRITER_FENCE_ENABLED', 'SERVICES_QUIESCED')
                                        for e in state['unresolved']):
        report['next_admissible_mode'] = {'mode': 'restore-services', 'implemented': True}
    admission(mode, state['unresolved'], ids, relation)
    if mode.startswith('abort-relation-'):
        # Only a rehearsal-backed authenticated plan may supply this optional
        # budget. Current relation size is a lower bound, never a substitute.
        budget = reviewed.get('delete', {}).get(relation, {}).get('autovacuum_budget_bytes')
        if type(budget) is not int or not 0 < budget <= 2**63 - 1:
            raise ValueError('autovacuum_budget_not_measured')
    identity = runtime.query(c.IDENTITY_SQL)
    defaults = identity.get('role_defaults')
    if (not isinstance(defaults, list) or any(v not in ('default_transaction_read_only=off',
            'default_transaction_read_only=on') for v in defaults)):
        raise ValueError('writer_fence_catalog_unknown')
    if ('default_transaction_read_only=on' in defaults and not any(
            event['event_kind'] == 'WRITER_FENCE_ENABLED' for event in state['unresolved'])):
        raise ValueError('application_role_already_read_only_or_unknown')
    entries = c.validate_identity({**identity, 'role_defaults': []}, report, runtime=runtime)
    # Identity and authenticated ownership precede even recovery mutations.
    # Resolving batches uses only metadata, so an unavailable rewrite heap
    # cannot prevent safe recovery status/refusal.
    report['postmaster_started_epoch'] = identity.get('postmaster_started_epoch')
    identity['data_directory'] = runtime.data_directory()
    report['wal_before'] = c.measure_wal(runtime, identity['data_directory'])
    tx.resolve_batches(runtime.query, ids, relation)
    if mode == 'restore-services':
        restore(c, tx, runtime, report, ids, acknowledge_failed_stop, reviewed=reviewed)
        report['wal_after'] = c.measure_wal(runtime, identity['data_directory'])
        c.finalize_wal_delta(runtime, report)
        report['status'] = 'success'
        return
    objects = runtime.query(c.OBJECTS_SQL)
    if not objects or any(obj.get('valid') is not True for obj in objects):
        raise ValueError('relation_or_index_evidence_invalid')
    filesystem = runtime.storage(identity, objects)
    report['filesystem_before'] = filesystem
    report['relation_bytes_before'] = objects
    expected, installed = c.check_wrapper()
    report.update(expected_wrapper_sha256=expected, installed_wrapper_sha256=installed)
    if expected != plan.get('expected_wrapper_sha256'):
        raise ValueError('plan_backup_wrapper_hash_changed')
    if mode.startswith('abort-relation-'):
        # 016 records the budgeted abort in FAILED_STOP before restoring its
        # exact prior heap/TOAST options. No logical completion is synthesized.
        current_bytes = sum(obj['total_bytes'] for obj in objects if obj['relation'] == 'v3_derived.' + relation)
        budget = max(budget, current_bytes)
        measured = measurement(c, runtime, identity, report, report['wal_before'], 0)
        measured.update(autovacuum_budget_bytes=budget, aborted=True)
        report['abort_headroom'] = {**measured, 'required_bytes': c.FREE_FLOOR_BYTES + budget,
                                  'shortfall_bytes': max(0, c.FREE_FLOOR_BYTES + budget - measured['filesystem_free_bytes'])}
        if measured['filesystem_free_bytes'] < c.FREE_FLOOR_BYTES + budget:
            raise ValueError('abort_autovacuum_headroom_shortfall')
        report['result'] = tx.abort_relation(runtime.query, ids, relation, measured)
        # An aborted relation may still hold target rows. Guidance is based on
        # a new count after restoration, never the plan or pre-abort counts.
        report['next_admissible_mode'] = {'mode': 'status', 'reason': 'relation_counts_not_proven'}
        try:
            observed = runtime.query(c.STATUS_RELATION_SQL[relation]).get('targets')
        except RuntimeError:
            observed = None
        target_ids = [target[0] for target in c.TARGETS.values()]
        if isinstance(observed, dict):
            report['rows_remaining'] = {key: observed.get(key) for key in target_ids}
            counts = [observed.get(key) for key in target_ids]
            valid = [count for count in counts if type(count) is int and count >= 0]
            if any(valid):
                report['next_admissible_mode'] = {'mode': 'delete-' + mode.removeprefix('abort-relation-'), 'implemented': True}
            elif len(valid) == len(target_ids):
                report['next_admissible_mode'] = {'mode': 'rewrite-' + mode.removeprefix('abort-relation-'), 'implemented': True}
        c.finalize_wal_delta(runtime, report)
        report['status'] = 'success'
        return
    controller_pid = controller_pid or os.getppid()
    controller_run_id = controller_run_id or os.environ.get('GITHUB_RUN_ID')
    controller_start = controller_identity(controller_pid, controller_run_id)
    launcher_pid = os.getpid()
    launcher_start = controller_identity(launcher_pid, controller_run_id)
    limit, peak, source = batch_bounds(reviewed, relation)
    report.update(batch_limit=limit, batch_peak_bytes=peak, batch_peak_source=source,
                  wall_clock_timeout_seconds=wall_clock_seconds,
                  runner_state={'controller_pid': controller_pid, 'controller_run_id': controller_run_id,
                                'controller_start_ticks': controller_start, 'launcher_pid': launcher_pid, 'loop_pid': None})
    stop = multiprocessing.get_context('fork').Event()
    fenced = False
    def controller_alive():
        if (controller_identity(controller_pid, controller_run_id) != controller_start
                or controller_identity(launcher_pid, controller_run_id) != launcher_start):
            raise ValueError('controller_lost')
    def gates():
        controller_alive()
        if stop.is_set():
            raise ValueError('delete_stop_requested')
        if fenced and fresh_probe(runtime, c) != 'on':
            raise ValueError('writer_fence_fresh_probe_drift')
        waited = tx.wait_for_competing_writers(runtime.query)
        report['competing_writer_wait'] = waited
        c.require_reviewed_migration_ledger(runtime, entries)
        # Measurements follow the bounded writer wait: 016 requires <=30s old.
        measured = measurement(c, runtime, identity, report, report['wal_before'], peak)
        age_gate(c, tx, runtime, report, ids, relation, reviewed, sum(counts.values()), wall_clock_seconds + 65)
        measured['competing_writer_wait'] = waited
        return measured
    def boundary(*, final=False):
        observed = runtime.query(tx.PLAN_SQL)
        tx._targets(observed.get('targets'), failed=True)
        snapshot = observed['snapshot']
        pointers = {key: snapshot.get(key) for key in ('canonical', 'derived', 'spatial')}
        if report.get('pointers_before') is None:
            report.update(pointers_before=pointers, survivors_before=snapshot.get('survivors'), targets=observed['targets'])
        report.update(pointers_after=pointers, survivors_after=snapshot.get('survivors'))
        if any(snapshot.get(k) != reviewed['snapshot'].get(k) for k in ('canonical', 'derived', 'spatial')):
            raise ValueError('delete_pointer_changed')
        if snapshot.get('survivors') != reviewed['snapshot'].get('survivors'):
            raise ValueError('delete_published_survivor_count_drift')
        if snapshot.get('retained') != reviewed['snapshot'].get('retained'):
            raise ValueError('delete_retained_metadata_drift')
        if runtime.query(c.POINTER_IDENTITIES_SQL) != reviewed.get('pointer_identities'):
            raise ValueError('delete_pointer_changed')
        checks = runtime.query(tx.COMPLETION_STATE_SQL, {'plan_sha256': reviewed['plan_sha256']})
        if (not isinstance(checks, dict) or any(checks.get(k) != 0
                for k in ('invalid_foreign_keys', 'invalid_indexes', 'invalid_triggers'))):
            raise ValueError('delete_fk_or_index_failure')
        if final:
            report['fk_check'] = checks
        return observed
    # All ordinary preflight failures above and here leave new fences untouched.
    initial = boundary()
    counts = {target['id']: target['payload_counts'][relation] for target in initial['targets']}
    age_gate(c, tx, runtime, report, ids, relation, reviewed, sum(counts.values()), wall_clock_seconds + 65)
    report['rows_affected_cumulative'] = sum(target['payload_counts'][relation] for target in reviewed['targets']) - sum(counts.values())
    gates()
    def fail(exc):
        # Set local recovery evidence before any further DB/transport operation.
        # It travels back from the loop process even if FAILED_STOP cannot commit.
        report.update(failed_stop_attempted=True, failed_stop_recorded=None, integrity_failed=True)
        condition = str(exc)
        integrity = condition in INTEGRITY_FAILURES
        # A definer refusal can be the first observer of pointer/count/index
        # drift. Re-read retained-data evidence before deciding to reopen writes.
        try:
            boundary()
        except Exception as observed:
            # An unavailable integrity observation is never proof of safety.
            integrity = True
            if str(observed) in INTEGRITY_FAILURES:
                condition = str(observed)
        cause = exc
        while cause is not None:
            if str(cause) in INTEGRITY_FAILURES:
                condition = str(cause)
                integrity = True
                break
            cause = cause.__cause__
        report['integrity_failed'] = integrity
        payload = {'condition': condition if re.fullmatch('[a-zA-Z0-9_]+', condition) else 'delete_batch_failed',
                   'integrity_failed': integrity, 'filesystem_free_bytes': report.get('filesystem_after', filesystem)['free_bytes'],
                   'wal_bytes': (report.get('wal_after') or {}).get('bytes'),
                   'measurements': report.get('last_batch_measurement'),
                   'wal_health': report.get('wal_after'), 'workers': report.get('workers'),
                   'autovacuum_ages': report.get('autovacuum_ages'), 'controller': report.get('runner_state'),
                   'competing_writer_wait': report.get('competing_writer_wait')}
        try:
            recorded = tx.record_failed_stop(runtime.query, ids, payload, relation)
            if not recorded:
                raise ValueError('purge_failed_stop_outcome_unknown')
        except Exception:
            # Even a non-integrity stop has an unknown durable outcome here.
            report['integrity_failed'] = True
            raise
        report['failed_stop_recorded'] = recorded
    def remaining():
        # Seeded from this dispatch's exact database counts. Every decrement is
        # a committed016 result; the final boundary re-counts exactly. Avoid
        # another galaxy scan between fresh evidence and the <=30s admission.
        report['rows_remaining'] = dict(counts)
        return sum(counts.values())
    def batch(measured):
        generation = next(g for g, count in counts.items() if count > 0)
        requests_by_generation = {r['derived_generation_id']: r['purge_id'] for r in requests}
        purge_id = requests_by_generation[generation]
        def monitor():
            disk = free_space(report['data_mount']['source'])
            report['filesystem_after'] = disk
            if disk['free_bytes'] < c.FREE_FLOOR_BYTES:
                raise ValueError('filesystem_free_space_floor_mid_batch')
        def cancel():
            tx.cancel_batch(runtime.query, purge_id, relation, 'free_space_floor')
        result = monitored_batch(lambda: tx.payload_batch(runtime.query, purge_id, relation, limit, measured), monitor, cancel)
        counts[generation] -= result['rows_affected']
        report['rows_affected_cumulative'] += result['rows_affected']
        if counts[generation] < 0:
            raise ValueError('delete_batch_count_drift')
        report['rows_affected_this_run'] = (report.get('rows_affected_this_run') or 0) + result['rows_affected']
        return result['rows_affected']
    # Option (b) keeps the API serving reads. Its exact running writer set is
    # durable host evidence; no false SERVICES_QUIESCED event is inserted.
    containers = running_services(runtime, c.ROOT / 'deploy/v3-production/target-authority.json')
    save_host_state({'purge_ids': ids, 'containers': containers, 'writer_mode': 'read-only',
                     'recorded_at': datetime.now(timezone.utc).isoformat()})
    with stop_signals(stop):
        try:
            # Docker/host evidence can take time. Recheck the full remaining
            # horizon immediately before opening or adopting the durable fence.
            age_gate(c, tx, runtime, report, ids, relation, reviewed, sum(counts.values()), wall_clock_seconds + 65)
            report['autovacuum'] = tx.autovacuum_fence(runtime.query, ids, relation)
            report['writer_fence'] = {**(report.get('writer_fence') or {}),
                **tx.writer_fence(runtime.query, ids[0], True, lambda: fresh_probe(runtime, c), purge_ids=ids)}
            fenced = True
            def work():
                report['rows_affected_this_run'] = delete_loop(gates, batch, remaining, fail, stop.is_set,
                                                            budget_seconds=wall_clock_seconds,
                                                            controller_alive=controller_alive)
                boundary(final=True)
                fresh_objects = runtime.query(c.OBJECTS_SQL)
                if (not isinstance(fresh_objects, list) or not fresh_objects
                        or any(obj.get('valid') is not True or type(obj.get('total_bytes')) is not int
                               or obj['total_bytes'] < 0 for obj in fresh_objects)):
                    raise ValueError('relation_or_index_evidence_invalid')
                report['relation_bytes_after'] = fresh_objects
                measured = gates()
                sealed = {**measured, 'receipt_sha256': c.evidence.canonical_sha256(measured)}
                tx.complete_relation(runtime.query, ids, relation, sealed)
                report['next_admissible_mode'] = {'mode': 'rewrite-' + mode.removeprefix('delete-'), 'implemented': True}
            run_loop_process(work, report, stop)
        except Exception as exc:
            if not report.get('failed_stop_attempted'):
                fail(exc)
            raise
        finally:
            # payload_batch's non-daemon thread has already been joined by the
            # monitor. Recovery checks the recorded backend as a second guard.
            stop.set()
            runtime.deadline = max(runtime.deadline, time.monotonic() + 120)
            tx.resolve_batches(runtime.query, ids, relation)
            restore(c, tx, runtime, report, ids, None, automatic=True, reviewed=reviewed)
            backup_skips(runtime, report)
    report['result'] = 'relation_logically_empty_waiting_for_rewrite'
    c.finalize_wal_delta(runtime, report)
    report['status'] = 'success'


def free_space(path):
    disk = os.statvfs(path)
    return {'total_bytes': disk.f_blocks * disk.f_frsize,
            'used_bytes': (disk.f_blocks - disk.f_bfree) * disk.f_frsize,
            'free_bytes': disk.f_bavail * disk.f_frsize}


def fresh_probe(runtime, c):
    # A new login as the actual application role, without SET ROLE or SET GUC.
    sql = "BEGIN READ ONLY; SELECT jsonb_build_object('observed',current_setting('default_transaction_read_only')); COMMIT;"
    return runtime.query(sql)['observed']


def measurement(c, runtime, identity, report, before, peak):
    # The authoritative worker inventory can take longer than these small
    # catalog/filesystem probes. Keep space and WAL observations after it.
    if runtime.workers() is not True:
        raise ValueError('named_workers_not_stopped')
    filesystem = free_space(report['data_mount']['source'])
    report['filesystem_after'] = filesystem
    wal = c.measure_wal(runtime, identity['data_directory'])
    report['wal_after'] = wal
    c.wal_health(before, wal)
    if runtime.device(identity['data_directory'] + '/pg_wal') != report['data_mount']['device']:
        raise ValueError('tablespace_or_wal_filesystem_mismatch')
    if filesystem['free_bytes'] < c.FREE_FLOOR_BYTES + (3 * peak + 1) // 2:
        raise ValueError('filesystem_free_space_floor')
    # Closed relation enum; this catalog-only probe never scans a payload heap.
    observed = runtime.query(c.read_sql("SELECT jsonb_build_object('active',count(*)) FROM pg_stat_progress_vacuum WHERE relid IN "
        "(SELECT oid FROM pg_class WHERE oid IN ('v3_derived.system_search'::regclass,'v3_derived.economy_opportunity'::regclass,"
        "'v3_derived.body_mechanics'::regclass,'v3_derived.system_rating_vector'::regclass) OR oid IN "
        "(SELECT reltoastrelid FROM pg_class WHERE oid IN ('v3_derived.system_search'::regclass,'v3_derived.economy_opportunity'::regclass,"
        "'v3_derived.body_mechanics'::regclass,'v3_derived.system_rating_vector'::regclass)))"))
    if observed.get('active') != 0:
        raise ValueError('autovacuum_running_on_payload')
    measured = {'filesystem_free_bytes': filesystem['free_bytes'], 'batch_peak_bytes': peak,
                'wal_bytes': wal['bytes'], 'wal_healthy': True, 'wal_same_filesystem': True,
                'workers_stopped': True, 'observed_at': datetime.now(timezone.utc).isoformat()}
    report['last_batch_measurement'] = measured
    return measured


def backup_skips(runtime, report):
    try:
        journal = runtime.run(['journalctl', '--no-pager', '--output=json',
            '--since=' + report['created_at'], '--lines=1000',
            '--unit=edfinder-v3-pgbackrest@full.service', '--unit=edfinder-v3-pgbackrest@diff.service',
            '--unit=edfinder-v3-pgbackrest@verify.service'])
        records = [json.loads(line) for line in journal.splitlines() if line]
        report['skipped_scheduled_backups'] = {'window': 'dispatch_up_to_1000_entries', 'records': [
            {'message': item['MESSAGE'], 'timestamp': item.get('__REALTIME_TIMESTAMP'),
             'unit': item.get('_SYSTEMD_UNIT')} for item in records
            if isinstance(item.get('MESSAGE'), str) and item['MESSAGE'].startswith('SKIP:')]}
    except (ValueError, RuntimeError, OSError, AttributeError, KeyError):
        report['skipped_scheduled_backups'] = None


def age_gate(c, tx, runtime, report, ids, relation, reviewed, remaining_rows, dispatch_seconds):
    """Reserve the remaining delete cadence AND the reviewed rewrite time.

    Counts start at this dispatch's exact DB boundary and decrease only after
    committed batches. The original fence's rates/ceilings still govern resume.
    """
    mode_relation = next(key for key, code in c.RELATIONS.items() if code == relation)
    def refuse(code):
        report['next_admissible_mode'] = {
            'mode': ('rewrite-' if remaining_rows == 0 else 'abort-relation-') + mode_relation,
            'implemented': True,
        }
        raise ValueError(code)
    config = reviewed.get('delete', {}).get(relation, {})
    rate = config.get('rows_per_second')
    rewrite = config.get('rewrite_allowance_seconds')
    if any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0
           for value in (rate, rewrite)):
        refuse('autovacuum_fence_horizon_not_reviewed')
    delete_seconds = remaining_rows / rate
    required_seconds = max(dispatch_seconds, delete_seconds + rewrite)
    if not math.isfinite(required_seconds):
        refuse('autovacuum_fence_horizon_not_reviewed')
    horizon = {'remaining_target_rows': remaining_rows, 'rows_per_second': rate,
               'rows_per_second_source': config.get('rows_per_second_source'),
               'delete_seconds': delete_seconds, 'rewrite_allowance_seconds': rewrite,
               'required_seconds': required_seconds, 'projections': []}
    report['autovacuum_fence_horizon'] = horizon
    metadata = tx.metadata_state(runtime.query, ids)
    opened = [event for event in metadata['autovacuum_fences'] if event['relation_code'] == relation]
    options = opened[-1]['operational_payload'] if opened else None
    observed = c.age_sample(runtime)
    report['autovacuum_ages'] = observed
    scopes = [obj for obj in observed['objects'] if obj['relation_code'] == relation]
    if not scopes or not any(obj['scope'] == 'heap' for obj in scopes):
        raise ValueError('autovacuum_age_observation_invalid')
    for obj in scopes:
        config = options.get(obj['scope'], {}) if options is not None else reviewed.get('autovacuum', {}).get(relation, {})
        for kind in ('xid', 'mxid'):
            ceiling, rate = config.get(kind + '_ceiling'), config.get(kind + '_rate')
            if (type(ceiling) is not int or type(rate) not in (int, float)
                    or not math.isfinite(rate) or rate < 0):
                refuse('autovacuum_fence_deadline_unsafe')
            ceiling = min(ceiling, obj[kind + '_limit'])
            margin = ceiling - obj[kind + '_age']
            projected = margin / rate if rate else None
            horizon['projections'].append({'scope': obj['scope'], 'kind': kind,
                                           'age': obj[kind + '_age'], 'ceiling': ceiling,
                                           'rate': rate, 'seconds_to_ceiling': projected})
            if margin <= 0 or (projected is not None and projected < required_seconds):
                refuse('autovacuum_fence_deadline_unsafe')


def restore(c, tx, runtime, report, ids, acknowledgement, *, automatic=False, reviewed=None):
    # The ledger alone cannot reveal a FAILED_STOP whose commit/transport failed.
    # Apply the same fail-closed rule for ordinary cleanup and signal cleanup.
    if automatic and (report.get('integrity_failed') is True or (
            report.get('failed_stop_attempted') and not report.get('failed_stop_recorded'))):
        report['integrity_failed'] = True
        report['writer_restore'] = 'refused_integrity_failed_stop'
        return
    state = runtime.state(allow_unresolved=True)
    if any(e['event_kind'] == 'REWRITE_STARTED' for e in state['unresolved']):
        c._load('v3_purge_rewrite_dispatch').resolve(c, tx, runtime, report, ids, reviewed, cancel=True)
        state = runtime.state(allow_unresolved=True)
    failures = [e for e in state['unresolved'] if e['event_kind'] == 'FAILED_STOP']
    if failures:
        if automatic:
            report['writer_restore'] = 'refused_integrity_failed_stop'
            return
        sequences = {e['event_sequence'] for e in failures}
        if acknowledgement not in sequences or len(sequences) != 1:
            raise ValueError('integrity_failed_stop_acknowledgement_required')
    if acknowledgement is not None:
        tx.acknowledge_failure(runtime.query, ids, acknowledgement)
    # Resolve before even sampling the restore's LSN, with exact PID+start guard.
    tx.resolve_batches(runtime.query, ids)
    if report.get('wal_before') is None:
        report['wal_before'] = runtime.query(c.WAL_SQL)
    restored = {}
    for purge_id in ids:
        restored.update(tx.writer_fence(runtime.query, purge_id, False,
                                        lambda: fresh_probe(runtime, c), purge_ids=ids,
                                        **({'acknowledge_failed_stop': acknowledgement} if acknowledgement is not None else {})))
    report['writer_fence'] = {**(report.get('writer_fence') or {}), **restored, 'enabled': False, 'verified': True}
    report['writer_restore'] = {'verified': True, 'acknowledge_failed_stop': acknowledgement}
    report['result'] = 'writer_fence_restored'
