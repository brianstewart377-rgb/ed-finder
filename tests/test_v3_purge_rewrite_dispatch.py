"""Rewrite-controller contracts against an isolated host and ledger model."""
from contextlib import contextmanager
from copy import deepcopy
import os
import signal
from types import SimpleNamespace

import pytest

from tests.test_v3_purge_delete_dispatch import DispatchModel, load


class RewriteModel(DispatchModel):
    def __init__(self, monkeypatch):
        super().__init__(monkeypatch)
        self.r = load('v3_purge_rewrite')
        self.dispatcher = load('v3_purge_rewrite_dispatch')
        self.counts = dict.fromkeys(self.ids, 0)
        self.open_rewrite = False
        self.recovery = 'committed'
        self.backend_error = None
        self.verification_error = None
        self.reviewed['targets'] = self.targets()
        self.reviewed['rewrite'] = {'system_search': {
            'rewrite_peak_bytes': 1_000_000_000, 'statement_timeout_ms': 600_000,
        }}
        self.tx.phase_state = lambda *_: {
            'target_counts': deepcopy(self.counts), 'open_batches': [],
        }
        self.tx.verify_empty = lambda *_args, **_kwargs: self.log.append('exclusions-verified')
        self.tx.metadata_state = self.metadata
        self.runtime.rewrite_backend = self.backend
        self.runtime.query = self.query
        self.tx.record_failed_stop = self.failed_stop
        self.monitor = SimpleNamespace(start=self.start_monitor)
        original_load = self.c._load
        modules = {'v3_purge_transactions': self.tx, 'v3_purge_rewrite': self.r,
                   'v3_purge_delete': self.d, 'v3_purge_rewrite_dispatch': self.dispatcher,
                   'v3_purge_rewrite_monitor': self.monitor}
        monkeypatch.setattr(self.c, '_load', lambda name: modules.get(name) or original_load(name))
        monkeypatch.setattr(self.r, 'start_rewrite', self.start)
        monkeypatch.setattr(self.r, 'verify_rewrite', self.verify)
        monkeypatch.setattr(self.r, 'resolve_rewrites', self.resolve_rewrite)

    def metadata(self, *_):
        return {**super().metadata(), 'open_rewrites': ([self.event()] if self.open_rewrite else []),
                'writer_fence': ({'event_kind': 'WRITER_FENCE_ENABLED', 'purge_id': self.ids[0],
                                  'operational_payload': {'verified': True}} if self.writer else None)}

    def event(self):
        return {'event_kind': 'REWRITE_STARTED', 'event_sequence': 10,
                'purge_id': self.ids[0], 'relation_code': 'system_search',
                'backend_pid': 812, 'backend_start': '2026-10-16T00:00:00+00:00'}

    def state(self, **kwargs):
        observed = super().state(**kwargs)
        if self.open_rewrite:
            observed['unresolved'].append(self.event())
        return observed

    def query(self, statement, params=None, **kwargs):
        if 'ANALYZE v3_derived.system_search;' in statement:
            assert kwargs.get('write') is True
            assert "SET ROLE v3_derived_purge_executor;" in statement
            assert "SET statement_timeout='600000ms';" in statement
            self.write('recovered-ANALYZE')
            return {'analyzed': True}
        return super().query(statement, params, **kwargs)

    @contextmanager
    def backend(self, timeout, *, on_wait):
        assert timeout == 600_000
        self.log.append('backend-open')
        backend = SimpleNamespace(query=object(), command=self.command)
        self.backend_query = backend.query
        try:
            yield backend
        finally:
            self.log.append('backend-gone')

    def command(self, statement):
        assert self.open_rewrite and self.writer and self.auto == 'system_search'
        assert statement == 'VACUUM (FULL, ANALYZE) v3_derived.system_search;'
        assert self.log.index('REWRITE_STARTED-committed') < self.log.index('monitor-started')
        self.write(statement)
        if self.backend_error:
            raise ValueError(self.backend_error)

    def start(self, query, ids, relation, measured):
        assert query is self.backend_query and ids == self.ids and relation == 'system_search'
        assert self.writer and self.auto == relation and not self.open_rewrite
        assert measured['rewrite_peak_bytes'] == 1_000_000_000
        # 016 caps batch_peak_bytes at one delete batch; a rewrite has none.
        assert measured['batch_peak_bytes'] == 0
        self.write('REWRITE_STARTED-committed')
        self.open_rewrite = True
        return {'start_event': 10, 'rewrite_started_at': '2026-10-16T00:00:00+00:00',
                **self.event()}

    def start_monitor(self, c, runtime, ids, relation, start, identity, report):
        assert self.open_rewrite and start['backend_pid'] == 812
        assert ids == self.ids and relation == 'system_search'
        self.write('monitor-started')

    def verify(self, query, ids, relation, receipt):
        assert self.open_rewrite and self.writer
        assert self.log[-1] != 'backend-open' and 'backend-gone' in self.log
        assert receipt['receipt_sha256']
        if self.verification_error:
            self.failed_stop(query, ids, {'integrity_failed': True, 'rewrite_committed': True}, relation)
            raise self.r.tx.PurgeTransactionError('rewrite_verification_failed',
                                                {'integrity_failed': True, 'rewrite_committed': True})
        self.write('REWRITE_VERIFIED')
        self.open_rewrite = False
        self.auto = None
        return {'event_sequence': 11}

    def resolve_rewrite(self, query, ids, relation, *, cancel, analyze, receipt):
        assert self.open_rewrite and relation == 'system_search'
        self.log.append('rewrite-cancel-and-wait' if cancel else 'rewrite-progress-checked')
        if cancel:
            assert 'backend-open' not in self.log or 'backend-gone' in self.log
        if self.recovery == 'committed':
            analyze(self.r.analyze_command(relation))
            assert receipt()['receipt_sha256']
            self.write('REWRITE_VERIFIED-recovered')
            verified, rolled_back = [relation], []
            self.auto = None
        else:
            self.write('REWRITE_ROLLED_BACK')
            verified, rolled_back = [], [relation]
        self.open_rewrite = False
        return {'verified_relations': verified, 'rolled_back_relations': rolled_back,
                'resolved_rewrite_events': [11]}

    def run_rewrite(self, *, plan=True, proof=True):
        report = self.c.receipt('rewrite-system-search')
        self.report = report
        self.dispatcher.dispatch(self.c, 'rewrite-system-search', self.runtime, report,
                                 self.plan if plan else None, self.proof if proof else None,
                                 controller_pid=123, controller_run_id='456')
        return report


def test_rewrite_commits_start_starts_monitor_vacuums_verifies_then_restores(monkeypatch):
    model = RewriteModel(monkeypatch)
    result = model.run_rewrite()
    ordered = ['REWRITE_STARTED-committed', 'monitor-started',
               'VACUUM (FULL, ANALYZE) v3_derived.system_search;', 'backend-gone',
               'REWRITE_VERIFIED', 'writer-restored']
    assert [model.log.index(value) for value in ordered] == sorted(model.log.index(value) for value in ordered)
    assert result['status'] == 'success' and result['result'] == 'rewrite_verified'
    assert not model.writer and not model.open_rewrite and model.auto is None


@pytest.mark.parametrize(('field', 'error'), [
    ('rewrite_peak_bytes', 'rewrite_peak_not_measured'),
    ('statement_timeout_ms', 'rewrite_statement_timeout_not_measured'),
])
def test_rewrite_missing_rehearsal_measurement_refuses_before_mutation(monkeypatch, field, error):
    model = RewriteModel(monkeypatch)
    del model.reviewed['rewrite']['system_search'][field]
    with pytest.raises(ValueError, match=error):
        model.run_rewrite()
    assert model.mutations == []


@pytest.mark.parametrize(('plan', 'proof', 'error'), [
    (False, True, 'authenticated_plan_required'), (True, False, 'sealed_verification_required'),
])
def test_rewrite_requires_authenticated_plan_and_sealed_exclusion_proof(monkeypatch, plan, proof, error):
    model = RewriteModel(monkeypatch)
    with pytest.raises(ValueError, match=error):
        model.run_rewrite(plan=plan, proof=proof)
    assert model.mutations == []


def test_redispatch_after_committed_rewrite_runs_recovered_analyze_without_vacuum(monkeypatch):
    model = RewriteModel(monkeypatch)
    model.open_rewrite = True
    result = model.run_rewrite()
    assert result['result'] == 'rewrite_verified_recovered'
    assert model.mutations == ['recovered-ANALYZE', 'REWRITE_VERIFIED-recovered']
    assert 'monitor-started' not in model.log and 'backend-open' not in model.log


def test_redispatch_after_rolled_back_rewrite_opens_fresh_start_and_rewrites(monkeypatch):
    model = RewriteModel(monkeypatch)
    model.open_rewrite = True
    model.recovery = 'rolled_back'
    assert model.run_rewrite()['result'] == 'rewrite_verified'
    assert model.log.index('REWRITE_ROLLED_BACK') < model.log.index('REWRITE_STARTED-committed')
    assert model.mutations.count('VACUUM (FULL, ANALYZE) v3_derived.system_search;') == 1


def test_interrupted_rewrite_joins_backend_resolves_ledger_before_restoring_writers(monkeypatch):
    model = RewriteModel(monkeypatch)
    model.backend_error = 'controller_interrupted'
    model.recovery = 'rolled_back'
    with pytest.raises(ValueError, match='controller_interrupted'):
        model.run_rewrite()
    ordered = ['backend-gone', 'rewrite-cancel-and-wait', 'REWRITE_ROLLED_BACK', 'writer-restored']
    assert [model.log.index(value) for value in ordered] == sorted(model.log.index(value) for value in ordered)
    assert not model.open_rewrite and not model.writer


def test_integrity_failure_after_changed_filenode_leaves_writers_fenced(monkeypatch):
    model = RewriteModel(monkeypatch)
    model.verification_error = True
    with pytest.raises(ValueError, match='rewrite_verification_failed'):
        model.run_rewrite()
    assert model.report['integrity_failed'] is True
    assert model.failures[-1]['operational_payload']['rewrite_committed'] is True
    assert model.writer and 'writer-restored' not in model.log
    assert 'rewrite-cancel-and-wait' not in model.log


def test_restore_services_resolves_open_rewrite_before_restoring_writer_fence(monkeypatch):
    model = RewriteModel(monkeypatch)
    model.open_rewrite = True
    model.writer = True
    model.auto = 'system_search'
    model.recovery = 'committed'
    result = model.run('restore-services')
    assert result['status'] == 'success'
    ordered = ['rewrite-cancel-and-wait', 'recovered-ANALYZE', 'REWRITE_VERIFIED-recovered', 'writer-restored']
    assert [model.log.index(value) for value in ordered] == sorted(model.log.index(value) for value in ordered)
    assert not model.writer and not model.open_rewrite


@pytest.mark.parametrize('field', ('reviewed_plan_sha256', 'purge_id'))
def test_rewrite_refuses_proof_for_another_plan_or_purge(monkeypatch, field):
    model = RewriteModel(monkeypatch)
    model.proof[field] = 'f' * 64 if field == 'reviewed_plan_sha256' else []
    with pytest.raises(ValueError, match='verification_request_plan_mismatch'):
        model.run_rewrite()
    assert model.mutations == []


@pytest.mark.parametrize('condition', ('rows_remain', 'batch_open'))
def test_rewrite_refuses_incomplete_logical_deletion_before_fences(monkeypatch, condition):
    model = RewriteModel(monkeypatch)
    model.tx.phase_state = lambda *_: {
        'target_counts': {model.ids[0]: 1 if condition == 'rows_remain' else 0},
        'open_batches': [10] if condition == 'batch_open' else [],
    }
    with pytest.raises(ValueError, match='rewrite_relation_not_logically_empty|rewrite_open_batch'):
        model.run_rewrite()
    assert model.mutations == []


def test_monitor_start_failure_resolves_committed_start_before_restoring_writers(monkeypatch):
    model = RewriteModel(monkeypatch)
    model.recovery = 'rolled_back'
    def fail_monitor(*args):
        assert model.open_rewrite
        raise ValueError('transient_monitor_start_failed')
    model.monitor.start = fail_monitor
    with pytest.raises(ValueError, match='transient_monitor_start_failed'):
        model.run_rewrite()
    assert 'VACUUM (FULL, ANALYZE) v3_derived.system_search;' not in model.log
    assert model.log.index('backend-gone') < model.log.index('REWRITE_ROLLED_BACK') < model.log.index('writer-restored')


def test_unresolved_rewrite_recovery_failure_never_restores_writers(monkeypatch):
    model = RewriteModel(monkeypatch)
    model.backend_error = 'interrupted'
    def unresolved(*args, **kwargs):
        raise ValueError('purge_rewrite_backend_did_not_exit')
    monkeypatch.setattr(model.r, 'resolve_rewrites', unresolved)
    with pytest.raises(ValueError, match='purge_rewrite_backend_did_not_exit'):
        model.run_rewrite()
    assert model.writer and model.open_rewrite and 'writer-restored' not in model.log


@pytest.mark.parametrize('interrupt', (signal.SIGINT, signal.SIGTERM, signal.SIGHUP))
def test_signal_trap_resolves_committed_rewrite_before_restoring_writer(monkeypatch, interrupt):
    model = RewriteModel(monkeypatch)
    command = model.command
    def interrupted(statement):
        command(statement)
        os.kill(os.getpid(), interrupt)
    model.command = interrupted
    with pytest.raises(ValueError, match='controller_lost'):
        model.run_rewrite()
    ordered = ['backend-gone', 'rewrite-cancel-and-wait', 'recovered-ANALYZE',
               'REWRITE_VERIFIED-recovered', 'writer-restored']
    assert [model.log.index(value) for value in ordered] == sorted(model.log.index(value) for value in ordered)
    assert not model.open_rewrite and not model.writer


def test_partial_committed_writer_enable_is_restored_before_return(monkeypatch):
    model = RewriteModel(monkeypatch)
    ordinary = model.tx.writer_fence
    def partial_enable(query, purge_id, enabled, probe, **kwargs):
        result = ordinary(query, purge_id, enabled, probe, **kwargs)
        if enabled:
            raise ValueError('purge_writer_fence_fresh_probe_failed')
        return result
    model.tx.writer_fence = partial_enable
    with pytest.raises(ValueError, match='purge_writer_fence_fresh_probe_failed'):
        model.run_rewrite()
    assert not model.writer
    assert model.log.index('writer-enabled') < model.log.index('writer-restored')
    assert 'REWRITE_STARTED-committed' not in model.log


@pytest.mark.parametrize('recovery', ('committed', 'rolled_back'))
def test_redispatch_resolves_matching_start_with_its_verified_writer_fence(monkeypatch, recovery):
    model = RewriteModel(monkeypatch)
    model.open_rewrite = True
    model.writer = True
    model.auto = 'system_search'
    model.recovery = recovery
    result = model.run_rewrite()
    assert not model.writer and not model.open_rewrite
    assert result['writer_fence']['enabled'] is False and result['writer_fence']['verified'] is True
    if recovery == 'committed':
        assert result['result'] == 'rewrite_verified_recovered'
        assert 'backend-open' not in model.log
        assert model.log.index('REWRITE_VERIFIED-recovered') < model.log.index('writer-restored')
    else:
        assert model.log.index('REWRITE_ROLLED_BACK') < model.log.index('writer-restored')
        assert model.log.index('writer-restored') < model.log.index('REWRITE_STARTED-committed')
        assert model.log.count('VACUUM (FULL, ANALYZE) v3_derived.system_search;') == 1


def test_matching_recovery_never_adopts_unverified_writer_fence(monkeypatch):
    model = RewriteModel(monkeypatch)
    model.open_rewrite = True
    model.writer = True
    original = model.tx.metadata_state
    def unverified(*args):
        value = original(*args)
        value['writer_fence']['operational_payload']['verified'] = False
        return value
    model.tx.metadata_state = unverified
    with pytest.raises(ValueError, match='rewrite_recovery_writer_fence_unverified'):
        model.run_rewrite()
    assert model.mutations == [] and model.writer


@pytest.mark.parametrize('drift', (False, True))
def test_verified_retry_rechecks_integrity_without_opening_fences(monkeypatch, drift):
    model = RewriteModel(monkeypatch)
    original_query = model.runtime.query
    def query(statement, params=None, **kwargs):
        result = original_query(statement, params, **kwargs)
        if statement == model.tx.COMPLETION_STATE_SQL:
            result.update(rewrites=['system_search'], targets=model.targets(), snapshot=deepcopy(model.snapshot))
            if drift:
                result['snapshot']['survivors']['system_search'] += 1
        return result
    model.runtime.query = query
    if drift:
        with pytest.raises(ValueError, match='rewrite_integrity_precondition_failed'):
            model.run_rewrite()
    else:
        assert model.run_rewrite()['result'] == 'rewrite_already_verified'
    assert model.mutations == []
    assert not model.writer and model.auto is None


def test_rewrite_refuses_published_archetype_survivor_drift_before_any_fence(monkeypatch):
    model = RewriteModel(monkeypatch)
    model.archetype_rows = 6
    with pytest.raises(ValueError, match='published_archetype_survivor_count_drift'):
        model.run_rewrite()
    assert model.mutations == []


def test_rewrite_survivor_drift_after_vacuum_is_an_integrity_stop_that_keeps_writers_fenced(monkeypatch):
    model = RewriteModel(monkeypatch)
    query = model.runtime.query
    def drifted(statement, params=None, **kwargs):
        if (statement == model.c.PUBLISHED_SURVIVORS_SQL
                and 'VACUUM (FULL, ANALYZE) v3_derived.system_search;' in model.mutations):
            model.log.append('published-survivors')
            return model.survivors(drifted=True)
        return query(statement, params, **kwargs)
    model.runtime.query = drifted
    with pytest.raises(ValueError, match='published_archetype_survivor_count_drift'):
        model.run_rewrite()
    stop = model.failures[-1]['operational_payload']
    assert stop['integrity_failed'] is True and stop['rewrite_committed'] is True
    assert stop['start_event'] == 10
    assert stop['condition'] == 'published_archetype_survivor_count_drift'
    assert model.report['integrity_failed'] is True
    # 016 admits owner-acknowledged writer restoration for exactly this shape;
    # nothing verifies the rewrite or reopens writes automatically.
    assert 'REWRITE_VERIFIED' not in model.mutations
    assert model.writer and 'writer-restored' not in model.log
    assert model.open_rewrite


def test_successful_rewrite_records_both_published_survivor_proofs(monkeypatch):
    model = RewriteModel(monkeypatch)
    report = model.run_rewrite()
    assert report['published_survivors_before'] == model.reviewed['published_survivors']
    assert report['published_survivors_after'] == model.reviewed['published_survivors']
    assert (model.log.index('published-survivors') < model.log.index('REWRITE_STARTED-committed')
            and model.log.index('VACUUM (FULL, ANALYZE) v3_derived.system_search;')
            < len(model.log) - 1 - model.log[::-1].index('published-survivors')
            < model.log.index('REWRITE_VERIFIED'))
