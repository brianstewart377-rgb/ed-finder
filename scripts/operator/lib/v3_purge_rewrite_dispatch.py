"""Rewrite admission and cleanup, extending the delete controller's host gates."""
from __future__ import annotations

from datetime import datetime, timezone
import multiprocessing
import os
import time


def resolve(c, tx, runtime, report, ids, reviewed, *, relation=None, cancel=True):
    """Both trap and restore-services use the identical durable resolution."""
    rewrite = c._load('v3_purge_rewrite')
    delete = c._load('v3_purge_delete')
    events = tx.metadata_state(runtime.query, ids)['open_rewrites']
    result = {'verified_relations': [], 'rolled_back_relations': [], 'resolved_rewrite_events': []}
    for event in events:
        code = event['relation_code']
        if relation is not None and code != relation:
            raise ValueError('different_relation_rewrite_open')
        config = rewrite.rewrite_configuration(reviewed, code)
        def analyze(command):
            # The recorded backend has departed at this callback. Re-check
            # host placement and the installed wrapper before recovered ANALYZE.
            c.check_wrapper()
            identity = runtime.query(c.IDENTITY_SQL)
            identity['data_directory'] = runtime.data_directory()
            objects = runtime.query(c.OBJECTS_SQL)
            if not objects or any(obj.get('valid') is not True for obj in objects):
                raise ValueError('relation_or_index_evidence_invalid')
            runtime.storage(identity, objects)
            runtime.query(rewrite.session_setup(config['statement_timeout_ms']) + command
                          + "\nSELECT jsonb_build_object('analyzed',true);", write=True)
        def receipt():
            # Only a committed (changed-filenode) rewrite reaches this point.
            # Prove the published archetype survivors before REWRITE_VERIFIED;
            # any refusal here becomes resolve_rewrites' integrity FAILED_STOP,
            # so drift can never be verified or have its writers restored.
            c.survivor_gate(runtime, reviewed, report, 'published_survivors_after')
            identity = runtime.query(c.IDENTITY_SQL)
            identity['data_directory'] = runtime.data_directory()
            objects = runtime.query(c.OBJECTS_SQL)
            if not objects or any(obj.get('valid') is not True for obj in objects):
                raise ValueError('relation_or_index_evidence_invalid')
            runtime.storage(identity, objects)
            measured = delete.measurement(c, runtime, identity, report, report['wal_before'], 0)
            report['relation_bytes_after'] = objects
            return {**measured, 'receipt_sha256': c.evidence.canonical_sha256(measured)}
        try:
            resolved = rewrite.resolve_rewrites(runtime.query, ids, code, cancel=cancel,
                                                 analyze=analyze, receipt=receipt)
        except Exception as exc:
            evidence = getattr(exc, 'evidence', {})
            if evidence.get('integrity_failed'):
                report.update(integrity_failed=True, failure_evidence=evidence)
            raise
        for key in result:
            result[key].extend(resolved[key])
        report['rewrite_resolution'] = result
    return result


def dispatch(c, mode, runtime, report, plan, verification, *, wall_clock_seconds=300,
             controller_pid=None, controller_run_id=None, acknowledge_failed_stop=None,
             writer_mode='read-only'):
    tx = c._load('v3_purge_transactions')
    rewrite = c._load('v3_purge_rewrite')
    delete = c._load('v3_purge_delete')
    monitor = c._load('v3_purge_rewrite_monitor')
    if writer_mode != 'read-only':
        raise ValueError('quiesce_mode_not_authorized_option_b_only')
    if plan is None:
        raise ValueError('authenticated_plan_required')
    relation = c.RELATIONS[mode.removeprefix('rewrite-')]
    reviewed = plan['reviewed_plan']
    config = rewrite.rewrite_configuration(reviewed, relation)
    ids = tx.get_purge_ids(runtime.query, reviewed['plan_sha256'])
    requests = tx._requests(runtime.query, ids, reviewed)
    proof = c.verification_gate(verification, requests)
    if proof['status'] != 'proven':
        raise ValueError('sealed_verification_required')
    report.update(purge_id=ids, reviewed_plan_sha256=reviewed['plan_sha256'], relation=relation,
                  system_archetype_verification=proof,
                  statement_timeout_ms=config['statement_timeout_ms'], lock_timeout_seconds=5)
    state = runtime.state(allow_unresolved=True)
    opened = state['unresolved']
    matching = [event for event in opened if event['event_kind'] == 'REWRITE_STARTED'
                and event['purge_id'] in ids and event['relation_code'] == relation]
    # A matching re-dispatch first performs only recovery. It cannot begin a
    # fresh rewrite beside an orphaned writer fence. All other dispatches keep
    # the ordinary restore-services admission requirement.
    recovery_writer = (len(matching) == 1 and any(
        event['event_kind'] == 'WRITER_FENCE_ENABLED' for event in opened))
    admitted = ([event for event in opened if event['event_kind'] != 'WRITER_FENCE_ENABLED']
                if recovery_writer else opened)
    if recovery_writer and any(event['purge_id'] not in ids for event in opened):
        raise ValueError('different_purge_fence_open')
    delete.admission(mode, admitted, ids, relation)
    if recovery_writer and any(event['event_kind'] == 'BATCH_STARTED' for event in opened):
        raise ValueError('rewrite_open_batch')
    identity = runtime.query(c.IDENTITY_SQL)
    defaults = identity.get('role_defaults')
    allowed = ('default_transaction_read_only=off', 'default_transaction_read_only=on')
    if (not isinstance(defaults, list) or any(value not in allowed for value in defaults)
            or ('default_transaction_read_only=on' in defaults) != recovery_writer):
        raise ValueError('application_role_already_read_only_or_unknown')
    if recovery_writer:
        fence = tx.metadata_state(runtime.query, ids).get('writer_fence')
        if (not isinstance(fence, dict) or fence.get('purge_id') not in ids
                or fence.get('event_kind') != 'WRITER_FENCE_ENABLED'
                or fence.get('operational_payload', {}).get('verified') is not True
                or delete.fresh_probe(runtime, c) != 'on'):
            raise ValueError('rewrite_recovery_writer_fence_unverified')
    entries = c.validate_identity({**identity, 'role_defaults': []} if recovery_writer else identity,
                                  report, runtime=runtime)
    report['postmaster_started_epoch'] = identity.get('postmaster_started_epoch')
    identity['data_directory'] = runtime.data_directory()
    report['wal_before'] = c.measure_wal(runtime, identity['data_directory'])
    tx.resolve_batches(runtime.query, ids, relation)
    # Recovery precedes payload scans: an active rewrite may hold EXCLUSIVE.
    recovered = resolve(c, tx, runtime, report, ids, reviewed, relation=relation, cancel=False)
    if recovery_writer:
        delete.restore(c, tx, runtime, report, ids, None, reviewed=reviewed)
        identity = runtime.query(c.IDENTITY_SQL)
        restored_writer = report.get('writer_fence') or {}
        c.validate_identity(identity, report, runtime=runtime)
        report['writer_fence'] = {**(report.get('writer_fence') or {}), **restored_writer}
        identity['data_directory'] = runtime.data_directory()
    if relation in recovered['verified_relations']:
        report.update(status='success', result='rewrite_verified_recovered')
        c.finalize_wal_delta(runtime, report)
        return
    # A verified retry is a no-op, never a second rewrite or a new fence.
    completion = runtime.query(tx.COMPLETION_STATE_SQL, {'plan_sha256': reviewed['plan_sha256']})
    if relation in completion.get('rewrites', []):
        tx._targets(completion.get('targets'), failed=True)
        if (completion.get('snapshot') != reviewed['snapshot']
                or any(target['payload_counts'][relation] != 0 for target in completion['targets'])
                or any(completion.get(key) != 0 for key in
                       ('invalid_foreign_keys', 'invalid_indexes', 'invalid_triggers'))
                or runtime.query(c.POINTER_IDENTITIES_SQL) != reviewed['pointer_identities']):
            raise ValueError('rewrite_integrity_precondition_failed')
        report.update(status='success', result='rewrite_already_verified')
        c.finalize_wal_delta(runtime, report)
        return
    phase = tx.phase_state(runtime.query, ids, relation)
    if any(phase['target_counts'].values()):
        raise ValueError('rewrite_relation_not_logically_empty')
    if phase['open_batches']:
        raise ValueError('rewrite_open_batch')
    tx.verify_empty(runtime.query, purge_ids=ids)
    observed = runtime.query(tx.PLAN_SQL)
    tx._targets(observed.get('targets'), failed=True)
    if observed['snapshot'] != reviewed['snapshot'] or runtime.query(c.POINTER_IDENTITIES_SQL) != reviewed['pointer_identities']:
        raise ValueError('rewrite_integrity_precondition_failed')
    # Before any fence: the published archetype product, outside 016's
    # snapshot, still holds exactly the plan's frozen survivor rows.
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
    controller_pid = controller_pid or os.getppid()
    controller_run_id = controller_run_id or os.environ.get('GITHUB_RUN_ID')
    controller_start = delete.controller_identity(controller_pid, controller_run_id)
    launcher_start = delete.controller_identity(os.getpid(), controller_run_id)
    report['runner_state'] = {'controller_pid': controller_pid, 'controller_run_id': controller_run_id,
                              'controller_start_ticks': controller_start, 'launcher_pid': os.getpid(),
                              'launcher_start_ticks': launcher_start}
    stop = multiprocessing.get_context('fork').Event()
    def controller_alive():
        if (stop.is_set() or delete.controller_identity(controller_pid, controller_run_id) != controller_start
                or delete.controller_identity(os.getpid(), controller_run_id) != launcher_start):
            raise ValueError('controller_lost')
    def measure(peak):
        controller_alive()
        c.require_reviewed_migration_ledger(runtime, entries)
        c.check_wrapper()
        return delete.measurement(c, runtime, identity, report, report['wal_before'], peak)
    timeout_seconds = config['statement_timeout_ms'] / 1000
    # The reviewed timeout governs this dispatch; never truncate a live rewrite
    # to the delete controller's one-hour default.
    runtime.deadline = max(runtime.deadline, time.monotonic() + timeout_seconds + 300)
    delete.age_gate(c, tx, runtime, report, ids, relation, reviewed, 0, timeout_seconds + 65)
    measure(config['rewrite_peak_bytes'])
    containers = delete.running_services(runtime, c.ROOT / 'deploy/v3-production/target-authority.json')
    delete.save_host_state({'purge_ids': ids, 'containers': containers, 'writer_mode': 'read-only',
                            'recorded_at': datetime.now(timezone.utc).isoformat()})
    start = None
    verified = False
    fenced = False
    def cancel_if_stopping():
        try:
            controller_alive()
        except Exception:
            stop.set()
            if start is not None:
                try:
                    rewrite.cancel_rewrite(runtime.query, ids[0], relation, 'controller_loss')
                except Exception:
                    pass
    with delete.stop_signals(stop):
        try:
            delete.age_gate(c, tx, runtime, report, ids, relation, reviewed, 0, timeout_seconds + 65)
            report['autovacuum'] = tx.autovacuum_fence(runtime.query, ids, relation)
            # Cleanup must cover a committed enable whose recycle/probe or
            # verification subsequently fails. Restoration reads the ledger.
            fenced = True
            report['writer_fence'] = tx.writer_fence(runtime.query, ids[0], True,
                                                     lambda: delete.fresh_probe(runtime, c), purge_ids=ids)
            if delete.fresh_probe(runtime, c) != 'on':
                raise ValueError('writer_fence_fresh_probe_drift')
            waited = tx.wait_for_competing_writers(runtime.query)
            report['competing_writer_wait'] = waited
            measured = rewrite.start_evidence(measure(config['rewrite_peak_bytes']),
                                              config['rewrite_peak_bytes'], waited)
            with runtime.rewrite_backend(config['statement_timeout_ms'], on_wait=cancel_if_stopping) as backend:
                start = rewrite.start_rewrite(backend.query, ids, relation, measured)
                report['rewrite_started_at'] = start['rewrite_started_at']
                report['backend_state'] = start
                monitor.start(c, runtime, ids, relation, start, identity, report)
                # A lost controller while the monitor starts cannot start work.
                controller_alive()
                measure(config['rewrite_peak_bytes'])
                backend.command(rewrite.rewrite_command(relation))
            # The VACUUM command has returned, so its rewrite has committed.
            # Survivor drift here is an integrity stop that keeps the writer
            # fence, exactly like a failed verification of a changed filenode.
            try:
                c.survivor_gate(runtime, reviewed, report, 'published_survivors_after')
            except ValueError as exc:
                failure = {'condition': ('published_archetype_survivor_count_drift'
                                         if str(exc) == 'published_archetype_survivor_count_drift'
                                         else 'published_survivor_observation_failed'),
                           'rewrite_committed': True, 'integrity_failed': True,
                           'start_event': start['start_event'],
                           'published_survivors': report.get('published_survivors_after')}
                report.update(integrity_failed=True, failure_evidence=failure)
                tx.record_failed_stop(runtime.query, ids, failure, relation)
                raise rewrite.tx.PurgeTransactionError(failure['condition'], failure) from None
            receipt = measure(0)
            receipt['receipt_sha256'] = c.evidence.canonical_sha256(receipt)
            report['rewrite_result'] = rewrite.verify_rewrite(runtime.query, ids, relation, receipt)
            verified = True
            report['filesystem_reclamation_performed'] = True
            report['rewrite_completed_at'] = datetime.now(timezone.utc).isoformat()
            report['relation_bytes_after'] = runtime.query(c.OBJECTS_SQL)
        except Exception as exc:
            evidence = getattr(exc, 'evidence', {})
            if evidence.get('integrity_failed'):
                report.update(integrity_failed=True, failure_evidence=evidence)
            raise
        finally:
            runtime.deadline = max(runtime.deadline, time.monotonic() + 180)
            if start is not None and not verified and not report.get('integrity_failed'):
                # Context exit joins the backend before recovery; the same
                # branch serves interruption, transport failure and traps.
                resolve(c, tx, runtime, report, ids, reviewed, relation=relation, cancel=True)
            if fenced:
                delete.restore(c, tx, runtime, report, ids, None, automatic=True, reviewed=reviewed)
            delete.backup_skips(runtime, report)
    c.finalize_wal_delta(runtime, report)
    report.update(status='success', result='rewrite_verified')
