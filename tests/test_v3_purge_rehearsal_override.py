"""The disposable override cannot admit a production identity or remote Docker."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.operator.lib import v3_purge_rehearsal as tool

NAME = 'edfinder-purge-rehearsal-' + 'a' * 32
TOKEN = 'b' * 64


def target():
    inspection = {
        'Name': '/' + NAME, 'Id': 'c' * 64, 'State': {'Running': True},
        'Config': {'Hostname': NAME, 'Labels': {tool.LABEL: TOKEN}},
        'HostConfig': {'NetworkMode': 'none', 'Privileged': False},
        'Mounts': [{'Type': 'volume', 'Name': NAME + '-data',
                    'Destination': '/var/lib/postgresql', 'RW': True}],
    }
    volume = {'Name': NAME + '-data', 'Labels': {tool.LABEL: TOKEN}, 'Driver': 'local', 'Options': None}
    marker = {'database': tool.DATABASE, 'marker': tool.MARKER_PREFIX + TOKEN}
    return inspection, volume, marker


def test_valid_isolated_target_is_pinned_to_immutable_id():
    assert tool.validate_target(NAME, TOKEN, 'contabo', 'contabo.local', *target()) == 'c' * 64


@pytest.mark.parametrize('host', sorted(tool.PRODUCTION_HOSTS))
@pytest.mark.parametrize('position', ('short', 'full'))
def test_production_host_never_accepts_even_a_valid_marker(host, position):
    short, full = (host, 'contabo.local') if position == 'short' else ('contabo', host)
    with pytest.raises(ValueError, match='rehearsal_production_or_invalid_identity'):
        tool.validate_target(NAME, TOKEN, short, full, *target())


@pytest.mark.parametrize('name', (tool.PRODUCTION_CONTAINER, 'postgres', '', NAME + ';echo', NAME + '/foo'))
def test_non_disposable_container_names_never_accepted(name):
    with pytest.raises(ValueError, match='identity'):
        tool.validate_target(name, TOKEN, 'contabo', 'contabo.local', *target())


@pytest.mark.parametrize('database', (tool.PRODUCTION_DATABASE, 'postgres', 'edfinder_v3', None))
def test_production_database_never_accepts_even_a_valid_marker(database):
    inspection, volume, marker = target()
    marker['database'] = database
    with pytest.raises(ValueError, match='marker_missing'):
        tool.validate_target(NAME, TOKEN, 'contabo', 'contabo.local', inspection, volume, marker)


@pytest.mark.parametrize('key,value', (
    ('NetworkMode', 'host'), ('NetworkMode', 'bridge'), ('Privileged', True),
    ('Binds', ['/var/lib/production:/var/lib/postgresql']), ('Devices', ['disk']),
    ('PortBindings', {'5432/tcp': [{'HostPort': '5432'}]}),
    ('VolumesFrom', ['production']), ('PidMode', 'host'), ('IpcMode', 'host'),
))
def test_container_escape_boundaries_refused(key, value):
    inspection, volume, marker = target()
    inspection['HostConfig'][key] = value
    with pytest.raises(ValueError, match='not_disposable'):
        tool.validate_target(NAME, TOKEN, 'contabo', 'contabo.local', inspection, volume, marker)


@pytest.mark.parametrize('mutation', ('unlabeled', 'mismatched_label', 'bind', 'production_volume',
                                    'external_volume', 'remote_volume', 'second_mount', 'readonly', 'no_marker'))
def test_markers_mounts_and_volume_all_required(mutation):
    inspection, volume, marker = deepcopy(target())
    if mutation == 'unlabeled':
        inspection['Config']['Labels'] = {}
    elif mutation == 'mismatched_label':
        volume['Labels'][tool.LABEL] = 'd' * 64
    elif mutation == 'bind':
        inspection['Mounts'][0]['Type'] = 'bind'
    elif mutation == 'production_volume':
        inspection['Mounts'][0]['Name'] = 'production-data'
    elif mutation == 'external_volume':
        volume['Options'] = {'device': '/var/lib/production', 'type': 'none', 'o': 'bind'}
    elif mutation == 'remote_volume':
        volume['Driver'] = 'nfs'
    elif mutation == 'second_mount':
        inspection['Mounts'].append(dict(inspection['Mounts'][0]))
    elif mutation == 'readonly':
        inspection['Mounts'][0]['RW'] = False
    else:
        marker['marker'] = None
    with pytest.raises(ValueError):
        tool.validate_target(NAME, TOKEN, 'contabo', 'contabo.local', inspection, volume, marker)


def controller():
    path = Path(tool.__file__).with_name('v3_generation_purge.py')
    spec = importlib.util.spec_from_file_location('override_controller_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('host', sorted(tool.PRODUCTION_HOSTS))
def test_production_refusal_precedes_all_docker_and_db_access(monkeypatch, host):
    c = controller()
    calls = []
    def run(self, argv, **kwargs):
        calls.append(argv)
        assert argv[0] == 'hostname'
        return host
    monkeypatch.setattr(c.Runtime, 'run', run)
    with pytest.raises(ValueError, match='identity'):
        tool.install(c, {}, NAME, TOKEN)
    assert all(call[0] == 'hostname' for call in calls)
    assert c.CONTAINER == tool.PRODUCTION_CONTAINER
    assert c.DATABASE == tool.PRODUCTION_DATABASE


@pytest.mark.parametrize('endpoint', ('tcp://127.0.0.1:2375', 'ssh://ed-finder-prod', 'unix:///tmp/other.sock'))
def test_remote_or_noncanonical_daemon_refused_before_container_access(monkeypatch, endpoint):
    c = controller()
    def run(self, argv, **kwargs):
        if argv[0] == 'hostname':
            return 'contabo'
        if argv == ['docker', 'context', 'show']:
            return 'default'
        assert argv == ['docker', '--context', 'default', 'context', 'inspect', 'default']
        return json.dumps([{'Endpoints': {'docker': {'Host': endpoint}}}])
    monkeypatch.setattr(c.Runtime, 'run', run)
    with pytest.raises(ValueError, match='unexpected_docker_endpoint'):
        tool.install(c, {}, NAME, TOKEN)
    assert c.CONTAINER == tool.PRODUCTION_CONTAINER


@pytest.mark.parametrize('args', (
    ['plan', '--rehearsal-container', NAME], ['plan', '--rehearsal-token', TOKEN],
))
def test_override_requires_both_explicit_cli_arguments(monkeypatch, capsys, args):
    c = controller()
    monkeypatch.setattr(c.Runtime, 'run', lambda *_args, **_kwargs: pytest.fail('must refuse before access'))
    assert c.main(args) == 1
    assert json.loads(capsys.readouterr().out)['failures'] == ['rehearsal_arguments_require_pair']


def test_environment_cannot_enable_override(monkeypatch, capsys):
    c = controller()
    monkeypatch.setenv('REHEARSAL_CONTAINER', NAME)
    monkeypatch.setenv('REHEARSAL_TOKEN', TOKEN)
    monkeypatch.setattr(c.Runtime, 'guard', lambda _self: (_ for _ in ()).throw(ValueError('production_guard_used')))
    assert c.main(['plan']) == 1
    assert json.loads(capsys.readouterr().out)['failures'] == ['production_guard_used']


def test_disposable_plan_is_rejected_by_default_runtime(monkeypatch, capsys):
    c = controller()
    monkeypatch.setattr(c, 'authenticated_plan', lambda *_args, **_kwargs: {
        'reviewed_plan': {'disposable_rehearsal_only': True}})
    monkeypatch.setattr(c.Runtime, 'guard', lambda _: pytest.fail('must refuse before production guard'))
    assert c.main(['authorize', '--plan', '/not/read', '--plan-sha256', 'a' * 64]) == 1
    assert json.loads(capsys.readouterr().out)['failures'] == ['disposable_plan_refused_in_production']


def install_fake_target(monkeypatch, tmp_path, *, marker_override=None):
    c = controller()
    inspection, volume, marker = target()
    if marker_override is not None:
        marker = marker_override
    observed = []
    def run(self, argv, **kwargs):
        observed.append((argv, kwargs))
        if argv[0] == 'hostname':
            return 'contabo'
        if argv == ['docker', 'context', 'show']:
            return 'default'
        command = argv[3:]
        if command == ['context', 'inspect', 'default']:
            return json.dumps([{'Endpoints': {'docker': {'Host': 'unix:///var/run/docker.sock'}}}])
        if command == ['inspect', NAME]:
            return json.dumps([inspection])
        if command == ['volume', 'inspect', NAME + '-data']:
            return json.dumps([volume])
        if command[:2] == ['exec', NAME]:
            return json.dumps(marker)
        if command[:3] == ['exec', '-i', 'c' * 64]:
            return '{"observed":true}'
        pytest.fail('unexpected transport command')
    monkeypatch.setattr(c.Runtime, 'run', run)
    monkeypatch.setattr(tool.tempfile, 'gettempdir', lambda: str(tmp_path))
    runtime = tool.install(c, {}, NAME, TOKEN)
    return c, runtime, observed


def test_admitted_queries_use_fixed_database_and_immutable_container_id(monkeypatch, tmp_path):
    c, runtime, observed = install_fake_target(monkeypatch, tmp_path)
    assert c.DATABASE == tool.DATABASE
    assert c.CONTAINER == 'c' * 64
    assert runtime.query('SELECT json_build_object(\'observed\',true)') == {'observed': True}
    argv, kwargs = observed[-1]
    assert argv[:6] == ['docker', '--context', 'default', 'exec', '-i', 'c' * 64]
    assert argv[argv.index('--dbname') + 1] == tool.DATABASE
    assert tool.PRODUCTION_CONTAINER not in argv and tool.PRODUCTION_DATABASE not in argv
    assert runtime.report['statement_durations'][0]['duration_seconds'] >= 0
    assert kwargs['input'].endswith("SELECT json_build_object('observed',true)")


def test_bootstrap_plan_is_explicitly_unmeasured_and_disposable(monkeypatch, tmp_path):
    c, runtime, _ = install_fake_target(monkeypatch, tmp_path)
    reviewed = {'delete': {relation: {} for relation in c.RELATIONS.values()}}
    runtime.prepare_plan(reviewed)
    assert reviewed['disposable_rehearsal_only'] is True
    assert all(config['rows_per_second_source'] == 'disposable_bootstrap_unmeasured'
               for config in reviewed['delete'].values())
    assert c.FREE_FLOOR_BYTES == 100_000_000_000
    assert c._load('v3_purge_rewrite').FLOOR_BYTES == 100_000_000_000


def test_wrong_marker_refused_before_controller_target_changes(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match='marker_missing'):
        install_fake_target(monkeypatch, tmp_path, marker_override={
            'database': tool.PRODUCTION_DATABASE, 'marker': tool.MARKER_PREFIX + TOKEN})


def test_verification_fault_inserts_then_fails_before_commit_and_only_marks_after_rollback(monkeypatch, tmp_path):
    c, runtime, _ = install_fake_target(monkeypatch, tmp_path)
    scenario = 'rewrite_verified_transaction_failure'
    marker = tmp_path / 'verification-rolled-back.json'
    monkeypatch.setenv('ED_PURGE_REHEARSAL_FAULT', scenario)
    monkeypatch.setenv('ED_PURGE_REHEARSAL_FAULT_FILE', str(marker))
    observed = []
    def execute(self, *argv, **kwargs):
        observed.append(kwargs)
        assert not marker.exists()
        assert kwargs['allow_failure'] is kwargs['return_result'] is True
        statement = kwargs['input']
        assert statement.index('purge_record_event(') < statement.index('SELECT 1 / 0;') < statement.index('COMMIT;')
        return SimpleNamespace(returncode=3, stdout='{"event_sequence":43}\n', stderr='ERROR:  22012\n')
    monkeypatch.setattr(c.Runtime, 'docker', execute)
    monkeypatch.setattr(tool.time, 'sleep', lambda seconds: None)
    with pytest.raises(ValueError, match='rehearsal_fault_not_interrupted'):
        runtime.query(c._load('v3_purge_rewrite').EVENT_SQL, {
            'purge_id': '49a0c00d-e722-4209-afd8-9d62b877e30a',
            'kind': 'REWRITE_VERIFIED', 'relation': 'system_rating_vector', 'evidence': '{}'}, write=True)
    proof = json.loads(marker.read_text())
    assert proof['scenario'] == scenario
    assert proof['verification_event_sequence'] == 43
    assert proof['verification_transaction_sqlstate'] == '22012'
    assert len(observed) == 1
    assert runtime._rehearsal_verification is False


@pytest.mark.parametrize('returncode,stdout,stderr', [
    (0, '{"event_sequence":43}', ''), (3, '{"event_sequence":43}', 'ERROR:  08006'),
    (3, '{}', 'ERROR:  22012'), (3, '{"event_sequence":0}', 'ERROR:  22012'),
    (3, '', 'ERROR:  22012'),
])
def test_verification_fault_cannot_mark_unobserved_insert_or_unexpected_failure(
        monkeypatch, tmp_path, returncode, stdout, stderr):
    c, runtime, _ = install_fake_target(monkeypatch, tmp_path)
    marker = tmp_path / 'verification-rolled-back.json'
    monkeypatch.setenv('ED_PURGE_REHEARSAL_FAULT', 'rewrite_verified_transaction_failure')
    monkeypatch.setenv('ED_PURGE_REHEARSAL_FAULT_FILE', str(marker))
    monkeypatch.setattr(c.Runtime, 'docker', lambda *args, **kwargs: SimpleNamespace(
        returncode=returncode, stdout=stdout, stderr=stderr))
    with pytest.raises(ValueError, match='rehearsal_verification_.*_not_observed'):
        runtime.query(c._load('v3_purge_rewrite').EVENT_SQL, {
            'purge_id': '49a0c00d-e722-4209-afd8-9d62b877e30a',
            'kind': 'REWRITE_VERIFIED', 'relation': 'system_rating_vector', 'evidence': '{}'}, write=True)
    assert not marker.exists()


def test_injected_batch_pause_ends_inside_the_recovery_wait():
    # A killed client is noticed only when the injected sleep ends; 016 cannot
    # cancel a backend that is no longer running the payload batch. Recovery
    # must therefore outlast the pause with margin, or it refuses to resolve.
    import inspect
    from scripts.operator.lib import v3_purge_transactions as tx
    bound = inspect.signature(tx.resolve_batches).parameters['maximum_seconds'].default
    assert 0 < tool.BATCH_PAUSE_SECONDS <= bound - 20
