"""Run the real local transport with every host/service/privilege call stubbed."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / 'scripts/operator/actions/v3-live-checkpoint-local.sh'
SHA = 'a' * 40
UNITS = '\n'.join(sorted([
    'actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker.service',
    'actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-2.service',
    'actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-3.service',
]))
STUBS = r'''
hostname() { printf '%s\n' "${TEST_HOST:-vmi3542235}"; }
uname() { echo x86_64; }
id() {
  case "$1" in -un) echo codex;; -u|-g) echo "${TEST_UID:-1001}";; *) return 91;; esac
}
python3.14() { cat >/dev/null; return "${TEST_PYTHON_RC:-0}"; }
systemctl() {
  printf '%s\n' "$TEST_UNITS"
}
git() {
  if [ "$1" = rev-parse ]; then echo "${TEST_HEAD:-$GITHUB_SHA}";
  elif [ "$1" = archive ]; then
    printf '%s\n' "$*" >> "$TEST_ROOT/archive-calls"
    /usr/bin/tar -cf - --files-from /dev/null
  else return 91; fi
}
mktemp() { mkdir "$TEST_ROOT/work"; printf '%s\n' "$TEST_ROOT/work"; }
sudo() {
  printf '%s\n' "$*" >> "$TEST_ROOT/sudo-calls"
  case " $* " in
    *' docker login '*) cat >/dev/null; return "${TEST_LOGIN_RC:-0}";;
    *' docker logout '*) return "${TEST_LOGOUT_RC:-0}";;
    *) printf '{"status":"accepted"}\n'; return "${TEST_APPLY_RC:-0}";;
  esac
}
source "$TEST_SCRIPT" "$@"
'''


def run_local(tmp_path: Path, args: list[str], **overrides):
    candidate = tmp_path / 'candidate'
    candidate.mkdir(exist_ok=True)
    (candidate / 'v3-application-release.json').write_text('{}\n')
    (candidate / 'v3-application-release.json.sha256').write_text('fixture\n')
    env = {
        **os.environ, 'TEST_ROOT': str(tmp_path), 'RUNNER_TEMP': str(tmp_path),
        'TEST_SCRIPT': str(LOCAL), 'TEST_UNITS': UNITS,
        'GITHUB_REPOSITORY': 'brianstewart377-rgb/ed-finder',
        'GITHUB_REF': 'refs/heads/main', 'GITHUB_SHA': SHA,
        'GITHUB_EVENT_NAME': 'issue_comment' if args[0] == 'provision' else 'workflow_dispatch',
        'GHCR_TOKEN': 'synthetic-unit-test-token', **overrides,
    }
    return subprocess.run(['bash', '-c', STUBS, '_', *args], env=env,
                          text=True, capture_output=True, timeout=15, check=False)


@pytest.mark.parametrize('overrides', [
    {'GITHUB_REF': 'refs/heads/unreviewed'},
    {'GITHUB_REPOSITORY': 'other/repository'},
    {'GITHUB_SHA': 'not-a-sha'}, {'TEST_HEAD': 'b' * 40},
    {'TEST_HOST': 'wrong-host'}, {'TEST_UID': '0'},
    {'TEST_UNITS': UNITS + '\nactions.runner.unexpected.service'},
    {'TEST_PYTHON_RC': '78'}, {'GITHUB_EVENT_NAME': 'pull_request'},
])
def test_untrusted_or_wrong_host_request_stops_before_privilege(tmp_path, overrides):
    result = run_local(tmp_path, ['provision'], **overrides)
    assert result.returncode != 0
    assert not (tmp_path / 'sudo-calls').exists()
    assert not (tmp_path / 'work').exists()


@pytest.mark.parametrize('args', [
    ['unknown'], ['provision', 'extra'], ['deploy'],
    ['deploy', 'delete', '1'], ['deploy', 'bootstrap', '1;echo-injected'],
    ['deploy', 'upgrade', '0'], ['deploy', 'upgrade', '1', 'extra'],
])
def test_only_fixed_operations_and_typed_arguments_are_executable(tmp_path, args):
    result = run_local(tmp_path, args)
    assert result.returncode != 0
    assert not (tmp_path / 'sudo-calls').exists()


def test_provision_archives_exact_commit_and_invokes_only_reviewed_root_script(tmp_path):
    result = run_local(tmp_path, ['provision'])
    assert result.returncode == 0, result.stderr
    calls = (tmp_path / 'sudo-calls').read_text()
    archive = (tmp_path / 'archive-calls').read_text()
    assert f'archive {SHA} ' in archive
    assert 'scripts/seed_check.sh sql deploy/v3-live-checkpoint/target-authority.json' in archive
    assert 'CHECKPOINT_OPERATOR_UID=1001 CHECKPOINT_OPERATOR_GID=1001 CHECKPOINT_OPERATOR_USER=codex' in calls
    assert 'bash scripts/operator/actions/v3-live-checkpoint-provision.sh' in calls
    assert 'docker login' not in calls
    assert 'synthetic-unit-test-token' not in calls
    assert not (tmp_path / 'work').exists()


@pytest.mark.parametrize('mode', ['bootstrap', 'upgrade'])
@pytest.mark.parametrize('overrides, expected_rc', [
    ({}, 0), ({'TEST_LOGIN_RC': '1'}, 1),
    ({'TEST_APPLY_RC': '78'}, 78), ({'TEST_LOGOUT_RC': '1'}, 78),
])
def test_deploy_refreshes_nonroot_groups_and_always_logs_out(tmp_path, mode, overrides, expected_rc):
    result = run_local(tmp_path, ['deploy', mode, '42'], **overrides)
    assert result.returncode == expected_rc, result.stderr
    calls = (tmp_path / 'sudo-calls').read_text().splitlines()
    assert 'docker login ghcr.io -u brianstewart377-rgb --password-stdin' in calls[0]
    assert 'docker logout ghcr.io' in calls[-1]
    assert all('-n -u codex -- env -i' in line for line in calls)
    if not overrides.get('TEST_LOGIN_RC'):
        assert f'--mode {mode} --candidate-run-id 42' in calls[1]
        assert 'v3-app-live-checkpoint-preflight.sh' in calls[1]
    else:
        assert len(calls) == 2
    assert 'synthetic-unit-test-token' not in '\n'.join(calls) + result.stdout + result.stderr
    assert not (tmp_path / 'work').exists()


def test_workflows_keep_trusted_code_and_mutation_separation():
    control = yaml.safe_load((ROOT / '.github/workflows/v3-live-checkpoint-control.yml').read_text())
    deploy = yaml.safe_load((ROOT / '.github/workflows/v3-application-live-checkpoint-preflight.yml').read_text())
    for job in (control['jobs']['provision'], deploy['jobs']['deploy']):
        assert 'self-hosted' in str(job['runs-on']) and 'codex' in str(job['runs-on'])
        assert "github.ref == 'refs/heads/main'" in job['if']
        assert job['environment'] == 'v3-live-checkpoint'
        checkout = next(s for s in job['steps'] if s.get('uses', '').startswith('actions/checkout@'))
        assert checkout['with']['ref'] == '${{ github.sha }}'
        assert checkout['with']['persist-credentials'] is False
    assert control['jobs']['provision']['concurrency'] == deploy['concurrency']
    assert control['jobs']['release']['runs-on'] == 'ubuntu-24.04'
    assert control['jobs']['deploy']['runs-on'] == 'ubuntu-24.04'
    assert deploy['jobs']['public-smoke']['runs-on'] == 'ubuntu-24.04'
    assert deploy['jobs']['public-smoke']['needs'] == 'deploy'
    assert 'secrets.' not in json.dumps(control)
    # Default local transport needs no SSH settings; retained SSH compatibility
    # steps must be explicitly opted into and cannot block the local path.
    inputs = deploy.get('on', deploy.get(True))['workflow_dispatch']['inputs']
    assert inputs['transport']['default'] == 'local'
    for step in deploy['jobs']['deploy']['steps']:
        if 'secrets.V3_LIVE_CHECKPOINT' in json.dumps(step):
            assert "inputs.transport == 'ssh'" in step['if']
    local_step = next(s for s in deploy['jobs']['deploy']['steps'] if s['name'] == 'Run bounded Contabo local deployment boundary')
    assert local_step['if'] == "inputs.transport != 'ssh'"
    assert 'secrets.' not in json.dumps(local_step)
    local = LOCAL.read_text()
    assert 'systemctl restart' not in local and 'usermod' not in local
    assert 'codex exec' not in local and 'git pull' not in local


def load_public_smoke(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts/operator'))
    path = ROOT / 'scripts/operator/v3_checkpoint_public_smoke.py'
    spec = importlib.util.spec_from_file_location('public_checkpoint_smoke_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_smoke_reuses_canonical_checks_on_fixed_public_fqdn(monkeypatch):
    module = load_public_smoke(monkeypatch)
    calls = []
    monkeypatch.setattr(module, 'wait_for_origin_ready', lambda *args: calls.append(args))
    monkeypatch.setattr(module, 'smoke_origin', lambda *args: {'/api/health': {'status': 200}})
    receipt = module.verify_public_checkpoint(SHA)
    assert calls == [('http://vmi3542235.contaboserver.net', SHA)]
    assert receipt['status'] == 'accepted' and receipt['production'] is False
    with pytest.raises(module.DeploymentError):
        module.verify_public_checkpoint('invalid')


def test_failed_public_smoke_writes_stopped_receipt(monkeypatch, tmp_path):
    module = load_public_smoke(monkeypatch)
    def fail(_sha):
        raise module.DeploymentError('public endpoint unavailable')
    monkeypatch.setattr(module, 'verify_public_checkpoint', fail)
    receipt_path = tmp_path / 'receipt.json'
    monkeypatch.setattr(sys, 'argv', ['smoke', '--receipt', str(receipt_path)])
    assert module.main() == 78
    assert json.loads(receipt_path.read_text())['status'] == 'stopped'
