from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
README_PATH = DOCS / 'README.md'
STAGE18H4_PATH = DOCS / 'stage-18h4-warehouse-evidence-ux-clarification.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


def test_stage18h4_authority_records_readonly_ux_clarification():
    authority = _json(AUTHORITY_PATH)
    stage18h4 = authority['stage18h4']

    assert STAGE18H4_PATH.exists()
    assert authority['stage21']['next_checkpoint'] == 'Stage 18J - Station type canonical write pilot'
    assert stage18h4['status'] == 'completed'
    assert stage18h4['checkpoint_type'] == 'ux_clarification'
    assert stage18h4['document'] == 'docs/colonisation-redesign/stage-18h4-warehouse-evidence-ux-clarification.md'
    assert stage18h4['freshness_badge_added'] is True
    assert stage18h4['review_status_added'] is True
    assert stage18h4['source_posture_added'] is True
    assert stage18h4['warnings_added'] is True
    assert stage18h4['interactive_controls_added'] is False
    assert stage18h4['planner_truth_changed'] is False
    assert stage18h4['db_writes_authorized'] is False


def test_stage18h4_docs_and_ci_parity_record_the_ux_slice():
    document = _read(STAGE18H4_PATH)
    readme = _read(README_PATH)
    parity = _read(LOCAL_CI_PARITY)

    for fragment in (
        'freshness is explicit',
        'review status is explicit',
        'source posture is explicit',
        'does **not**',
        'Stage 18I',
    ):
        assert fragment in document

    assert 'stage-18h4-warehouse-evidence-ux-clarification.md' in readme
    assert 'tests/test_stage18h4_warehouse_evidence_ux_clarification.py' in parity
