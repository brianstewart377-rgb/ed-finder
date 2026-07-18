#!/usr/bin/env python3
"""Resolve Stage 19/test-environment authority before operational work."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUTHORITY_FILE = ROOT / 'docs/colonisation-redesign/stage-19-state-authority.json'

FAILURE_CATEGORIES = {
    'none',
    'not_git_repo',
    'origin_main_unavailable',
    'authority_file_missing',
    'authority_file_invalid',
    'authority_commit_missing',
    'wrong_branch',
    'current_branch_superseded',
    'current_head_superseded',
    'ambiguous_local_state',
    'stale_stage19_context',
    'unknown',
}

GitRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def main(
    argv: Sequence[str] | None = None,
    *,
    authority_path: Path = DEFAULT_AUTHORITY_FILE,
    git_runner: GitRunner | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    args = parse_args(argv)
    result = resolve_project_state(
        authority_path=authority_path,
        git_runner=git_runner,
        allow_docs_only=args.allow_docs_only,
        env=env,
    )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print_human(result)

    strict_ok = result['safe_for_operational_work']
    if args.allow_docs_only:
        strict_ok = result['safe_for_docs_only_work']
    return 0 if not args.strict or strict_ok else 2


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Resolve Stage 19/test-environment authority before operational work.',
    )
    parser.add_argument('--json', action='store_true', help='Print machine-readable JSON.')
    parser.add_argument('--strict', action='store_true', help='Exit nonzero when state is not safe.')
    parser.add_argument(
        '--allow-docs-only',
        action='store_true',
        help='Permit docs-only/scratch work while keeping operational work unsafe.',
    )
    return parser.parse_args(argv)


def resolve_project_state(
    *,
    authority_path: Path = DEFAULT_AUTHORITY_FILE,
    git_runner: GitRunner | None = None,
    allow_docs_only: bool = False,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    runner = git_runner or default_git_runner
    environment = dict(os.environ if env is None else env)
    authority, authority_error = load_authority(authority_path)
    if authority_error is not None:
        return build_failure(
            authority_path=authority_path,
            failure_category=authority_error,
            next_action='Restore a valid Stage 19 state authority file before continuing.',
            allow_docs_only=allow_docs_only,
        )

    assert authority is not None
    stage19_status, stage19as_au_status = stage19_statuses(authority)

    inside = run_git(runner, ('rev-parse', '--is-inside-work-tree'))
    if inside.returncode != 0 or inside.stdout.strip() != 'true':
        return build_failure(
            authority_path=authority_path,
            authority=authority,
            stage19_status=stage19_status,
            stage19as_au_status=stage19as_au_status,
            failure_category='not_git_repo',
            next_action='Run state resolution from a valid ed-finder git checkout.',
            allow_docs_only=allow_docs_only,
        )

    current_branch = git_output(runner, ('branch', '--show-current'))
    current_head = git_output(runner, ('rev-parse', 'HEAD'))
    checkout_context = 'named_branch'
    effective_branch = current_branch
    if not current_head:
        return build_failure(
            authority_path=authority_path,
            authority=authority,
            stage19_status=stage19_status,
            stage19as_au_status=stage19as_au_status,
            current_branch=current_branch,
            effective_branch=effective_branch,
            current_head=current_head,
            failure_category='ambiguous_local_state',
            next_action=ambiguous_state_next_action(environment),
            checkout_context='missing_head',
            allow_docs_only=allow_docs_only,
        )
    if not effective_branch:
        detached_context = github_actions_detached_pr_head_context(environment, current_head)
        if detached_context is not None:
            effective_branch = detached_context['head_ref']
            checkout_context = detached_context['checkout_context']
        else:
            return build_failure(
                authority_path=authority_path,
                authority=authority,
                stage19_status=stage19_status,
                stage19as_au_status=stage19as_au_status,
                current_branch=current_branch,
                effective_branch=effective_branch,
                current_head=current_head,
                failure_category='ambiguous_local_state',
                next_action=ambiguous_state_next_action(environment),
                checkout_context='detached_head',
                allow_docs_only=allow_docs_only,
            )

    origin_main = git_output(runner, ('rev-parse', 'origin/main'))
    origin_main_contains_authority = bool(origin_main)

    expected_head = authority_test_env_head(authority)
    authority_commit_available = False
    head_contains_authority = False
    if expected_head:
        authority_commit_available = run_git(runner, ('rev-parse', '--verify', expected_head)).returncode == 0
        head_contains_authority = (
            run_git(runner, ('merge-base', '--is-ancestor', expected_head, 'HEAD')).returncode == 0
        )
    else:
        authority_commit_available = True
        head_contains_authority = True

    matched_state, matched_by = find_matching_invalid_state(authority, effective_branch, current_head)
    failure_category = 'none'
    next_action = 'State authority checks passed for operational work.'

    if not origin_main:
        failure_category = 'origin_main_unavailable'
        next_action = 'Fetch origin/main and rerun state resolution before operational work.'
    elif not authority_commit_available:
        failure_category = 'authority_commit_missing'
        next_action = 'Fetch the authoritative test-environment commit before continuing.'
    elif matched_state and matched_by == 'branch':
        failure_category = 'current_branch_superseded'
        next_action = 'Do not use this invalid state as authority; switch to a clean branch from origin/main.'
    elif matched_state and matched_by == 'head':
        failure_category = 'current_head_superseded'
        next_action = 'Do not use this invalid state as authority; switch to a clean branch from origin/main.'
    elif effective_branch == 'work':
        failure_category = 'wrong_branch'
        next_action = 'Branch work is non-authoritative for Stage 19/test-env operational work.'
    elif not head_contains_authority:
        failure_category = 'stale_stage19_context'
        next_action = 'Current HEAD is not based on the authoritative test-environment commit.'

    safe_for_operational_work = failure_category == 'none'
    safe_for_docs_only_work = safe_for_operational_work or (
        allow_docs_only
        and failure_category == 'wrong_branch'
        and source_of_truth_available(origin_main, origin_main_contains_authority, authority_commit_available)
    )

    return {
        'state_authority_file': relative_path(authority_path),
        'current_branch': current_branch,
        'effective_branch': effective_branch,
        'current_head': current_head,
        'checkout_context': checkout_context,
        'origin_main': origin_main,
        'origin_main_contains_authority': origin_main_contains_authority,
        'stage19_status': stage19_status,
        'stage19as_au_status': stage19as_au_status,
        'current_state_is_superseded': matched_state is not None,
        'matched_invalid_state': public_state(matched_state),
        'matched_superseded_state': public_state(matched_state),
        'safe_for_operational_work': safe_for_operational_work,
        'safe_for_docs_only_work': safe_for_docs_only_work,
        'failure_category': failure_category,
        'next_action': next_action,
        'authority_test_env_branch': authority_test_env_branch(authority),
        'authority_test_env_head': expected_head,
        'head_contains_authority': head_contains_authority,
        'authority_commit_available': authority_commit_available,
        'invalid_states': [public_state(state) for state in invalid_states(authority)],
        'superseded_states': [public_state(state) for state in invalid_states(authority)],
        'historical_context': authority.get('historical_context', {}),
        'rules': authority_rules(authority),
        'prompt_rules': authority_rules(authority),
    }


def load_authority(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, 'authority_file_missing'
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None, 'authority_file_invalid'
    if not isinstance(data, dict):
        return None, 'authority_file_invalid'
    simplified_required = ('stage19', 'invalid_states', 'rules')
    legacy_required = ('current_authority', 'superseded_states', 'prompt_rules')
    has_simplified = all(key in data for key in simplified_required)
    has_legacy = all(key in data for key in legacy_required)
    if not has_simplified and not has_legacy:
        return None, 'authority_file_invalid'
    return data, None


def build_failure(
    *,
    authority_path: Path,
    failure_category: str,
    next_action: str,
    allow_docs_only: bool,
    authority: Mapping[str, Any] | None = None,
    stage19_status: str = 'unknown',
    stage19as_au_status: str = 'unknown',
    current_branch: str | None = None,
    effective_branch: str | None = None,
    current_head: str | None = None,
    checkout_context: str = 'unknown',
) -> dict[str, Any]:
    assert failure_category in FAILURE_CATEGORIES
    return {
        'state_authority_file': relative_path(authority_path),
        'current_branch': current_branch,
        'effective_branch': effective_branch,
        'current_head': current_head,
        'checkout_context': checkout_context,
        'origin_main': None,
        'origin_main_contains_authority': False,
        'stage19_status': stage19_status,
        'stage19as_au_status': stage19as_au_status,
        'current_state_is_superseded': False,
        'matched_invalid_state': None,
        'matched_superseded_state': None,
        'safe_for_operational_work': False,
        'safe_for_docs_only_work': False,
        'failure_category': failure_category,
        'next_action': next_action,
        'authority_test_env_branch': authority_test_env_branch(authority or {}),
        'authority_test_env_head': authority_test_env_head(authority or {}),
        'head_contains_authority': False,
        'authority_commit_available': False,
        'invalid_states': [public_state(state) for state in invalid_states(authority or {})],
        'superseded_states': [public_state(state) for state in invalid_states(authority or {})],
        'historical_context': (authority or {}).get('historical_context', {}),
        'rules': authority_rules(authority or {}),
        'prompt_rules': authority_rules(authority or {}),
        'allow_docs_only': allow_docs_only,
    }


def default_git_runner(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ('git', *args),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )


def run_git(runner: GitRunner, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    try:
        return runner(tuple(args))
    except Exception as exc:
        return subprocess.CompletedProcess(tuple(args), 1, stdout='', stderr=type(exc).__name__)


def git_output(runner: GitRunner, args: Sequence[str]) -> str | None:
    completed = run_git(runner, args)
    if completed.returncode != 0:
        return None
    text = completed.stdout.strip()
    return text or None


def ambiguous_state_next_action(environment: Mapping[str, str]) -> str:
    if is_github_actions_pull_request(environment):
        return 'Ensure CI checks out the pull request head SHA with a resolvable origin/main reference before continuing.'
    return 'Check out a named branch with a resolvable HEAD before continuing.'


def is_github_actions_pull_request(environment: Mapping[str, str]) -> bool:
    return (
        str(environment.get('GITHUB_ACTIONS', '')).lower() == 'true'
        and str(environment.get('GITHUB_EVENT_NAME', '')) == 'pull_request'
    )


def github_actions_detached_pr_head_context(
    environment: Mapping[str, str],
    current_head: str,
) -> dict[str, str] | None:
    if not is_github_actions_pull_request(environment):
        return None
    event_path = environment.get('GITHUB_EVENT_PATH')
    if not event_path:
        return None
    try:
        payload = json.loads(Path(event_path).read_text(encoding='utf-8'))
    except Exception:
        return None
    pull_request = payload.get('pull_request')
    if not isinstance(pull_request, Mapping):
        return None
    head = pull_request.get('head')
    if not isinstance(head, Mapping):
        return None
    expected_head = str(head.get('sha') or '').strip()
    expected_branch = str(head.get('ref') or '').strip()
    head_ref = str(environment.get('GITHUB_HEAD_REF', '')).strip()
    if not expected_head or not expected_branch or not head_ref or head_ref != expected_branch:
        return None
    if not commit_matches(current_head, expected_head):
        return None
    return {
        'head_ref': expected_branch,
        'head_sha': expected_head,
        'checkout_context': 'github_actions_detached_pr_head',
    }


def stage19_statuses(authority: Mapping[str, Any]) -> tuple[str, str]:
    stage19 = authority.get('stage19', {})
    if isinstance(stage19, Mapping):
        status = stage19.get('status')
        stage19as_au_status = stage19.get('stage19as_au_status')
        if status is not None or stage19as_au_status is not None:
            return str(status or 'unknown'), str(stage19as_au_status or 'unknown')

    current_authority = authority.get('current_authority', {})
    if isinstance(current_authority, Mapping):
        return (
            str(current_authority.get('stage19_status', 'unknown')),
            str(current_authority.get('stage19as_au_status', 'unknown')),
        )
    return 'unknown', 'unknown'


def authority_test_env_branch(authority: Mapping[str, Any]) -> str | None:
    current_authority = authority.get('current_authority', {})
    if not isinstance(current_authority, Mapping):
        return None
    value = current_authority.get('test_env_branch')
    return str(value) if value is not None else None


def authority_test_env_head(authority: Mapping[str, Any]) -> str:
    current_authority = authority.get('current_authority', {})
    if not isinstance(current_authority, Mapping):
        return ''
    return str(current_authority.get('test_env_head', ''))


def invalid_states(authority: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    states = authority.get('invalid_states')
    if isinstance(states, list):
        return [state for state in states if isinstance(state, Mapping)]

    legacy_states = authority.get('superseded_states')
    if isinstance(legacy_states, list):
        return [state for state in legacy_states if isinstance(state, Mapping)]
    return []


def authority_rules(authority: Mapping[str, Any]) -> Mapping[str, Any]:
    rules = authority.get('rules')
    if isinstance(rules, Mapping):
        return rules

    prompt_rules = authority.get('prompt_rules')
    if isinstance(prompt_rules, Mapping):
        return prompt_rules
    return {}


def find_matching_invalid_state(
    authority: Mapping[str, Any],
    current_branch: str,
    current_head: str,
) -> tuple[Mapping[str, Any] | None, str | None]:
    for state in invalid_states(authority):
        if state.get('branch') and state.get('branch') == current_branch:
            return state, 'branch'
        if current_branch in state_identifiers(state):
            return state, 'branch'
    for state in invalid_states(authority):
        if any(commit_matches(current_head, commit) for commit in state_commits(state)):
            return state, 'head'
    return None, None


def state_commits(state: Mapping[str, Any]) -> list[str]:
    commits = state_identifiers(state)
    if state.get('commit'):
        commits.append(str(state['commit']))
    commits.extend(str(commit) for commit in state.get('commits', []))
    return commits


def state_identifiers(state: Mapping[str, Any]) -> list[str]:
    if state.get('id') is None:
        return []
    return [str(state['id'])]


def commit_matches(current_head: str, known_commit: str) -> bool:
    current = current_head.lower()
    known = known_commit.lower()
    return current.startswith(known) or known.startswith(current)


def source_of_truth_available(
    origin_main: str | None,
    origin_main_contains_authority: bool,
    authority_commit_available: bool,
) -> bool:
    return bool(origin_main and origin_main_contains_authority and authority_commit_available)


def public_state(state: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not state:
        return None
    keys = ('id', 'branch', 'commit', 'commits', 'status', 'reason', 'replacement', 'evidence_only')
    return {key: state[key] for key in keys if key in state}


def relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def print_human(result: Mapping[str, Any]) -> None:
    for key in (
        'state_authority_file',
        'current_branch',
        'effective_branch',
        'current_head',
        'checkout_context',
        'origin_main',
        'origin_main_contains_authority',
        'stage19_status',
        'stage19as_au_status',
        'current_state_is_superseded',
        'matched_invalid_state',
        'safe_for_operational_work',
        'safe_for_docs_only_work',
        'failure_category',
        'next_action',
    ):
        print(f'{key}: {format_value(result.get(key))}')


def format_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    if value is None:
        return 'null'
    return str(value)


if __name__ == '__main__':
    raise SystemExit(main())
