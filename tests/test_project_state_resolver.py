import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RESOLVER_PATH = ROOT / 'scripts' / 'dev' / 'resolve_project_state.py'
AUTHORITY_PATH = ROOT / 'docs' / 'colonisation-redesign' / 'stage-19-state-authority.json'

DEFAULT_HEAD = '887c6900000000000000000000000000000000000'
DEFAULT_ORIGIN_MAIN = '887c6900000000000000000000000000000000000'
SECRET_SENTINEL = 'do-not-print-this-secret'

spec = importlib.util.spec_from_file_location('resolve_project_state', RESOLVER_PATH)
resolver = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = resolver
spec.loader.exec_module(resolver)


pytestmark = pytest.mark.unit


def completed(args, returncode=0, stdout='', stderr=''):
    return subprocess.CompletedProcess(tuple(args), returncode, stdout=stdout, stderr=stderr)


def github_pr_env(tmp_path: Path, *, head: str = DEFAULT_HEAD, head_ref: str = 'feat/local-review-test-environment'):
    event_path = tmp_path / 'github-event.json'
    event_path.write_text(
        json.dumps({
            'pull_request': {
                'head': {
                    'sha': head,
                    'ref': head_ref,
                },
            },
        }),
        encoding='utf-8',
    )
    return {
        'GITHUB_ACTIONS': 'true',
        'GITHUB_EVENT_NAME': 'pull_request',
        'GITHUB_HEAD_REF': head_ref,
        'GITHUB_EVENT_PATH': str(event_path),
    }


def git_runner(
    *,
    branch='docs/trim-state-authority-history',
    head=DEFAULT_HEAD,
    origin_main=DEFAULT_ORIGIN_MAIN,
    origin_available=True,
    inside_git=True,
):
    def run(args):
        args = tuple(args)
        if args == ('rev-parse', '--is-inside-work-tree'):
            return completed(args, 0 if inside_git else 128, 'true\n' if inside_git else '')
        if args == ('branch', '--show-current'):
            return completed(args, 0, f'{branch}\n')
        if args == ('rev-parse', 'HEAD'):
            return completed(args, 0, f'{head}\n')
        if args == ('rev-parse', 'origin/main'):
            if not origin_available:
                return completed(args, 128, '', SECRET_SENTINEL)
            return completed(args, 0, f'{origin_main}\n')
        return completed(args, 1, '', SECRET_SENTINEL)

    return run


def resolve(**kwargs):
    env = kwargs.pop('env', None)
    return resolver.resolve_project_state(
        authority_path=AUTHORITY_PATH,
        git_runner=git_runner(**kwargs),
        allow_docs_only=kwargs.get('allow_docs_only', False),
        env=env,
    )


def test_authority_file_parses():
    authority, error = resolver.load_authority(AUTHORITY_PATH)

    assert error is None
    assert authority['schema_version'] == 1
    assert authority['stage19']['status'] == 'paused'
    assert authority['stage19']['stage19as_au_status'] == 'completed'
    assert authority['approved_stage19ar_baseline']['rows'] == 25
    checkpoint = authority['stage19as_au_completed_checkpoint']
    assert checkpoint['source_run_key'] == 'stage19as-au-edsm-100-row-controlled-expansion-1843ccf903dfa6c9'
    assert checkpoint['bridge_key'] == 'source_runs:stage19as-au-edsm-100-row-controlled-expansion-1843ccf903dfa6c9'
    assert checkpoint['artifact'] == '7f6f20a4d01b543d8ef12072891d8fda749bcc1b6633c26bc9ec178a40b8f84e'
    assert checkpoint['rows_read'] == 100
    assert checkpoint['rows_staged'] == 100
    assert checkpoint['canonical_writes_performed'] is False
    assert [state['id'] for state in authority['invalid_states']] == [
        '45e2d58',
        'f72812a',
        '8509171250b1449832a7fe3227d87acc02fb015e',
    ]


def test_active_authority_does_not_require_verbose_superseded_reasons():
    authority, error = resolver.load_authority(AUTHORITY_PATH)

    assert error is None
    assert 'superseded_states' not in authority
    assert all('reason' not in state for state in authority['invalid_states'])


def test_json_output_works(capsys):
    exit_code = resolver.main(
        ['--json'],
        authority_path=AUTHORITY_PATH,
        git_runner=git_runner(),
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload['failure_category'] == 'none'
    assert payload['safe_for_operational_work'] is True
    assert payload['stage19_status'] == 'paused'
    assert payload['stage19as_au_status'] == 'completed'
    assert 'matched_invalid_state' in payload


def test_resolver_rejects_work_branch_for_operational_work():
    result = resolve(branch='work')

    assert result['failure_category'] == 'wrong_branch'
    assert result['safe_for_operational_work'] is False
    assert result['current_branch'] == 'work'


def test_resolver_accepts_valid_detached_github_actions_pr_head(tmp_path):
    result = resolver.resolve_project_state(
        authority_path=AUTHORITY_PATH,
        git_runner=git_runner(branch=''),
        env=github_pr_env(tmp_path),
    )

    assert result['failure_category'] == 'none'
    assert result['safe_for_operational_work'] is True
    assert result['current_branch'] is None
    assert result['effective_branch'] == 'feat/local-review-test-environment'
    assert result['checkout_context'] == 'github_actions_detached_pr_head'


def test_resolver_rejects_detached_github_actions_merge_checkout(tmp_path):
    result = resolver.resolve_project_state(
        authority_path=AUTHORITY_PATH,
        git_runner=git_runner(branch='', head='4e294371f16c3087ba6f73a1dc82aaf0c6d1a4ad', origin_available=False),
        env=github_pr_env(tmp_path, head=DEFAULT_HEAD),
    )

    assert result['failure_category'] == 'ambiguous_local_state'
    assert result['safe_for_operational_work'] is False
    assert result['checkout_context'] == 'detached_head'
    assert result['next_action'] == 'Ensure CI checks out the pull request head SHA with a resolvable origin/main reference before continuing.'


def test_resolver_still_rejects_invalid_state_in_detached_github_actions_pr_checkout(tmp_path):
    invalid_head = '8509171250b1449832a7fe3227d87acc02fb015e'
    result = resolver.resolve_project_state(
        authority_path=AUTHORITY_PATH,
        git_runner=git_runner(branch='', head=invalid_head),
        env=github_pr_env(tmp_path, head=invalid_head),
    )

    assert result['failure_category'] == 'current_head_superseded'
    assert result['safe_for_operational_work'] is False
    assert result['effective_branch'] == 'feat/local-review-test-environment'


def test_resolver_identifies_850917_on_work_as_non_authoritative():
    result = resolve(
        branch='work',
        head='8509171250b1449832a7fe3227d87acc02fb015e',
    )

    assert result['failure_category'] == 'current_head_superseded'
    assert result['current_state_is_superseded'] is True
    assert result['matched_invalid_state']['id'] == '8509171250b1449832a7fe3227d87acc02fb015e'
    assert result['safe_for_operational_work'] is False


def test_resolver_rejects_45e2d58():
    result = resolve(
        branch='fix/stage19-approved-rebaseline',
        head='45e2d58abc000000000000000000000000000000',
    )

    assert result['failure_category'] == 'current_head_superseded'
    assert result['matched_invalid_state']['id'] == '45e2d58'
    assert result['safe_for_operational_work'] is False


def test_resolver_rejects_f72812a():
    result = resolve(
        branch='run/stage19as-au-100-row-expansion',
        head='f72812abc0000000000000000000000000000000',
    )

    assert result['failure_category'] == 'current_head_superseded'
    assert result['matched_invalid_state']['id'] == 'f72812a'
    assert result['safe_for_operational_work'] is False


def test_archive_only_historical_stack_does_not_pollute_active_authority():
    result = resolve()
    invalid_ids = {state['id'] for state in result['invalid_states']}

    assert {'0042471', 'd66a568', '09eee44'}.isdisjoint(invalid_ids)
    assert result['historical_context']['unrecoverable_test_env_stack'] == [
        '0042471',
        'd66a568',
        '09eee44',
    ]


def test_uploaded_pasted_logs_are_evidence_only_rule_exists():
    result = resolve()

    assert result['rules']['pasted_logs_are_evidence_only'] is True
    assert result['prompt_rules']['pasted_logs_are_evidence_only'] is True


def test_missing_authority_file_fails_closed(tmp_path):
    result = resolver.resolve_project_state(
        authority_path=tmp_path / 'missing.json',
        git_runner=git_runner(),
    )

    assert result['failure_category'] == 'authority_file_missing'
    assert result['safe_for_operational_work'] is False


def test_origin_main_unavailable_reports_cleanly_without_secret():
    result = resolve(origin_available=False)
    encoded = json.dumps(result, sort_keys=True)

    assert result['failure_category'] == 'origin_main_unavailable'
    assert result['origin_main'] is None
    assert SECRET_SENTINEL not in encoded


def test_docs_only_mode_does_not_permit_operational_work():
    result = resolver.resolve_project_state(
        authority_path=AUTHORITY_PATH,
        git_runner=git_runner(branch='work'),
        allow_docs_only=True,
    )

    assert result['failure_category'] == 'wrong_branch'
    assert result['safe_for_operational_work'] is False
    assert result['safe_for_docs_only_work'] is True


def test_no_secrets_printed_in_cli_output(capsys):
    exit_code = resolver.main(
        ['--json'],
        authority_path=AUTHORITY_PATH,
        git_runner=git_runner(origin_available=False),
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert SECRET_SENTINEL not in output
