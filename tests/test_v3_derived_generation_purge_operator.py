"""P2a fences and P2b1 operator contracts using local evidence and SQL fakes."""
from __future__ import annotations

import fcntl
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
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


def _action_tool():
    return _load('scripts/operator/lib/v3_generation_purge.py', 'purge_action_test')


@pytest.mark.parametrize('mode', ('plan', 'status', 'authorize',
                                'verify-system-archetype-empty', 'complete'))
def test_p2b1_modes_are_implemented(mode):
    module = _action_tool()
    module.classify_mode(mode)


@pytest.mark.parametrize('mode', [
    f'{prefix}{relation}'
    for prefix in ('rewrite-',)
    for relation in ('system-search', 'economy-opportunity', 'body-mechanics',
                     'system-rating-vector')
])
def test_p2b2b_rewrite_modes_have_explicit_failure_and_cannot_fall_through(mode):
    module = _action_tool()
    with pytest.raises(Exception, match='mode_not_implemented_until_p2b2b'):
        module.classify_mode(mode)


@pytest.mark.parametrize('mode', ('', 'delete-system-archetype', 'rewrite-cluster',
                                'delete-system_search', 'PLAN', 'plan; SELECT 1',
                                'restore-services-extra'))
def test_unknown_and_injection_modes_fail_closed(mode):
    module = _action_tool()
    with pytest.raises(Exception, match='unknown'):
        module.classify_mode(mode)


def test_action_bash_syntax_and_restricted_sql_contract():
    action = ROOT / 'scripts/operator/actions/v3-derived-generation-purge.sh'
    subprocess.run(['bash', '-n', str(action)], check=True)
    source = action.read_text() + (ROOT / 'scripts/operator/lib/v3_generation_purge.py').read_text()
    source += (ROOT / 'scripts/operator/lib/v3_purge_transactions.py').read_text()
    for forbidden in ('ssh-keyscan', 'session_replication_role', 'DISABLE TRIGGER', 'CASCADE',
                      'RESET ROLE', 'SET SESSION AUTHORIZATION', 'DROP TABLE',
                      'TRUNCATE ', '--password=', 'PGPASSWORD='):
        assert forbidden not in source
    assert 'SET ROLE v3_derived_purge_executor' in source
    assert '--no-psqlrc' in source and '--no-password' in source
    assert 'lock_timeout' in source and 'statement_timeout' in source
    assert '016_v3_governed_derived_purge.sql' in source
    assert 'sql/v3/migration-manifest.txt' in source
    purge_operator = _action_tool()
    assert purge_operator.FQDN == 'nb79a3d.mevnode.com'
    assert purge_operator.HOST == 'ed-finder-prod'
    assert 'begin_derived_generation_purge' in source
    assert 'complete_derived_generation_purge' in source


def test_migration_hash_pin_is_the_exact_registered_016_bytes():
    module = _action_tool()
    migration = ROOT / 'sql/v3/migrations/016_v3_governed_derived_purge.sql'
    digest = hashlib.sha256(migration.read_bytes()).hexdigest()
    assert module.MIGRATION_SHA256 == digest
    manifest = (ROOT / 'sql/v3/migration-manifest.txt').read_text()
    registered = [line for line in manifest.splitlines()
                  if line and not line.startswith('#') and '016_v3_governed_derived_purge.sql' in line]
    assert len(registered) == 1 and digest in registered[0]


def test_wrapper_hash_mismatch_stops_and_preserves_both_files(tmp_path):
    module = _action_tool()
    source = tmp_path / 'committed-wrapper'
    installed = tmp_path / 'installed-wrapper'
    source.write_bytes(b'committed ledger-aware wrapper')
    installed.write_bytes(b'old wrapper')
    with pytest.raises(Exception, match='wrapper'):
        module.check_wrapper(source, installed)
    assert source.read_bytes() == b'committed ledger-aware wrapper'
    assert installed.read_bytes() == b'old wrapper'
    installed.write_bytes(source.read_bytes())
    module.check_wrapper(source, installed)


def test_action_and_helper_are_bound_into_operator_content_identity():
    from scripts.operator.lib import f2d_operator_identity

    entries = f2d_operator_identity.manifest_entries(ROOT)
    assert 'scripts/operator/actions/v3-derived-generation-purge.sh' in entries
    assert 'scripts/operator/lib/v3_generation_purge.py' in entries


def test_purge_lease_owner_still_checks_ledger(monkeypatch):
    module = _tool(monkeypatch)
    monkeypatch.setattr(module, 'lease_state', lambda: pytest.fail('owner must not probe its own lock'))
    report = module.check(_query(module), lease_held_by_caller=True)
    assert report['lease'] == 'held_by_caller'
    with pytest.raises(module.PurgeStateError, match='purge_unresolved_REWRITE_STARTED'):
        module.check(_query(module, kinds=('REWRITE_STARTED',)), lease_held_by_caller=True)


def _sealed_plan(module, path, *, age=0, **changes):
    now = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    body = module.receipt('plan')
    body.update(status='success', reviewed_plan={'plan_sha256': '1' * 64},
                created_at=(now - timedelta(seconds=age)).isoformat())
    body.update(changes)
    value = module.evidence.seal(body)
    path.write_text(json.dumps(value))
    return now, value


def test_plan_authentication_requires_the_external_expected_content_seal(tmp_path):
    module = _action_tool()
    path = tmp_path / 'plan.json'
    now, plan = _sealed_plan(module, path)
    assert module.authenticated_plan(path, plan['content_sha256'], now=now) == plan
    with pytest.raises(ValueError, match='plan_expected_sha256_mismatch'):
        module.authenticated_plan(path, '2' * 64, now=now)
    with pytest.raises(ValueError, match='plan_expected_sha256_invalid'):
        module.authenticated_plan(path, '../../untrusted', now=now)
    plan['reviewed_plan']['plan_sha256'] = '3' * 64
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match='plan_seal_invalid'):
        module.authenticated_plan(path, plan['content_sha256'], now=now)


@pytest.mark.parametrize('age', (-1, 3601, 86400))
def test_plan_authentication_refuses_future_or_expired_artifacts(tmp_path, age):
    module = _action_tool()
    path = tmp_path / 'plan.json'
    now, plan = _sealed_plan(module, path, age=age)
    with pytest.raises(ValueError, match='plan_expired_or_future'):
        module.authenticated_plan(path, plan['content_sha256'], now=now)


@pytest.mark.parametrize('changes', ({'status': 'stopped'}, {'phase': 'status'},
                                    {'reviewed_plan': None}, {'created_at': 'bad'}))
def test_correct_seal_does_not_authenticate_an_invalid_plan_contract(tmp_path, changes):
    module = _action_tool()
    path = tmp_path / 'plan.json'
    now, value = _sealed_plan(module, path)
    body = {key: field for key, field in value.items() if key != 'content_sha256'}
    body.update(changes)
    value = module.evidence.seal(body)
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='plan_'):
        module.authenticated_plan(path, value['content_sha256'], now=now)


def test_plan_symlink_is_not_accepted(tmp_path):
    module = _action_tool()
    path = tmp_path / 'plan.json'
    now, plan = _sealed_plan(module, path)
    link = tmp_path / 'plan-link.json'
    link.symlink_to(path)
    with pytest.raises(ValueError, match='plan_seal_invalid'):
        module.authenticated_plan(link, plan['content_sha256'], now=now)


@pytest.mark.parametrize('kind', ('heap', 'index', 'toast', 'toast-index'))
def test_any_payload_storage_object_on_another_device_stops(kind):
    module = _action_tool()
    with pytest.raises(ValueError, match='filesystem_mismatch'):
        module.check_placement(42, [{'device': 42}, {'device': 43, 'kind': kind}], [42], 42)


@pytest.mark.parametrize('temps,wal', (([43], 42), ([42], 43), ([], 42), ([None], 42)))
def test_unproved_temp_or_wal_placement_stops(temps, wal):
    module = _action_tool()
    with pytest.raises(ValueError, match='filesystem_mismatch'):
        module.check_placement(42, [{'device': 42}], temps, wal)
    assert module.check_placement(42, [{'device': 42}], [42], 42)


@pytest.mark.parametrize('outside', ('base/1/heap', 'pg_tblspc/index', 'pg_tblspc/toast',
                                  '/external/temp', 'pg_wal'))
def test_runtime_storage_checks_actual_devices_before_accepting_free_space(monkeypatch, outside):
    module = _action_tool()
    runtime = module.Runtime(module.receipt('plan'))
    directory = '/var/lib/postgresql/data'
    objects = [{'path': path} for path in ('base/1/heap', 'pg_tblspc/index', 'pg_tblspc/toast')]
    identity = {'data_directory': directory, 'temp_tablespaces': 'work',
                'tablespaces': [{'name': 'work', 'location': '/external/temp'}]}
    def device(path):
        return 43 if path in (outside, directory + '/' + outside) else 42
    monkeypatch.setattr(runtime, 'device', device)
    monkeypatch.setattr(runtime, 'docker', lambda *args, **kwargs:
                        pytest.fail('mismatched placement reached mount/free-space acceptance'))
    with pytest.raises(ValueError, match='filesystem_mismatch'):
        runtime.storage(identity, objects)


@pytest.mark.parametrize('tablespace,location,other_device', (
    ('pg_default', '', False),
    ('work', '/external/temp', False),
    ('work', '/external/temp', True),
))
def test_empty_temp_tablespaces_checks_database_default_device(
        tmp_path, monkeypatch, tablespace, location, other_device):
    module = _action_tool()
    runtime = module.Runtime(module.receipt('plan'))
    device = tmp_path.stat().st_dev
    observed = []
    def docker(*args, **kwargs):
        if args[:2] == ('exec', module.CONTAINER):
            assert args[2:7] == ('stat', '-L', '-c', '%d', '--')
            observed.append(args[-1])
            return str(device + 1 if other_device and args[-1] == location else device)
        assert not other_device, 'unproved placement reached free-space acceptance'
        assert args == ('inspect', '-f', '{{json .Mounts}}', module.CONTAINER)
        return json.dumps([{'Source': str(tmp_path), 'Destination': '/data'}])
    monkeypatch.setattr(runtime, 'docker', docker)
    identity = {'data_directory': '/data', 'temp_tablespaces': '',
                'database_tablespace': tablespace,
                'tablespaces': [{'name': tablespace, 'location': location}]}
    objects = [{'path': 'base/1/heap'}]
    if other_device:
        with pytest.raises(ValueError, match='tablespace_or_wal_filesystem_mismatch'):
            runtime.storage(identity, objects)
    else:
        assert runtime.storage(identity, objects)['free_bytes'] > 0
        assert runtime.report['data_mount']['temp_devices'] == [device]
    assert (location or '/data') in observed


@pytest.mark.parametrize('tablespace,locations', (
    (None, []),
    ('missing', []),
    ('work', [{'name': 'work', 'location': ''}]),
    ('work', [{'name': 'work', 'location': None}]),
    ('work', [{'name': 'work', 'location': 'relative/path'}]),
))
def test_empty_temp_tablespaces_requires_proven_database_default(monkeypatch, tablespace, locations):
    module = _action_tool()
    runtime = module.Runtime(module.receipt('plan'))
    def docker(*args, **kwargs):
        assert args[:2] == ('exec', module.CONTAINER), 'unproved placement reached free-space acceptance'
        return '42'
    monkeypatch.setattr(runtime, 'docker', docker)
    with pytest.raises(ValueError, match='tablespace_or_wal_filesystem_mismatch'):
        runtime.storage({'data_directory': '/data', 'temp_tablespaces': '',
                         'database_tablespace': tablespace, 'tablespaces': locations},
                        [{'path': 'base/1/heap'}])


def test_lease_contention_refuses_without_changing_existing_lease(tmp_path, monkeypatch):
    module = _action_tool()
    lease = tmp_path / 'lease'
    lease.write_bytes(b'unchanged')
    monkeypatch.setattr(module, 'LEASE', lease)
    runtime = module.Runtime(module.receipt('authorize'))
    with lease.open() as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match='purge_host_lease_held'), runtime.lease():
            pytest.fail('contended lease admitted')
    assert runtime.lease_fd is None
    assert lease.read_bytes() == b'unchanged'
    with runtime.lease():
        assert module.purge_state.lease_state(lease) == 'held'
    assert module.purge_state.lease_state(lease) == 'free'


@pytest.mark.parametrize('guard_failure', ('host', 'fqdn', 'context', 'endpoint', 'container'))
def test_pinned_host_context_and_container_guards_stop_before_database(monkeypatch, guard_failure):
    module = _action_tool()
    report = module.receipt('authorize')
    runtime = module.Runtime(report)
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        if argv == ['hostname', '-s']:
            return 'wrong-host' if guard_failure == 'host' else module.HOST
        if argv == ['hostname', '-f']:
            return 'wrong.example' if guard_failure == 'fqdn' else module.FQDN
        if argv == ['docker', 'context', 'show']:
            return 'other' if guard_failure == 'context' else 'default'
        if argv[:5] == ['docker', '--context', 'default', 'context', 'inspect']:
            endpoint = 'tcp://remote:2375' if guard_failure == 'endpoint' else 'unix:///var/run/docker.sock'
            return json.dumps([{'Endpoints': {'docker': {'Host': endpoint}}}])
        if 'inspect' in argv:
            return 'false' if guard_failure == 'container' else 'true'
        pytest.fail(f'guard failure reached unexpected command: {argv}')
    monkeypatch.setattr(runtime, 'run', run)
    with pytest.raises(ValueError):
        runtime.guard()
    assert not any('psql' in command for command in calls)
    assert report['db_writes_performed'] is False


def test_query_binds_hostile_values_as_hex_data_and_pins_psql(monkeypatch):
    module = _action_tool()
    report = module.receipt('plan')
    runtime = module.Runtime(report)
    observed = []
    def docker(*argv, **kwargs):
        observed.append((argv, kwargs))
        return '{"ok":true}'
    monkeypatch.setattr(runtime, 'docker', docker)
    hostile = "'); DROP TABLE v3_meta.derived_generation; --\\n\\! touch /tmp/pwned"
    sql = module.read_sql('SELECT jsonb_build_object(\'data\',%(value)s)')
    assert runtime.query(sql, {'value': hostile}) == {'ok': True}
    argv, kwargs = observed[0]
    assert module.CONTAINER in argv and module.USER in argv and module.DATABASE in argv
    assert all(flag in argv for flag in ('-X', '--no-psqlrc', '--no-password', '--file=-'))
    assert hostile not in kwargs['input'] and hostile.encode().hex() in kwargs['input']
    assert kwargs['input'].count('SET ROLE v3_derived_purge_executor') == 1
    assert report['db_writes_performed'] is False
    for params in ({'invalid; SELECT 1': 'x'}, {}):
        with pytest.raises(ValueError):
            runtime.query(sql, params)
    assert len(observed) == 1


def test_unknown_commit_outcome_is_null_and_does_not_leak_subprocess_error(monkeypatch):
    module = _action_tool()
    report = module.receipt('authorize')
    runtime = module.Runtime(report)
    def broken(*args, **kwargs):
        raise RuntimeError('connection interrupted')
    monkeypatch.setattr(runtime, 'docker', broken)
    with pytest.raises(RuntimeError):
        runtime.query('fixed mutation function transaction', write=True)
    assert report['db_writes_performed'] is None
    assert report['transaction_outcome'] is None


@pytest.mark.parametrize('workers,stopped,expected', (
    ([{'name': 'known', 'running': False, 'exists': True}], True, True),
    ([{'name': 'known', 'running': True, 'exists': True}], False, False),
    ([{'name': 'known', 'running': False, 'exists': False}], True, True),
))
def test_worker_gate_uses_current_lifecycle_action(monkeypatch, workers, stopped, expected):
    module = _action_tool()
    runtime = module.Runtime(module.receipt('plan'))
    observed = []
    def run(argv, **kwargs):
        observed.append(argv)
        return json.dumps({'workers': workers, 'all_named_workers_stopped': stopped})
    monkeypatch.setattr(runtime, 'run', run)
    assert runtime.workers() is expected
    assert observed == [['bash', str(ROOT / 'scripts/operator/actions/v3-derived-lifecycle-status.sh')]]


@pytest.mark.parametrize('workers', ([], None, [{'name': 'unknown', 'running': None}]))
def test_worker_gate_refuses_unknown_or_absent_proof(monkeypatch, workers):
    module = _action_tool()
    runtime = module.Runtime(module.receipt('plan'))
    monkeypatch.setattr(runtime, 'run', lambda *args, **kwargs:
                        json.dumps({'workers': workers, 'all_named_workers_stopped': True}))
    with pytest.raises(ValueError, match='worker_state_unknown'):
        runtime.workers()


def test_receipt_has_full_shared_evidence_schema_and_unobserved_nulls():
    module = _action_tool()
    result = module.receipt('status')
    for key in ('schema_version', 'operation', 'phase', 'status', 'result', 'failures',
                'workflow_run_id', 'source_git_sha', 'script_sha256', 'migration_live_sha256',
                'migration_expected_sha256', 'migration_set_identity', 'migration_verified',
                'host', 'fqdn', 'container', 'database', 'postgresql_version', 'data_mount',
                'purge_id', 'reviewed_plan_sha256', 'targets', 'pointers_before', 'pointers_after',
                'workers', 'relation', 'batch_limit', 'rows_affected_this_run',
                'rows_affected_cumulative', 'rows_remaining', 'survivors_before', 'survivors_after',
                'fk_check', 'relation_bytes_before', 'relation_bytes_after', 'filesystem_before',
                'filesystem_after', 'wal_before', 'wal_after', 'wal_byte_delta', 'archive_status',
                'replication_slots', 'checkpoint_counters', 'temp_bytes', 'backend_state',
                'runner_state', 'rewrite_started_at', 'rewrite_completed_at', 'transaction_outcome',
                'lock_timeout', 'statement_timeout', 'wall_clock_timeout_seconds', 'reserve_bytes',
                'abort_threshold_bytes', 'competing_writer_wait'):
        assert key in result
    for key in ('fk_check', 'migration_verified', 'transaction_outcome', 'survivors_after',
                'filesystem_after', 'wal_after'):
        assert result[key] is None
    flags = ('db_writes_performed', 'canonical_writes_performed', 'pointer_changes_performed',
             'publication_performed', 'service_changes_performed', 'filesystem_reclamation_performed',
             'migration_execution_performed', 'application_deployment_performed')
    assert all(result[key] is False for key in flags)
    assert result['reserve_bytes'] == 100_000_000_000


def _preflight_runtime(module, monkeypatch, failure):
    report = module.receipt('authorize')
    report.update(source_git_sha='1' * 40, script_sha256='2' * 64)
    identity = {'database': module.DATABASE, 'session_user': module.USER,
                'current_user': 'v3_derived_purge_executor', 'version': 180000,
                'migration_sha256': module.MIGRATION_SHA256, 'writer_fence_owner': module.USER,
                'writer_fence_owner_permitted': True, 'role_defaults': [], 'data_directory': '/data'}
    if failure == 'migration':
        identity['migration_sha256'] = 'f' * 64
    if failure == 'writer-authority':
        identity['writer_fence_owner_permitted'] = False
    if failure == 'already-readonly':
        identity['role_defaults'] = ['default_transaction_read_only=on']
    snapshot = {'canonical': {'generation_id': 'canonical'},
                'derived': {'derived_generation_id': module.PUBLISHED_ID},
                'spatial': {'spatial_generation_id': 'spatial'}, 'survivors': {},
                'schema_ledger_sha256': '3' * 64}
    observed = {'snapshot': snapshot, 'targets': [
        {'id': target_id, 'key': key, 'state': state, 'manifest_sha256': '4' * 64,
         'payload_counts': {code: 0 for code in module.RELATIONS.values()}}
        for key, (target_id, state) in module.TARGETS.items()]}
    published = {'key': module.PUBLISHED_KEY, 'state': 'PUBLISHED', 'manifest_sha256': '5' * 64}
    wal = {'archive_mode': 'on', 'archiver': {'failed_count': 0, 'last_failed_time': None,
                                           'last_archived_time': None},
           'slots': [], 'checkpoints': {}, 'temp_bytes': 0}
    if failure == 'wal':
        wal['slots'] = [{'active': False, 'wal_status': 'reserved'}]
    calls = []
    def query(sql, params=None, *, write=False):
        calls.append((sql, write))
        assert write is False, 'preflight failure reached a database mutation'
        if sql == module.IDENTITY_SQL:
            return identity
        if sql == module.MIGRATION_LEDGER_SQL:
            return [{key: entry[key] for key in ('ledger_name', 'sha256')}
                    for entry in module.schema_identity.derive_entries(ROOT)]
        if "'snapshot',v3_meta.purge_snapshot()" in sql:
            return observed
        if sql == module.OBJECTS_SQL:
            return [{'valid': failure != 'index', 'path': 'base/heap'}]
        if sql == module.WAL_SQL:
            return wal
        if "'manifest_sha256',encode(manifest_sha256,'hex')" in sql:
            return published
        pytest.fail('unexpected SQL reached beyond requested preflight stop')
    def state(**kwargs):
        if failure == 'ledger':
            raise ValueError('purge_unresolved_REWRITE_STARTED')
        return {'unresolved': []}
    def storage(*args):
        if failure == 'placement':
            raise ValueError('tablespace_or_wal_filesystem_mismatch')
        return {'free_bytes': 99_000_000_000 if failure == 'disk' else 101_000_000_000}
    def wrapper():
        if failure == 'wrapper':
            raise ValueError('installed_backup_wrapper_hash_mismatch')
        return 'a' * 64, 'a' * 64
    monkeypatch.setattr(module, 'check_wrapper', wrapper)
    def autovacuum(runtime):
        if failure == 'freeze-age':
            raise ValueError('autovacuum_fence_deadline_unsafe')
        return {'configuration': {}}
    monkeypatch.setattr(module, 'measure_autovacuum', autovacuum)
    runtime = SimpleNamespace(state=state, query=query, storage=storage,
                              data_directory=lambda: '/data',
                              workers=lambda: failure != 'workers',
                              docker=lambda *args, **kwargs: '0 /data/pg_wal')
    plan = {'source_git_sha': '9' * 40, 'script_sha256': '2' * 64,
            'published_generation': published, 'reviewed_plan': {'plan_sha256': '6' * 64}}
    return report, runtime, plan, calls


@pytest.mark.parametrize('failure', ('ledger', 'migration', 'writer-authority', 'already-readonly',
                                   'index', 'placement', 'disk', 'wrapper', 'workers', 'freeze-age',
                                   'wal', 'source-drift'))
def test_shared_preflight_failure_never_reaches_a_mutation(monkeypatch, failure):
    module = _action_tool()
    report, runtime, plan, calls = _preflight_runtime(module, monkeypatch, failure)
    expected = {'ledger': 'purge_unresolved_REWRITE_STARTED',
                'migration': 'database_or_guard_migration_identity_mismatch',
                'writer-authority': 'writer_fence_owner_precondition_failed',
                'already-readonly': 'application_role_already_read_only_or_unknown',
                'index': 'relation_or_index_evidence_invalid',
                'placement': 'tablespace_or_wal_filesystem_mismatch',
                'disk': 'filesystem_free_space_floor',
                'wrapper': 'installed_backup_wrapper_hash_mismatch',
                'workers': 'named_workers_not_stopped',
                'freeze-age': 'autovacuum_fence_deadline_unsafe',
                'wal': 'wal_retention_unhealthy',
                'source-drift': 'plan_source_or_script_changed'}
    with pytest.raises(ValueError, match=expected[failure]):
        module.execute('authorize', runtime, report, plan)
    assert all(not write for _sql, write in calls)
    assert report['db_writes_performed'] is False
    assert report['canonical_writes_performed'] is False
    assert report['service_changes_performed'] is False
    assert report['wal_byte_delta'] is None


@pytest.mark.parametrize('mode,expected', (
    ('delete-system-search', 'sealed_verification_required'),
    ('rewrite-system-search', 'mode_not_implemented_until_p2b2b'),
    ('restore-services', 'sealed_verification_required'),
    ('delete-system-archetype', 'unknown_mode'),
))
def test_cli_mode_refusal_is_json_only_and_precedes_all_host_access(mode, expected):
    process = subprocess.run(['bash', str(ROOT / 'scripts/operator/actions/v3-derived-generation-purge.sh'), mode],
                             capture_output=True, text=True, check=False)
    assert process.returncode == 1 and process.stderr == ''
    result = json.loads(process.stdout)
    assert result['failures'] == [expected]
    assert result['db_writes_performed'] is False
    assert result['host'] is None
    body = {key: value for key, value in result.items() if key != 'content_sha256'}
    assert _action_tool().evidence.canonical_sha256(body) == result['content_sha256']


@pytest.mark.parametrize('failure', ('counter', 'timestamp', 'inactive-slot', 'extended-slot'))
def test_gate_two_rejects_both_archiver_failures_and_slot_retention(failure):
    module = _action_tool()
    before = {'archive_mode': 'on', 'archiver': {'failed_count': 1, 'last_failed_time': None,
                                              'last_archived_time': '2026-10-15T12:00:00+00:00'},
              'slots': []}
    after = json.loads(json.dumps(before))
    if failure == 'counter':
        # A success after the failure does not erase the counter evidence.
        after['archiver'].update(failed_count=2, last_failed_time='2026-10-15T11:59:00+00:00')
    elif failure == 'timestamp':
        after['archiver']['last_failed_time'] = '2026-10-15T12:01:00+00:00'
    else:
        after['slots'] = [{'active': failure != 'inactive-slot',
                           'wal_status': 'extended' if failure == 'extended-slot' else 'reserved'}]
    with pytest.raises(ValueError, match='archiver_|wal_retention_'):
        module.wal_health(before, after)
    module.wal_health(before, before)


def test_plan_refuses_a_freeze_deadline_before_the_planning_horizon(monkeypatch):
    module = _action_tool()
    samples = []
    for xid in (100, 200):
        samples.append({'xid_next': str(xid), 'objects': [
            {'relation_code': code, 'scope': 'heap', 'oid': index + 1, 'relminmxid': '1',
             'xid_age': 100, 'mxid_age': 100, 'xid_limit': 1000, 'mxid_limit': 1000}
            for index, code in enumerate(module.RELATIONS.values())]})
    clock = iter((0, 5))
    monkeypatch.setattr(module.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(module.time, 'sleep', lambda _: None)
    runtime = SimpleNamespace(query=lambda _: samples.pop(0))
    with pytest.raises(ValueError, match='autovacuum_fence_deadline_unsafe'):
        module.measure_autovacuum(runtime)


def test_open_autovacuum_status_reports_both_rates_and_the_nearer_ceiling():
    module = _action_tool()
    ages = {'objects': [{'relation_code': 'system_search', 'scope': 'heap',
                         'xid_age': 100, 'mxid_age': 50}]}
    state = {'unresolved': [{'event_kind': 'AUTOVACUUM_DISABLED', 'event_sequence': 7,
                              'relation_code': 'system_search'}]}
    progress = {'events': [{'event_sequence': 7, 'operational_payload': {'heap': {
        'xid_ceiling': 200, 'mxid_ceiling': 250, 'xid_rate': 10, 'mxid_rate': 10}}}]}
    result = module.status_deadlines(ages, state, progress)
    assert result[0]['xid_seconds_to_ceiling'] == 10
    assert result[0]['mxid_seconds_to_ceiling'] == 20
    assert result[0]['nearer_ceiling_seconds'] == 10
    assert result[0]['ceiling_exceeded'] is False


def _successful_phase(module, monkeypatch, mode, *, open_fence=False):
    """Exercise real controller/transaction dispatch over a disposable SQL model."""
    transactions = module._load('v3_purge_transactions')
    report = module.receipt(mode)
    report.update(source_git_sha='1' * 40, script_sha256='2' * 64)
    identity = {'database': module.DATABASE, 'session_user': module.USER,
                'current_user': 'v3_derived_purge_executor', 'version': 180000,
                'migration_sha256': module.MIGRATION_SHA256, 'writer_fence_owner': module.USER,
                'writer_fence_owner_permitted': True, 'role_defaults': [], 'data_directory': '/data'}
    snapshot = {'canonical': {'generation_id': 'canonical', 'publication_sequence': 1},
                'derived': {'derived_generation_id': module.PUBLISHED_ID, 'publication_sequence': 1},
                'spatial': {'spatial_generation_id': 'spatial', 'publication_sequence': 1},
                'retained': {'generation': 3, 'products': 2},
                'survivors': {code: 7 for code in module.RELATIONS.values()},
                'schema_ledger_sha256': '3' * 64}
    targets = [{'id': identity_, 'key': key, 'state': state, 'manifest_sha256': '4' * 64,
                'payload_counts': dict.fromkeys(transactions.RELATIONS, 0)}
               for identity_, key, state in sorted(transactions.TARGET_IDENTITIES)]
    published = {'key': module.PUBLISHED_KEY, 'state': 'PUBLISHED', 'manifest_sha256': '5' * 64}
    extra_codes = ('cluster_run', 'cluster', 'cluster_member', 'system_archetype')
    extra_counts = {identity_: dict.fromkeys(extra_codes, 0) for identity_ in transactions.TARGET_IDS}
    extra_counts[module.PUBLISHED_ID] = dict.fromkeys(extra_codes, 7)
    pointer_identities = {**snapshot, 'canonical': {**snapshot['canonical'], 'generation_key': 'canonical-key'},
                          'derived': {**snapshot['derived'], 'generation_key': module.PUBLISHED_KEY},
                          'spatial': {**snapshot['spatial'], 'canonical_generation_id': 'canonical',
                                      'pyramid_version': 'spatial-pyramid-v1'}}
    reviewed = {'snapshot': snapshot, 'targets': targets, 'workers_stopped': True,
                'plan_sha256': '6' * 64, 'source_git_sha': report['source_git_sha'],
                'actor': 'operator', 'reason': 'reviewed purge',
                'extra_payload_counts': extra_counts, 'pointer_identities': pointer_identities}
    plan = {'source_git_sha': report['source_git_sha'], 'script_sha256': report['script_sha256'],
            'reviewed_plan': reviewed, 'published_generation': published}
    ids = list(transactions.TARGET_IDS)
    current = {'failed': mode in ('verify-system-archetype-empty', 'complete', 'status'), 'writes': 0}
    calls = []
    fence = {'event_kind': 'WRITER_FENCE_ENABLED', 'event_sequence': 7, 'relation_code': None}
    state = {'unresolved': [fence] if open_fence else []}
    ages = {'xid_next': '100', 'objects': [
        {'relation_code': code, 'scope': 'heap', 'oid': index + 1, 'relminmxid': '1',
         'xid_age': 100, 'mxid_age': 100, 'xid_limit': 1000000, 'mxid_limit': 1000000}
        for index, code in enumerate(module.RELATIONS.values())]}
    def observe():
        result = json.loads(json.dumps({'snapshot': snapshot, 'targets': targets}))
        if current['failed']:
            for target in result['targets']:
                target['state'] = 'FAILED'
        return result
    def query(sql, params=None, *, write=False):
        calls.append(('query', sql, write))
        if write:
            current['writes'] += 1
            report.update(db_writes_performed=True, transaction_outcome='committed')
        if sql == module.IDENTITY_SQL:
            if open_fence:
                identity['role_defaults'] = ['default_transaction_read_only=on']
            return identity
        if sql == module.MIGRATION_LEDGER_SQL:
            return [{key: entry[key] for key in ('ledger_name', 'sha256')}
                    for entry in module.schema_identity.derive_entries(ROOT)]
        if sql in (transactions.PLAN_SQL, module.STATUS_METADATA_SQL):
            return observe()
        if sql in module.STATUS_RELATION_SQL.values():
            code = next(code for code, query_sql in module.STATUS_RELATION_SQL.items() if sql == query_sql)
            return {'targets': {target['id']: target['payload_counts'][code] for target in targets},
                    'survivors': snapshot['survivors'][code], 'total_bytes': 60}
        if sql == module.OBJECTS_SQL:
            return [{'valid': True, 'path': 'base/heap', 'heap_bytes': 40, 'index_bytes': 20,
                     'total_bytes': 60}]
        if sql == module.WAL_SQL:
            return {'lsn': '0/10', 'archive_mode': 'on', 'archiver': {'failed_count': 0, 'last_failed_time': None,
                                                      'last_archived_time': None},
                    'slots': [], 'checkpoints': {}, 'temp_bytes': 0}
        if sql == module.WAL_LSN_DIFF_SQL:
            assert params == {'before_lsn': '0/10', 'after_lsn': '0/10'}
            return {'wal_byte_delta': 0}
        if sql == module.AGES_SQL:
            return ages
        if sql == module.PROGRESS_SQL:
            return {'requests': [{'purge_id': identity_, 'plan_sha256': '6' * 64} for identity_ in ids],
                    'events': [], 'backends': []}
        if sql == module.EXTRA_COUNTS_SQL:
            return extra_counts
        if sql == module.POINTER_IDENTITIES_SQL:
            return pointer_identities
        if sql == transactions.PLAN_HASH_SQL:
            return {'plan_sha256': '6' * 64}
        if sql == transactions.EXCLUSIONS_SQL:
            return dict.fromkeys(('cluster_run', 'cluster', 'cluster_member', 'system_archetype'), 0)
        if sql == transactions.COMPETING_WRITER_SQL:
            return {'competing_writers': 0, 'background_writers': 0}
        if sql == transactions.AUTHORIZE_SQL:
            assert write and json.loads(params['plan']) == reviewed
            current['failed'] = True
            return {'purge_ids': ids, 'snapshot': snapshot, 'verified': 1}
        if sql == transactions.PLAN_REQUEST_IDS_SQL:
            return {'purge_ids': ids}
        if sql == transactions.REQUESTS_SQL:
            return {'requests': [{'purge_id': identity_, 'derived_generation_id': identity_,
                                  'frozen_snapshot': snapshot, 'plan_sha256': '6' * 64}
                                 for identity_ in ids]}
        if sql == transactions.COMPLETION_STATE_SQL:
            return {**observe(), 'rewrites': list(transactions.RELATIONS),
                    'invalid_foreign_keys': 0, 'invalid_indexes': 0, 'invalid_triggers': 0}
        if sql == transactions.COMPLETE_SQL:
            assert write
            completion = json.loads(params['receipt'])
            assert completion['filesystem_free_bytes'] > module.FREE_FLOOR_BYTES
            assert completion['wal_bytes'] == 10
            return {'completed_ids': ids, 'verified': 2, 'snapshot': snapshot, 'snapshot_verified': 1}
        if "'manifest_sha256',encode(manifest_sha256,'hex')" in sql:
            return published
        pytest.fail('unexpected SQL in successful phase')
    def state_check(**kwargs):
        calls.append(('state', kwargs))
        return state
    def workers():
        report['workers'] = [{'name': 'named-worker', 'running': False}]
        return True
    runtime = SimpleNamespace(state=state_check, query=query,
                              storage=lambda *_: {'total_bytes': 200_000_000_000,
                                                  'used_bytes': 50_000_000_000,
                                                  'free_bytes': 150_000_000_000},
                              data_directory=lambda: '/data', workers=workers,
                              status_workers=workers,
                              docker=lambda *args, **kwargs: '10 /data/pg_wal',
                              run=lambda *args, **kwargs: json.dumps({'MESSAGE': 'SKIP: active purge backend'}))
    monkeypatch.setattr(module, 'check_wrapper', lambda: ('a' * 64, 'a' * 64))
    monkeypatch.setattr(module, 'measure_autovacuum', lambda _: {'configuration': {}})
    return report, runtime, plan, calls


@pytest.mark.parametrize('mode,write_count', (('plan', 0), ('status', 0), ('authorize', 1),
                                            ('verify-system-archetype-empty', 0), ('complete', 1)))
def test_successful_controller_phases_keep_truthful_evidence_and_transaction_flags(monkeypatch, mode, write_count):
    module = _action_tool()
    report, runtime, plan, calls = _successful_phase(module, monkeypatch, mode)
    verification = {'purge_id': list(module.TARGETS[key][0] for key in module.TARGETS),
                    'reviewed_plan_sha256': plan['reviewed_plan']['plan_sha256'], 'content_sha256': '7' * 64}
    module.execute(mode, runtime, report, None if mode in ('plan', 'status') else plan,
                   verification=verification if mode == 'complete' else None)
    assert report['status'] == 'success'
    assert report['wal_byte_delta'] == (None if mode == 'status' else 0)
    assert calls[0][0] == 'state'
    writes = [call for call in calls if call[0] == 'query' and call[2]]
    assert len(writes) == write_count
    assert report['db_writes_performed'] is bool(write_count)
    assert report['canonical_writes_performed'] is False
    assert report['publication_performed'] is False
    assert report['service_changes_performed'] is False
    ledger_reads = [call for call in calls if call[0] == 'query' and call[1] == module.MIGRATION_LEDGER_SQL]
    assert len(ledger_reads) == {'plan': 3, 'status': 0, 'authorize': 2,
                                 'verify-system-archetype-empty': 1, 'complete': 2}[mode]
    if mode == 'status':
        assert report['next_admissible_mode'] == {'mode': 'verify-system-archetype-empty', 'implemented': True,
                                                'reason': 'system_archetype_empty_not_proven'}
        assert report['system_archetype_verification']['status'] == 'not_proven'
        assert report['workers'][0]['running'] is False
        assert len(report['skipped_scheduled_backups']['records']) == 1
    elif mode == 'verify-system-archetype-empty':
        assert report['pointers_after'] is None and report['survivors_after'] is None
    else:
        assert report['pointers_after'] == report['pointers_before']
        assert report['survivors_after'] == report['survivors_before']
        assert report['installed_wrapper_sha256'] == report['expected_wrapper_sha256']
    if mode == 'authorize':
        assert all(target['current_state'] == 'FAILED' for target in report['targets'])
        assert report['purge_id'] == list(module.TARGETS[key][0] for key in module.TARGETS)
        assert report['competing_writer_wait']['remaining_competing_writers'] == 0
    if mode == 'complete':
        assert report['fk_check'] is True
        assert report['completion_receipt']['receipt_sha256']


@pytest.mark.parametrize('mode', ('plan', 'authorize', 'complete'))
@pytest.mark.parametrize('drift', ('extra', 'missing', 'checksum', 'guard-checksum', 'reordered'))
@pytest.mark.parametrize('observation', (1, 2))
def test_unreviewed_live_migration_ledger_stops_before_seal_or_mutation(
        monkeypatch, mode, drift, observation):
    module = _action_tool()
    report, runtime, plan, calls = _successful_phase(module, monkeypatch, mode)
    original_query = runtime.query
    ledger_reads = 0

    def query(sql, params=None, *, write=False):
        nonlocal ledger_reads
        result = original_query(sql, params, write=write)
        if sql == module.MIGRATION_LEDGER_SQL:
            ledger_reads += 1
            if ledger_reads == observation:
                if drift == 'extra':
                    result.append({'ledger_name': '017_unreviewed.sql', 'sha256': 'f' * 64})
                elif drift == 'missing':
                    result.pop(0)  # Keep 016 present: its checksum alone is insufficient.
                elif drift == 'checksum':
                    result[0]['sha256'] = 'f' * 64
                elif drift == 'guard-checksum':
                    result[-1]['sha256'] = 'f' * 64
                else:
                    result[0], result[1] = result[1], result[0]
        return result

    runtime.query = query
    verification = {'purge_id': [module.TARGETS[key][0] for key in module.TARGETS],
                    'reviewed_plan_sha256': plan['reviewed_plan']['plan_sha256'],
                    'content_sha256': '7' * 64}
    with pytest.raises(ValueError, match='^live_migration_ledger_unreviewed$'):
        module.execute(mode, runtime, report, None if mode == 'plan' else plan,
                       verification=verification if mode == 'complete' else None)
    assert ledger_reads == observation
    assert not any(call[0] == 'query' and call[2] for call in calls)
    if mode == 'plan':
        # collect_plan hashes its initial observation; the final reviewed plan
        # must never be sealed or recorded after ledger drift is discovered.
        assert report.get('reviewed_plan') is None
        hash_sql = module._load('v3_purge_transactions').PLAN_HASH_SQL
        assert sum(call[0] == 'query' and call[1] == hash_sql for call in calls) == observation - 1
    assert report['db_writes_performed'] is False
    assert report['status'] == 'stopped'


def test_live_migration_ledger_uses_the_migration_runner_order():
    module = _action_tool()
    assert 'ORDER BY applied_at,migration_name' in module.MIGRATION_LEDGER_SQL
    assert module.MIGRATION_LEDGER_SQL.startswith('SET ROLE v3_derived_purge_executor;')
    assert 'BEGIN READ ONLY;' in module.MIGRATION_LEDGER_SQL


def test_status_stays_available_for_open_writer_fence_and_reports_recovery_first(monkeypatch):
    module = _action_tool()
    report, runtime, _plan, calls = _successful_phase(module, monkeypatch, 'status', open_fence=True)
    module.execute('status', runtime, report)
    assert report['result'] == 'unresolved_state_first'
    assert report['writer_fence']['role_defaults'] == ['default_transaction_read_only=on']
    assert report['next_admissible_mode'] == {'mode': 'restore-services', 'implemented': True}
    assert not any(call[0] == 'query' and call[2] for call in calls)


def test_host_gates_are_refreshed_after_exact_counts_before_authorization(monkeypatch):
    module = _action_tool()
    report, runtime, plan, calls = _successful_phase(module, monkeypatch, 'authorize')
    observations = 0
    def storage(*args):
        nonlocal observations
        observations += 1
        return {'free_bytes': 150_000_000_000 if observations == 1 else 99_000_000_000}
    runtime.storage = storage
    with pytest.raises(ValueError, match='filesystem_free_space_floor'):
        module.execute('authorize', runtime, report, plan)
    assert observations == 2
    assert report['db_writes_performed'] is False
    assert not any(call[0] == 'query' and call[2] for call in calls)
    assert report['status'] == 'stopped'


@pytest.mark.parametrize('remaining,expected', ((1, 'abort-relation-system-search'),
                                               (0, 'rewrite-system-search')))
def test_expired_autovacuum_fence_never_recommends_another_delete(remaining, expected):
    module = _action_tool()
    state = {'unresolved': [{'event_kind': 'AUTOVACUUM_DISABLED', 'relation_code': 'system_search',
                              'event_sequence': 1}]}
    progress = {'requests': [{'purge_id': 'request'}], 'events': []}
    counts = {'targets': [{'payload_counts': {'system_search': remaining}}]}
    deadlines = [{'relation_code': 'system_search', 'ceiling_exceeded': True}]
    result = module.next_mode(state, progress, counts, deadlines=deadlines)
    assert result['mode'] == expected
    assert result['implemented'] is (not expected.startswith('rewrite-'))


def test_sql_adapter_binds_sha256_parameter_names_used_by_later_phases(monkeypatch):
    module = _action_tool()
    runtime = module.Runtime(module.receipt('complete'))
    calls = []
    def docker(*argv, **kwargs):
        calls.append(kwargs['input'])
        return '{"ok":true}'
    monkeypatch.setattr(runtime, 'docker', docker)
    runtime.query(module.read_sql("SELECT jsonb_build_object('plan',%(plan_sha256)s)"),
                  {'plan_sha256': 'a' * 64})
    assert "\\set plan_sha256 '" in calls[0]
    assert "decode(:'plan_sha256','hex')" in calls[0]


@pytest.mark.parametrize('response,epoch,valid', (
    ('/data\n100', 100, True),
    ('/data\n101', 100, False),
    ('/data', 100, False),
    ('relative\n100', 100, False),
    ('/data/../elsewhere\n100', 100, False),
))
def test_data_directory_pid_file_must_match_live_sql_start_epoch(monkeypatch, response, epoch, valid):
    module = _action_tool()
    report = module.receipt('plan')
    report['postmaster_started_epoch'] = epoch
    runtime = module.Runtime(report)
    monkeypatch.setattr(runtime, 'docker', lambda *args, **kwargs: response)
    if valid:
        assert runtime.data_directory() == '/data'
    else:
        with pytest.raises(ValueError, match='data_directory_unresolved'):
            runtime.data_directory()


def test_status_preserves_current_ages_instead_of_fence_time_ages():
    module = _action_tool()
    ages = {'objects': [{'relation_code': 'system_search', 'scope': 'heap',
                         'xid_age': 150, 'mxid_age': 80}]}
    state = {'unresolved': [{'event_kind': 'AUTOVACUUM_DISABLED', 'event_sequence': 7,
                            'relation_code': 'system_search'}]}
    progress = {'events': [{'event_sequence': 7, 'operational_payload': {'heap': {
        'xid_age': 100, 'mxid_age': 50, 'xid_ceiling': 200, 'mxid_ceiling': 250,
        'xid_rate': 10, 'mxid_rate': 10}}}]}
    observed = module.status_deadlines(ages, state, progress)[0]
    assert observed['xid_age'] == 150 and observed['mxid_age'] == 80
    assert observed['ages_at_fence'] == {'xid_age': 100, 'mxid_age': 50}
    assert observed['nearer_ceiling_seconds'] == 5


def test_floor_filesystem_must_match_container_data_device(tmp_path, monkeypatch):
    module = _action_tool()
    runtime = module.Runtime(module.receipt('plan'))
    host_device = tmp_path.stat().st_dev
    monkeypatch.setattr(runtime, 'device', lambda _: host_device + 1)
    monkeypatch.setattr(runtime, 'docker', lambda *args, **kwargs: json.dumps([
        {'Source': str(tmp_path), 'Destination': '/data'},
    ]))
    with pytest.raises(ValueError, match='host_data_mount_device_mismatch'):
        runtime.storage({'data_directory': '/data', 'temp_tablespaces': '',
                         'database_tablespace': 'pg_default',
                         'tablespaces': [{'name': 'pg_default', 'location': ''}]},
                        [{'path': 'base/1/heap'}])


def _verification_receipt(module, tmp_path, **changes):
    body = {
        'operation': 'v3-derived-generation-purge', 'phase': 'verify-system-archetype-empty',
        'status': 'success', 'created_at': '2020-01-01T00:00:00+00:00',
        'reviewed_plan_sha256': 'a' * 64,
        'purge_id': ['49a0c00d-e722-4209-afd8-9d62b877e30a',
                     '403b2d43-820c-414a-ad57-0d4de0ca3e82'],
        'result': {'empty': True, 'counts': dict.fromkeys(
            ('cluster_run', 'cluster', 'cluster_member', 'system_archetype'), 0),
            'database_writes': False},
        **changes,
    }
    proof = module.evidence.seal(body)
    path = tmp_path / 'verification.json'
    path.write_text(json.dumps(proof))
    return path, proof


def test_authenticated_verification_accepts_durable_old_receipt_and_exact_ledger_binding(tmp_path):
    module = _action_tool()
    path, proof = _verification_receipt(module, tmp_path)
    authenticated = module.authenticated_verification(path, proof['content_sha256'])
    assert authenticated == proof
    requests = [{'purge_id': purge_id, 'plan_sha256': proof['reviewed_plan_sha256']}
                for purge_id in reversed(proof['purge_id'])]
    assert module.verification_gate(authenticated, requests) == {
        'status': 'proven', 'content_sha256': proof['content_sha256'],
        'reviewed_plan_sha256': proof['reviewed_plan_sha256'], 'purge_ids': proof['purge_id']}


@pytest.mark.parametrize('expected', ('b' * 64, '', '../verification.json'))
def test_authenticated_verification_requires_the_expected_external_sha256(tmp_path, expected):
    module = _action_tool()
    path, _proof = _verification_receipt(module, tmp_path)
    with pytest.raises(ValueError, match='verification_expected_sha256_'):
        module.authenticated_verification(path, expected)


def test_authenticated_verification_rejects_tampered_content_seal(tmp_path):
    module = _action_tool()
    path, proof = _verification_receipt(module, tmp_path)
    tampered = {**proof, 'reviewed_plan_sha256': 'b' * 64}
    path.write_text(json.dumps(tampered))
    with pytest.raises(ValueError, match='content_sha256 mismatch'):
        module.authenticated_verification(path, proof['content_sha256'])


@pytest.mark.parametrize(('field', 'value'), (
    ('operation', 'other-operation'),
    ('phase', 'authorize'),
    ('status', 'stopped'),
    ('result', {'empty': False, 'counts': {'system_archetype': 1}, 'database_writes': False}),
    ('result', {'empty': True, 'counts': {'cluster_run': 0, 'cluster': 0, 'cluster_member': 0,
                                       'system_archetype': 1}, 'database_writes': False}),
    ('result', {'empty': True, 'counts': {'system_archetype': 0}, 'database_writes': False}),
    ('result', {'empty': True, 'counts': {'cluster_run': 0, 'cluster': 0, 'cluster_member': 0,
                                       'system_archetype': 0}, 'database_writes': True}),
    ('result', {'empty': 1, 'counts': {'cluster_run': 0, 'cluster': 0, 'cluster_member': 0,
                                    'system_archetype': 0}, 'database_writes': False}),
    ('result', {'empty': True, 'counts': {'cluster_run': False, 'cluster': 0, 'cluster_member': 0,
                                       'system_archetype': 0}, 'database_writes': False}),
))
def test_authenticated_verification_requires_successful_exact_empty_check(tmp_path, field, value):
    module = _action_tool()
    path, proof = _verification_receipt(module, tmp_path, **{field: value})
    with pytest.raises(ValueError, match='verification_not_successful'):
        module.authenticated_verification(path, proof['content_sha256'])


@pytest.mark.parametrize('mismatch', ('foreign_plan', 'mixed_request_plans', 'partial_receipt_ids',
                                      'different_receipt_ids', 'partial_requests', 'duplicate_receipt_ids'))
def test_verification_gate_rejects_proof_for_another_plan_or_request_pair(tmp_path, mismatch):
    module = _action_tool()
    path, proof = _verification_receipt(module, tmp_path)
    proof = module.authenticated_verification(path, proof['content_sha256'])
    requests = [{'purge_id': purge_id, 'plan_sha256': proof['reviewed_plan_sha256']}
                for purge_id in proof['purge_id']]
    if mismatch == 'foreign_plan':
        proof['reviewed_plan_sha256'] = 'b' * 64
    elif mismatch == 'mixed_request_plans':
        requests[1]['plan_sha256'] = 'b' * 64
    elif mismatch == 'partial_receipt_ids':
        proof['purge_id'] = proof['purge_id'][:1]
    elif mismatch == 'different_receipt_ids':
        proof['purge_id'] = [proof['purge_id'][0], '00000000-0000-0000-0000-000000000000']
    elif mismatch == 'partial_requests':
        requests = requests[:1]
    else:
        proof['purge_id'] = [proof['purge_id'][0]] * 2
    with pytest.raises(ValueError, match='verification_request_plan_mismatch'):
        module.verification_gate(proof, requests)


@pytest.mark.parametrize('verification', (None, {'status': 'not_proven'}))
def test_authorized_status_requires_empty_verification_before_first_delete(verification):
    module = _action_tool()
    state = {'unresolved': []}
    progress = {'requests': [{'purge_id': 'first'}, {'purge_id': 'second'}], 'events': []}
    counts = {'targets': [{'payload_counts': dict.fromkeys(module.RELATIONS.values(), 1)}]}
    assert module.next_mode(state, progress, counts, verification=verification) == {
        'mode': 'verify-system-archetype-empty', 'implemented': True,
        'reason': 'system_archetype_empty_not_proven'}
    assert module.verification_gate(None, progress['requests']) == {
        'status': 'not_proven', 'reason': 'sealed_verification_path_and_sha256_required'}


def test_authorized_status_advances_only_after_bound_sealed_empty_verification(tmp_path):
    module = _action_tool()
    path, proof = _verification_receipt(module, tmp_path)
    requests = [{'purge_id': purge_id, 'plan_sha256': proof['reviewed_plan_sha256']}
                for purge_id in proof['purge_id']]
    verification = module.verification_gate(
        module.authenticated_verification(path, proof['content_sha256']), requests)
    counts = {'targets': [{'payload_counts': dict.fromkeys(module.RELATIONS.values(), 1)}]}
    assert module.next_mode({'unresolved': []}, {'requests': requests, 'events': []}, counts,
                            verification=verification) == {
        'mode': 'delete-system-search', 'implemented': True}


@pytest.mark.parametrize('backend,locked', (('live', False), ('reused-pid', True), ('departed', True)))
def test_status_reports_recovery_before_independent_locked_relation_probes(monkeypatch, backend, locked):
    module = _action_tool()
    report, runtime, _plan, calls = _successful_phase(module, monkeypatch, 'status')
    opened = {'event_kind': 'REWRITE_STARTED', 'event_sequence': 9,
              'relation_code': 'system_search', 'purge_id': 'request'}
    recorded = {**opened, 'backend_pid': 123, 'backend_start': '2026-10-15T12:00:00+00:00'}
    backends = [] if backend == 'departed' else [{'pid': 123, 'backend_start': (
        recorded['backend_start'] if backend == 'live' else '2026-10-15T13:00:00+00:00')}]
    original_query = runtime.query
    def query(sql, params=None, *, write=False):
        assert sql not in (module._load('v3_purge_transactions').PLAN_SQL, module.OBJECTS_SQL)
        if sql == module.PROGRESS_SQL:
            return {'requests': [{'purge_id': 'request', 'plan_sha256': '6' * 64}],
                    'events': [recorded], 'backends': backends}
        if sql in module.STATUS_RELATION_SQL.values():
            # Recovery evidence exists before the first potentially blocking SQL.
            assert report['purge_state']['unresolved'] == [opened]
            assert report['backend_state'] == backends
            assert report['next_admissible_mode'] == {'mode': 'rewrite-system-search', 'implemented': False}
            if sql == module.STATUS_RELATION_SQL['system_search']:
                assert locked, 'the live rewrite relation must never be probed'
                raise RuntimeError('database_lock_timeout')
        return original_query(sql, params, write=write)
    runtime.query = query
    runtime.state = lambda **_: {'unresolved': [opened]}
    runtime.workers = lambda: pytest.fail('status must not run lifecycle relation-size probes')
    module.execute('status', runtime, report)
    assert report['status'] == 'success'
    assert report['result'] == 'unresolved_state_first'
    assert report['relation_probes']['system_search']['reason'] == ('lock_timeout' if locked else 'open_rewrite_backend')
    assert report['relation_probes']['system_search']['targets'] is None
    assert report['relation_bytes_before']['system_search'] is None
    assert report['survivors_before']['system_search'] is None
    assert all(target['payload_counts']['system_search'] is None for target in report['targets'])
    for code in ('economy_opportunity', 'body_mechanics', 'system_rating_vector'):
        assert report['relation_probes'][code]['reason'] is None
        assert report['relation_bytes_before'][code] == 60
    assert not any(call[0] == 'query' and call[2] for call in calls)


def test_status_probe_failure_preserves_recovery_guidance_and_does_not_hide_database_errors(monkeypatch):
    module = _action_tool()
    report, runtime, _plan, _calls = _successful_phase(module, monkeypatch, 'status', open_fence=True)
    original_query = runtime.query
    def query(sql, params=None, *, write=False):
        if sql in module.STATUS_RELATION_SQL.values():
            raise RuntimeError('bounded_command_failed')
        return original_query(sql, params, write=write)
    runtime.query = query
    with pytest.raises(RuntimeError, match='bounded_command_failed'):
        module.execute('status', runtime, report)
    assert report['next_admissible_mode'] == {'mode': 'restore-services', 'implemented': True}
    assert report['purge_state']['unresolved'][0]['event_kind'] == 'WRITER_FENCE_ENABLED'
    assert report['backend_state'] == []
    assert report['status'] == 'stopped'


@pytest.mark.parametrize('sqlstate,expected', (('55P03', 'database_lock_timeout'), ('42501', 'bounded_command_failed')))
def test_psql_lock_timeout_is_identified_by_sqlstate_without_leaking_diagnostics(monkeypatch, sqlstate, expected):
    module = _action_tool()
    report = module.receipt('status')
    runtime = module.Runtime(report)
    def run(argv, **kwargs):
        assert 'VERBOSITY=sqlstate' in argv
        return SimpleNamespace(returncode=3, stdout='', stderr=f'psql:<stdin>:2: ERROR:  {sqlstate}\nprivate diagnostics')
    monkeypatch.setattr(module.subprocess, 'run', run)
    with pytest.raises(RuntimeError, match='^' + expected + '$'):
        runtime.query(module.STATUS_RELATION_SQL['system_search'])
    assert report['db_writes_performed'] is False


def test_status_worker_inventory_uses_docker_without_lifecycle_sql(monkeypatch):
    module = _action_tool()
    runtime = module.Runtime(module.receipt('status'))
    calls = []
    def docker(*argv):
        calls.append(argv)
        return json.dumps({'Names': 'edfinder-v3-system-search-p4-opt1', 'State': 'running'})
    monkeypatch.setattr(runtime, 'docker', docker)
    runtime.status_workers()
    assert calls == [('container', 'ls', '--all', '--format', '{{json .}}')]
    workers = runtime.report['workers']
    assert len(workers) == 6
    assert next(worker for worker in workers if worker['name'] == 'edfinder-v3-system-search-p4-opt1')['running'] is True
    assert all(worker['running'] is False for worker in workers if not worker['exists'])


def test_complete_requires_verification_proof_before_any_mutation(monkeypatch):
    module = _action_tool()
    report, runtime, plan, calls = _successful_phase(module, monkeypatch, 'complete')
    with pytest.raises(ValueError, match='sealed_verification_required'):
        module.execute('complete', runtime, report, plan)
    assert report['system_archetype_verification']['status'] == 'not_proven'
    assert not any(call[0] == 'query' and call[2] for call in calls)
    assert report['db_writes_performed'] is False


def test_cli_complete_requires_external_verification_before_host_access(capsys):
    module = _action_tool()
    assert module.main(['complete']) == 1
    report = json.loads(capsys.readouterr().out)
    assert report['failures'] == ['sealed_verification_required']
    assert report['host'] is None
    assert report['db_writes_performed'] is False


@pytest.mark.parametrize('changed', (
    'deploy/v3-production/backup/pgbackrest-operation.sh',
    'scripts/operator/actions/v3-derived-generation-purge.sh',
    'scripts/operator/actions/v3-derived-lifecycle-status.sh',
    'scripts/operator/lib/f2d_evidence.py',
    'scripts/operator/lib/v3_generation_purge.py',
    'scripts/operator/lib/v3_purge_delete.py',
    'scripts/operator/lib/v3_purge_state.py',
    'scripts/operator/lib/v3_purge_transactions.py',
    'scripts/operator/v3_schema_identity.py',
))
def test_purge_script_identity_covers_every_executed_source(monkeypatch, tmp_path, changed):
    module = _action_tool()
    sources = (
        'deploy/v3-production/backup/pgbackrest-operation.sh',
        'scripts/operator/actions/v3-derived-generation-purge.sh',
        'scripts/operator/actions/v3-derived-lifecycle-status.sh',
        'scripts/operator/lib/f2d_evidence.py',
        'scripts/operator/lib/v3_generation_purge.py',
        'scripts/operator/lib/v3_purge_delete.py',
        'scripts/operator/lib/v3_purge_state.py',
        'scripts/operator/lib/v3_purge_transactions.py',
        'scripts/operator/v3_schema_identity.py',
    )
    for relative in sources:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative.encode())
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    report = module.receipt('plan')
    runtime = module.Runtime(report)
    commands = {
        ('hostname', '-s'): module.HOST,
        ('hostname', '-f'): module.FQDN,
        ('docker', 'context', 'show'): 'default',
        ('git', '-C', str(tmp_path), 'rev-parse', 'HEAD'): '1' * 40,
    }
    wrapper_relative = 'deploy/v3-production/backup/pgbackrest-operation.sh'
    committed_blob = hashlib.sha256((tmp_path / wrapper_relative).read_bytes()).hexdigest()[:40]
    commands[('git', '-C', str(tmp_path), 'rev-parse', '1' * 40 + ':' + wrapper_relative)] = committed_blob
    def run(argv):
        if len(argv) > 3 and argv[3] == 'hash-object':
            return hashlib.sha256(Path(argv[-1]).read_bytes()).hexdigest()[:40]
        return commands[tuple(argv)]
    monkeypatch.setattr(runtime, 'run', run)
    docker_commands = {
        ('context', 'inspect', 'default'): json.dumps([
            {'Endpoints': {'docker': {'Host': 'unix:///var/run/docker.sock'}}}]),
        ('inspect', '-f', '{{.State.Running}}', module.CONTAINER): 'true',
    }
    monkeypatch.setattr(runtime, 'docker', lambda *argv: docker_commands[argv])
    runtime.guard()
    original = report['script_sha256']
    assert original == module.evidence.canonical_sha256({
        relative: hashlib.sha256((tmp_path / relative).read_bytes()).hexdigest()
        for relative in sorted(sources)
    })
    path = tmp_path / changed
    path.write_bytes(path.read_bytes() + b'\n# changed source bytes\n')
    if changed == wrapper_relative:
        with pytest.raises(ValueError, match='backup_wrapper_committed_source_mismatch'):
            runtime.guard()
        assert report['script_sha256'] == original
        return
    runtime.guard()
    assert report['source_git_sha'] == '1' * 40
    assert report['script_sha256'] != original


def test_authorize_rejects_script_drift_before_any_mutation(monkeypatch):
    module = _action_tool()
    report, runtime, plan, calls = _successful_phase(module, monkeypatch, 'authorize')
    plan['script_sha256'] = '9' * 64
    assert plan['source_git_sha'] == report['source_git_sha']
    with pytest.raises(ValueError, match='plan_source_or_script_changed'):
        module.execute('authorize', runtime, report, plan)
    assert not any(call[0] == 'query' and call[2] for call in calls)
    assert report['db_writes_performed'] is False


def test_launcher_requires_python314_without_executing_python3_fallback(tmp_path):
    fallback = tmp_path / 'python3'
    marker = tmp_path / 'fallback-used'
    fallback.write_text('#!/bin/bash\nprintf used > "$FALLBACK_MARKER"\n')
    fallback.chmod(0o700)
    result = subprocess.run(
        ['/bin/bash', str(ROOT / 'scripts/operator/actions/v3-derived-generation-purge.sh'), 'plan'],
        env={'PATH': str(tmp_path), 'FALLBACK_MARKER': str(marker)},
        text=True, capture_output=True, check=False)
    assert result.returncode == 1
    assert json.loads(result.stdout)['failures'] == ['python314_required']
    assert not marker.exists()


def test_wal_delta_uses_parameterized_server_lsn_arithmetic():
    module = _action_tool()
    report = module.receipt('authorize')
    report['wal_before'] = {'lsn': '1/FFFFFFF0'}
    calls = []
    def query(sql, params=None):
        calls.append((sql, params))
        if sql == module.WAL_SQL:
            return {'lsn': '2/10'}
        assert sql == module.WAL_LSN_DIFF_SQL
        assert params == {'before_lsn': '1/FFFFFFF0', 'after_lsn': '2/10'}
        return {'wal_byte_delta': 32}
    module.finalize_wal_delta(SimpleNamespace(query=query), report)
    assert report['wal_byte_delta'] == 32
    assert 'pg_wal_lsn_diff' in calls[-1][0]
    assert '1/FFFFFFF0' not in calls[-1][0]


@pytest.mark.parametrize('before,after,delta', (
    (None, '0/10', 0), ('0/10', None, 0), ('bad', '0/10', 0),
    ('0/10', '0/20', None), ('0/10', '0/20', -1), ('0/10', '0/20', True),
))
def test_wal_delta_fails_closed_if_it_cannot_be_derived(before, after, delta):
    module = _action_tool()
    report = module.receipt('plan')
    report['wal_before'] = {'lsn': before}
    def query(sql, params=None):
        if sql == module.WAL_SQL:
            return {'lsn': after}
        return {'wal_byte_delta': delta}
    with pytest.raises(ValueError, match='wal_byte_delta_unavailable'):
        module.finalize_wal_delta(SimpleNamespace(query=query), report)
    assert report['status'] == 'stopped'
    assert report['wal_byte_delta'] is None


def test_backup_schedule_lock_is_nonblocking_and_held_for_entire_phase(tmp_path, monkeypatch):
    module = _action_tool()
    lock = tmp_path / 'backup.lock'
    lock.touch(mode=0o600)
    monkeypatch.setattr(module, 'BACKUP_SCHEDULE_LOCK', lock)
    runtime = module.Runtime(module.receipt('authorize'))
    monkeypatch.setattr(runtime, 'docker', lambda *args: 'PID COMMAND\n1 postgres')
    with lock.open('r') as rival:
        fcntl.flock(rival, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match='backup_schedule_lock_held'), runtime.backup_lock():
            pytest.fail('held backup lock admitted mutation')
    with runtime.backup_lock(), lock.open('r') as rival:
        with pytest.raises(BlockingIOError):
            fcntl.flock(rival, fcntl.LOCK_EX | fcntl.LOCK_NB)
    with lock.open('r') as rival:
        fcntl.flock(rival, fcntl.LOCK_EX | fcntl.LOCK_NB)


@pytest.mark.parametrize('processes,error', (
    ('PID COMMAND\n123 pgbackrest --stanza=edfinder_v3 backup', 'backup_or_verify_process_active'),
    ('PID COMMAND\n123 pgbackrest --stanza=edfinder_v3 verify', 'backup_or_verify_process_active'),
    ('', 'backup_process_state_unknown'),
    ('unrecognized-output', 'backup_process_state_unknown'),
))
def test_backup_process_gate_refuses_before_yield(tmp_path, monkeypatch, processes, error):
    module = _action_tool()
    monkeypatch.setattr(module, 'BACKUP_SCHEDULE_LOCK', tmp_path / 'backup.lock')
    runtime = module.Runtime(module.receipt('complete'))
    monkeypatch.setattr(runtime, 'docker', lambda *args: processes)
    with pytest.raises(ValueError, match=error), runtime.backup_lock():
        pytest.fail('backup gate failure admitted mutation')
    assert runtime.report['db_writes_performed'] is False


@pytest.mark.parametrize('mode', ('authorize', 'complete'))
def test_single_transaction_mutators_hold_backup_lock_through_dispatch(monkeypatch, capsys, mode):
    from contextlib import contextmanager
    module = _action_tool()
    calls = []
    monkeypatch.setattr(module, 'authenticated_plan', lambda *args, **kwargs: {})
    monkeypatch.setattr(module, 'authenticated_verification', lambda *args: {})
    monkeypatch.setattr(module.Runtime, 'guard', lambda self: None)
    monkeypatch.setattr(module.Runtime, 'state', lambda self, **kwargs: {'unresolved': []})
    @contextmanager
    def lease(self):
        calls.append('lease-acquired')
        yield
        calls.append('lease-released')
    @contextmanager
    def backup_lock(self):
        calls.append('backup-acquired')
        yield
        calls.append('backup-released')
    monkeypatch.setattr(module.Runtime, 'lease', lease)
    monkeypatch.setattr(module.Runtime, 'backup_lock', backup_lock)
    def execute(mode, runtime, report, *args, **kwargs):
        assert calls == ['lease-acquired', 'backup-acquired']
        calls.append('execute')
        report['status'] = 'success'
    monkeypatch.setattr(module, 'execute', execute)
    args = [mode, '--plan=unused', '--plan-sha256=' + '1' * 64]
    if mode == 'complete':
        args += ['--verification=unused', '--verification-sha256=' + '2' * 64]
    assert module.main(args) == 0
    assert calls == ['lease-acquired', 'backup-acquired', 'execute', 'backup-released', 'lease-released']
    assert json.loads(capsys.readouterr().out)['status'] == 'success'


@pytest.mark.parametrize('budget', (True, 0, -1, 1.5, '1000', None, 2**63))
def test_authenticated_plan_refuses_invalid_optional_autovacuum_budget(tmp_path, budget):
    module = _action_tool()
    path = tmp_path / 'plan.json'
    now, plan = _sealed_plan(module, path, reviewed_plan={
        'plan_sha256': '1' * 64,
        'delete': {'system_search': {'batch_limit': 1000, 'autovacuum_budget_bytes': budget}},
    })
    with pytest.raises(ValueError, match='autovacuum_budget_invalid'):
        module.authenticated_plan(path, plan['content_sha256'], now=now)


@pytest.mark.parametrize('configuration', ({'batch_limit': 1000},
                                         {'batch_limit': 1000, 'autovacuum_budget_bytes': 1_000_000}))
def test_authenticated_plan_keeps_optional_rehearsal_budget_without_default(tmp_path, configuration):
    module = _action_tool()
    path = tmp_path / 'plan.json'
    reviewed = {'plan_sha256': '1' * 64, 'delete': {'system_search': configuration}}
    now, plan = _sealed_plan(module, path, reviewed_plan=reviewed)
    result = module.authenticated_plan(path, plan['content_sha256'], now=now)
    assert result['reviewed_plan'] == reviewed


def test_generated_plan_does_not_invent_rehearsal_budget(monkeypatch):
    module = _action_tool()
    report, runtime, _plan, _calls = _successful_phase(module, monkeypatch, 'plan')
    module.execute('plan', runtime, report)
    assert report['reviewed_plan']['delete'] == {
        code: {'batch_limit': 1000} for code in module.RELATIONS.values()}


@pytest.mark.parametrize('mode', ('plan', 'authorize', 'complete', 'verify-system-archetype-empty'))
@pytest.mark.parametrize('kind', ('WRITER_FENCE_ENABLED', 'SERVICES_QUIESCED'))
@pytest.mark.parametrize('open_batch', (False, True))
def test_regular_dispatch_refuses_orphaned_application_fence_before_host_access(mode, kind, open_batch):
    module = _action_tool()
    report = module.receipt(mode)
    unresolved = [{'event_kind': kind}]
    if open_batch:
        unresolved.append({'event_kind': 'BATCH_STARTED'})
    state = {'unresolved': unresolved, 'failures': ['purge_unresolved_' + kind]}
    runtime = SimpleNamespace(state=lambda **kwargs: state)
    with pytest.raises(ValueError, match='orphaned_writer_fence_requires_restore_services'):
        module.execute(mode, runtime, report)
    assert report['purge_state'] is state
    assert report['next_admissible_mode'] == {'mode': 'restore-services', 'implemented': True}
    assert report['db_writes_performed'] is False
    assert report['service_changes_performed'] is False


@pytest.mark.parametrize('failure', ('purge_unresolved_FAILED_STOP', 'purge_host_lease_held',
                                   'purge_unresolved_REWRITE_STARTED'))
def test_regular_dispatch_preserves_other_p2a_refusals(failure):
    module = _action_tool()
    report = module.receipt('authorize')
    runtime = SimpleNamespace(state=lambda **kwargs: {'unresolved': [], 'failures': [failure]})
    with pytest.raises(ValueError, match=failure):
        module.execute('authorize', runtime, report)
    assert report['db_writes_performed'] is False


@pytest.mark.parametrize('mode', ('authorize', 'complete', 'delete-system-search', 'abort-relation-system-search'))
@pytest.mark.parametrize('kind', ('WRITER_FENCE_ENABLED', 'SERVICES_QUIESCED'))
def test_cli_refuses_orphaned_application_fence_before_acquiring_dispatch_lease(monkeypatch, capsys, mode, kind):
    module = _action_tool()
    monkeypatch.setattr(module, 'authenticated_plan', lambda *args, **kwargs: {})
    monkeypatch.setattr(module, 'authenticated_verification', lambda *args, **kwargs: {})
    monkeypatch.setattr(module.Runtime, 'guard', lambda self: None)
    monkeypatch.setattr(module.Runtime, 'state', lambda self, **kwargs: {
        'unresolved': [{'event_kind': kind}], 'failures': ['purge_unresolved_' + kind]})
    monkeypatch.setattr(module.Runtime, 'lease', lambda self: pytest.fail('orphaned fence acquired lease'))
    arguments = [mode, '--plan=unused', '--plan-sha256=' + '1' * 64]
    if mode != 'authorize':
        arguments += ['--verification=unused', '--verification-sha256=' + '2' * 64]
    assert module.main(arguments) == 1
    report = json.loads(capsys.readouterr().out)
    assert report['failures'] == ['orphaned_writer_fence_requires_restore_services']
    assert report['next_admissible_mode'] == {'mode': 'restore-services', 'implemented': True}
    assert report['db_writes_performed'] is False
