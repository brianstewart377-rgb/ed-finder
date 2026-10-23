"""Exercise complete delete/recovery dispatches against a disposable host/DB model."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import os
from pathlib import Path
import signal
from types import SimpleNamespace
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts/operator/lib' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DispatchModel:
    """Keep committed counts and open fences across independent dispatches."""

    def __init__(self, monkeypatch):
        self.c = load('v3_generation_purge')
        self.d = load('v3_purge_delete')
        real_tx = load('v3_purge_transactions')
        self.ids = [value[0] for value in self.c.TARGETS.values()]
        self.counts = dict(zip(self.ids, (3, 0), strict=True))
        self.log = []
        self.mutations = []
        self.batch_count = 0
        self.failure = None
        self.failure_after_batch = None
        self.integrity = None
        self.on_batch = None
        self.open_batch = False
        self.writer = False
        self.auto = None
        self.free = 105_000_000_000
        self.relation_bytes = 3_000_000_000
        self.failures = []
        self.snapshot = {'canonical': {'id': 'c'}, 'derived': {'id': 'd'}, 'spatial': {'id': 's'},
                         'survivors': {'system_search': 7}, 'retained': {'manifests': 3}}
        self.reviewed = {'plan_sha256': 'a' * 64, 'snapshot': deepcopy(self.snapshot),
                         'pointer_identities': {'identities': 'stable'},
                         'delete': {'system_search': {'batch_limit': 1, 'batch_peak_bytes': 10,
                                                      'rows_per_second': 1,
                                                      'rewrite_allowance_seconds': 600}}}
        self.archetype_rows = 7
        self.archetype_drift = False
        self.reviewed['published_survivors'] = self.survivors()
        self.age_config = {'xid_ceiling': 1_000_000, 'mxid_ceiling': 1_000_000,
                           'xid_rate': 0, 'mxid_rate': 0}
        self.reviewed['autovacuum'] = {'system_search': self.age_config}
        self.reviewed['targets'] = self.targets()
        self.plan = {'reviewed_plan': self.reviewed, 'expected_wrapper_sha256': 'c' * 64}
        self.proof = {'purge_id': self.ids, 'reviewed_plan_sha256': 'a' * 64,
                      'content_sha256': 'b' * 64}
        self.tx = SimpleNamespace(
            PLAN_SQL='PLAN', COMPLETION_STATE_SQL='CHECKS',
            _targets=real_tx._targets,
            get_purge_ids=lambda *_: self.ids,
            _requests=lambda *_: [{'purge_id': value, 'derived_generation_id': value,
                                  'plan_sha256': 'a' * 64} for value in self.ids],
            resolve_batches=self.resolve, autovacuum_fence=self.autovacuum,
            writer_fence=self.fence, payload_batch=self.batch,
            wait_for_competing_writers=self.wait, record_failed_stop=self.failed_stop,
            complete_relation=self.complete, abort_relation=self.abort,
            metadata_state=self.metadata,
            cancel_batch=lambda *_: self.log.append('cancel-batch'))
        original_load = self.c._load
        monkeypatch.setattr(self.c, '_load', lambda name: self.tx if name == 'v3_purge_transactions'
                            else original_load(name))
        monkeypatch.setattr(self.c, 'validate_identity', self.identity)
        monkeypatch.setattr(self.c, 'require_reviewed_migration_ledger', self.ledger)
        monkeypatch.setattr(self.c, 'check_wrapper', self.wrapper)
        monkeypatch.setattr(self.d, 'controller_identity', self.controller)
        monkeypatch.setattr(self.d, 'free_space', self.space)
        monkeypatch.setattr(self.d, 'running_services', lambda *_: [{'name': 'authorized-api', 'id': 'container-id'}])
        monkeypatch.setattr(self.d, 'save_host_state', lambda value: self.log.append('host-state'))
        # Keep this disposable in-memory DB visible to the dispatch model;
        # process joining and inherited lease descriptors have separate tests.
        monkeypatch.setattr(self.d, 'run_loop_process', lambda work, report, stop: work())
        self.runtime = SimpleNamespace(query=self.query, state=self.state, storage=lambda *_: self.space('/data'),
                                       data_directory=self.data_directory, docker=lambda *_: '10 /data/pg_wal',
                                       device=self.device, workers=self.workers, deadline=time.monotonic() + 3600)

    def trip(self, condition):
        return self.failure == condition or (self.batch_count > 0 and self.failure_after_batch == condition)

    def write(self, value):
        self.log.append(value)
        self.mutations.append(value)

    def identity(self, identity, report, **kwargs):
        if self.trip('identity'):
            raise ValueError('database_or_guard_migration_identity_mismatch')
        report['data_mount'] = {'source': '/data', 'device': 1}
        return []

    def wrapper(self):
        if self.trip('wrapper'):
            raise ValueError('installed_backup_wrapper_hash_mismatch')
        return 'c' * 64, 'c' * 64

    def controller(self, *_):
        self.log.append('controller')
        if self.trip('controller'):
            raise ValueError('controller_lost')
        return '12345'

    def ledger(self, *_):
        self.log.append('migration-ledger')
        if self.trip('ledger'):
            raise ValueError('migration_ledger_changed')

    def device(self, *_):
        self.log.append('wal-placement')
        return 2 if self.trip('placement') else 1

    def workers(self):
        self.log.append('named-workers')
        return not self.trip('workers')

    def space(self, *_):
        self.log.append('free-space')
        return {'free_bytes': 99_000_000_000 if self.trip('floor') else self.free}

    def data_directory(self):
        # The real runtime authenticates postmaster.pid against SQL identity.
        # Exercise that check so dispatch must populate the receipt first.
        runtime = SimpleNamespace(report=self.report, docker=lambda *_: '/data\n1234567890')
        return self.c.Runtime.data_directory(runtime)

    def query(self, sql, params=None, **kwargs):
        assert not kwargs.get('write'), 'all writes must use the transaction model'
        if sql == self.c.IDENTITY_SQL:
            return {'role_defaults': ['default_transaction_read_only=on'] if self.writer else [],
                    'postmaster_started_epoch': 1234567890}
        if sql == self.c.OBJECTS_SQL:
            return [{'relation': 'v3_derived.system_search', 'valid': not self.trip('index'),
                     'total_bytes': self.relation_bytes}]
        if sql == self.c.WAL_SQL:
            self.log.append('wal-health')
            return {'lsn': '0/20', 'archive_mode': 'on', 'bytes': None,
                    'archiver': {'failed_count': int(self.trip('wal')),
                                 'last_failed_time': '2026-10-15T10:00:00+00:00' if self.trip('archive-time') else None,
                                 'last_archived_time': '2026-10-15T09:00:00+00:00'},
                    'slots': [{'active': False, 'wal_status': 'extended'}] if self.trip('slot') else [],
                    'checkpoints': {}, 'temp_bytes': 0}
        if sql == self.c.WAL_LSN_DIFF_SQL:
            return {'wal_byte_delta': 0}
        if sql == self.c.AGES_SQL:
            self.log.append('age-ceilings')
            return {'xid_next': '123', 'objects': [
                {'relation_code': relation, 'scope': 'heap', 'oid': index + 1,
                 'xid_age': 1_000_000 if self.trip('ages') else 10, 'mxid_age': 10,
                 'xid_limit': 2_000_000, 'mxid_limit': 2_000_000}
                for index, relation in enumerate(self.c.RELATIONS.values())]}
        if sql == self.tx.PLAN_SQL:
            self.log.append('exact-boundary-counts')
            snapshot = deepcopy(self.snapshot)
            if self.integrity and self.batch_count:
                snapshot[self.integrity] = {'changed': True}
            return {'snapshot': snapshot, 'targets': self.targets()}
        if sql == self.tx.COMPLETION_STATE_SQL:
            return dict.fromkeys(('invalid_foreign_keys', 'invalid_indexes', 'invalid_triggers'), 0)
        if sql == self.c.POINTER_IDENTITIES_SQL:
            return self.reviewed['pointer_identities']
        if sql == self.c.PUBLISHED_SURVIVORS_SQL:
            self.log.append('published-survivors')
            return self.survivors(drifted=self.archetype_drift and self.batch_count > 0)
        if sql in self.c.STATUS_RELATION_SQL.values():
            self.log.append('database-counts')
            return {'targets': dict(self.counts)}
        if "'observed',current_setting" in sql:
            self.log.append('fresh-role-probe')
            return {'observed': 'on' if self.writer else 'off'}
        if 'pg_stat_progress_vacuum' in sql:
            self.log.append('autovacuum-check')
            return {'active': int(self.trip('autovacuum'))}
        raise AssertionError('unexpected SQL')

    def state(self, **kwargs):
        events = []
        if self.auto:
            events.append({'event_kind': 'AUTOVACUUM_DISABLED', 'purge_id': self.ids[0],
                           'event_sequence': 1, 'relation_code': self.auto})
        if self.open_batch:
            events.append({'event_kind': 'BATCH_STARTED', 'purge_id': self.ids[0],
                           'event_sequence': 2, 'relation_code': 'system_search'})
        if self.writer:
            events.append({'event_kind': 'WRITER_FENCE_ENABLED', 'purge_id': self.ids[0],
                           'event_sequence': 3, 'relation_code': None})
        events.extend(e for e in self.failures if e['operational_payload']['integrity_failed'])
        return {'unresolved': events}

    def survivors(self, *, drifted=False):
        return {'system_archetype_rows': self.archetype_rows - int(drifted),
                'products': {code: {'lifecycle_state': 'READY', 'expected_rows': 7,
                                    'manifest_sha256': 'e' * 64, 'product_version': code + '-1',
                                    'published_at': '2026-10-23T12:00:00+00:00'}
                             for code in ('system_search', 'system_archetype')}}

    def targets(self):
        return [{'id': value, 'key': key, 'state': 'FAILED', 'manifest_sha256': 'd' * 64,
                 'payload_counts': {code: self.counts[value] if code == 'system_search' else 0
                                    for code in self.c.RELATIONS.values()}}
                for key, (value, _) in self.c.TARGETS.items()]

    def resolve(self, *args):
        self.log.append('resolve-batches')
        if self.open_batch:
            self.write('batch-backend-cancelled-and-gone')
            self.write('batch-rolled-back')
            self.open_batch = False

    def metadata(self, *args):
        return {'autovacuum_fences': ([{'relation_code': self.auto,
                 'operational_payload': {'heap': self.age_config}}] if self.auto else [])}

    def autovacuum(self, query, ids, relation):
        if self.auto:
            assert self.auto == relation
            self.log.append('autovacuum-adopted')
        else:
            self.write('autovacuum-disabled')
            self.auto = relation
        return {'adopted': True, 'relation_code': relation}

    def fence(self, query, purge_id, enabled, probe, **kwargs):
        if self.writer == enabled:
            return {'adopted': True}
        self.write('writer-enabled' if enabled else 'writer-restored')
        self.writer = enabled
        assert probe() == ('on' if enabled else 'off')
        return {'enabled': enabled, 'verified': True}

    def wait(self, *_):
        self.log.append('competing-writer-wait')
        if self.trip('competing-writer'):
            raise ValueError('competing_writer_wait_exhausted')
        return {'maximum_seconds': 30, 'elapsed_seconds': 0, 'attempts': 1,
                'background_writer_observed': False, 'remaining_competing_writers': 0}

    def batch(self, query, purge_id, relation, limit, measured):
        assert self.writer and self.auto == relation
        assert measured['competing_writer_wait']['maximum_seconds'] == 30
        self.write('batch-started')
        self.open_batch = True
        if self.on_batch:
            self.on_batch()
        affected = min(limit, self.counts[purge_id])
        self.counts[purge_id] -= affected
        self.batch_count += 1
        self.open_batch = False
        self.write('batch-committed')
        return {'rows_affected': affected}

    def failed_stop(self, query, ids, payload, relation=None):
        self.write('FAILED_STOP')
        event = {'event_kind': 'FAILED_STOP', 'event_sequence': 100 + len(self.failures),
                 'purge_id': self.ids[0], 'relation_code': relation,
                 'operational_payload': deepcopy(payload)}
        self.failures.append(event)
        return event

    def complete(self, *_):
        assert sum(self.counts.values()) == 0
        self.write('relation-logically-empty')

    def abort(self, *args):
        self.write('autovacuum-restored-aborted')
        self.auto = None
        return {'aborted': True}

    def run(self, mode='delete-system-search', **kwargs):
        report = self.c.receipt(mode)
        self.report = report
        self.d.dispatch(self.c, mode, self.runtime, report, self.plan, self.proof,
                        controller_pid=123, controller_run_id='456', **kwargs)
        return report


@pytest.mark.parametrize('gate,error', (
    ('floor', 'filesystem_free_space_floor'), ('wal', 'archiver_failed_count_changed'),
    ('workers', 'named_workers_not_stopped'), ('placement', 'tablespace_or_wal_filesystem_mismatch'),
    ('autovacuum', 'autovacuum_running_on_payload'), ('controller', 'controller_lost'),
    ('ledger', 'migration_ledger_changed'), ('competing-writer', 'competing_writer_wait_exhausted'),
    ('ages', 'autovacuum_fence_deadline_unsafe'), ('slot', 'wal_retention_unhealthy'),
    ('archive-time', 'archiver_last_failure_newer_than_success'),
))
def test_delete_dispatch_stops_before_next_batch_and_resumes_from_database_counts(monkeypatch, gate, error):
    model = DispatchModel(monkeypatch)
    model.failure_after_batch = gate
    with pytest.raises(ValueError, match=error):
        model.run()
    assert model.batch_count == 1
    assert sum(model.counts.values()) == 2
    assert model.failures[-1]['operational_payload']['integrity_failed'] is False
    assert model.failures[-1]['operational_payload']['condition'] == error
    assert model.log.index('batch-committed') < model.log.index('FAILED_STOP') < model.log.index('writer-restored')
    assert not model.writer
    assert model.auto == 'system_search'
    model.failure_after_batch = None
    report = model.run()
    assert report['status'] == 'success'
    assert sum(model.counts.values()) == 0
    assert model.batch_count == 3
    assert 'autovacuum-adopted' in model.log
    assert report['next_admissible_mode']['mode'] == 'rewrite-system-search'


@pytest.mark.parametrize('failure', ('identity', 'index', 'wrapper', 'floor', 'placement', 'workers',
                                      'controller', 'ledger', 'competing-writer', 'autovacuum', 'ages', 'slot',
                                      'archive-time'))
def test_delete_dispatch_preflight_failure_never_opens_a_new_fence(monkeypatch, failure):
    model = DispatchModel(monkeypatch)
    model.failure = failure
    with pytest.raises(ValueError):
        model.run()
    assert model.mutations == []
    assert model.counts[model.ids[0]] == 3


def test_each_batch_has_fresh_gates_and_competing_writer_wait(monkeypatch):
    model = DispatchModel(monkeypatch)
    report = model.run()
    assert report['status'] == 'success'
    previous = 0
    for index, value in enumerate(model.log):
        if value != 'batch-started':
            continue
        preceding = model.log[previous:index]
        assert {'controller', 'competing-writer-wait', 'migration-ledger', 'free-space',
                'wal-health', 'wal-placement', 'named-workers', 'autovacuum-check', 'age-ceilings'} <= set(preceding)
        final_measurement = preceding.index('autovacuum-check')
        assert 'exact-boundary-counts' not in preceding[final_measurement:]
        previous = index + 1
    assert model.log.count('exact-boundary-counts') == 2
    assert 'database-counts' not in model.log
    assert model.log.index('relation-logically-empty') < model.log.index('writer-restored')
    assert report['writer_fence']['enabled'] is False
    assert report['writer_fence']['verified'] is True


@pytest.mark.parametrize('kind', ('xid', 'mxid'))
@pytest.mark.parametrize('scope', ('heap', 'toast'))
@pytest.mark.parametrize('opened', (False, True))
def test_delete_requires_the_entire_remaining_horizon_before_opening_or_adopting_fence(
        monkeypatch, kind, scope, opened):
    model = DispatchModel(monkeypatch)
    model.auto = 'system_search' if opened else None
    model.reviewed['delete']['system_search'].update(rows_per_second=0.003, rewrite_allowance_seconds=600)
    # 1,000 seconds until the nearer ceiling admits this 365-second
    # dispatch, but cannot cover 1,000 seconds of deletes plus the rewrite.
    near = {**model.age_config, kind + '_ceiling': 1010, kind + '_rate': 1}
    if scope == 'heap':
        model.age_config.update(near)
    query = model.runtime.query
    def ages(sql, *args, **kwargs):
        value = query(sql, *args, **kwargs)
        if sql == model.c.AGES_SQL and scope == 'toast':
            value['objects'].append({**value['objects'][0], 'scope': 'toast', 'oid': 100})
        return value
    model.runtime.query = ages
    if scope == 'toast':
        if opened:
            model.tx.metadata_state = lambda *_: {'autovacuum_fences': [{
                'relation_code': 'system_search', 'operational_payload': {
                    'heap': model.age_config, 'toast': near}}]}
        else:
            # Unopened fences use the plan's conservative per-relation rates.
            model.reviewed['autovacuum']['system_search'] = near
    with pytest.raises(ValueError, match='autovacuum_fence_deadline_unsafe'):
        model.run()
    assert model.batch_count == 0 and model.mutations == []
    assert 'autovacuum-adopted' not in model.log
    assert model.report['next_admissible_mode'] == {'mode': 'abort-relation-system-search', 'implemented': True}
    horizon = model.report['autovacuum_fence_horizon']
    assert horizon['remaining_target_rows'] == 3
    assert horizon['required_seconds'] == 1600
    assert horizon['projections'][-1]['seconds_to_ceiling'] == 1000


@pytest.mark.parametrize('kind', ('xid', 'mxid'))
def test_resumed_delete_with_comfortable_full_horizon_passes(monkeypatch, kind):
    model = DispatchModel(monkeypatch)
    model.auto = 'system_search'
    model.reviewed['delete']['system_search'].update(rows_per_second=0.003, rewrite_allowance_seconds=600)
    model.age_config.update({kind + '_ceiling': 2010, kind + '_rate': 1})
    horizons = []
    gate = model.d.age_gate
    def record(*args):
        gate(*args)
        horizons.append(deepcopy(model.report['autovacuum_fence_horizon']))
    monkeypatch.setattr(model.d, 'age_gate', record)
    assert model.run()['status'] == 'success'
    assert 'autovacuum-adopted' in model.log
    assert horizons[0]['required_seconds'] == 1600
    assert horizons[-1]['required_seconds'] == 600
    assert [h['remaining_target_rows'] for h in horizons][-4:] == [3, 2, 1, 0]


@pytest.mark.parametrize('field', ('rows_per_second', 'rewrite_allowance_seconds'))
@pytest.mark.parametrize('opened', (False, True))
def test_delete_refuses_unreviewed_horizon_fields_without_inventing_defaults(monkeypatch, field, opened):
    model = DispatchModel(monkeypatch)
    model.auto = 'system_search' if opened else None
    del model.reviewed['delete']['system_search'][field]
    with pytest.raises(ValueError, match='autovacuum_fence_horizon_not_reviewed'):
        model.run()
    assert model.batch_count == 0 and model.mutations == []
    assert model.report['next_admissible_mode']['mode'] == 'abort-relation-system-search'


def test_empty_relation_with_insufficient_rewrite_horizon_recommends_rewrite(monkeypatch):
    model = DispatchModel(monkeypatch)
    model.auto = 'system_search'
    model.counts = dict.fromkeys(model.ids, 0)
    model.age_config.update(xid_ceiling=510, xid_rate=1)
    with pytest.raises(ValueError, match='autovacuum_fence_deadline_unsafe'):
        model.run()
    assert model.mutations == []
    assert model.report['next_admissible_mode'] == {'mode': 'rewrite-system-search', 'implemented': True}


def test_delete_rechecks_full_horizon_immediately_before_adopting_fence(monkeypatch):
    model = DispatchModel(monkeypatch)
    model.auto = 'system_search'
    def host_evidence(*_):
        model.age_config.update(xid_ceiling=510, xid_rate=1)
        return []
    monkeypatch.setattr(model.d, 'running_services', host_evidence)
    with pytest.raises(ValueError, match='autovacuum_fence_deadline_unsafe'):
        model.run()
    assert 'autovacuum-adopted' not in model.log
    assert model.batch_count == 0
    assert model.report['next_admissible_mode']['mode'] == 'abort-relation-system-search'


def test_successful_delete_receipt_has_final_integrity_and_fresh_relation_sizes(monkeypatch):
    model = DispatchModel(monkeypatch)
    query = model.runtime.query
    observations = []
    def observed(sql, *args, **kwargs):
        result = query(sql, *args, **kwargs)
        if sql == model.tx.COMPLETION_STATE_SQL:
            result.update(snapshot=deepcopy(model.snapshot), targets=model.targets(), rewrites=[])
            observations.append(('integrity', deepcopy(result)))
        elif sql == model.c.OBJECTS_SQL:
            # A fresh observation must preserve heap, index and TOAST evidence,
            # even when DELETE leaves their physical sizes unchanged.
            result = [
                {**result[0], 'heap_bytes': model.relation_bytes - model.batch_count,
                 'index_bytes': 200, 'total_bytes': model.relation_bytes + 300 - model.batch_count},
                {'relation': 'v3_derived.system_search_pkey', 'kind': 'i', 'valid': True,
                 'heap_bytes': 200, 'index_bytes': 0, 'total_bytes': 200},
                {'relation': 'pg_toast.pg_toast_123', 'kind': 't', 'valid': True,
                 'heap_bytes': 100, 'index_bytes': 0, 'total_bytes': 100},
            ]
            observations.append(('sizes', deepcopy(result)))
        return result
    model.runtime.query = observed
    report = model.run()
    integrity = [value for kind, value in observations if kind == 'integrity']
    sizes = [value for kind, value in observations if kind == 'sizes']
    assert report['status'] == 'success'
    assert len(integrity) >= 2 and integrity[0] != integrity[-1]
    assert report['fk_check'] == integrity[-1]
    assert all(report['fk_check'][key] == 0 for key in
               ('invalid_foreign_keys', 'invalid_indexes', 'invalid_triggers'))
    assert len(sizes) >= 2 and sizes[0] != sizes[-1]
    assert report['relation_bytes_before'] == sizes[0]
    assert report['relation_bytes_after'] == sizes[-1]
    assert observations[-1][0] == 'sizes'


@pytest.mark.parametrize(('observation', 'failure'), (
    ('integrity', 'unavailable'), ('integrity', 'missing'), ('integrity', 'invalid'),
    ('sizes', 'unavailable'), ('sizes', 'missing'), ('sizes', 'empty'), ('sizes', 'invalid'),
))
def test_delete_cannot_succeed_without_final_integrity_and_size_observations(monkeypatch, observation, failure):
    model = DispatchModel(monkeypatch)
    query = model.runtime.query
    def unavailable(sql, *args, **kwargs):
        result = query(sql, *args, **kwargs)
        expected = model.tx.COMPLETION_STATE_SQL if observation == 'integrity' else model.c.OBJECTS_SQL
        if sql != expected or model.batch_count == 0:
            return result
        if failure == 'unavailable':
            raise RuntimeError('final_observation_unavailable')
        if observation == 'integrity':
            if failure == 'missing':
                del result['invalid_foreign_keys']
            else:
                result['invalid_indexes'] = 1
            return result
        if failure == 'missing':
            return None
        if failure == 'empty':
            return []
        return [{**result[0], 'valid': False}]
    model.runtime.query = unavailable
    with pytest.raises((ValueError, RuntimeError)):
        model.run()
    assert model.batch_count == 3
    assert model.report['status'] == 'stopped'
    assert model.report['result'] != 'relation_logically_empty_waiting_for_rewrite'
    if observation == 'integrity':
        assert model.report['fk_check'] is None
    else:
        assert model.report['relation_bytes_after'] is None


def test_integrity_failure_requires_exact_owner_acknowledgement_before_writer_restore(monkeypatch):
    model = DispatchModel(monkeypatch)
    model.integrity = 'survivors'
    with pytest.raises(ValueError, match='delete_published_survivor_count_drift'):
        model.run()
    assert model.writer
    assert 'writer-restored' not in model.log
    failed_sequence = model.failures[-1]['event_sequence']
    with pytest.raises(ValueError, match='acknowledgement_required'):
        model.run('restore-services')
    assert model.writer
    with pytest.raises(ValueError, match='acknowledgement_required'):
        model.run('restore-services', acknowledge_failed_stop=failed_sequence + 1)
    original = deepcopy(model.failures)
    acknowledged = []
    def acknowledge(query, ids, sequence):
        assert ids == model.ids and sequence == failed_sequence
        acknowledged.append(sequence)
        return {'acknowledge_failed_stop': sequence}
    model.tx.acknowledge_failure = acknowledge
    restore_fence = model.tx.writer_fence
    def fence(query, purge_id, enabled, probe, **kwargs):
        assert not enabled and kwargs['acknowledge_failed_stop'] == failed_sequence
        assert acknowledged == [failed_sequence]
        return restore_fence(query, purge_id, enabled, probe, **kwargs)
    model.tx.writer_fence = fence
    result = model.run('restore-services', acknowledge_failed_stop=failed_sequence)
    assert result['status'] == 'success'
    assert result['writer_restore'] == {'verified': True, 'acknowledge_failed_stop': failed_sequence}
    assert not model.writer and 'writer-restored' in model.mutations
    assert model.failures == original
    assert original[-1]['operational_payload']['integrity_failed'] is True
    with pytest.raises(ValueError, match='integrity_failed_stop_requires_restore_services_acknowledgement'):
        model.run()


def test_delete_boundaries_prove_the_frozen_published_archetype_survivors(monkeypatch):
    # 016's snapshot omits the published wide archetype product; the delete
    # boundary compares the plan's frozen archetype survivors before and after.
    model = DispatchModel(monkeypatch)
    report = model.run()
    assert report['status'] == 'success'
    assert model.log.count('published-survivors') >= 2
    assert report['published_survivors_before'] == model.reviewed['published_survivors']
    assert report['published_survivors_after'] == model.reviewed['published_survivors']


def test_published_archetype_survivor_drift_is_an_integrity_stop_that_keeps_writers_fenced(monkeypatch):
    model = DispatchModel(monkeypatch)
    model.archetype_drift = True
    with pytest.raises(ValueError, match='published_archetype_survivor_count_drift'):
        model.run()
    # Like 016's survivor snapshot, the exact count is a dispatch-boundary
    # proof: the final boundary refuses logical completion and stops.
    assert model.batch_count == 3
    assert 'relation-logically-empty' not in model.log
    assert model.failures[-1]['operational_payload']['integrity_failed'] is True
    assert model.failures[-1]['operational_payload']['condition'] == 'published_archetype_survivor_count_drift'
    assert model.writer and 'writer-restored' not in model.log


def test_plan_without_frozen_published_survivors_is_refused_before_any_fence(monkeypatch):
    model = DispatchModel(monkeypatch)
    del model.reviewed['published_survivors']
    with pytest.raises(ValueError, match='published_survivor_proof_missing'):
        model.run()
    assert model.mutations == []
    assert model.counts[model.ids[0]] == 3


@pytest.mark.parametrize('integrity', ('canonical', 'survivors', 'retained', 'fk', None))
@pytest.mark.parametrize('sig', (None, signal.SIGINT, signal.SIGTERM, signal.SIGHUP))
@pytest.mark.parametrize('committed', (False, True))
def test_failed_stop_recording_error_never_reopens_writes(monkeypatch, integrity, sig, committed):
    model = DispatchModel(monkeypatch)
    if integrity in ('canonical', 'survivors', 'retained'):
        model.integrity = integrity
    if sig is not None:
        model.on_batch = lambda: os.kill(os.getpid(), sig)
    else:
        model.failure_after_batch = 'workers'
    query = model.runtime.query
    def checks(sql, *args, **kwargs):
        result = query(sql, *args, **kwargs)
        if sql == model.tx.COMPLETION_STATE_SQL and model.batch_count and integrity == 'fk':
            result['invalid_foreign_keys'] = 1
        return result
    model.runtime.query = checks
    attempts = []
    def unavailable(*args):
        attempts.append(deepcopy(args[2]))
        if committed:
            model.failed_stop(*args)
        raise RuntimeError('failed_stop_transport_failed')
    model.tx.record_failed_stop = unavailable
    with pytest.raises(RuntimeError, match='failed_stop_transport_failed'):
        model.run()
    assert len(attempts) == 1
    assert attempts[0]['integrity_failed'] is (integrity is not None)
    assert model.report['integrity_failed'] is True
    assert model.report['failed_stop_recorded'] is None
    assert model.report['status'] == 'stopped'
    assert model.report['writer_fence']['enabled'] is True
    assert model.report['writer_restore'] == 'refused_integrity_failed_stop'
    assert model.writer and not model.open_batch
    assert 'writer-restored' not in model.log
    assert bool(model.failures) is committed


@pytest.mark.parametrize('integrity', ('canonical', 'survivors', 'retained', 'fk', 'unknown'))
def test_integrity_classification_survives_unavailable_failure_observation(monkeypatch, integrity):
    model = DispatchModel(monkeypatch)
    query = model.runtime.query
    def unavailable(sql, *args, **kwargs):
        if model.batch_count and sql == model.tx.PLAN_SQL:
            raise RuntimeError('integrity_observation_unavailable')
        return query(sql, *args, **kwargs)
    model.runtime.query = unavailable
    conditions = {'canonical': 'delete_pointer_changed', 'survivors': 'delete_published_survivor_count_drift',
                  'retained': 'delete_retained_metadata_drift', 'fk': 'delete_fk_or_index_failure',
                  'unknown': 'database_transport_failed'}
    batch = model.tx.payload_batch
    def failed(*args):
        batch(*args)
        raise ValueError(conditions[integrity])
    model.tx.payload_batch = failed
    with pytest.raises(ValueError, match=conditions[integrity]):
        model.run()
    assert model.report['integrity_failed'] is True
    assert model.report['failed_stop_recorded']
    assert model.failures[-1]['operational_payload']['integrity_failed'] is True
    assert model.writer and 'writer-restored' not in model.log


def test_failed_stop_recording_error_survives_real_loop_process_transport(monkeypatch):
    model = DispatchModel(monkeypatch)
    model.integrity = 'retained'
    model.failure_after_batch = 'workers'
    real_loop = load('v3_purge_delete')
    monkeypatch.setattr(model.d, 'run_loop_process', real_loop.run_loop_process)
    def unavailable(*args):
        raise RuntimeError('failed_stop_transport_failed')
    model.tx.record_failed_stop = unavailable
    with pytest.raises(real_loop.LoopFailure, match='failed_stop_transport_failed'):
        model.run()
    assert model.report['runner_state']['loop_exited'] is True
    assert model.report['integrity_failed'] is True
    assert model.report['failed_stop_recorded'] is None
    assert model.writer and 'writer-restored' not in model.log


def test_restore_dispatch_resolves_open_batch_before_writer_restore_and_is_idempotent(monkeypatch):
    model = DispatchModel(monkeypatch)
    model.open_batch = model.writer = True
    model.auto = 'system_search'
    first = model.run('restore-services')
    assert first['status'] == 'success'
    assert first['writer_fence']['enabled'] is False
    assert first['writer_fence']['verified'] is True
    assert model.log.index('batch-backend-cancelled-and-gone') < model.log.index('batch-rolled-back')
    assert model.log.index('batch-rolled-back') < model.log.index('writer-restored')
    mutations = list(model.mutations)
    second = model.run('restore-services')
    assert second['status'] == 'success'
    assert second['writer_fence']['enabled'] is False
    assert model.mutations == mutations
    assert model.auto == 'system_search'


def test_abort_dispatch_reports_shortfall_before_releasing_autovacuum(monkeypatch):
    model = DispatchModel(monkeypatch)
    model.auto = 'system_search'
    model.reviewed['delete']['system_search']['autovacuum_budget_bytes'] = model.relation_bytes
    model.free = model.c.FREE_FLOOR_BYTES + model.relation_bytes - 1
    with pytest.raises(ValueError, match='abort_autovacuum_headroom_shortfall'):
        model.run('abort-relation-system-search')
    assert model.mutations == []
    assert model.auto == 'system_search'
    model.free += 1
    report = model.run('abort-relation-system-search')
    assert report['abort_headroom']['shortfall_bytes'] == 0
    assert report['abort_headroom']['autovacuum_budget_bytes'] >= model.relation_bytes
    assert model.auto is None
    assert report['next_admissible_mode']['mode'] == 'delete-system-search'
    assert model.log.index('autovacuum-restored-aborted') < model.log.index('database-counts')


@pytest.mark.parametrize('mode', ('delete-system-search', 'abort-relation-system-search', 'restore-services'))
def test_delete_abort_and_restore_receipts_measure_physical_wal_bytes(monkeypatch, mode):
    model = DispatchModel(monkeypatch)
    if mode.startswith('abort-'):
        model.auto = 'system_search'
        model.reviewed['delete']['system_search']['autovacuum_budget_bytes'] = model.relation_bytes
    measurements = []
    def docker(*args):
        assert args == ('exec', model.c.CONTAINER, 'du', '--bytes', '--summarize',
                        '--dereference', '--', '/data/pg_wal')
        measurements.append(100 + len(measurements))
        return str(measurements[-1]) + ' /data/pg_wal'
    model.runtime.docker = docker
    report = model.run(mode)
    assert report['status'] == 'success'
    assert report['wal_before']['bytes'] == measurements[0]
    assert report['wal_after']['bytes'] == measurements[-1]
    assert report['wal_after']['bytes'] > report['wal_before']['bytes']
    # Directory growth is evidence distinct from WAL generated via LSN delta.
    assert report['wal_byte_delta'] == 0


@pytest.mark.parametrize('mode', ('delete-system-search', 'abort-relation-system-search'))
@pytest.mark.parametrize('failure', ('malformed', 'command-failed'))
def test_delete_and_abort_refuse_unavailable_initial_wal_bytes(monkeypatch, mode, failure):
    model = DispatchModel(monkeypatch)
    if mode.startswith('abort-'):
        model.auto = 'system_search'
        model.reviewed['delete']['system_search']['autovacuum_budget_bytes'] = model.relation_bytes
    def docker(*args):
        if failure == 'command-failed':
            raise RuntimeError('du_command_failed')
        return 'not measured'
    model.runtime.docker = docker
    with pytest.raises((ValueError, RuntimeError), match='wal_directory_bytes_unavailable|du_command_failed'):
        model.run(mode)
    assert model.mutations == []
    assert model.batch_count == 0
    assert 'resolve-batches' not in model.log


@pytest.mark.parametrize('budget', (None, True, False, 0, -1, 1.5, '3000000000', 2**63))
def test_abort_requires_valid_measured_plan_budget_before_any_mutation(monkeypatch, budget):
    model = DispatchModel(monkeypatch)
    model.auto = 'system_search'
    if budget is not None:
        model.reviewed['delete']['system_search']['autovacuum_budget_bytes'] = budget
    with pytest.raises(ValueError, match='autovacuum_budget_not_measured'):
        model.run('abort-relation-system-search')
    assert model.mutations == []
    assert model.auto == 'system_search'


@pytest.mark.parametrize('budget', (1, 4_000_000_000))
def test_abort_uses_larger_of_rehearsal_budget_and_current_size(monkeypatch, budget):
    model = DispatchModel(monkeypatch)
    model.auto = 'system_search'
    model.reviewed['delete']['system_search']['autovacuum_budget_bytes'] = budget
    required = model.c.FREE_FLOOR_BYTES + max(budget, model.relation_bytes)
    model.free = required - 1
    with pytest.raises(ValueError, match='abort_autovacuum_headroom_shortfall'):
        model.run('abort-relation-system-search')
    assert model.mutations == []
    model.free = required
    report = model.run('abort-relation-system-search')
    assert report['abort_headroom']['required_bytes'] == required
    assert report['abort_headroom']['autovacuum_budget_bytes'] == max(budget, model.relation_bytes)


@pytest.mark.parametrize(('counts', 'expected'), (
    ((0, 0), 'rewrite-system-search'), ((0, 2), 'delete-system-search'),
    ((None, None), 'status'), ((0, None), 'status'), ((None, 2), 'delete-system-search'),
    ((-1, 0), 'status'), ((False, 0), 'status'),
))
def test_abort_guidance_uses_both_fresh_target_counts(monkeypatch, counts, expected):
    model = DispatchModel(monkeypatch)
    model.auto = 'system_search'
    model.reviewed['delete']['system_search']['autovacuum_budget_bytes'] = model.relation_bytes
    query = model.runtime.query
    def observed(sql, *args, **kwargs):
        if sql == model.c.STATUS_RELATION_SQL['system_search']:
            assert model.auto is None
            return {'targets': dict(zip(model.ids, counts, strict=True))}
        return query(sql, *args, **kwargs)
    model.runtime.query = observed
    report = model.run('abort-relation-system-search')
    assert report['next_admissible_mode']['mode'] == expected
    assert report['rows_remaining'] == dict(zip(model.ids, counts, strict=True))


def test_abort_with_unavailable_fresh_counts_recommends_status(monkeypatch):
    model = DispatchModel(monkeypatch)
    model.auto = 'system_search'
    model.reviewed['delete']['system_search']['autovacuum_budget_bytes'] = model.relation_bytes
    query = model.runtime.query
    def locked(sql, *args, **kwargs):
        if sql == model.c.STATUS_RELATION_SQL['system_search']:
            raise RuntimeError('database_lock_timeout')
        return query(sql, *args, **kwargs)
    model.runtime.query = locked
    assert model.run('abort-relation-system-search')['next_admissible_mode']['mode'] == 'status'


@pytest.mark.parametrize('mode', ('delete-system-search', 'abort-relation-system-search'))
@pytest.mark.parametrize('open_batch', (False, True))
def test_lost_dispatch_writer_fence_requires_explicit_restoration(monkeypatch, mode, open_batch):
    model = DispatchModel(monkeypatch)
    model.writer = True
    model.open_batch = open_batch
    model.auto = 'system_search'
    # Includes death after final commit, with no open BATCH_STARTED.
    model.counts = dict.fromkeys(model.ids, 0)
    with pytest.raises(ValueError, match='orphaned_writer_fence_requires_restore_services'):
        model.run(mode)
    assert model.mutations == []
    assert model.writer
    assert model.report['next_admissible_mode']['mode'] == 'restore-services'
    restored = model.run('restore-services')
    assert restored['writer_fence']['enabled'] is False
    assert not model.writer


def test_stop_request_during_batch_waits_for_commit_before_restoring_writer(monkeypatch):
    from contextlib import contextmanager
    model = DispatchModel(monkeypatch)
    @contextmanager
    def signals(stop):
        def during_batch():
            stop.set()
            time.sleep(0.03)
            model.log.append('batch-worker-finishing')
        model.on_batch = during_batch
        yield
    monkeypatch.setattr(model.d, 'stop_signals', signals)
    with pytest.raises(ValueError, match='delete_stop_requested'):
        model.run()
    assert model.batch_count == 1
    assert not model.open_batch and not model.writer
    assert model.log.index('batch-worker-finishing') < model.log.index('batch-committed')
    assert model.log.index('batch-committed') < model.log.index('writer-restored')


def test_dispatch_refuses_another_relations_autovacuum_fence_without_mutation(monkeypatch):
    model = DispatchModel(monkeypatch)
    model.auto = 'body_mechanics'
    with pytest.raises(ValueError, match='different_relation_fence_open'):
        model.run()
    assert model.mutations == []


def test_dispatch_requires_sealed_verification_before_any_mutation(monkeypatch):
    model = DispatchModel(monkeypatch)
    model.proof = None
    with pytest.raises(ValueError, match='sealed_verification_required'):
        model.run()
    assert model.mutations == []


def test_dispatch_rejects_changed_wrapper_proof_before_any_mutation(monkeypatch):
    model = DispatchModel(monkeypatch)
    model.plan['expected_wrapper_sha256'] = 'e' * 64
    with pytest.raises(ValueError, match='plan_backup_wrapper_hash_changed'):
        model.run()
    assert model.mutations == []


def test_dispatch_requires_floor_plus_one_and_half_times_batch_peak(monkeypatch):
    model = DispatchModel(monkeypatch)
    model.free = model.c.FREE_FLOOR_BYTES + 14
    with pytest.raises(ValueError, match='filesystem_free_space_floor'):
        model.run()
    assert model.mutations == []


def test_dispatch_records_conservative_reservation_when_plan_has_no_rehearsal(monkeypatch):
    model = DispatchModel(monkeypatch)
    del model.reviewed['delete']['system_search']['batch_peak_bytes']
    report = model.run()
    assert report['batch_peak_bytes'] == model.d.DEFAULT_BATCH_PEAK_BYTES
    assert report['batch_peak_source'] == 'conservative_fixed_reservation'


def test_dispatch_requires_reviewed_per_relation_batch_limit_before_any_mutation(monkeypatch):
    model = DispatchModel(monkeypatch)
    del model.reviewed['delete']['system_search']['batch_limit']
    with pytest.raises(ValueError, match='delete_plan_batch_limit'):
        model.run()
    assert model.mutations == []


def test_restore_services_validates_supplied_acknowledgement_without_open_failure(monkeypatch):
    model = DispatchModel(monkeypatch)
    model.writer = True
    def acknowledge(*args):
        raise ValueError('purge_failed_stop_acknowledgement_invalid')
    model.tx.acknowledge_failure = acknowledge
    with pytest.raises(ValueError, match='purge_failed_stop_acknowledgement_invalid'):
        model.run('restore-services', acknowledge_failed_stop=999)
    assert model.writer and 'writer-restored' not in model.log
