#!/usr/bin/env python3
"""Resolve Stage 19/test-environment authority before operational work."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
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
) -> int:
    args = parse_args(argv)
    result = resolve_project_state(
        authority_path=authority_path,
        git_runner=git_runner,
        allow_docs_only=args.allow_docs_only,
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
) -> dict[str, Any]:
    runner = git_runner or default_git_runner
    authority, authority_error = load_authority(authority_path)
    if authority_error is not None:
        return build_failure(
            authority_path=authority_path,
            failure_category=authority_error,
            next_action='Restore a valid Stage 19 state authority file before continuing.',
            allow_docs_only=allow_docs_only,
        )

    assert authority is not None
    current_authority = authority.get('current_authority', {})
    stage19_status = str(current_authority.get('stage19_status', 'unknown'))
    stage19as_au_status = str(current_authority.get('stage19as_au_status', 'unknown'))

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
    if not current_branch or not current_head:
        return build_failure(
            authority_path=authority_path,
            authority=authority,
            stage19_status=stage19_status,
            stage19as_au_status=stage19as_au_status,
            current_branch=current_branch,
            current_head=current_head,
            failure_category='ambiguous_local_state',
            next_action='Check out a named branch with a resolvable HEAD before continuing.',
            allow_docs_only=allow_docs_only,
        )

    expected_origin_main = str(current_authority.get('origin_main', ''))
    origin_main = git_output(runner, ('rev-parse', 'origin/main'))
    origin_main_contains_authority = False
    if origin_main:
        origin_main_contains_authority = (
            run_git(runner, ('merge-base', '--is-ancestor', expected_origin_main, 'origin/main')).returncode == 0
        )

    expected_head = str(current_authority.get('test_env_head', ''))
    authority_commit_available = False
    head_contains_authority = False
    if expected_head:
        authority_commit_available = run_git(runner, ('rev-parse', '--verify', expected_head)).returncode == 0
        head_contains_authority = (
            run_git(runner, ('merge-base', '--is-ancestor', expected_head, 'HEAD')).returncode == 0
        )

    matched_state, matched_by = find_matching_superseded_state(authority, current_branch, current_head)
    failure_category = 'none'
    next_action = 'State authority checks passed for operational work.'

    if not origin_main:
        failure_category = 'origin_main_unavailable'
        next_action = 'Fetch origin/main and rerun state resolution before operational work.'
    elif not origin_main_contains_authority:
        failure_category = 'stale_stage19_context'
        next_action = 'Update origin/main to include the authoritative checkpoint before continuing.'
    elif not authority_commit_available:
        failure_category = 'authority_commit_missing'
        next_action = 'Fetch the authoritative test-environment commit before continuing.'
    elif matched_state and current_branch == 'work':
        failure_category = 'wrong_branch'
        next_action = 'Switch off work; use fix/test-env-roadmap-recreate or a clean child branch.'
    elif current_branch == 'work':
        failure_category = 'wrong_branch'
        next_action = 'Branch work is non-authoritative for Stage 19/test-env operational work.'
    elif matched_state and matched_by == 'branch':
        failure_category = 'current_branch_superseded'
        next_action = 'Switch to fix/test-env-roadmap-recreate or a clean child branch.'
    elif matched_state and matched_by == 'head':
        failure_category = 'current_head_superseded'
        next_action = 'Do not use this superseded commit as authority; switch to the current test-env branch.'
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
        'current_head': current_head,
        'origin_main': origin_main,
        'origin_main_contains_authority': origin_main_contains_authority,
        'stage19_status': stage19_status,
        'stage19as_au_status': stage19as_au_status,
        'current_state_is_superseded': matched_state is not None,
        'matched_superseded_state': public_state(matched_state),
        'safe_for_operational_work': safe_for_operational_work,
        'safe_for_docs_only_work': safe_for_docs_only_work,
        'failure_category': failure_category,
        'next_action': next_action,
        'authority_test_env_branch': current_authority.get('test_env_branch'),
        'authority_test_env_head': expected_head,
        'head_contains_authority': head_contains_authority,
        'authority_commit_available': authority_commit_available,
        'superseded_states': [public_state(state) for state in authority.get('superseded_states', [])],
        'prompt_rules': authority.get('prompt_rules', {}),
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
    required = ('current_authority', 'superseded_states', 'prompt_rules')
    if any(key not in data for key in required):
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
    current_head: str | None = None,
) -> dict[str, Any]:
    assert failure_category in FAILURE_CATEGORIES
    return {
        'state_authority_file': relative_path(authority_path),
        'current_branch': current_branch,
        'current_head': current_head,
        'origin_main': None,
        'origin_main_contains_authority': False,
        'stage19_status': stage19_status,
        'stage19as_au_status': stage19as_au_status,
        'current_state_is_superseded': False,
        'matched_superseded_state': None,
        'safe_for_operational_work': False,
        'safe_for_docs_only_work': False,
        'failure_category': failure_category,
        'next_action': next_action,
        'authority_test_env_branch': (authority or {}).get('current_authority', {}).get('test_env_branch'),
        'authority_test_env_head': (authority or {}).get('current_authority', {}).get('test_env_head'),
        'head_contains_authority': False,
        'authority_commit_available': False,
        'superseded_states': [public_state(state) for state in (authority or {}).get('superseded_states', [])],
        'prompt_rules': (authority or {}).get('prompt_rules', {}),
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


def find_matching_superseded_state(
    authority: Mapping[str, Any],
    current_branch: str,
    current_head: str,
) -> tuple[Mapping[str, Any] | None, str | None]:
    for state in authority.get('superseded_states', []):
        if state.get('branch') and state.get('branch') == current_branch:
            return state, 'branch'
    for state in authority.get('superseded_states', []):
        if any(commit_matches(current_head, commit) for commit in state_commits(state)):
            return state, 'head'
    return None, None


def state_commits(state: Mapping[str, Any]) -> list[str]:
    commits: list[str] = []
    if state.get('commit'):
        commits.append(str(state['commit']))
    commits.extend(str(commit) for commit in state.get('commits', []))
    return commits


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
        'current_head',
        'origin_main',
        'origin_main_contains_authority',
        'stage19_status',
        'stage19as_au_status',
        'current_state_is_superseded',
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
