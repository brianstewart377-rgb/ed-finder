import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
STAGE24_PATH = DOCS / 'stage-24-roadmap.md'
STAGE24D_PATH = DOCS / 'stage-24d-readonly-evidence-adoption-closeout.md'
README_PATH = DOCS / 'README.md'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


def _squash(text: str) -> str:
    return re.sub(r'\s+', ' ', text)


@pytest.mark.unit
def test_stage24d_authority_closes_stage24_without_reopening_write_lanes():
    authority = _json(AUTHORITY_PATH)
    stage24 = authority['stage24']
    stage24d = authority['stage24d']

    assert stage24['status'] == 'completed'
    assert stage24['current_checkpoint'] == 'Stage 24D - Closeout'
    assert stage24['next_checkpoint'] is None
    assert stage24['stage24_closed'] is True
    assert stage24['future_control_document_required'] is True
    assert stage24['write_capable_lane_authorized'] is False
    assert stage24['db_writes_authorized'] is False
    assert stage24['canonical_apply_authorized'] is False
    assert stage24['rebaseline_authorized'] is False
    assert stage24['scheduler_service_authorized'] is False
    assert stage24['no_new_implementation_mixed_in'] is True

    assert stage24d['status'] == 'completed'
    assert stage24d['checkpoint_type'] == 'readonly_evidence_adoption_closeout'
    assert stage24d['document'] == (
        'docs/colonisation-redesign/stage-24d-readonly-evidence-adoption-closeout.md'
    )
    assert stage24d['mode'] == 'closeout'
    assert stage24d['stage24_closed'] is True
    assert stage24d['stage24a_completed'] is True
    assert stage24d['stage24b_completed'] is True
    assert stage24d['stage24c_completed'] is True
    assert stage24d['future_control_document_required'] is True
    assert stage24d['stage23_remains_closed'] is True
    assert stage24d['stage19_remains_separately_gated'] is True
    assert stage24d['no_stage19bb_execution_occurred'] is True
    assert stage24d['write_capable_lane_authorized'] is False
    assert stage24d['db_writes_performed'] is False
    assert stage24d['canonical_apply_performed'] is False
    assert stage24d['rebaseline_performed'] is False
    assert stage24d['scheduler_enabled'] is False
    assert stage24d['source_files_committed'] is False
    assert stage24d['runtime_artifacts_committed'] is False
    assert stage24d['no_new_implementation_mixed_in'] is True


@pytest.mark.unit
def test_stage24d_document_records_closeout_mode_and_future_control_handoff():
    text = _read(STAGE24D_PATH)

    assert STAGE24D_PATH.exists()
    assert 'Stage 24D runs in `closeout` mode.' in text
    assert 'Stage 24 closes as the read-only evidence adoption and governance' in text
    assert 'Stage 24A` remains complete' in text
    assert 'Stage 24B` remains complete' in text
    assert 'Stage 24C` remains complete' in text
    assert 'Future work requires a new explicit post-Stage-24 control document.' in text
    assert 'Stage 23 remains closed.' in text
    assert 'Stage 19 remains separately gated.' in text
    assert 'no DB writes occurred' in text
    assert 'no canonical apply occurred' in text
    assert 'no rebaseline occurred' in text
    assert 'no new implementation was mixed into the closeout checkpoint' in text


@pytest.mark.unit
def test_stage24d_is_discoverable_from_roadmap_and_readme():
    roadmap = _squash(_read(STAGE24_PATH))
    readme = _read(README_PATH)

    assert 'Stage 24D is complete as the closeout checkpoint.' in roadmap
    assert 'stage-24d-readonly-evidence-adoption-closeout.md' in roadmap
    assert 'new explicit post-Stage-24 control document' in roadmap
    assert 'stage-24d-readonly-evidence-adoption-closeout.md' in readme
    assert 'completed Stage 24D closeout' in readme
    assert 'Completed Stage 24D closeout record' in readme
