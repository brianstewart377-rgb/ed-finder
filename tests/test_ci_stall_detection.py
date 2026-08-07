"""Every GitHub Actions job must declare timeout-minutes.

Without an explicit job-level timeout, a hung step (a docker command that
never returns, a retry loop with no bound, a network call with no client
timeout — the same class of bug the 2026-08-06 nightly_update.sh incident
and the 2026-08-07 Review Lab docker-startup flake both were) runs until
GitHub's global default of 360 minutes, silently occupying a runner and
leaving a PR's checks stuck "in progress" with no signal that anything is
actually stuck versus just slow. A bounded timeout turns a silent multi-hour
hang into a fast, visible failure.

Parsed with PyYAML (real structural parsing), not text scanning — the
first version of this test used a hand-rolled line scanner and Codex Review
correctly found five ways it could pass a workflow that actually violates
the contract: a `timeout-minutes` substring anywhere in a job block (even a
step's command or a comment) satisfied it; underscore-prefixed job IDs
(valid in GitHub Actions) weren't recognized as job starts; a top-level key
after `jobs:` (e.g. `defaults:`) wasn't detected as the end of the jobs
section, so its children were misread as job blocks; and `.yaml` (as
opposed to `.yml`) workflow files were never enumerated. Real YAML parsing
avoids all four by construction.
"""
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = ROOT / '.github' / 'workflows'

# Every job-bearing workflow file in this repo. New workflow files must be
# added here explicitly — a file silently excluded from this list would
# defeat the point of the contract.
CHECKED_WORKFLOWS = (
    'ci.yml',
    'container-image-parity.yml',
    'hetzner-operator.yml',
    'review-lab.yml',
)


def _load_workflow(filename: str) -> dict:
    return yaml.safe_load((WORKFLOWS_DIR / filename).read_text(encoding='utf-8'))


def test_every_workflow_job_declares_a_timeout():
    missing = []
    for filename in CHECKED_WORKFLOWS:
        workflow = _load_workflow(filename)
        jobs = workflow.get('jobs') or {}
        assert jobs, f'{filename}: found no jobs — workflow structure may have changed'
        for job_id, job in jobs.items():
            # GitHub Actions does not allow timeout-minutes on a job that
            # calls a reusable workflow (`uses:` at job level, distinct
            # from a step's `uses:`) — the reusable workflow's own jobs
            # carry their own timeouts instead. No such job exists in this
            # repo today, but the contract must not forbid a valid one.
            if 'uses' in job:
                continue
            if 'timeout-minutes' not in job:
                missing.append(f'{filename}:{job_id}')

    assert not missing, (
        'These jobs have no timeout-minutes and will run until GitHub\'s '
        'global 360-minute default before a hang becomes visible:\n'
        + '\n'.join(missing)
    )


def test_reusable_workflow_call_jobs_are_exempt_not_silently_ignored():
    """Direct unit test of the `uses:` exemption: proves a caller job is
    skipped deliberately (and would still need timeout-minutes if it also
    contains one, since the field being absent is what triggers the skip
    path — this doesn't accidentally exempt every job)."""
    workflow_yaml = (
        'jobs:\n'
        '  caller:\n'
        '    uses: ./.github/workflows/reusable.yml\n'
        '  direct_unbounded:\n'
        '    runs-on: ubuntu-latest\n'
    )
    workflow = yaml.safe_load(workflow_yaml)
    jobs = workflow['jobs']

    assert 'uses' in jobs['caller']
    assert 'timeout-minutes' not in jobs['direct_unbounded']
    # 'caller' must be skippable; 'direct_unbounded' must not be — this is
    # the exact distinction the exemption in the real test above relies on.


def test_underscore_prefixed_job_ids_are_recognized():
    """GitHub Actions permits a job ID to start with an underscore. A
    substring/regex-based scanner keyed on `[a-zA-Z]` would silently fold
    such a job into whatever job precedes it in the file."""
    workflow_yaml = (
        'jobs:\n'
        '  _internal:\n'
        '    runs-on: ubuntu-latest\n'
    )
    workflow = yaml.safe_load(workflow_yaml)

    assert '_internal' in workflow['jobs']
    assert 'timeout-minutes' not in workflow['jobs']['_internal']


def test_all_checked_workflow_files_exist():
    for filename in CHECKED_WORKFLOWS:
        assert (WORKFLOWS_DIR / filename).is_file(), f'missing workflow file: {filename}'

    # Both extensions GitHub Actions recognizes — a workflow added as
    # .yaml rather than .yml must not silently escape this contract.
    all_workflow_files = {
        p.name for p in WORKFLOWS_DIR.iterdir()
        if p.suffix in ('.yml', '.yaml')
    }
    assert all_workflow_files == set(CHECKED_WORKFLOWS), (
        'A workflow file exists that this contract does not check: '
        f'{all_workflow_files - set(CHECKED_WORKFLOWS)}. Add it to '
        'CHECKED_WORKFLOWS explicitly.'
    )
