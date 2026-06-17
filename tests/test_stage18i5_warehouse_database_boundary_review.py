from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
README_PATH = DOCS / 'README.md'
STAGE18I5_PATH = DOCS / 'stage-18i5-warehouse-database-boundary-review.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


def test_stage18i5_authority_records_boundary_review_and_stage18j_handoff():
    authority = _json(AUTHORITY_PATH)
    stage18i5 = authority['stage18i5']

    assert STAGE18I5_PATH.exists()
    assert authority['stage21']['next_checkpoint'] == 'Stage 18T - Canonical safety test environment'
    assert stage18i5['status'] == 'completed'
    assert stage18i5['checkpoint_type'] == 'boundary_review'
    assert stage18i5['document'] == 'docs/colonisation-redesign/stage-18i5-warehouse-database-boundary-review.md'
    assert stage18i5['design_only'] is True
    assert stage18i5['preferred_boundary_option'] == 'option_b_same_stack_separate_database'
    assert stage18i5['recommended_database_name'] == 'edfinder_enrichment'
    assert stage18i5['stage18j_apply_authorized'] is False
    assert stage18i5['warehouse_boundary_implemented'] is False
    assert stage18i5['db_writes_authorized'] is False
    assert stage18i5['production_like_db_execution_authorized'] is False


def test_stage18i5_docs_and_ci_parity_record_the_boundary_review():
    document = _read(STAGE18I5_PATH)
    readme = _read(README_PATH)
    parity = _read(LOCAL_CI_PARITY)

    for fragment in (
        'Stage 18I.5 is a documentation and design review only.',
        'Stage 18I.5 recommends Option B now if feasible',
        'edfinder_enrichment',
        'Stage 18J cannot start',
        'Do not implement Option B in this stage.',
    ):
        assert fragment in document

    assert 'stage-18i5-warehouse-database-boundary-review.md' in readme
    assert 'stage-18j-station-type-canonical-pilot-plan.md' in readme
    assert 'tests/test_stage18i5_warehouse_database_boundary_review.py' in parity
