"""Every GitHub Actions job must declare timeout-minutes.

Without an explicit job-level timeout, a hung step (a docker command that
never returns, a retry loop with no bound, a network call with no client
timeout — the same class of bug the 2026-08-06 nightly_update.sh incident
and the 2026-08-07 Review Lab docker-startup flake both were) runs until
GitHub's global default of 360 minutes, silently occupying a runner and
leaving a PR's checks stuck "in progress" with no signal that anything is
actually stuck versus just slow. A bounded timeout turns a silent multi-hour
hang into a fast, visible failure.

Parsed with plain text scanning rather than a YAML library: this repo's
workflow-file tests consistently avoid taking on a YAML-parsing dependency
for structural checks like this one, and a job block is simple enough
(2-space-indented `key:` lines) to find without it.
"""
import re
from pathlib import Path


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

_JOB_KEY_RE = re.compile(r'^  ([a-zA-Z][a-zA-Z0-9_-]*):\s*$')
_TOP_LEVEL_NON_JOB_KEYS = {'on', 'permissions', 'concurrency', 'env', 'jobs'}


def _job_blocks(workflow_text: str) -> dict[str, str]:
    lines = workflow_text.splitlines()
    job_starts: list[tuple[str, int]] = []
    in_jobs_section = False
    for i, line in enumerate(lines):
        if line == 'jobs:':
            in_jobs_section = True
            continue
        if not in_jobs_section:
            continue
        match = _JOB_KEY_RE.match(line)
        if match and match.group(1) not in _TOP_LEVEL_NON_JOB_KEYS:
            job_starts.append((match.group(1), i))

    blocks = {}
    for idx, (name, start) in enumerate(job_starts):
        end = job_starts[idx + 1][1] if idx + 1 < len(job_starts) else len(lines)
        blocks[name] = '\n'.join(lines[start:end])
    return blocks


def _read_workflow(filename: str) -> str:
    return (WORKFLOWS_DIR / filename).read_text(encoding='utf-8')


def test_every_workflow_job_declares_a_timeout():
    missing = []
    for filename in CHECKED_WORKFLOWS:
        blocks = _job_blocks(_read_workflow(filename))
        assert blocks, f'{filename}: found no jobs — job-block parsing may be broken'
        for job_name, block in blocks.items():
            if 'timeout-minutes:' not in block:
                missing.append(f'{filename}:{job_name}')

    assert not missing, (
        'These jobs have no timeout-minutes and will run until GitHub\'s '
        'global 360-minute default before a hang becomes visible:\n'
        + '\n'.join(missing)
    )


def test_job_block_parser_isolates_one_job_from_the_next():
    """Direct unit test of the block-splitting logic: proves a value that
    belongs to job B isn't misread as belonging to job A, which would let
    a missing timeout on A pass by reading B's."""
    sample = (
        'name: Sample\n'
        'on:\n'
        '  pull_request:\n'
        'jobs:\n'
        '  alpha:\n'
        '    name: Alpha\n'
        '    runs-on: ubuntu-latest\n'
        '  beta:\n'
        '    name: Beta\n'
        '    runs-on: ubuntu-latest\n'
        '    timeout-minutes: 10\n'
    )
    blocks = _job_blocks(sample)

    assert set(blocks) == {'alpha', 'beta'}
    assert 'timeout-minutes:' not in blocks['alpha']
    assert 'timeout-minutes:' in blocks['beta']


def test_all_checked_workflow_files_exist():
    for filename in CHECKED_WORKFLOWS:
        assert (WORKFLOWS_DIR / filename).is_file(), f'missing workflow file: {filename}'

    all_workflow_files = {p.name for p in WORKFLOWS_DIR.glob('*.yml')}
    assert all_workflow_files == set(CHECKED_WORKFLOWS), (
        'A workflow file exists that this contract does not check: '
        f'{all_workflow_files - set(CHECKED_WORKFLOWS)}. Add it to '
        'CHECKED_WORKFLOWS explicitly.'
    )
