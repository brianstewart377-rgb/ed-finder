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
    copy = c._load('v3_purge_copy')
    assert reviewed['disposable_rehearsal_only'] is True
    assert reviewed['copy']['source'] == copy.BOOTSTRAP_SOURCE == 'disposable_bootstrap_unmeasured'
    assert all(item['required_free_bytes_before_copy'] == copy.FLOOR_BYTES and item['copy_peak_bytes'] == 0
               for item in reviewed['copy']['relations'].values())
    assert 'rewrite' not in reviewed
    # The production admission floor is unchanged in the disposable fixture.
    assert c.FREE_FLOOR_BYTES == copy.FLOOR_BYTES == 100_000_000_000
    assert c._load('v3_purge_rewrite').FLOOR_BYTES == 100_000_000_000
    with pytest.raises(ValueError, match='plan_rehearsal_figures_required'):
        c._load('v3_purge_rehearsal_receipt').require_plan_binding(reviewed)


def test_wrong_marker_refused_before_controller_target_changes(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match='marker_missing'):
        install_fake_target(monkeypatch, tmp_path, marker_override={
            'database': tool.PRODUCTION_DATABASE, 'marker': tool.MARKER_PREFIX + TOKEN})


def _fault_env(monkeypatch, tmp_path, scenario):
    marker = tmp_path / 'fault.json'
    monkeypatch.setenv('ED_PURGE_REHEARSAL_FAULT', scenario)
    monkeypatch.setenv('ED_PURGE_REHEARSAL_FAULT_FILE', str(marker))
    return marker


@pytest.mark.parametrize(('scenario', 'statement'), [
    ('swap_committed_client_killed', 'SWAP_SQL'), ('swap_back_committed_client_killed', 'SWAP_BACK_SQL'),
    ('swap_back_committed_client_killed', 'SWAP_BACK_OPPORTUNITY_SQL'), ('drop_committed_client_killed', 'DROP_SQL'),
])
def test_committed_fault_pauses_only_after_its_own_statement_commits(monkeypatch, tmp_path, scenario, statement):
    c, runtime, observed = install_fake_target(monkeypatch, tmp_path)
    marker = _fault_env(monkeypatch, tmp_path, scenario)
    copy = c._load('v3_purge_copy')
    sql = getattr(copy, statement)
    params = {'purge_id': '49a0c00d-e722-4209-afd8-9d62b877e30a', 'relation': 'economy_opportunity'}
    assert runtime.query(copy.STATUS_SQL) == {'observed': True}
    assert not marker.exists() and 'pg_sleep' not in observed[-1][1]['input']
    assert runtime.query(sql, params, write=True) == {'observed': True}
    body = observed[-1][1]['input']
    commit = body.rindex('COMMIT;')
    assert body.index('pg_sleep(' + str(tool.PAUSE_SECONDS) + ')') > commit
    assert body[:commit].count('pg_sleep') == 0
    proof = json.loads(marker.read_text())
    assert proof['scenario'] == scenario and proof['pid'] > 0
    # A different scenario never alters this statement.
    monkeypatch.setenv('ED_PURGE_REHEARSAL_FAULT', 'drop_committed_client_killed' if statement != 'DROP_SQL'
                       else 'swap_committed_client_killed')
    runtime.query(sql, params, write=True)
    assert 'pg_sleep' not in observed[-1][1]['input']


@pytest.mark.parametrize(('name', 'function'), [('CHUNK_SQL', 'purge_copy_chunk('),
                                                 ('BUILD_INDEXES_SQL', 'purge_copy_build_indexes('),
                                                 ('VERIFY_SQL', 'purge_copy_verify(')])
def test_statement_pause_runs_after_the_019_call_inside_the_same_statement(monkeypatch, tmp_path, name, function):
    c, _runtime, _ = install_fake_target(monkeypatch, tmp_path)
    sql = getattr(c._load('v3_purge_copy'), name)
    paused = tool.pause_statement(name, sql)
    statement = paused[paused.index('SELECT jsonb_build_object('):]
    statement = statement[:statement.index(';')]
    assert statement.index(function) < statement.index('pg_sleep(40)')
    assert paused.count('pg_sleep') == 1 and paused.rstrip().endswith('COMMIT;')
    # psql's statement split is unchanged; the watchdog's cancel pattern still matches.
    assert paused.count(';') == sql.count(';')
    with pytest.raises(ValueError, match='rehearsal_fault_anchor_changed'):
        tool.pause_statement(name, sql.replace(tool.PAUSE_ANCHORS[name], 'x'))


@pytest.mark.parametrize(('scenario', 'statement', 'paused'), [
    ('copy_chunk_client_killed', 'CHUNK_SQL', [False, True, False]),
    ('copy_postgres_restart', 'CHUNK_SQL', [False, True, False]),
    ('index_build_backend_terminated', 'BUILD_INDEXES_SQL', [True]),
    ('verify_watchdog_cancel', 'VERIFY_SQL', [True]),
    ('swap_committed_client_killed', 'CHUNK_SQL', [False, False, False]),
])
def test_phase_backend_fault_pauses_only_its_named_statement(monkeypatch, tmp_path, scenario, statement, paused):
    from contextlib import contextmanager
    c, runtime, _ = install_fake_target(monkeypatch, tmp_path)
    marker = _fault_env(monkeypatch, tmp_path, scenario)
    copy = c._load('v3_purge_copy')
    sent = []
    @contextmanager
    def real_backend(*args, **kwargs):
        yield SimpleNamespace(query=lambda sql, params=None, **kw: sent.append(sql) or {'rows': 1})
    with tool.faulted_phase_backend(runtime, copy, [0], real_backend, c, runtime, 1000) as backend:
        for _ in paused:
            backend.query(getattr(copy, statement), {})
        backend.query(copy.STATUS_SQL)
    assert ['pg_sleep' in sql for sql in sent[:-1]] == paused and 'pg_sleep' not in sent[-1]
    assert marker.exists() is any(paused)
    # The adapter installs the same wrapper over the dispatcher's transport.
    assert c._load('v3_purge_copy_dispatch').phase_backend.__name__ == '<lambda>'


def test_rehearsal_finder_smoke_reads_every_application_surface(monkeypatch, tmp_path):
    c, runtime, observed = install_fake_target(monkeypatch, tmp_path)
    answers = iter([{'system_search': 1, 'system_archetype': 1, 'system_economy_rating': 1,
                     'economy_opportunity': 1, 'body_mechanics': 1},
                    {'system_search': 1, 'system_archetype': 0, 'system_economy_rating': 1,
                     'economy_opportunity': 1, 'body_mechanics': 1}])
    monkeypatch.setattr(c.Runtime, 'query', lambda self, sql, params=None, *, write=False: next(answers))
    smoke = c._load('v3_purge_copy').finder_smoke
    assert smoke()['passed'] is True
    with pytest.raises(ValueError, match='finder_smoke_failed'):
        smoke()
    assert tool.SMOKE_SQL.startswith('BEGIN READ ONLY;') and 'v3_app.system_archetype' in tool.SMOKE_SQL


def test_host_recovery_state_and_watchdog_conditions_stay_in_the_private_directory(monkeypatch, tmp_path):
    c, _runtime, _ = install_fake_target(monkeypatch, tmp_path)
    delete = c._load('v3_purge_delete')
    delete.save_host_state({'n_distinct': -0.13}, path=Path('/var/lib/ed-finder/v3-production/derived-purge-copy-statistics.json'))
    private = tmp_path / NAME
    assert json.loads((private / 'derived-purge-copy-statistics.json').read_text()) == {'n_distinct': -0.13}
    monitor = c._load('v3_purge_rewrite_monitor')
    (private / 'copy-economy_opportunity-verify-42.condition').write_text('controller_loss')
    assert monitor.copy_condition('copy-economy_opportunity-verify-42') == 'controller_loss'
    assert monitor.copy_condition('copy-economy_opportunity-verify-42') is None
    (private / 'copy-x-verify-1.condition').write_text('not a code;')
    assert monitor.copy_condition('copy-x-verify-1') is None
    (private / 'copy-economy_opportunity-index_build-42.detail').write_text('observe:bounded_command_failed')
    assert monitor.copy_detail('copy-economy_opportunity-index_build-42') == 'observe:bounded_command_failed'
    assert monitor.copy_detail('copy-economy_opportunity-index_build-42') is None
    (private / 'copy-x-verify-1.detail').write_text('observe:not a code;')
    assert monitor.copy_detail('copy-x-verify-1') is None


def test_injected_pause_ends_well_inside_the_chunk_timeout_and_the_orphan_wait():
    from scripts.operator.lib import v3_purge_copy as copy
    from scripts.rehearsal import v3_purge_crashes as crashes
    assert 0 < tool.PAUSE_SECONDS <= copy.PHASES['chunk'][0] / 1000 - 60
    assert tool.PAUSE_SECONDS <= crashes.ORPHAN_SECONDS - 60
    assert set(tool.STATEMENT_FAULTS.values()) <= set(tool.PAUSE_ANCHORS)
