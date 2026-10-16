"""Fail-closed contracts for protected purge dispatch and artifact admission."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import time
from types import SimpleNamespace

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/v3-production-derived-purge.yml'
HELPER = ROOT / 'scripts/operator/v3_production_purge_workflow.py'
SOURCE_SHA = 'a' * 40
RUN_ID = '123456'
RELATIONS = ('system-search', 'economy-opportunity', 'body-mechanics', 'system-rating-vector')
MODES = {
    'plan', 'status', 'authorize', 'verify-system-archetype-empty',
    'restore-services', 'complete',
    *(prefix + relation for prefix in ('delete-', 'rewrite-', 'abort-relation-') for relation in RELATIONS),
}


def _workflow():
    return yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)


def _helper():
    spec = importlib.util.spec_from_file_location('protected_purge_workflow_test', HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _job():
    jobs = _workflow()['jobs']
    assert len(jobs) == 1
    return next(iter(jobs.values()))


def _runs():
    return '\n'.join(step.get('run', '') for step in _job()['steps'])


def test_dispatch_modes_equal_the_actions_closed_list():
    workflow = _workflow()
    assert set(workflow['on']) == {'workflow_dispatch'}
    inputs = workflow['on']['workflow_dispatch']['inputs']
    assert set(inputs) == {
        'mode', 'confirm_target', 'plan_run_id', 'plan_sha256',
        'verification_run_id', 'verification_sha256', 'acknowledge_failed_stop',
        'wall_clock_seconds',
    }
    assert inputs['mode']['type'] == 'choice'
    assert len(inputs['mode']['options']) == len(MODES)
    assert set(inputs['mode']['options']) == MODES
    action_path = ROOT / 'scripts/operator/lib/v3_generation_purge.py'
    spec = importlib.util.spec_from_file_location('protected_purge_action_contract', action_path)
    action = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(action)
    action_modes = set(action.IMPLEMENTED) | {'restore-services'} | {
        prefix + relation
        for prefix in ('delete-', 'rewrite-', 'abort-relation-')
        for relation in action.RELATIONS
    }
    assert set(inputs['mode']['options']) == action_modes
    assert all(action.classify_mode(mode) == mode for mode in action_modes)
    assert inputs['confirm_target']['required'] == 'true'
    assert inputs['plan_run_id']['required'] == 'false'
    assert inputs['verification_run_id']['required'] == 'false'


def test_production_approval_and_both_authority_leases_are_required():
    workflow, job = _workflow(), _job()
    assert workflow['permissions'] == {'contents': 'read', 'actions': 'read'}
    assert workflow['concurrency'] == {
        'group': 'v3-production-application-authority', 'cancel-in-progress': 'false',
    }
    assert job['concurrency'] == {'group': 'chatgpt-ed-new-ops', 'cancel-in-progress': 'false'}
    assert job['environment'] == 'v3-production'
    assert "github.repository == 'brianstewart377-rgb/ed-finder'" in job['if']
    assert "github.ref == 'refs/heads/main'" in job['if']
    # The action admits at most 1,800s of deletion, plus a current batch. A
    # rewrite has a reviewed maximum allowance; it must fit below this ceiling.
    assert 60 < int(job['timeout-minutes']) <= 360


def test_input_expressions_only_enter_environment_or_action_parameters():
    """No GitHub expression can splice a dispatch string into shell source."""
    workflow = _workflow()
    inputs = workflow['on']['workflow_dispatch']['inputs']
    steps = _job()['steps']
    for step in steps:
        assert not re.search(r'\$\{\{\s*(?:github\.event\.)?inputs\.', step.get('run', ''))
    env_text = json.dumps([step.get('env', {}) for step in steps]) + json.dumps(_job().get('env', {}))
    for name in inputs:
        assert f'inputs.{name}' in env_text
    assert 'validate-inputs' in _runs()


def test_exact_main_is_refetched_after_approval_and_before_transport():
    source = _runs()
    assert source.count('git fetch --no-tags origin refs/heads/main') >= 2
    assert 'git rev-parse FETCH_HEAD' in source
    assert 'git rev-parse HEAD' in source
    assert 'GITHUB_SHA' in source
    checkout = next(step for step in _job()['steps'] if step.get('uses', '').startswith('actions/checkout@'))
    assert checkout['with']['persist-credentials'] == 'false'
    assert checkout['with']['ref'] in ('${{ github.sha }}', 'main')


def test_pinned_host_trust_and_existing_credential_boundary():
    source = WORKFLOW.read_text() + HELPER.read_text()
    assert 'ssh-keyscan' not in source
    assert 'StrictHostKeyChecking=yes' in source
    assert 'BatchMode=yes' in source
    assert 'IdentitiesOnly=yes' in source
    assert 'UserKnownHostsFile=' in source
    assert 'ed-finder-prod/nb79a3d.mevnode.com' in source
    assert 'ssh-keygen -F' in source
    allowed = set(re.findall(r'secrets\.([A-Z0-9_]+)', (ROOT / '.github/workflows/v3-production-schema-migration.yml').read_text()))
    allowed |= set(re.findall(r'secrets\.([A-Z0-9_]+)', (ROOT / '.github/workflows/chatgpt-ed-new-ops.yml').read_text()))
    actual = set(re.findall(r'secrets\.([A-Z0-9_]+)', WORKFLOW.read_text()))
    assert actual
    assert actual <= allowed
    assert any('KNOWN_HOSTS' in name for name in actual)


def test_cross_run_artifacts_have_fixed_names_and_authenticated_receipts():
    steps = _job()['steps']
    downloads = [step for step in steps if step.get('uses', '').startswith('actions/download-artifact@')]
    assert len(downloads) == 2
    assert {step['with']['name'] for step in downloads} == {
        'v3-derived-purge-plan', 'v3-derived-purge-verification',
    }
    assert {step['with']['run-id'] for step in downloads} == {
        '${{ inputs.plan_run_id }}', '${{ inputs.verification_run_id }}',
    }
    for step in downloads:
        assert step['with']['github-token'] == '${{ github.token }}'
        assert step['with']['repository'] == '${{ github.repository }}'
    assert 'authenticate' in _runs()
    uploads = [step for step in steps if step.get('uses', '').startswith('actions/upload-artifact@')]
    assert len(uploads) >= 3
    assert {'v3-derived-purge-plan', 'v3-derived-purge-verification'} <= {
        step['with']['name'] for step in uploads
    }
    receipt_upload = next(step for step in uploads if step['with']['name'] not in {
        'v3-derived-purge-plan', 'v3-derived-purge-verification',
    })
    assert receipt_upload['if'] == 'always()'
    for step in uploads:
        assert step['with']['retention-days'] == '180'
        assert step['with']['if-no-files-found'] == 'error'
    assert 'tee' in _runs()


def _inputs(mode='plan'):
    return {
        'INPUT_MODE': mode,
        'INPUT_CONFIRM_TARGET': 'ed-finder-prod/nb79a3d.mevnode.com',
        'INPUT_PLAN_RUN_ID': '' if mode in ('plan', 'status') else RUN_ID,
        'INPUT_PLAN_SHA256': '' if mode in ('plan', 'status') else 'b' * 64,
        'INPUT_VERIFICATION_RUN_ID': '',
        'INPUT_VERIFICATION_SHA256': '',
        'INPUT_ACKNOWLEDGE_FAILED_STOP': '',
        'INPUT_WALL_CLOCK_SECONDS': '',
        'GITHUB_RUN_ID': '987654',
        'GITHUB_SHA': SOURCE_SHA,
    }


def _run():
    return {
        'id': int(RUN_ID), 'head_repository': {'full_name': 'brianstewart377-rgb/ed-finder'},
        'path': '.github/workflows/v3-production-derived-purge.yml',
        'event': 'workflow_dispatch', 'status': 'completed', 'conclusion': 'success',
        'head_branch': 'main', 'head_sha': SOURCE_SHA,
    }


def _seal(body):
    canonical = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
    return {**body, 'content_sha256': hashlib.sha256(canonical.encode()).hexdigest()}


def _receipt(mode='plan'):
    return {
        'schema_version': 'ed-finder/derived-generation-purge/v1',
        'operation': 'v3-derived-generation-purge', 'phase': mode,
        'workflow_run_id': RUN_ID, 'source_git_sha': SOURCE_SHA,
        'host': 'ed-finder-prod', 'fqdn': 'nb79a3d.mevnode.com',
        'status': 'success', 'failures': [], 'read_only': True,
        'reviewed_plan': {},
    }


@pytest.mark.parametrize('mode', sorted(MODES))
def test_all_closed_modes_accept_only_their_required_input_evidence(mode):
    env = _inputs(mode)
    if mode.startswith('delete-'):
        env['INPUT_WALL_CLOCK_SECONDS'] = '300'
    if mode.startswith(('delete-', 'rewrite-', 'abort-relation-')) or mode in ('complete', 'restore-services'):
        env['INPUT_VERIFICATION_RUN_ID'] = '234567'
        env['INPUT_VERIFICATION_SHA256'] = 'c' * 64
    result = _helper().validate_inputs(env)
    assert result['mode'] == mode
    if mode.startswith('delete-'):
        assert result['wall_clock_seconds'] == 300


@pytest.mark.parametrize(('field', 'value'), [
    ('INPUT_MODE', 'delete-system-search; touch /tmp/purge-injected'),
    ('INPUT_MODE', 'rewrite-system_archetype'),
    ('INPUT_CONFIRM_TARGET', 'ed-finder-prod/nb79a3d.mevnode.com\n'),
    ('INPUT_CONFIRM_TARGET', 'other-host'),
    ('INPUT_PLAN_RUN_ID', '../123'),
    ('INPUT_PLAN_RUN_ID', '123\n'),
    ('INPUT_PLAN_RUN_ID', '$(id)'),
    ('INPUT_PLAN_RUN_ID', '0'),
    ('INPUT_PLAN_RUN_ID', '1' * 21),
    ('INPUT_PLAN_SHA256', 'B' * 64),
    ('INPUT_PLAN_SHA256', 'a' * 63),
    ('INPUT_PLAN_SHA256', 'a' * 64 + '\n'),
    ('INPUT_VERIFICATION_RUN_ID', '123;id'),
    ('INPUT_VERIFICATION_SHA256', '`id`'),
    ('INPUT_ACKNOWLEDGE_FAILED_STOP', '1'),
    ('INPUT_WALL_CLOCK_SECONDS', '300'),
])
def test_hostile_and_mode_inappropriate_inputs_fail_closed(field, value):
    env = _inputs('authorize')
    env[field] = value
    with pytest.raises(ValueError):
        _helper().validate_inputs(env)


@pytest.mark.parametrize('mode', ['plan', 'status'])
@pytest.mark.parametrize('field', ['INPUT_PLAN_RUN_ID', 'INPUT_PLAN_SHA256', 'INPUT_VERIFICATION_RUN_ID', 'INPUT_VERIFICATION_SHA256'])
def test_read_only_modes_refuse_artifact_inputs(mode, field):
    env = _inputs(mode)
    env[field] = RUN_ID if field.endswith('RUN_ID') else 'b' * 64
    with pytest.raises(ValueError):
        _helper().validate_inputs(env)


@pytest.mark.parametrize('mode', sorted(MODES - {'plan', 'status'}))
@pytest.mark.parametrize('field', ['INPUT_PLAN_RUN_ID', 'INPUT_PLAN_SHA256'])
def test_every_protected_phase_requires_both_plan_identifiers(mode, field):
    env = _inputs(mode)
    env[field] = ''
    with pytest.raises(ValueError):
        _helper().validate_inputs(env)


@pytest.mark.parametrize('value', ['0', '1801', '-1', '1.5', '300\n', '$(id)', '9' * 1000])
def test_delete_wall_clock_is_a_bounded_whole_integer(value):
    env = _inputs('delete-system-search')
    env.update(INPUT_VERIFICATION_RUN_ID='234567', INPUT_VERIFICATION_SHA256='c' * 64,
               INPUT_WALL_CLOCK_SECONDS=value)
    with pytest.raises(ValueError):
        _helper().validate_inputs(env)


@pytest.mark.parametrize('value', ['1', '1800'])
def test_delete_wall_clock_boundaries_are_admitted(value):
    env = _inputs('delete-system-search')
    env.update(INPUT_VERIFICATION_RUN_ID='234567', INPUT_VERIFICATION_SHA256='c' * 64,
               INPUT_WALL_CLOCK_SECONDS=value)
    assert _helper().validate_inputs(env)['wall_clock_seconds'] == int(value)


def test_failed_stop_acknowledgement_is_restore_only_and_digits_only():
    env = _inputs('restore-services')
    env.update(INPUT_VERIFICATION_RUN_ID='234567', INPUT_VERIFICATION_SHA256='c' * 64,
               INPUT_ACKNOWLEDGE_FAILED_STOP='42')
    assert str(_helper().validate_inputs(env)['acknowledge_failed_stop']) == '42'
    for value in ('0', '42\n', '42;id', '-1'):
        env['INPUT_ACKNOWLEDGE_FAILED_STOP'] = value
        with pytest.raises(ValueError):
            _helper().validate_inputs(env)


def test_successful_exact_main_run_has_accepted_provenance():
    _helper().validate_run(_run(), run_id=RUN_ID, source_sha=SOURCE_SHA)


@pytest.mark.parametrize(('field', 'value'), [
    ('id', 999), ('head_repository', {'full_name': 'attacker/ed-finder'}),
    ('head_repository', None),
    ('path', '.github/workflows/chatgpt-ed-new-ops.yml'),
    ('event', 'pull_request'), ('status', 'in_progress'), ('conclusion', 'failure'),
    ('head_branch', 'attacker'), ('head_sha', 'b' * 40),
])
def test_artifact_run_provenance_rejects_every_wrong_boundary(field, value):
    run = _run()
    run[field] = value
    with pytest.raises(ValueError):
        _helper().validate_run(run, run_id=RUN_ID, source_sha=SOURCE_SHA)


def test_sealed_exact_run_receipt_is_authenticated(tmp_path):
    receipt = _seal(_receipt())
    path = tmp_path / 'receipt.json'
    path.write_text(json.dumps(receipt))
    _helper().authenticate_receipt(path, receipt['content_sha256'], mode='plan', run_id=RUN_ID, source_sha=SOURCE_SHA)


@pytest.mark.parametrize(('field', 'value'), [
    ('schema_version', 'other'), ('operation', 'other'), ('phase', 'status'),
    ('workflow_run_id', '999'), ('source_git_sha', 'b' * 40),
    ('status', 'stopped'), ('failures', ['host_mismatch']),
    ('host', 'other'), ('fqdn', 'other.example'),
])
def test_sealed_receipt_still_requires_exact_action_run_and_phase(tmp_path, field, value):
    body = _receipt()
    body[field] = value
    receipt = _seal(body)
    path = tmp_path / 'receipt.json'
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        _helper().authenticate_receipt(path, receipt['content_sha256'], mode='plan', run_id=RUN_ID, source_sha=SOURCE_SHA)


def test_tampered_receipt_or_wrong_reviewed_digest_is_rejected(tmp_path):
    receipt = _seal(_receipt())
    path = tmp_path / 'receipt.json'
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        _helper().authenticate_receipt(path, 'f' * 64, mode='plan', run_id=RUN_ID, source_sha=SOURCE_SHA)
    receipt['reviewed_plan'] = {'tampered': True}
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        _helper().authenticate_receipt(path, receipt['content_sha256'], mode='plan', run_id=RUN_ID, source_sha=SOURCE_SHA)


def test_receipt_symlink_is_refused(tmp_path):
    receipt = _seal(_receipt())
    path = tmp_path / 'receipt.json'
    path.write_text(json.dumps(receipt))
    symlink = tmp_path / 'linked.json'
    symlink.symlink_to(path)
    with pytest.raises(ValueError):
        _helper().authenticate_receipt(symlink, receipt['content_sha256'], mode='plan', run_id=RUN_ID, source_sha=SOURCE_SHA)


def test_remote_controller_polls_and_waits_for_action_exit():
    source = HELPER.read_text()
    assert 'kill -0' in source
    assert 'wait ' in source
    assert '--controller-pid' in source
    assert '--controller-run-id' in source
    assert 'GITHUB_RUN_ID' in source
    assert 'subprocess.run(' in source
    assert 'v3-derived-generation-purge.sh' in source
    assert 'start_new_session=True' not in source
    assert 'nohup' not in source


@pytest.mark.parametrize('mode', sorted(
    {mode for mode in MODES if mode.startswith(('delete-', 'rewrite-', 'abort-relation-'))}
    | {'complete', 'restore-services'}
))
@pytest.mark.parametrize('field', ['INPUT_VERIFICATION_RUN_ID', 'INPUT_VERIFICATION_SHA256'])
def test_destructive_completion_and_recovery_modes_require_the_exclusion_proof(mode, field):
    env = _inputs(mode)
    env.update(INPUT_VERIFICATION_RUN_ID='234567', INPUT_VERIFICATION_SHA256='c' * 64)
    if mode.startswith('delete-'):
        env['INPUT_WALL_CLOCK_SECONDS'] = '300'
    env[field] = ''
    with pytest.raises(ValueError):
        _helper().validate_inputs(env)


@pytest.mark.parametrize('field', ['INPUT_PLAN_RUN_ID', 'INPUT_VERIFICATION_RUN_ID'])
def test_dispatch_cannot_authenticate_an_artifact_from_itself(field):
    env = _inputs('delete-system-search')
    env.update(INPUT_VERIFICATION_RUN_ID='234567', INPUT_VERIFICATION_SHA256='c' * 64,
               INPUT_WALL_CLOCK_SECONDS='300')
    env[field] = env['GITHUB_RUN_ID']
    with pytest.raises(ValueError):
        _helper().validate_inputs(env)


@pytest.mark.parametrize('mode', ['plan', 'verify-system-archetype-empty'])
def test_a_plan_cannot_stand_in_for_an_exclusion_verification_receipt(tmp_path, mode):
    actual_mode = 'verify-system-archetype-empty' if mode == 'plan' else 'plan'
    receipt = _seal(_receipt(actual_mode))
    path = tmp_path / 'receipt.json'
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        _helper().authenticate_receipt(path, receipt['content_sha256'], mode=mode, run_id=RUN_ID, source_sha=SOURCE_SHA)


def test_remote_controller_remains_running_until_its_action_exits(tmp_path):
    """Execute the actual polling/trap shell with a local inert action."""
    module = _helper()
    script = module.remote_script(module.validate_inputs(_inputs()), SOURCE_SHA, RUN_ID)
    # The source-unpacking/host admission prefix is independently asserted by
    # workflow contracts. Run the unmodified controller body in a disposable
    # directory so this check needs no SSH, root, credentials or production.
    script = script[script.index('export GITHUB_RUN_ID='):]
    action = tmp_path / 'scripts/operator/actions/v3-derived-generation-purge.sh'
    action.parent.mkdir(parents=True)
    action.write_text('touch action-started\nsleep 0.3\ntouch action-finished\nexit 23\n')
    process = subprocess.Popen(['bash', '-c', script], cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 2
        while not (tmp_path / 'action-started').exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert (tmp_path / 'action-started').exists()
        assert process.poll() is None, 'controller returned while remote action was running'
        process.communicate(timeout=5)
        assert process.returncode == 23
        assert (tmp_path / 'action-finished').exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


@pytest.mark.parametrize('timeout', [None, 0, -1, True, '7200000', 7_200_001])
def test_rewrite_must_fit_the_reviewed_workflow_timeout_envelope(monkeypatch, tmp_path, timeout):
    module = _helper()
    env = _artifact_environment(module, monkeypatch, tmp_path, 'rewrite-system-search')
    path = tmp_path / 'purge-plan/receipt.json'
    body = json.loads(path.read_text())
    del body['content_sha256']
    body['reviewed_plan'] = {'rewrite': {'system_search': {'statement_timeout_ms': timeout}}}
    sealed = _seal(body)
    path.write_text(json.dumps(sealed))
    env['INPUT_PLAN_SHA256'] = sealed['content_sha256']
    with pytest.raises(ValueError, match='rewrite_timeout_outside_workflow_budget'):
        module.authenticate(env, fetch=False)


@pytest.mark.parametrize('timeout', [1, 7_200_000])
def test_rewrite_timeout_envelope_admits_its_boundaries(monkeypatch, tmp_path, timeout):
    module = _helper()
    env = _artifact_environment(module, monkeypatch, tmp_path, 'rewrite-system-search')
    path = tmp_path / 'purge-plan/receipt.json'
    body = json.loads(path.read_text())
    del body['content_sha256']
    body['reviewed_plan'] = {'rewrite': {'system_search': {'statement_timeout_ms': timeout}}}
    sealed = _seal(body)
    path.write_text(json.dumps(sealed))
    env['INPUT_PLAN_SHA256'] = sealed['content_sha256']
    assert module.authenticate(env, fetch=False)['mode'] == 'rewrite-system-search'
    assert module.MAX_REWRITE_MS == 7_200_000
    assert int(_job()['timeout-minutes']) * 60 > timeout / 1000 + 1800 + 65


@pytest.mark.parametrize(('field', 'value'), [
    ('SSH_HOST', 'other.example'), ('SSH_HOST', 'nb79a3d.mevnode.com;id'),
    ('SSH_PORT', '0'), ('SSH_PORT', '65536'), ('SSH_PORT', '22\n'),
    ('SSH_USER', 'root;id'), ('SSH_USER', '-oProxyCommand=id'),
    ('INPUT_MODE', 'plan;id'),
])
def test_invalid_transport_or_dispatch_identity_never_starts_ssh(monkeypatch, tmp_path, field, value):
    module = _helper()
    env = _inputs()
    env.update(SSH_HOST='nb79a3d.mevnode.com', SSH_PORT='22', SSH_USER='root', RUNNER_TEMP=str(tmp_path))
    env[field] = value
    calls = []
    monkeypatch.setattr(module.subprocess, 'run', lambda *args, **kwargs: calls.append(args))
    with pytest.raises(ValueError):
        module.execute(env)
    assert calls == []


def _artifact_environment(module, monkeypatch, tmp_path, mode, *, receipt_sha=SOURCE_SHA):
    env = _inputs(mode)
    env.update(RUNNER_TEMP=str(tmp_path), GITHUB_SHA='d' * 40)
    if mode.startswith(('delete-', 'rewrite-', 'abort-relation-')) or mode in ('complete', 'restore-services'):
        env.update(INPUT_VERIFICATION_RUN_ID='234567', INPUT_VERIFICATION_SHA256='c' * 64)
    if mode.startswith('delete-'):
        env['INPUT_WALL_CLOCK_SECONDS'] = '300'
    for prefix, phase in (('plan', 'plan'), ('verification', 'verify-system-archetype-empty')):
        run_id = env['INPUT_' + prefix.upper() + '_RUN_ID']
        if not run_id:
            continue
        receipt = _receipt(phase)
        receipt.update(workflow_run_id=run_id, source_git_sha=receipt_sha)
        sealed = _seal(receipt)
        directory = tmp_path / ('purge-' + prefix)
        directory.mkdir()
        (directory / 'receipt.json').write_text(json.dumps(sealed))
        env['INPUT_' + prefix.upper() + '_SHA256'] = sealed['content_sha256']
    original_load = module._load
    def fetch_run(repository, run_id, token):
        run = _run()
        run['id'] = int(run_id)
        return run
    def load(name, path):
        if str(path).endswith('scripts/release/v3_release_run.py'):
            return SimpleNamespace(fetch_run=fetch_run)
        return original_load(name, path)
    monkeypatch.setattr(module, '_load', load)
    return env


@pytest.mark.parametrize('mode', ['restore-services', 'delete-system-search'])
def test_authenticated_older_main_plan_keeps_recovery_and_continuation_available(monkeypatch, tmp_path, mode):
    module = _helper()
    env = _artifact_environment(module, monkeypatch, tmp_path, mode)
    assert env['GITHUB_SHA'] != SOURCE_SHA
    assert module.authenticate(env)['mode'] == mode
    # The execute step repeats seal/receipt admission after the earlier API
    # provenance check, and must preserve the same recovery behavior.
    assert module.authenticate(env, fetch=False)['mode'] == mode


def test_authorization_requires_a_plan_from_the_current_main_source(monkeypatch, tmp_path):
    module = _helper()
    env = _artifact_environment(module, monkeypatch, tmp_path, 'authorize')
    with pytest.raises(ValueError):
        module.authenticate(env)


@pytest.mark.parametrize('mode', ['restore-services', 'delete-system-search', 'authorize'])
def test_receipt_source_must_match_its_successful_origin_run(monkeypatch, tmp_path, mode):
    module = _helper()
    env = _artifact_environment(module, monkeypatch, tmp_path, mode, receipt_sha='b' * 40)
    with pytest.raises(ValueError):
        module.authenticate(env)


@pytest.mark.parametrize('mode', ['authorize', 'delete-system-search', 'restore-services'])
def test_oversized_rewrite_budget_is_refused_before_entering_or_recovering_a_plan(monkeypatch, tmp_path, mode):
    module = _helper()
    env = _artifact_environment(module, monkeypatch, tmp_path, mode)
    path = tmp_path / 'purge-plan/receipt.json'
    body = json.loads(path.read_text())
    del body['content_sha256']
    # Authorization is otherwise from its current head. Subsequent phases use
    # the same old immutable plan, including recovery's possible ANALYZE budget.
    if mode == 'authorize':
        env['GITHUB_SHA'] = SOURCE_SHA
    body['reviewed_plan']['rewrite'] = {'system_search': {'statement_timeout_ms': 7_200_001}}
    sealed = _seal(body)
    path.write_text(json.dumps(sealed))
    env['INPUT_PLAN_SHA256'] = sealed['content_sha256']
    with pytest.raises(ValueError, match='rewrite_timeout_outside_workflow_budget'):
        module.authenticate(env)


def test_remote_success_requires_a_sealed_success_receipt_before_reusable_artifact_upload():
    source = _runs()
    assert 'evidence.load_sealed(remote)' in source
    assert "receipt.get('status') != 'success'" in source
    assert "receipt.get('failures') != []" in source
    assert "receipt.get('source_git_sha') != os.environ['GITHUB_SHA']" in source
    assert "receipt.get('workflow_run_id') != os.environ['GITHUB_RUN_ID']" in source
    steps = _job()['steps']
    for step in steps:
        if step.get('with', {}).get('name') in ('v3-derived-purge-plan', 'v3-derived-purge-verification') and step.get('uses', '').startswith('actions/upload-artifact@'):
            assert step['if'].startswith('success() &&')


def test_transport_failure_receipt_keeps_the_full_sealed_shape_and_unknown_write_outcomes(tmp_path):
    module = _helper()
    env = _inputs('delete-system-search')
    env['RUNNER_TEMP'] = str(tmp_path)
    module.initialize_receipt(env)
    sealed = json.loads((tmp_path / 'receipt.json').read_text())
    digest = sealed.pop('content_sha256')
    assert digest == _seal(sealed)['content_sha256']
    assert sealed['status'] == 'stopped'
    assert sealed['failures'] == ['workflow_did_not_complete']
    assert sealed['workflow_run_id'] == env['GITHUB_RUN_ID']
    assert sealed['source_git_sha'] == env['GITHUB_SHA']
    for field in ('db_writes_performed', 'canonical_writes_performed', 'pointer_changes_performed',
                  'publication_performed', 'service_changes_performed', 'filesystem_reclamation_performed',
                  'migration_execution_performed', 'application_deployment_performed'):
        assert field in sealed and sealed[field] is None
    assert 'transaction_outcome' in sealed and sealed['transaction_outcome'] is None
