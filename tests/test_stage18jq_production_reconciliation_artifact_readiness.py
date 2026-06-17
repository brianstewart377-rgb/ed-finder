from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
README_PATH = DOCS / 'README.md'
STAGE18JQ_PATH = DOCS / 'stage-18j-q-production-reconciliation-artifact-readiness.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


def test_stage18jq_authority_records_readiness_review_and_stage18jq2_handoff():
    authority = _json(AUTHORITY_PATH)
    stage18jq = authority['stage18jq']

    assert STAGE18JQ_PATH.exists()
    assert authority['stage21']['next_checkpoint'] == 'Stage 18J-P-filter - Strict station-type dry-run filter'
    assert stage18jq['status'] == 'completed'
    assert stage18jq['checkpoint_type'] == 'artifact_readiness_review'
    assert stage18jq['document'] == 'docs/colonisation-redesign/stage-18j-q-production-reconciliation-artifact-readiness.md'
    assert stage18jq['artifact_search_completed'] is True
    assert stage18jq['suitable_production_artifact_found'] is False
    assert stage18jq['report_only_generation_path_reviewed'] is True
    assert stage18jq['production_connected_command_run'] is False
    assert stage18jq['stage18jp_blocked'] is True
    assert stage18jq['production_apply_authorized'] is False
    assert stage18jq['production_artifact_generated'] is False
    assert stage18jq['db_writes_authorized'] is False
    assert stage18jq['production_like_db_execution_authorized'] is False


def test_stage18jq_docs_and_ci_parity_record_the_readiness_review():
    document = _read(STAGE18JQ_PATH)
    readme = _read(README_PATH)
    parity = _read(LOCAL_CI_PARITY)

    for fragment in (
        'Stage 18J-Q prepares the missing prerequisite for Stage 18J-P',
        'No suitable production `enrichment_staging_reconciliation/v1` artifact was',
        'This command was reviewed but not run.',
        'Stage 18J-P remains blocked.',
        'Stage 18J-Q2 defines the exact later operator command plan',
    ):
        assert fragment in document

    assert 'stage-18j-q-production-reconciliation-artifact-readiness.md' in readme
    assert 'stage-18j-q2-readonly-production-reconciliation-plan.md' in readme
    assert 'tests/test_stage18jq_production_reconciliation_artifact_readiness.py' in parity
