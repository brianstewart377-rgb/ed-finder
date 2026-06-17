from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
README_PATH = DOCS / 'README.md'
STAGE18T_PATH = DOCS / 'stage-18t-canonical-safety-test-environment.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'
LOCAL_RUNNER_PATH = ROOT / 'scripts' / 'run_canonical_safety_tests.sh'
CI_REQUIREMENTS_PATH = ROOT / 'tests' / 'requirements-ci.txt'
WORKFLOW_PATH = ROOT / '.github' / 'workflows' / 'ci.yml'
POSTGRES_REHEARSAL_TEST_PATH = ROOT / 'tests' / 'test_station_type_canonical_pilot_postgres.py'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


def test_stage18t_authority_records_canonical_safety_environment_and_stage18jq_handoff():
    authority = _json(AUTHORITY_PATH)
    stage18t = authority['stage18t']

    assert STAGE18T_PATH.exists()
    assert LOCAL_RUNNER_PATH.exists()
    assert CI_REQUIREMENTS_PATH.exists()
    assert WORKFLOW_PATH.exists()
    assert POSTGRES_REHEARSAL_TEST_PATH.exists()
    assert authority['stage21']['next_checkpoint'] == 'Stage 18J-Q - Production reconciliation artifact readiness'
    assert stage18t['status'] == 'completed'
    assert stage18t['checkpoint_type'] == 'canonical_safety_environment'
    assert stage18t['document'] == 'docs/colonisation-redesign/stage-18t-canonical-safety-test-environment.md'
    assert stage18t['canonical_safety_ci_job_present'] is True
    assert stage18t['local_canonical_safety_runner_present'] is True
    assert stage18t['ci_requirements_manifest_present'] is True
    assert stage18t['disposable_postgres_rehearsal_present'] is True
    assert stage18t['permission_boundary_rehearsal_present'] is True
    assert stage18t['production_apply_authorized'] is False
    assert stage18t['production_artifact_generated'] is False
    assert stage18t['db_writes_authorized'] is False
    assert stage18t['production_like_db_execution_authorized'] is False


def test_stage18t_docs_workflow_runner_and_ci_parity_record_the_safety_environment():
    document = _read(STAGE18T_PATH)
    readme = _read(README_PATH)
    parity = _read(LOCAL_CI_PARITY)
    runner = _read(LOCAL_RUNNER_PATH)
    workflow = _read(WORKFLOW_PATH)
    requirements = _read(CI_REQUIREMENTS_PATH)

    for fragment in (
        'Stage 18T hardens the test environment around canonical-write-capable code.',
        'Canonical safety tests',
        './scripts/run_canonical_safety_tests.sh',
        'EDFINDER_CANONICAL_TEST_DSN',
        'permission-boundary',
        'Stage 18J-Q',
    ):
        assert fragment in document

    assert 'stage-18t-canonical-safety-test-environment.md' in readme
    assert 'stage-18j-q-production-reconciliation-artifact-readiness.md' in readme
    assert 'tests/test_stage18t_canonical_safety_environment.py' in parity
    assert 'tests/test_station_type_canonical_pilot.py' in runner
    assert 'tests/test_station_type_canonical_pilot_postgres.py' in runner
    assert 'Canonical safety tests' in workflow
    assert 'tests/requirements-ci.txt' in workflow
    assert 'EDFINDER_CANONICAL_TEST_DSN' in workflow
    assert 'pytest-asyncio' in requirements
