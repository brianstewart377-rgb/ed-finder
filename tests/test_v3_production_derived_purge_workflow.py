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
REHEARSAL_RUN_ID = '345678'
RELATIONS = ('system-search', 'economy-opportunity', 'body-mechanics', 'system-rating-vector')
COPY_PREFIXES = ('preflight-', 'copy-', 'swap-', 'swap-back-', 'drop-', 'abandon-')
MODES = {
    'plan', 'status', 'authorize', 'verify-system-archetype-empty',
    'restore-services', 'complete',
    *(prefix + relation for prefix in (*COPY_PREFIXES, 'abort-relation-') for relation in RELATIONS),
}
# Disabled by the accepted copy-and-drop design (owner answer 6): refused
# before approval/SSH and by the action, and absent from the workflow choices.
DISABLED_MODES = {prefix + relation for prefix in ('delete-', 'rewrite-') for relation in RELATIONS}
PROOF_PREFIXES = ('copy-', 'swap-', 'swap-back-', 'drop-', 'abandon-', 'abort-relation-')


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
        'verification_run_id', 'verification_sha256', 'rehearsal_run_id', 'rehearsal_sha256',
        'acknowledge_failed_stop', 'wall_clock_seconds',
    }
    assert inputs['mode']['type'] == 'choice'
    assert len(inputs['mode']['options']) == len(MODES)
    assert set(inputs['mode']['options']) == MODES
    action_path = ROOT / 'scripts/operator/lib/v3_generation_purge.py'
    spec = importlib.util.spec_from_file_location('protected_purge_action_contract', action_path)
    action = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(action)
    action_modes = set(action.MODES)
    assert set(inputs['mode']['options']) == action_modes
    assert action_modes == MODES
    assert all(action.classify_mode(mode) == mode for mode in action_modes)
    assert set(action.DISABLED_MODES) == DISABLED_MODES
    assert not DISABLED_MODES & set(inputs['mode']['options'])
    for mode in sorted(DISABLED_MODES):
        with pytest.raises(ValueError, match=action.DISABLED_REASON):
            action.classify_mode(mode)
    assert inputs['confirm_target']['required'] == 'true'
    assert inputs['plan_run_id']['required'] == 'false'
    assert inputs['verification_run_id']['required'] == 'false'
    assert inputs['rehearsal_run_id']['required'] == 'false'


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
    assert len(downloads) == 3
    # Every download is by exact name; none uses a pattern.
    assert all('pattern' not in step['with'] for step in downloads)
    rehearsal_name = ('v3-derived-purge-rehearsal-${{ inputs.rehearsal_run_id }}'
                      '-${{ steps.rehearsal-attempt.outputs.attempt }}')
    assert {step['with']['name'] for step in downloads} == {
        'v3-derived-purge-plan', 'v3-derived-purge-verification', rehearsal_name,
    }
    # The rehearsal artifact name carries its run attempt. The workflow
    # resolves the attempt GitHub reports and downloads exactly that artifact
    # into its own directory, where authentication (which re-fetches the run)
    # reads it: a single-match pattern download would extract into the root
    # instead (plan run 40939364894).
    rehearsal = next(step for step in downloads if step['with']['name'] == rehearsal_name)
    assert rehearsal['if'] == "inputs.mode == 'plan'"
    assert rehearsal['with']['path'] == '${{ runner.temp }}/purge-rehearsal/' + rehearsal_name
    resolve = next(step for step in steps if step.get('id') == 'rehearsal-attempt')
    assert resolve['if'] == "inputs.mode == 'plan'"
    assert steps.index(resolve) < steps.index(rehearsal)
    assert resolve['env'] == {'GH_TOKEN': '${{ github.token }}'}
    assert '[[ "$INPUT_REHEARSAL_RUN_ID" =~ ^[1-9][0-9]{0,19}$ ]] || exit 64' in resolve['run']
    assert 'actions/runs/$INPUT_REHEARSAL_RUN_ID" --jq \'.run_attempt\'' in resolve['run']
    assert '[[ "$attempt" =~ ^[1-9][0-9]{0,4}$ ]] || exit 64' in resolve['run']
    assert {step['with']['run-id'] for step in downloads} == {
        '${{ inputs.plan_run_id }}', '${{ inputs.verification_run_id }}', '${{ inputs.rehearsal_run_id }}',
    }
    assert '"$RUNNER_TEMP/purge-rehearsal/receipt.json" "$bundle/artifacts/rehearsal.json"' in _runs()
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
        'INPUT_REHEARSAL_RUN_ID': REHEARSAL_RUN_ID if mode == 'plan' else '',
        'INPUT_REHEARSAL_SHA256': 'e' * 64 if mode == 'plan' else '',
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
    if mode.startswith('copy-'):
        env['INPUT_WALL_CLOCK_SECONDS'] = '300'
    if mode.startswith(PROOF_PREFIXES) or mode in ('complete', 'restore-services'):
        env['INPUT_VERIFICATION_RUN_ID'] = '234567'
        env['INPUT_VERIFICATION_SHA256'] = 'c' * 64
    result = _helper().validate_inputs(env)
    assert result['mode'] == mode
    if mode.startswith('copy-'):
        assert result['wall_clock_seconds'] == 300
    else:
        assert result['wall_clock_seconds'] is None


@pytest.mark.parametrize('mode', sorted(DISABLED_MODES))
def test_disabled_delete_and_rewrite_modes_are_refused_before_approval_or_ssh(mode):
    env = _inputs(mode)
    env.update(INPUT_VERIFICATION_RUN_ID='234567', INPUT_VERIFICATION_SHA256='c' * 64)
    if mode.startswith('delete-'):
        env['INPUT_WALL_CLOCK_SECONDS'] = '300'
    helper = _helper()
    with pytest.raises(ValueError, match=helper.DISABLED_REASON):
        helper.validate_inputs(env)


@pytest.mark.parametrize('relation', RELATIONS)
def test_preflight_is_plan_only_and_refuses_the_exclusion_proof(relation):
    env = _inputs('preflight-' + relation)
    assert _helper().validate_inputs(env)['mode'] == 'preflight-' + relation
    env.update(INPUT_VERIFICATION_RUN_ID='234567', INPUT_VERIFICATION_SHA256='c' * 64)
    with pytest.raises(ValueError):
        _helper().validate_inputs(env)


@pytest.mark.parametrize(('field', 'value'), [
    ('INPUT_MODE', 'copy-system-search; touch /tmp/purge-injected'),
    ('INPUT_MODE', 'swap-system_archetype'),
    ('INPUT_MODE', 'delete-system-search'),
    ('INPUT_MODE', 'rewrite-system-search'),
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


@pytest.mark.parametrize('value', ['0', '9001', '-1', '1.5', '300\n', '$(id)', '9' * 1000, ''])
def test_copy_wall_clock_is_a_bounded_whole_integer(value):
    env = _inputs('copy-system-search')
    env.update(INPUT_VERIFICATION_RUN_ID='234567', INPUT_VERIFICATION_SHA256='c' * 64,
               INPUT_WALL_CLOCK_SECONDS=value)
    with pytest.raises(ValueError):
        _helper().validate_inputs(env)


@pytest.mark.parametrize('value', ['1', '9000'])
def test_copy_wall_clock_boundaries_are_admitted(value):
    env = _inputs('copy-system-search')
    env.update(INPUT_VERIFICATION_RUN_ID='234567', INPUT_VERIFICATION_SHA256='c' * 64,
               INPUT_WALL_CLOCK_SECONDS=value)
    assert _helper().validate_inputs(env)['wall_clock_seconds'] == int(value)


@pytest.mark.parametrize('mode', ['swap-system-search', 'drop-body-mechanics', 'abandon-system-rating-vector',
                                  'swap-back-economy-opportunity', 'complete', 'authorize'])
def test_wall_clock_is_copy_only(mode):
    env = _inputs(mode)
    if mode != 'authorize':
        env.update(INPUT_VERIFICATION_RUN_ID='234567', INPUT_VERIFICATION_SHA256='c' * 64)
    env['INPUT_WALL_CLOCK_SECONDS'] = '300'
    with pytest.raises(ValueError, match='wall_clock_is_copy_only'):
        _helper().validate_inputs(env)


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
    {mode for mode in MODES if mode.startswith(PROOF_PREFIXES)}
    | {'complete', 'restore-services'}
))
@pytest.mark.parametrize('field', ['INPUT_VERIFICATION_RUN_ID', 'INPUT_VERIFICATION_SHA256'])
def test_destructive_completion_and_recovery_modes_require_the_exclusion_proof(mode, field):
    env = _inputs(mode)
    env.update(INPUT_VERIFICATION_RUN_ID='234567', INPUT_VERIFICATION_SHA256='c' * 64)
    if mode.startswith('copy-'):
        env['INPUT_WALL_CLOCK_SECONDS'] = '300'
    env[field] = ''
    with pytest.raises(ValueError):
        _helper().validate_inputs(env)


@pytest.mark.parametrize('field', ['INPUT_PLAN_RUN_ID', 'INPUT_VERIFICATION_RUN_ID'])
def test_dispatch_cannot_authenticate_an_artifact_from_itself(field):
    env = _inputs('copy-system-search')
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
    # The inert action holds for long enough that "controller still running
    # once the action has started" cannot be lost to scheduler jitter between
    # the marker appearing and the poll below (0.3 s was too tight on CI).
    action.write_text('touch action-started\nsleep 1.5\ntouch action-finished\nexit 23\n')
    process = subprocess.Popen(['bash', '-c', script], cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 10
        while not (tmp_path / 'action-started').exists() and time.monotonic() < deadline:
            if process.poll() is not None:
                break
            time.sleep(0.01)
        assert (tmp_path / 'action-started').exists(), process.poll()
        assert process.poll() is None, 'controller returned while remote action was running'
        process.communicate(timeout=15)
        assert process.returncode == 23
        assert (tmp_path / 'action-finished').exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


COMMITTED_REHEARSAL = ROOT / 'docs/operations/evidence/2026-10-24-v3-derived-purge-rehearsal-receipt-run-40074011789.json'


def _committed_rewrite_figures():
    """The legacy per-relation VACUUM FULL estimates of the 2026-10-24 receipt."""
    receipt = json.loads(COMMITTED_REHEARSAL.read_text())
    figures = {relation: {key: item['production'][key] for key in ('rewrite_peak_bytes', 'statement_timeout_ms')}
               for relation, item in receipt['per_relation'].items()}
    assert figures['system_search']['statement_timeout_ms'] == 30_659_000
    return figures


def _replace_plan(tmp_path, env, mutate):
    path = tmp_path / 'purge-plan/receipt.json'
    body = json.loads(path.read_text())
    del body['content_sha256']
    mutate(body)
    sealed = _seal(body)
    path.write_text(json.dumps(sealed))
    env['INPUT_PLAN_SHA256'] = sealed['content_sha256']


@pytest.mark.parametrize('mode', ['swap-system-search', 'copy-system-search', 'restore-services',
                                  'drop-economy-opportunity', 'swap-back-body-mechanics'])
def test_legacy_rewrite_estimates_no_longer_gate_the_copy_route(monkeypatch, tmp_path, mode):
    """Codex 4379797627: the copy route never runs a VACUUM FULL, so the
    committed receipt's 30,659,000 ms Search estimate must not refuse a plan."""
    module = _helper()
    env = _artifact_environment(module, monkeypatch, tmp_path, mode)
    _replace_plan(tmp_path, env, lambda body: body.update(reviewed_plan={'rewrite': _committed_rewrite_figures()}))
    assert module.authenticate(env, fetch=False)['mode'] == mode
    assert module.authenticate(env)['mode'] == mode


def test_authorize_admits_a_copy_bound_plan_that_also_carries_the_legacy_estimates(monkeypatch, tmp_path):
    from tests.test_v3_purge_rehearsal_receipt import example_receipt, tool
    module = _helper()
    reviewed = {'rewrite': _committed_rewrite_figures()}
    tool.apply_to_plan(reviewed, example_receipt())
    env = _bound_plan_environment(module, monkeypatch, tmp_path, reviewed)
    assert module.authenticate(env)['mode'] == 'authorize'


@pytest.mark.parametrize('timeout', [0, -1, True, '7200000', 7_200_001, None])
@pytest.mark.parametrize('mode', ['swap-system-search', 'copy-system-search', 'restore-services'])
def test_sealed_copy_phase_timeouts_must_fit_the_reviewed_workflow_envelope(monkeypatch, tmp_path, timeout, mode):
    module = _helper()
    env = _artifact_environment(module, monkeypatch, tmp_path, mode)
    def mutate(body):
        body['reviewed_plan'] = {'copy': {'phase_timeouts': {'verify': {'statement_timeout_ms': timeout}}}}
    _replace_plan(tmp_path, env, mutate)
    with pytest.raises(ValueError, match='copy_phase_timeout_outside_workflow_budget'):
        module.authenticate(env, fetch=False)


@pytest.mark.parametrize('block', [[], 'copy', {'phase_timeouts': None}, {'phase_timeouts': []}])
def test_a_malformed_copy_block_is_refused(monkeypatch, tmp_path, block):
    module = _helper()
    env = _artifact_environment(module, monkeypatch, tmp_path, 'swap-system-search')
    _replace_plan(tmp_path, env, lambda body: body.update(reviewed_plan={'copy': block}))
    with pytest.raises(ValueError, match='copy_phase_timeout_outside_workflow_budget'):
        module.authenticate(env, fetch=False)


@pytest.mark.parametrize('timeout', [1, 7_200_000])
def test_copy_phase_timeout_envelope_admits_its_boundaries(monkeypatch, tmp_path, timeout):
    module = _helper()
    env = _artifact_environment(module, monkeypatch, tmp_path, 'swap-system-search')
    def mutate(body):
        body['reviewed_plan'] = {'copy': {'phase_timeouts': {'verify': {'statement_timeout_ms': timeout}}}}
    _replace_plan(tmp_path, env, mutate)
    assert module.authenticate(env, fetch=False)['mode'] == 'swap-system-search'
    assert module.MAX_REWRITE_MS == 7_200_000
    assert int(_job()['timeout-minutes']) * 60 > timeout / 1000 + 1800 + 65


def test_every_phase_the_copy_route_executes_fits_the_workflow_envelope(monkeypatch, tmp_path):
    """The budget applies to the statements the route runs: v3_purge_copy.PHASES."""
    module = _helper()
    copy = module._load('purge_workflow_copy_check', ROOT / 'scripts/operator/lib/v3_purge_copy.py')
    assert max(statement for statement, *_ in copy.PHASES.values()) == module.MAX_REWRITE_MS
    env = _artifact_environment(module, monkeypatch, tmp_path, 'swap-system-search')
    original = module._load
    def load(name, path):
        loaded = original(name, path)
        if str(path).endswith('scripts/operator/lib/v3_purge_copy.py'):
            loaded.PHASES = {**loaded.PHASES, 'verify': (module.MAX_REWRITE_MS + 1, 5_000, None, True)}
        return loaded
    monkeypatch.setattr(module, '_load', load)
    with pytest.raises(ValueError, match='copy_phase_timeout_outside_workflow_budget'):
        module.authenticate(env, fetch=False)


def test_the_action_still_bounds_a_recovered_legacy_rewrite_analyze():
    """restore-services may still recover an open 016 rewrite; that ANALYZE uses
    the plan's legacy timeout, so the action itself refuses one over budget."""
    source = (ROOT / 'scripts/operator/lib/v3_purge_rewrite_dispatch.py').read_text()
    assert "config['statement_timeout_ms'] > rewrite.MAX_RECOVERY_STATEMENT_MS" in source
    assert "raise ValueError('rewrite_timeout_outside_workflow_budget')" in source
    rewrite_source = (ROOT / 'scripts/operator/lib/v3_purge_rewrite.py').read_text()
    assert 'MAX_RECOVERY_STATEMENT_MS = 7_200_000' in rewrite_source


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
    if mode.startswith(PROOF_PREFIXES) or mode in ('complete', 'restore-services'):
        env.update(INPUT_VERIFICATION_RUN_ID='234567', INPUT_VERIFICATION_SHA256='c' * 64)
    if mode.startswith('copy-'):
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


@pytest.mark.parametrize('mode', ['restore-services', 'copy-system-search', 'swap-back-system-search'])
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


@pytest.mark.parametrize('mode', ['restore-services', 'copy-system-search', 'authorize'])
def test_receipt_source_must_match_its_successful_origin_run(monkeypatch, tmp_path, mode):
    module = _helper()
    env = _artifact_environment(module, monkeypatch, tmp_path, mode, receipt_sha='b' * 40)
    with pytest.raises(ValueError):
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
    env = _inputs('copy-system-search')
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


@pytest.mark.parametrize('field', ['INPUT_REHEARSAL_RUN_ID', 'INPUT_REHEARSAL_SHA256'])
def test_protected_plan_requires_both_rehearsal_identifiers(field):
    env = _inputs('plan')
    env[field] = ''
    with pytest.raises(ValueError, match='invalid_rehearsal_reference'):
        _helper().validate_inputs(env)


@pytest.mark.parametrize('mode', sorted(MODES - {'plan'}))
@pytest.mark.parametrize('field', ['INPUT_REHEARSAL_RUN_ID', 'INPUT_REHEARSAL_SHA256'])
def test_rehearsal_identifiers_are_plan_only(mode, field):
    env = _inputs(mode)
    env.update(INPUT_VERIFICATION_RUN_ID='234567', INPUT_VERIFICATION_SHA256='c' * 64)
    if mode == 'status' or mode in ('authorize', 'verify-system-archetype-empty') or mode.startswith('preflight-'):
        env.update(INPUT_VERIFICATION_RUN_ID='', INPUT_VERIFICATION_SHA256='')
    if mode.startswith('copy-'):
        env['INPUT_WALL_CLOCK_SECONDS'] = '300'
    _helper().validate_inputs(env)
    env[field] = REHEARSAL_RUN_ID if field.endswith('RUN_ID') else 'e' * 64
    with pytest.raises(ValueError, match='rehearsal_reference_not_admitted'):
        _helper().validate_inputs(env)


@pytest.mark.parametrize(('field', 'value'), [
    ('INPUT_REHEARSAL_RUN_ID', '$(id)'), ('INPUT_REHEARSAL_RUN_ID', '0'),
    ('INPUT_REHEARSAL_RUN_ID', '345678\n'), ('INPUT_REHEARSAL_SHA256', 'E' * 64),
    ('INPUT_REHEARSAL_RUN_ID', '987654'),
])
def test_hostile_or_self_referencing_rehearsal_identifiers_fail_closed(field, value):
    env = _inputs('plan')
    env[field] = value
    with pytest.raises(ValueError):
        _helper().validate_inputs(env)


def test_rehearsal_run_provenance_is_the_dedicated_rehearsal_workflow_only():
    module = _helper()
    run = {**_run(), 'id': int(REHEARSAL_RUN_ID), 'path': module.REHEARSAL_WORKFLOW_PATH}
    module.validate_run(run, run_id=REHEARSAL_RUN_ID, source_sha=SOURCE_SHA, path=module.REHEARSAL_WORKFLOW_PATH)
    with pytest.raises(ValueError):
        module.validate_run(run, run_id=REHEARSAL_RUN_ID, source_sha=SOURCE_SHA)
    with pytest.raises(ValueError):
        module.validate_run(run, run_id=REHEARSAL_RUN_ID, source_sha=SOURCE_SHA,
                            path='.github/workflows/chatgpt-ed-new-ops.yml')


def _rehearsal_environment(module, monkeypatch, tmp_path, *, attempt=2, run_updates=None,
                           receipt_updates=None, stored_attempts=(1, 2)):
    from tests.test_v3_purge_rehearsal_receipt import example_receipt
    env = _inputs('plan')
    env.update(RUNNER_TEMP=str(tmp_path), GITHUB_SHA='d' * 40)
    receipt = example_receipt(**{'source_git_sha': SOURCE_SHA, **(receipt_updates or {})})
    root = tmp_path / 'purge-rehearsal'
    for stored in stored_attempts:
        directory = root / f'v3-derived-purge-rehearsal-{REHEARSAL_RUN_ID}-{stored}'
        directory.mkdir(parents=True)
        # An earlier failed attempt keeps a different, stopped receipt.
        value = receipt if stored == attempt else example_receipt(
            source_git_sha=SOURCE_SHA, status='stopped', failures=['crash_gate_failed'])
        (directory / 'rehearsal-receipt.json').write_text(json.dumps(value))
    env['INPUT_REHEARSAL_SHA256'] = receipt['content_sha256']
    original_load = module._load
    def fetch_run(repository, run_id, token):
        assert run_id == REHEARSAL_RUN_ID
        return {**_run(), 'id': int(run_id), 'path': module.REHEARSAL_WORKFLOW_PATH,
                'run_attempt': attempt, **(run_updates or {})}
    def load(name, path):
        if str(path).endswith('scripts/release/v3_release_run.py'):
            return SimpleNamespace(fetch_run=fetch_run)
        return original_load(name, path)
    monkeypatch.setattr(module, '_load', load)
    return env, receipt


def test_successful_attempts_one_percent_rehearsal_is_authenticated_and_staged(monkeypatch, tmp_path):
    module = _helper()
    env, receipt = _rehearsal_environment(module, monkeypatch, tmp_path)
    assert module.authenticate(env)['mode'] == 'plan'
    staged = tmp_path / 'purge-rehearsal/receipt.json'
    assert json.loads(staged.read_text()) == receipt
    assert staged.stat().st_mode & 0o777 == 0o600
    # The execute step re-authenticates exactly the staged bytes, tokenless.
    monkeypatch.setattr(module, '_load', _helper()._load)
    assert module.authenticate(env, fetch=False)['mode'] == 'plan'
    script = module.remote_script(module.validate_inputs(env), SOURCE_SHA, RUN_ID)
    assert ('--rehearsal-receipt artifacts/rehearsal.json --rehearsal-receipt-sha256 '
            + receipt['content_sha256']) in script


@pytest.mark.parametrize('defect', (
    'workflow', 'conclusion', 'branch', 'event', 'attempt', 'attempt_type', 'missing_artifact',
    'digest', 'smoke', 'crash_gate', 'source', 'symlink', 'oversized',
))
def test_rehearsal_receipt_admission_fails_closed(monkeypatch, tmp_path, defect):
    module = _helper()
    run_updates, receipt_updates, stored = {}, {}, (1, 2)
    if defect == 'workflow':
        run_updates['path'] = module.WORKFLOW_PATH
    elif defect == 'conclusion':
        run_updates['conclusion'] = 'failure'
    elif defect == 'branch':
        run_updates['head_branch'] = 'feature'
    elif defect == 'event':
        run_updates['event'] = 'push'
    elif defect == 'attempt':
        run_updates['run_attempt'] = 3
    elif defect == 'attempt_type':
        run_updates['run_attempt'] = '2'
    elif defect == 'missing_artifact':
        stored = (1,)
    elif defect == 'smoke':
        receipt_updates['scale'] = 'smoke'
    elif defect == 'crash_gate':
        receipt_updates['gate_10_crash_rehearsal_passed'] = False
    elif defect == 'source':
        receipt_updates['source_git_sha'] = 'b' * 40
    env, receipt = _rehearsal_environment(module, monkeypatch, tmp_path, run_updates=run_updates,
                                          receipt_updates=receipt_updates, stored_attempts=stored)
    path = tmp_path / f'purge-rehearsal/v3-derived-purge-rehearsal-{REHEARSAL_RUN_ID}-2/rehearsal-receipt.json'
    if defect == 'digest':
        env['INPUT_REHEARSAL_SHA256'] = 'f' * 64
    elif defect == 'symlink':
        target = tmp_path / 'elsewhere.json'
        target.write_text(path.read_text())
        path.unlink()
        path.symlink_to(target)
    elif defect == 'oversized':
        path.write_text(' ' * (module.MAX_RECEIPT + 1))
    with pytest.raises(ValueError):
        module.authenticate(env)
    assert defect != 'missing_artifact' or not (tmp_path / 'purge-rehearsal/receipt.json').exists()


def _bound_plan_environment(module, monkeypatch, tmp_path, reviewed):
    env = _artifact_environment(module, monkeypatch, tmp_path, 'authorize')
    env['GITHUB_SHA'] = SOURCE_SHA
    path = tmp_path / 'purge-plan/receipt.json'
    body = json.loads(path.read_text())
    del body['content_sha256']
    body['reviewed_plan'] = reviewed
    sealed = _seal(body)
    path.write_text(json.dumps(sealed))
    env['INPUT_PLAN_SHA256'] = sealed['content_sha256']
    return env


def test_authorize_admits_a_plan_carrying_reviewed_rehearsal_figures(monkeypatch, tmp_path):
    from tests.test_v3_purge_rehearsal_receipt import example_receipt, tool
    module = _helper()
    reviewed = {}
    tool.apply_to_plan(reviewed, example_receipt())
    env = _bound_plan_environment(module, monkeypatch, tmp_path, reviewed)
    assert module.authenticate(env)['mode'] == 'authorize'


def test_authorize_refuses_a_plan_without_reviewed_rehearsal_figures_before_ssh(monkeypatch, tmp_path):
    module = _helper()
    env = _bound_plan_environment(module, monkeypatch, tmp_path, {'plan_sha256': '6' * 64})
    with pytest.raises(ValueError, match='plan_rehearsal_figures_required'):
        module.authenticate(env)


def _bundle_paths():
    source = _runs()
    command = source[source.index('git archive HEAD') + len('git archive HEAD'):]
    command = command[:command.index('| tar')]
    return [token for token in command.replace('\\\n', ' ').split() if token != '\\']


def test_transported_source_bundle_can_revalidate_a_reviewed_rehearsal_receipt(tmp_path):
    """Reproduce the archive's path set and run the remote receipt validation in it."""
    import shutil
    from tests.test_v3_purge_rehearsal_receipt import example_receipt, tool
    bundle = tmp_path / 'bundle'
    paths = _bundle_paths()
    for relative in tool.HARNESS_FILES + (str(tool.LIFECYCLE_RECEIPT.relative_to(ROOT)),):
        assert relative in paths or any(relative.startswith(path + '/') for path in paths), relative
    tracked = subprocess.run(['git', '-C', str(ROOT), 'ls-files', '--', *paths],
                             capture_output=True, text=True, check=True).stdout.split()
    assert tracked
    for relative in tracked:
        target = bundle / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    spec = importlib.util.spec_from_file_location(
        'bundled_rehearsal_receipt', bundle / 'scripts/operator/lib/v3_purge_rehearsal_receipt.py')
    bundled = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bundled)
    assert bundled.ROOT == bundle
    receipt = example_receipt()
    path = tmp_path / 'rehearsal.json'
    path.write_text(json.dumps(receipt))
    assert bundled.load_reviewed(path, receipt['content_sha256'])['content_sha256'] == receipt['content_sha256']
