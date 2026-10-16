#!/usr/bin/env python3
"""Protected purge dispatch validation and foreground trusted-main transport.

No host connection is made by validation or artifact authentication. The execute
command is exclusively a protected workflow transport; the action owns leases,
SQL admission, cancellation and recovery. Git objects travel with the bounded
source bundle because the action authenticates HEAD and committed backup bytes.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = '.github/workflows/v3-production-derived-purge.yml'
REPOSITORY = 'brianstewart377-rgb/ed-finder'
TARGET = 'ed-finder-prod/nb79a3d.mevnode.com'
RELATIONS = ('system-search', 'economy-opportunity', 'body-mechanics', 'system-rating-vector')
MODES = ('plan', 'status', 'authorize', 'verify-system-archetype-empty',
         *(prefix + relation for prefix in ('delete-', 'rewrite-', 'abort-relation-') for relation in RELATIONS),
         'restore-services', 'complete')
RUN_ID = re.compile(r'[1-9][0-9]{0,19}\Z')
SHA256 = re.compile(r'[0-9a-f]{64}\Z')
SOURCE_SHA = re.compile(r'[0-9a-f]{40}\Z')
MAX_REWRITE_MS = 7_200_000
MAX_RECEIPT = 8 * 1024 * 1024


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_inputs(env):
    fields = ('mode', 'confirm_target', 'plan_run_id', 'plan_sha256', 'verification_run_id',
              'verification_sha256', 'acknowledge_failed_stop', 'wall_clock_seconds')
    request = {key: env.get('INPUT_' + key.upper(), '') for key in fields}
    mode = request['mode']
    if mode not in MODES or request['confirm_target'] != TARGET:
        raise ValueError('invalid_mode_or_target')
    plan_required = mode not in ('plan', 'status')
    proof_required = mode == 'complete' or mode == 'restore-services' or mode.startswith(
        ('delete-', 'rewrite-', 'abort-relation-'))
    for prefix, required in (('plan', plan_required), ('verification', proof_required)):
        run_id, digest = request[prefix + '_run_id'], request[prefix + '_sha256']
        if required:
            if not RUN_ID.fullmatch(run_id) or not SHA256.fullmatch(digest):
                raise ValueError('invalid_' + prefix + '_reference')
            if run_id == env.get('GITHUB_RUN_ID'):
                raise ValueError('self_referencing_artifact')
        elif run_id or digest:
            raise ValueError(prefix + '_reference_not_admitted')
    ack = request['acknowledge_failed_stop']
    if ack and (mode != 'restore-services' or not RUN_ID.fullmatch(ack) or int(ack) >= 2**63):
        raise ValueError('acknowledgement_not_admitted')
    wall = request['wall_clock_seconds']
    if mode.startswith('delete-'):
        if re.fullmatch(r'[1-9][0-9]{0,3}', wall) is None or not 1 <= int(wall) <= 1800:
            raise ValueError('delete_wall_clock_budget_invalid')
        request['wall_clock_seconds'] = int(wall)
    elif wall:
        raise ValueError('wall_clock_is_delete_only')
    else:
        request['wall_clock_seconds'] = None
    return request


def validate_run(run, *, run_id, source_sha):
    if not RUN_ID.fullmatch(run_id) or not SOURCE_SHA.fullmatch(source_sha):
        raise ValueError('invalid_run_identity')
    expected = {'id': int(run_id), 'path': WORKFLOW_PATH, 'head_branch': 'main',
                'head_sha': source_sha, 'event': 'workflow_dispatch', 'status': 'completed',
                'conclusion': 'success'}
    if (any(run.get(key) != value for key, value in expected.items())
            or (run.get('head_repository') or {}).get('full_name', '').casefold() != REPOSITORY.casefold()):
        raise ValueError('purge_artifact_run_provenance_failed')


def authenticate_receipt(path, expected_sha, *, mode, run_id, source_sha):
    path = Path(path)
    if (not SHA256.fullmatch(expected_sha) or not RUN_ID.fullmatch(run_id)
            or not SOURCE_SHA.fullmatch(source_sha) or path.is_symlink()
            or path.stat().st_size > MAX_RECEIPT):
        raise ValueError('purge_artifact_identity_invalid')
    evidence = _load('purge_workflow_evidence', ROOT / 'scripts/operator/lib/f2d_evidence.py')
    value = evidence.load_sealed(path)
    expected = {'schema_version': 'ed-finder/derived-generation-purge/v1',
                'operation': 'v3-derived-generation-purge', 'phase': mode, 'status': 'success',
                'workflow_run_id': run_id, 'source_git_sha': source_sha, 'failures': [],
                'host': 'ed-finder-prod', 'fqdn': 'nb79a3d.mevnode.com', 'content_sha256': expected_sha}
    if any(value.get(key) != expected_value for key, expected_value in expected.items()):
        raise ValueError('purge_artifact_receipt_provenance_failed')
    return value


def authenticate(env, *, fetch=True):
    request = validate_inputs(env)
    source_sha = env.get('GITHUB_SHA', '')
    if not SOURCE_SHA.fullmatch(source_sha):
        raise ValueError('invalid_source_sha')
    receipts = {}
    for prefix, mode in (('plan', 'plan'), ('verification', 'verify-system-archetype-empty')):
        run_id = request[prefix + '_run_id']
        if not run_id:
            continue
        path = Path(env['RUNNER_TEMP']) / ('purge-' + prefix) / 'receipt.json'
        if fetch:
            runs = _load('purge_workflow_runs', ROOT / 'scripts/release/v3_release_run.py')
            run = runs.fetch_run(REPOSITORY, run_id, env.get('GITHUB_TOKEN', ''))
            artifact_source = run.get('head_sha', '')
            validate_run(run, run_id=run_id, source_sha=artifact_source)
        else:
            # The preceding authentication step proved run provenance. Recheck
            # the same sealed bytes here without handing the API token to SSH.
            if path.is_symlink() or path.stat().st_size > MAX_RECEIPT:
                raise ValueError('purge_artifact_identity_invalid')
            evidence = _load('purge_workflow_evidence', ROOT / 'scripts/operator/lib/f2d_evidence.py')
            artifact_source = evidence.load_sealed(path).get('source_git_sha', '')
        receipts[prefix] = authenticate_receipt(
            path, request[prefix + '_sha256'], mode=mode, run_id=run_id, source_sha=artifact_source)
        # Authorization must use an exact-head plan; recovery and subsequent
        # phases retain the original immutable plan even if main has advanced.
        if prefix == 'plan' and request['mode'] == 'authorize' and artifact_source != source_sha:
            raise ValueError('authorize_plan_source_changed')
    # Hosted jobs must have time to observe exit and preserve receipts. Larger
    # reviewed rewrites need a separately reviewed workflow timeout, never an
    # early disconnect from the existing action.
    if 'plan' in receipts:
        configurations = receipts['plan'].get('reviewed_plan', {}).get('rewrite', {})
        if not isinstance(configurations, dict):
            raise ValueError('rewrite_timeout_outside_workflow_budget')
        for config in configurations.values():
            if not isinstance(config, dict):
                raise ValueError('rewrite_timeout_outside_workflow_budget')
            timeout = config.get('statement_timeout_ms')
            # Reject oversized plans before authorization or deletion too:
            # restore-services may later need that timeout for recovered ANALYZE.
            if timeout is not None and (type(timeout) is not int or not 1 <= timeout <= MAX_REWRITE_MS):
                raise ValueError('rewrite_timeout_outside_workflow_budget')
    if request['mode'].startswith('rewrite-'):
        relation = request['mode'].removeprefix('rewrite-').replace('-', '_')
        config = receipts['plan'].get('reviewed_plan', {}).get('rewrite', {}).get(relation, {})
        timeout = config.get('statement_timeout_ms')
        if type(timeout) is not int or not 1 <= timeout <= MAX_REWRITE_MS:
            raise ValueError('rewrite_timeout_outside_workflow_budget')
    return request


def remote_script(request, source_sha, run_id):
    """All interpolated values have closed modes or fixed numeric/hex grammar."""
    if not SOURCE_SHA.fullmatch(source_sha) or not RUN_ID.fullmatch(run_id):
        raise ValueError('invalid_controller_identity')
    args = [request['mode']]
    for prefix in ('plan', 'verification'):
        if request[prefix + '_run_id']:
            args += ['--' + prefix, 'artifacts/' + prefix + '.json',
                     '--' + prefix + '-sha256', request[prefix + '_sha256']]
    if request['wall_clock_seconds'] is not None:
        args += ['--wall-clock-seconds', str(request['wall_clock_seconds'])]
    if request['acknowledge_failed_stop']:
        args += ['--acknowledge-failed-stop', request['acknowledge_failed_stop']]
    # No cleanup of source here: a monitor may outlive this controller. /run is
    # ephemeral, root owned and not group/world writable, unlike /tmp ancestors.
    return f'''set -euo pipefail
umask 077
[ "$(id -u)" -eq 0 ] || exit 64
work="$(mktemp -d /run/edfinder-v3-purge-source.XXXXXXXX)"
tar --no-same-permissions --no-same-owner --no-overwrite-dir -xf - -C "$work"
chmod -R go-w "$work"
cd "$work"
[ "$(git rev-parse HEAD)" = {shlex.quote(source_sha)} ] || exit 64
export GITHUB_RUN_ID={shlex.quote(run_id)}
child=''
cancel() {{
  trap '' HUP INT TERM
  if [ -n "$child" ]; then
    kill -TERM "$child" 2>/dev/null || true
    set +e
    wait "$child"
    result=$?
    exit "$result"
  fi
  exit 143
}}
trap cancel HUP INT TERM
bash scripts/operator/actions/v3-derived-generation-purge.sh {shlex.join(args)} --controller-pid "$$" --controller-run-id "$GITHUB_RUN_ID" &
child=$!
# Keep both GitHub concurrency fences until the action has exited. The action
# owns its leases; the independent rewrite monitor deliberately owns neither.
while kill -0 "$child" 2>/dev/null; do sleep 2; done
set +e
wait "$child"
result=$?
exit "$result"
'''


def execute(env=os.environ):
    request = authenticate(env, fetch=False)
    host, port, user = (env.get('SSH_' + key, '') for key in ('HOST', 'PORT', 'USER'))
    if (host != 'nb79a3d.mevnode.com' or re.fullmatch(r'[0-9]{1,5}', port) is None
            or not 1 <= int(port) <= 65535 or re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', user) is None):
        raise ValueError('invalid_ssh_target')
    script = remote_script(request, env['GITHUB_SHA'], env['GITHUB_RUN_ID'])
    remote = 'exec sudo -n bash -c ' + shlex.quote(script)
    # Root logins do not need sudo. The controller itself still insists on root.
    if user == 'root':
        remote = 'exec bash -c ' + shlex.quote(script)
    argv = ['ssh', '-i', str(Path.home() / '.ssh/v3_production_key'), '-p', port,
            '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'UserKnownHostsFile=' + str(Path.home() / '.ssh/known_hosts'),
            '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3', user + '@' + host, remote]
    # Deliberately synchronous: no detached remote launcher and no early return.
    with (Path(env['RUNNER_TEMP']) / 'purge-source.tar').open('rb') as bundle:
        return subprocess.run(argv, stdin=bundle, check=False).returncode


def initialize_receipt(env=os.environ):
    """Retain the action's full receipt shape with unknown remote outcomes."""
    action = _load('purge_workflow_action', ROOT / 'scripts/operator/lib/v3_generation_purge.py')
    mode = env.get('INPUT_MODE', '')
    report = action.receipt(mode if mode in MODES else 'unknown')
    # A lost transport cannot prove that a remote mutation did or did not
    # commit. Never retain the action's preflight-only false defaults here.
    for key in report:
        if key.endswith('_performed'):
            report[key] = None
    report.update(failures=['workflow_did_not_complete'], workflow_run_id=env['GITHUB_RUN_ID'],
                  source_git_sha=env['GITHUB_SHA'], read_only=None)
    path = Path(env['RUNNER_TEMP']) / 'receipt.json'
    path.write_text(action.evidence.canonical_json(action.evidence.seal(report)) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('initialize-receipt', 'validate-inputs', 'authenticate', 'execute'))
    args = parser.parse_args()
    try:
        if args.command == 'initialize-receipt':
            initialize_receipt()
        elif args.command == 'validate-inputs':
            validate_inputs(os.environ)
        elif args.command == 'authenticate':
            authenticate(os.environ)
        else:
            return execute()
    except Exception:
        # Never echo operator strings, remote diagnostics or credentials.
        print('protected purge dispatch validation or transport failed', file=sys.stderr)
        return 78
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
