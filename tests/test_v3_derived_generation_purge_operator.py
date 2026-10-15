"""P2a fences: no production access, fixed SQL and local lease/plan fakes."""
from __future__ import annotations

import fcntl
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(relative, name='purge_fence_test'):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tool(monkeypatch):
    module = _load('scripts/operator/lib/v3_purge_state.py')
    monkeypatch.setattr(module, 'lease_state', lambda: 'free')
    return module


def _query(module, *, present=True, kinds=()):
    def query(sql):
        assert sql in (module.PRESENCE_SQL, module.STATE_SQL)
        result = {'database': module.DATABASE_NAME, 'read_only': 'on'}
        if sql == module.PRESENCE_SQL:
            result['ledger_present'] = present
        else:
            result['unresolved'] = [
                {'event_kind': kind, 'event_sequence': index + 1,
                 'purge_id': '49a0c00d-e722-4209-afd8-9d62b877e30a', 'relation_code': None}
                for index, kind in enumerate(kinds)
            ]
        return json.dumps(result)
    return query


@pytest.mark.parametrize('kind', sorted(('BATCH_STARTED', 'REWRITE_STARTED', 'SERVICES_QUIESCED',
                                        'WRITER_FENCE_ENABLED', 'AUTOVACUUM_DISABLED', 'FAILED_STOP')))
def test_shared_fence_refuses_every_unresolved_kind(monkeypatch, kind):
    module = _tool(monkeypatch)
    with pytest.raises(module.PurgeStateError, match='purge_unresolved_' + kind) as error:
        module.check(_query(module, kinds=(kind,)))
    assert error.value.report['unresolved'][0]['event_kind'] == kind


def test_combines_held_lease_and_all_unresolved_kinds(monkeypatch):
    module = _tool(monkeypatch)
    monkeypatch.setattr(module, 'lease_state', lambda: 'held')
    with pytest.raises(module.PurgeStateError) as error:
        module.check(_query(module, kinds=sorted(module.KINDS)))
    assert error.value.report['lease'] == 'held'
    assert len(error.value.report['failures']) == 7


def test_actual_flock_probe_does_not_create_or_write(tmp_path):
    module = _load('scripts/operator/lib/v3_purge_state.py')
    lease = tmp_path / 'lease'
    assert module.lease_state(lease) == 'free'
    assert not lease.exists()
    lease.write_text('unchanged')
    with lease.open('r') as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert module.lease_state(lease) == 'held'
    assert module.lease_state(lease) == 'free'
    assert lease.read_text() == 'unchanged'


@pytest.mark.parametrize('bootstrap', (True, False))
def test_lease_refusal_applies_even_to_bootstrap(monkeypatch, bootstrap):
    module = _tool(monkeypatch)
    monkeypatch.setattr(module, 'lease_state', lambda: 'held')
    with pytest.raises(module.PurgeStateError, match='purge_host_lease_held'):
        module.check(_query(module, present=False), bootstrap=bootstrap)


def test_missing_relation_is_refused_except_explicit_migration_bootstrap(monkeypatch):
    module = _tool(monkeypatch)
    with pytest.raises(module.PurgeStateError, match='purge_ledger_absent'):
        module.check(_query(module, present=False))
    assert module.check(_query(module, present=False), bootstrap=True)['bootstrap'] is True
    assert module.check(_query(module))['status'] == 'clear'


@pytest.mark.parametrize('response', ('bad json', '{}', '[]',
    '{"database":"wrong","read_only":"on","ledger_present":true}'))
def test_query_shape_identity_and_failures_refuse_without_leaking(monkeypatch, response):
    module = _tool(monkeypatch)
    with pytest.raises(module.PurgeStateError, match='purge_state_query_failed'):
        module.check(lambda _sql: response)
    def broken(_sql):
        raise RuntimeError('credential must never escape')
    with pytest.raises(module.PurgeStateError) as error:
        module.check(broken)
    assert 'credential' not in str(error.value)


def _entries():
    # Deliberately not production migration names: the exception follows a plan,
    # never a hardcoded pre-014/through-015 list.
    return [{'ledger_name': name, 'sha256': str(i) * 64, 'path': 'unused', 'mode': 'auto'}
            for i, name in enumerate(('001_other.sql', '007_other.sql',
                                      '016_v3_governed_derived_purge.sql'), 1)]


@pytest.mark.parametrize('prefix_length', (0, 1, 2))
def test_bootstrap_only_exact_authenticated_prefix_and_complete_suffix(prefix_length):
    module = _load('scripts/operator/v3_production_migrate.py')
    desired = _entries()
    live = [{key: entry[key] for key in ('ledger_name', 'sha256')}
            for entry in desired[:prefix_length]]
    plan = {'applied_before': live, 'pending': desired[prefix_length:]}
    assert module.purge_bootstrap_allowed(desired, live, plan)
    assert not module.purge_bootstrap_allowed(desired, live, {**plan, 'pending': desired[:-1]})
    assert not module.purge_bootstrap_allowed(desired, live, {**plan, 'applied_before': ['drift']})
    assert not module.purge_bootstrap_allowed(desired + [{'ledger_name': '017_future.sql'}], live, plan)


def test_absent_ledger_refuses_after_016_applied_and_when_suffix_not_016(monkeypatch):
    migration = _load('scripts/operator/v3_production_migrate.py')
    tool = _tool(monkeypatch)
    desired = _entries()
    full = [{key: entry[key] for key in ('ledger_name', 'sha256')} for entry in desired]
    for live, plan in (
        (full, {'applied_before': full, 'pending': []}),
        ([], {'applied_before': [], 'pending': desired[:-1]}),
        (full[:1], {'applied_before': [], 'pending': desired}),
    ):
        allowed = migration.purge_bootstrap_allowed(desired, live, plan)
        assert not allowed
        with pytest.raises(tool.PurgeStateError, match='purge_ledger_absent'):
            tool.check(_query(tool, present=False), bootstrap=allowed)


def test_apply_gate_passes_bootstrap_only_through_shared_fence(monkeypatch):
    migration = _load('scripts/operator/v3_production_migrate.py')
    tool = _tool(monkeypatch)
    original_load = migration._load
    monkeypatch.setattr(migration, '_load', lambda name, path:
                        tool if name == 'v3_purge_state' else original_load(name, path))
    deployer = SimpleNamespace(POSTGRES_CONTAINER=tool.CONTAINER, DATABASE_USER=tool.DATABASE_USER,
                              DATABASE_NAME=tool.DATABASE_NAME)
    desired = _entries()
    plan = {'applied_before': [], 'pending': desired}
    calls = []
    def runner(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(stdout=_query(tool, present=False)(argv[-1]))
    assert migration.require_purge_clear(deployer, {}, runner, desired=desired, live=[],
                                         reviewed_plan=plan)['bootstrap']
    assert len(calls) == 1 and '--no-psqlrc' in calls[0] and '--no-password' in calls[0]
    for kind in tool.KINDS:
        def blocked(argv, **kwargs):
            return SimpleNamespace(stdout=_query(tool, kinds=(kind,))(argv[-1]))
        with pytest.raises(tool.PurgeStateError, match=kind):
            migration.require_purge_clear(deployer, {}, blocked, desired=desired, live=[], reviewed_plan=plan)


def test_apply_fences_precede_lock_and_ddl_and_plan_is_transported():
    source = (ROOT / 'scripts/operator/v3_production_migrate.py').read_text()
    apply = source[source.index('def _main('):]
    assert apply.index('reviewed_apply_plan(') < apply.index('require_purge_clear(') < apply.index('deployer.acquire_lock(')
    assert apply.rindex('require_purge_clear(') < apply.index('apply_migration(')
    workflow = (ROOT / '.github/workflows/v3-production-schema-migration.yml').read_text()
    assert '--reviewed-plan' in workflow
    assert '"$RUNNER_TEMP/reviewed-plan/v3-production-migration.json"' in workflow
    assert 'scripts/operator/lib/v3_purge_state.py' in workflow


def test_fixed_sql_reuses_016_open_event_and_never_takes_a_database_lock():
    module = _load('scripts/operator/lib/v3_purge_state.py')
    assert 'v3_meta.purge_open_event(' in module.STATE_SQL
    assert "failure_evidence->'integrity_failed'='true'::jsonb" in module.STATE_SQL
    assert "'REWRITE_VERIFIED','REWRITE_ROLLED_BACK','FAILED_STOP'" in module.STATE_SQL
    for sql in (module.STATE_SQL, module.PRESENCE_SQL):
        assert sql.startswith('BEGIN READ ONLY;')
        assert 'FOR UPDATE' not in sql and 'pg_advisory' not in sql
