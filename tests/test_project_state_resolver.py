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
    return resolver.resolve_project_state(
        authority_path=AUTHORITY_PATH,
        git_runner=git_runner(**kwargs),
        allow_docs_only=kwargs.get('allow_docs_only', False),
    )


def test_authority_file_parses():
    authority, error = resolver.load_authority(AUTHORITY_PATH)

    assert error is None
    assert authority['schema_version'] == 1
    assert authority['stage19']['status'] == 'paused'
    assert authority['stage19']['stage19as_au_status'] == 'not_run'
    assert authority['approved_stage19ar_baseline']['rows'] == 25
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
    assert payload['stage19as_au_status'] == 'not_run'
    assert 'matched_invalid_state' in payload


def test_resolver_rejects_work_branch_for_operational_work():
    result = resolve(branch='work')

    assert result['failure_category'] == 'wrong_branch'
    assert result['safe_for_operational_work'] is False
    assert result['current_branch'] == 'work'


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
