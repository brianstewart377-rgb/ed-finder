from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
README_PATH = DOCS / 'README.md'
STAGE18I_PATH = DOCS / 'stage-18i-canonical-write-design-review.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


def test_stage18i_authority_records_design_only_checkpoint_and_stage18i5_dependency():
    authority = _json(AUTHORITY_PATH)
    stage18i = authority['stage18i']

    assert STAGE18I_PATH.exists()
    assert authority['stage21']['next_checkpoint'] == 'Stage 18T - Canonical safety test environment'
    assert stage18i['status'] == 'completed'
    assert stage18i['checkpoint_type'] == 'design_review'
    assert stage18i['document'] == 'docs/colonisation-redesign/stage-18i-canonical-write-design-review.md'
    assert stage18i['design_only'] is True
    assert stage18i['recommended_first_stage18j_pilot'] == 'exact_station_type_promotion'
    assert stage18i['stage18i5_required_before_stage18j'] is True
    assert stage18i['write_path_implemented'] is False
    assert stage18i['canonical_writes_authorized'] is False
    assert stage18i['db_writes_authorized'] is False
    assert stage18i['production_like_db_execution_authorized'] is False


def test_stage18i_docs_and_ci_parity_record_the_design_review():
    document = _read(STAGE18I_PATH)
    readme = _read(README_PATH)
    parity = _read(LOCAL_CI_PARITY)

    for fragment in (
        'Stage 18I is a documentation and design review only.',
        'Stage 18I does not authorize canonical writes.',
        'Stage 18J cannot begin until Stage 18I and Stage 18I.5 are complete.',
        'exact station type promotion',
        'Proceed next to Stage 18I.5',
    ):
        assert fragment in document

    assert 'stage-18i-canonical-write-design-review.md' in readme
    assert 'stage-18i5-warehouse-database-boundary-review.md' in readme
    assert 'tests/test_stage18i_canonical_write_design_review.py' in parity
