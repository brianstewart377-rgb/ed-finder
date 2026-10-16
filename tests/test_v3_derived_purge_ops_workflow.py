"""Read-only ops routing contracts; SSH is replaced with a local recorder."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/chatgpt-ed-new-ops.yml'


def _workflow():
    return yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)


def _step(name):
    return next(step for step in _workflow()['jobs']['execute']['steps'] if step.get('name') == name)


def test_ops_purge_choices_are_exactly_plan_and_status_with_independent_allowlist():
    workflow = _workflow()
    options = workflow['on']['workflow_dispatch']['inputs']['operation']['options']
    assert [option for option in options if option.startswith('v3-derived-purge-')] == [
        'v3-derived-purge-plan', 'v3-derived-purge-status',
    ]
    source = WORKFLOW.read_text()
    assert 'v3-derived-purge-plan|v3-derived-purge-status) ;;' in source
    assert workflow['permissions'] == {'contents': 'read'}
    assert workflow['jobs']['execute']['environment'] == 'ed-new-operator'
    assert workflow['concurrency'] == {'group': 'chatgpt-ed-new-ops', 'cancel-in-progress': 'false'}
    run = _step('Run read-only derived purge plan or status')['run']
    assert 'v3-derived-purge-plan) mode=plan ;;' in run
    assert 'v3-derived-purge-status) mode=status ;;' in run
    assert '*) exit 64 ;;' in run
    assert '${{' not in run
    for forbidden in ('authorize', 'verify-system-archetype-empty', 'delete-', 'rewrite-', 'abort-relation-', 'restore-services', 'complete'):
        assert forbidden not in run


def test_ops_purge_streams_committed_main_source_with_git_identity_and_pinned_trust():
    source = WORKFLOW.read_text()
    assert 'ref: main' in source
    assert 'persist-credentials: false' in source
    prepare = _step('Prepare trusted read-only derived purge bundle')['run']
    assert 'git -C trusted-main archive HEAD scripts/operator scripts/release deploy/v3-production sql' in prepare
    assert 'cp -R trusted-main/.git "$bundle/.git"' in prepare
    assert 'rm -f "$bundle/.git/config"' in prepare
    assert 'rm -rf "$bundle/.git/hooks"' in prepare
    step = _step('Run read-only derived purge plan or status')
    assert step['env']['OPERATION'] == '${{ steps.request.outputs.operation }}'
    assert step['env']['SSH_HOST'] == '${{ secrets.ED_NEW_OPERATOR_HOST }}'
    run = step['run']
    assert '[ "$SSH_HOST" = nb79a3d.mevnode.com ]' in run
    assert '[ "$(git -C "$work" rev-parse HEAD)" = "$2" ]' in run
    assert 'export GITHUB_RUN_ID="$3"' in run
    assert 'scripts/operator/actions/v3-derived-generation-purge.sh" "$1"' in run
    for option in ('BatchMode=yes', 'IdentitiesOnly=yes', 'StrictHostKeyChecking=yes', 'UserKnownHostsFile=~/.ssh/known_hosts'):
        assert option in run
    assert 'ssh-keyscan' not in source
    assert '| tee "$RECEIPT"' in run
    # The command executes the action in the SSH foreground. Neither SSH nor
    # the action is detached, so ops concurrency remains held until it exits.
    assert 'nohup' not in run
    assert 'disown' not in run
    assert ' & ' not in run


def test_ops_purge_receipt_is_always_required_and_retained_180_days():
    step = _step('Upload read-only derived purge receipt')
    assert step['if'].startswith('always() && ')
    assert step['with'] == {
        'name': 'v3-derived-purge-read-only',
        'path': '${{ runner.temp }}/v3-derived-purge-read-only.json',
        'if-no-files-found': 'error',
        'retention-days': '180',
    }


def _run_route(tmp_path, **changes):
    binary = tmp_path / 'bin'
    binary.mkdir()
    capture = tmp_path / 'ssh.json'
    commands = {
        'git': '#!/bin/sh\nprintf "%040d\\n" 1\n',
        'tar': '#!/bin/sh\nexit 0\n',
        'ssh': f'#!{sys.executable}\nimport json,os,pathlib,sys\nsys.stdin.read()\npathlib.Path(os.environ["TEST_CAPTURE"]).write_text(json.dumps(sys.argv[1:]))\nprint("{{}}")\n',
    }
    for name, source in commands.items():
        path = binary / name
        path.write_text(source)
        path.chmod(0o755)
    env = {
        **os.environ, 'PATH': str(binary) + os.pathsep + os.environ['PATH'],
        'OPERATION': 'v3-derived-purge-plan', 'SSH_HOST': 'nb79a3d.mevnode.com',
        'SSH_PORT': '22', 'SSH_USER': 'operator', 'RUN_ID': '1234',
        'RUNNER_TEMP': str(tmp_path), 'RECEIPT': str(tmp_path / 'receipt.json'),
        'TEST_CAPTURE': str(capture), **changes,
    }
    result = subprocess.run(['bash', '-c', _step('Run read-only derived purge plan or status')['run']],
                            env=env, capture_output=True, text=True, check=False)
    return result, json.loads(capture.read_text()) if capture.exists() else None


@pytest.mark.parametrize(('operation', 'mode'), [('v3-derived-purge-plan', 'plan'), ('v3-derived-purge-status', 'status')])
def test_ops_routes_only_fixed_literal_purge_arguments(tmp_path, operation, mode):
    result, command = _run_route(tmp_path, OPERATION=operation)
    assert result.returncode == 0, result.stderr
    assert f"-- '{mode}' '{'0' * 39}1' '1234'" in command[-1]
    assert command[-2] == 'operator@nb79a3d.mevnode.com'
    subprocess.run(['bash', '-n', '-c', command[-1]], check=True)


@pytest.mark.parametrize(('key', 'value'), [
    ('OPERATION', 'v3-derived-purge-authorize'), ('OPERATION', 'v3-derived-purge-plan; touch /tmp/injected'),
    ('SSH_HOST', 'another-host'), ('SSH_PORT', '22;bad'), ('SSH_PORT', '0'), ('SSH_PORT', '65536'),
    ('SSH_USER', "operator'; bad"), ('RUN_ID', '123;bad'),
])
def test_ops_purge_rejects_unvalidated_remote_arguments_before_ssh(tmp_path, key, value):
    result, command = _run_route(tmp_path, **{key: value})
    assert result.returncode == 64
    assert command is None
