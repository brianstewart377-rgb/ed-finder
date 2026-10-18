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


@pytest.mark.parametrize("operation", ("v3-disk-inventory", "v3-host-storage-detail"))
def test_host_storage_read_only_operations_have_closed_choice_and_independent_allowlist(operation):
    options = _workflow()['on']['workflow_dispatch']['inputs']['operation']['options']
    assert options.count(operation) == 1
    assert f'\n            {operation}) ;;' in WORKFLOW.read_text()


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
    # The whole workflow stays in its own group; the derived purge job holds the
    # same group, so host clean-up can never overlap a purge. Moving every ops
    # operation into the application-authority group would let a read-only
    # dispatch replace a pending release.
    assert workflow['concurrency'] == {'group': 'chatgpt-ed-new-ops', 'cancel-in-progress': 'false'}
    assert 'concurrency' not in workflow['jobs']['execute']
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
    assert '[ "$SSH_HOST" != nb79a3d.mevnode.com ]' in run
    assert 'getent ahosts nb79a3d.mevnode.com' in run
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
        'getent': '#!/bin/sh\n[ "$2" = nb79a3d.mevnode.com ] && printf "203.0.113.7 STREAM nb79a3d.mevnode.com\\n2001:db8::7 STREAM\\n"\n',
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


@pytest.mark.parametrize('address', ['203.0.113.7', '2001:db8::7'])
def test_ops_accepts_a_current_address_of_the_production_fqdn(tmp_path, address):
    result, command = _run_route(tmp_path, SSH_HOST=address)
    assert result.returncode == 0, result.stderr
    assert command[-2] == 'operator@' + address


@pytest.mark.parametrize('host', ['198.51.100.9', 'other.example', 'nb79a3d.mevnode.com;id', '203.0.113.7 ', ''])
def test_ops_refuses_any_other_host_before_ssh(tmp_path, host):
    result, command = _run_route(tmp_path, SSH_HOST=host)
    assert result.returncode == 64
    assert command is None
    assert 'neither the production FQDN nor one of its current addresses' in result.stderr


def test_cleanup_step_shares_the_same_host_rule():
    run = _step('Clean up fixed V3 host leftovers')['run']
    assert 'getent ahosts nb79a3d.mevnode.com' in run
    assert run.count('exit 64') >= 3


def _lifecycle_receipt():
    return {
        'status': 'success', 'failures': [], 'all_named_workers_stopped': True,
        'workers': [
            {'name': 'edfinder-worker', 'running': False, 'exists': True,
             'status': 'exited', 'exit_code': 0, 'inspect_error': 'password=unrelated-secret'},
        ],
        'migration_apply_preconditions': {
            'all_named_workers_stopped': True, 'current_pointers_recorded': True,
            'inspection_complete': True, 'ready_for_governed_plan': True,
            'environment': 'password=unrelated-secret',
        },
        'finder_migrations_applied': {'010_v3_system_search_body_type_counts.sql': True},
        'finder_products_on_published_generation': {'system_search': 'READY', 'system_archetype': None},
        'derived_generations': [{'generation_key': 'ratings_parallel', 'lifecycle_state': 'PUBLISHED'}],
        'derived_products': [{'generation_key': 'ratings_parallel', 'product_code': 'system_search',
                              'lifecycle_state': 'READY', 'failure': 'password=unrelated-secret'}],
        'footprint': {'host_disk': {'avail_bytes': 5 * 1024 ** 3, 'size_bytes': 20 * 1024 ** 3,
                                    'mount': 'password=unrelated-secret'}},
        'postgres': {'wal': {'archive_mode': 'on', 'failed_count': 0,
                             'last_archived_time': '2026-10-18 12:00:00+00', 'last_failed_time': None},
                     'environment': 'password=unrelated-secret'},
        'query_error': 'postgres://operator:unrelated-secret@host/db',
        'unrelated': 'password=unrelated-secret',
    }


def _lifecycle_summary(tmp_path, receipt):
    path = tmp_path / 'receipt.json'
    if receipt is not None:
        path.write_text(receipt if isinstance(receipt, str) else json.dumps(receipt))
    step = _step('Annotate V3 derived lifecycle status')
    assert step['if'] == "always() && steps.request.outputs.operation == 'v3-derived-lifecycle-status'"
    assert step['env'] == {'RECEIPT': '${{ runner.temp }}/v3-derived-lifecycle-status.json'}
    result = subprocess.run(['bash', '-c', step['run']], env={**os.environ, 'RECEIPT': str(path)},
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ''
    lines = result.stdout.splitlines()
    assert 1 <= len(lines) <= 8
    assert all(line.startswith('::notice title=Derived lifecycle status::') for line in lines)
    assert all(len(line) < 4000 for line in lines)
    assert 'unrelated-secret' not in result.stdout
    return result.stdout


@pytest.mark.parametrize('status,failures', [('success', []), ('stopped', ['worker_state_unknown'])])
def test_lifecycle_annotation_reports_operational_fields_without_unrelated_text(tmp_path, status, failures):
    receipt = _lifecycle_receipt()
    receipt.update(status=status, failures=failures)
    output = _lifecycle_summary(tmp_path, receipt)
    for field in (
        f'status={status}', 'failures=', 'all_named_workers_stopped=true',
        'name=edfinder-worker', 'running=false', 'exists=true', 'status=exited', 'exit_code=0',
        'migration_apply_preconditions:', 'current_pointers_recorded=true', 'inspection_complete=true',
        'ready_for_governed_plan=true', 'finder_migrations_applied:',
        '010_v3_system_search_body_type_counts.sql=true', 'finder_products_on_published_generation:',
        'system_search=READY', 'system_archetype=unknown',
        'generation_key=ratings_parallel; lifecycle_state=PUBLISHED', 'derived_products',
        'generation_key=ratings_parallel; product_code=system_search; lifecycle_state=READY',
        f'footprint.host_disk.avail_bytes={5 * 1024 ** 3} (5.00 GiB)',
        f'footprint.host_disk.size_bytes={20 * 1024 ** 3} (20.00 GiB)',
        'postgres.wal.archive_mode=on', 'postgres.wal.failed_count=0',
        'postgres.wal.last_archived_time=2026-10-18 12:00:00+00', 'postgres.wal.last_failed_time=unknown',
        *failures,
    ):
        assert field in output


@pytest.mark.parametrize('receipt', [None, 'password=unrelated-secret', '[]', 'null', '{'])
def test_lifecycle_annotation_handles_missing_invalid_receipts(tmp_path, receipt):
    output = _lifecycle_summary(tmp_path, receipt)
    assert 'status=stopped' in output
    assert 'failures=receipt unavailable or invalid' in output


def test_lifecycle_annotation_escapes_command_data(tmp_path):
    receipt = _lifecycle_receipt()
    receipt['status'] = 'stopped%\r\ninjected'
    receipt['failures'] = ['failed%\r\ncommand']
    receipt['workers'][0]['name'] = 'worker%\r\nname'
    output = _lifecycle_summary(tmp_path, receipt)
    for value in ('stopped%25%0D%0Ainjected', 'failed%25%0D%0Acommand', 'worker%25%0D%0Aname'):
        assert value in output
    assert '\r' not in output


def test_lifecycle_annotation_bounds_large_escaped_receipts_with_disclosure(tmp_path):
    receipt = _lifecycle_receipt()
    receipt['failures'] = ['%' * 10000] * 200
    for key in ('workers', 'derived_generations', 'derived_products'):
        receipt[key] = [{**receipt[key][0], 'name': '%' * 10000, 'generation_key': '%' * 10000}] * 200
    output = _lifecycle_summary(tmp_path, receipt)
    assert len(output.splitlines()) == 8
    assert '[truncated:' in output
    assert '[field truncated]' in output
    assert 'footprint.host_disk.avail_bytes=' in output
    assert 'postgres.wal.last_failed_time=' in output


def test_lifecycle_annotation_rejects_nested_or_credential_bearing_field_values(tmp_path):
    receipt = _lifecycle_receipt()
    receipt['failures'] = [{'secret': 'unrelated-secret'}, 'postgres://operator:unrelated-secret@host/db']
    receipt['workers'][0]['status'] = 'PASSWORD=unrelated-secret'
    receipt['footprint']['host_disk']['avail_bytes'] = {'secret': 'unrelated-secret'}
    receipt['postgres']['wal']['last_failed_time'] = 'token=unrelated-secret'
    output = _lifecycle_summary(tmp_path, receipt)
    assert '[redacted]' in output
    assert 'avail_bytes=unknown' in output


def test_lifecycle_receipt_is_always_uploaded_and_retained_30_days():
    step = _step('Upload V3 derived lifecycle status receipt')
    assert step['if'] == "always() && steps.request.outputs.operation == 'v3-derived-lifecycle-status'"
    assert step['with'] == {
        'name': 'v3-derived-lifecycle-status-receipt',
        'path': '${{ runner.temp }}/v3-derived-lifecycle-status.json',
        'if-no-files-found': 'warn', 'retention-days': '30',
    }


@pytest.mark.parametrize('exit_code', [0, 7])
def test_lifecycle_capture_preserves_action_exit_status_and_stdout(tmp_path, exit_code):
    action = tmp_path / 'trusted-main/scripts/operator/actions/v3-derived-lifecycle-status.sh'
    action.parent.mkdir(parents=True)
    action.touch()
    binary = tmp_path / 'bin'
    binary.mkdir()
    ssh = binary / 'ssh'
    ssh.write_text(f'#!/bin/sh\nprintf \'{{"status":"stopped"}}\\n\'\nexit {exit_code}\n')
    ssh.chmod(0o755)
    result = subprocess.run(
        ['bash', '-c', _step('Inspect V3 derived lifecycle status')['run']], cwd=tmp_path,
        env={**os.environ, 'PATH': str(binary) + os.pathsep + os.environ['PATH'],
             'SSH_USER': 'operator', 'SSH_HOST': 'local.invalid', 'SSH_PORT': '22', 'RUNNER_TEMP': str(tmp_path)},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == exit_code, result.stderr
    assert result.stdout == '{"status":"stopped"}\n'
    assert (tmp_path / 'v3-derived-lifecycle-status.json').read_text() == result.stdout


def _validation_summary(tmp_path, content):
    path = tmp_path / 'validation.txt'
    if content is not None:
        path.write_text(content)
    step = _step('Annotate V3 Search constraint validation')
    assert step['if'].startswith('always() && ')
    result = subprocess.run(['bash', '-c', step['run']], env={**os.environ, 'RECEIPT': str(path)},
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert len(lines) == 1
    assert lines[0].startswith('::notice title=Search constraint validation::')
    assert len(lines[0]) < 4000
    return lines[0]


def test_validation_status_annotation_reports_progress_without_query_text(tmp_path):
    receipt = {
        'operation': 'v3-system-search-validate-constraints-status', 'status': 'success',
        'failures': [], 'migration_010_in_ledger': True, 'validated_count': 7, 'all_validated': False,
        'runner_pid_alive': True, 'runner_pid_file_stale': False, 'runner_exit_code': None,
        'constraints': [{'name': f'system_search_check_{n}', 'validated': n < 7} for n in range(18)],
        'active_validations': [{'pid': 9, 'state': 'active', 'running_for': '00:04:12',
                                'query': "ALTER TABLE x VALIDATE CONSTRAINT y; password='unrelated-secret'"}],
        'log_tail': ["password='unrelated-secret'"],
    }
    line = _validation_summary(tmp_path, 'noise before\n' + json.dumps(receipt) + '\n')
    for field in ('status=success', 'validated_count=7', 'all_validated=false', 'constraints_total=18',
                  'system_search_check_7', 'running_for=00:04:12', 'runner_pid_alive=true'):
        assert field in line
    assert 'unrelated-secret' not in line
    assert 'VALIDATE' not in line


@pytest.mark.parametrize('content', [None, '', 'not json', '[1, 2]'])
def test_validation_annotation_survives_missing_or_invalid_receipt(tmp_path, content):
    line = _validation_summary(tmp_path, content)
    assert 'receipt unavailable or invalid' in line
