import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RESOLVER_PATH = ROOT / 'scripts' / 'dev' / 'resolve_project_state.py'
AUTHORITY_PATH = ROOT / 'docs' / 'colonisation-redesign' / 'stage-19-state-authority.json'

AUTHORITY_COMMIT = '887c690bdf0e47345782cf0e81d28c013d8f83db'
PR198_HEAD = '581a84c1159b58dff86e3359a28d00f9b4f5a82b'
PR198_MERGE_COMMIT = '7ed8b050a02b2d43a87452302c594ad791051ab1'
SECRET_SENTINEL = 'do-not-print-this-secret'

spec = importlib.util.spec_from_file_location('resolve_project_state', RESOLVER_PATH)
resolver = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = resolver
spec.loader.exec_module(resolver)


pytestmark = pytest.mark.unit


def completed(args, returncode=0, stdout='', stderr=''):
    return subprocess.CompletedProcess(tuple(args), returncode, stdout=stdout, stderr=stderr)


def git_runner(
    *,
    branch='docs/state-authority-post-pr199-refresh',
    head=AUTHORITY_COMMIT,
    origin_main=AUTHORITY_COMMIT,
    origin_available=True,
    origin_contains=True,
    authority_available=True,
    head_contains=True,
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
        if args == ('rev-parse', '--verify', AUTHORITY_COMMIT):
            return completed(args, 0 if authority_available else 128, f'{AUTHORITY_COMMIT}\n')
        if args[:2] == ('merge-base', '--is-ancestor'):
            ancestor = args[2]
            target = args[3]
            if ancestor == AUTHORITY_COMMIT and target == 'origin/main':
                return completed(args, 0 if origin_contains else 1)
            if ancestor == AUTHORITY_COMMIT and target == 'HEAD':
                return completed(args, 0 if head_contains else 1)
        return completed(args, 1, '', SECRET_SENTINEL)

    return run


def resolve(**kwargs):
    return resolver.resolve_project_state(
        authority_path=AUTHORITY_PATH,
        git_runner=git_runner(**kwargs),
        allow_docs_only=kwargs.get('allow_docs_only', False),
    )


def test_authority_file_parses():
    authority, error = resolver.load_authority(AUTHORITY_PATH)

    assert error is None
    assert authority['current_authority']['stage19_status'] == 'paused'
    assert authority['current_authority']['stage19as_au_status'] == 'not_run'
    assert authority['current_authority']['origin_main'] == AUTHORITY_COMMIT
    assert authority['current_authority']['test_env_pr198_merge_commit'] == PR198_MERGE_COMMIT
    assert authority['current_authority']['test_env_pr199_merge_commit'] == AUTHORITY_COMMIT
    assert authority['approved_stage19ar_baseline']['rows'] == 25


def test_origin_main_887c690_is_accepted_as_current_authority():
    result = resolve()

    assert result['origin_main'] == AUTHORITY_COMMIT
    assert result['authority_origin_main'] == AUTHORITY_COMMIT
    assert result['authority_test_env_head'] == AUTHORITY_COMMIT
    assert result['authority_test_env_prs'] == [198, 199]
    assert result['failure_category'] == 'none'
    assert result['safe_for_operational_work'] is True
    assert result['current_state_is_superseded'] is False


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


def test_pr198_branch_state_is_historical_after_merge():
    result = resolve()
    state = next(
        item for item in result['historical_states']
        if item['id'] == 'test_env_roadmap_recreate_pr198'
    )

    assert state['branch'] == 'fix/test-env-roadmap-recreate'
    assert state['status'] == 'merged_via_pr198'
    assert state['merge_commit'] == PR198_MERGE_COMMIT


def test_pr199_branch_state_is_historical_after_merge():
    result = resolve()
    state = next(
        item for item in result['historical_states']
        if item['id'] == 'state_authority_branch_gate_pr199'
    )

    assert state['branch'] == 'fix/test-env-state-authority-branch-gate'
    assert state['status'] == 'merged_via_pr199'
    assert state['merge_commit'] == AUTHORITY_COMMIT


def test_resolver_does_not_require_pr198_branch_after_merge():
    result = resolve(branch='main', head=AUTHORITY_COMMIT)

    assert result['current_branch'] == 'main'
    assert result['authority_test_env_branch'] is None
    assert result['failure_category'] == 'none'
    assert result['safe_for_operational_work'] is True


def test_resolver_rejects_work_branch_for_operational_work():
    result = resolve(branch='work')

    assert result['failure_category'] == 'wrong_branch'
    assert result['safe_for_operational_work'] is False
    assert result['current_branch'] == 'work'


def test_resolver_identifies_850917_on_work_as_non_authoritative():
    result = resolve(
        branch='work',
        head='8509171250b1449832a7fe3227d87acc02fb015e',
        head_contains=False,
    )

    assert result['failure_category'] == 'wrong_branch'
    assert result['current_state_is_superseded'] is True
    assert result['matched_superseded_state']['id'] == 'non_authoritative_state_authority_attempt_850917_on_work'
    assert result['matched_superseded_state']['evidence_only'] is True


def test_resolver_rejects_45e2d58():
    result = resolve(
        branch='fix/stage19-approved-rebaseline',
        head='45e2d58abc000000000000000000000000000000',
        head_contains=False,
    )

    assert result['failure_category'] == 'current_branch_superseded'
    assert result['matched_superseded_state']['id'] == 'superseded_partial_rebaseline_45e2d58'
    assert result['safe_for_operational_work'] is False


def test_resolver_rejects_f72812a():
    result = resolve(
        branch='run/stage19as-au-100-row-expansion',
        head='f72812abc0000000000000000000000000000000',
        head_contains=False,
    )

    assert result['failure_category'] == 'current_branch_superseded'
    assert result['matched_superseded_state']['id'] == 'superseded_stage19as_au_docs_only_checkpoint_f72812a'
    assert result['safe_for_operational_work'] is False


def test_resolver_lists_unrecoverable_historical_test_env_context():
    result = resolve()
    state = next(
        item for item in result['superseded_states']
        if item['id'] == 'unrecoverable_historical_test_env_stack_0042471_d66a568_09eee44'
    )

    assert state['status'] == 'unrecoverable_historical_context'
    assert state['commits'] == ['0042471', 'd66a568', '09eee44']
    assert state['replacement']['commit'] == PR198_HEAD


def test_resolver_marks_uploaded_prompt_bundles_evidence_only():
    result = resolve()
    state = next(
        item for item in result['superseded_states']
        if item['id'] == 'uploaded_or_pasted_prompt_bundles'
    )

    assert state['status'] == 'evidence_only'
    assert state['evidence_only'] is True
    assert result['prompt_rules']['pasted_chat_logs_are_evidence_not_authority'] is True


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
