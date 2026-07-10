import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
STAGE23_ROADMAP_PATH = DOCS / 'stage-23-roadmap.md'
STAGE23E_PATH = DOCS / 'stage-23e-readonly-evidence-closeout.md'
STAGE24_ROADMAP_PATH = DOCS / 'stage-24-roadmap.md'
README_PATH = DOCS / 'README.md'

PRIMARY_OBJECTIVE = (
    'Turn the completed Stage 23 read-only planner evidence baseline into a '
    'discoverable, explainable, and consistently governed product surface without '
    'authorizing Stage 19 execution, DB writes, canonical apply, rebaseline, or '
    'scheduler/service activation.'
)
FIRST_CHECKPOINT = 'Stage 24A - Read-only evidence adoption implementation contract'
FINAL_CHECKPOINT = 'Stage 24D - Closeout'
SELECTED_WORKSTREAM = 'ux_product_adoption_of_readonly_evidence_baseline'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


def _squash(text: str) -> str:
    return re.sub(r'\s+', ' ', text)


@pytest.mark.unit
def test_stage24_authority_records_the_closed_post_stage23_control():
    authority = _json(AUTHORITY_PATH)
    stage23 = authority['stage23']
    stage23e = authority['stage23e']
    stage24 = authority['stage24']
    baseline = authority['stage24_planning_baseline']

    assert stage23['status'] == 'completed'
    assert stage23['stage23_closed'] is True
    assert stage23e['stage23_closed'] is True

    assert stage24['status'] == 'completed'
    assert stage24['planning_authorized'] is True
    assert stage24['implementation_started'] is True
    assert stage24['implementation_authorized'] is True
    assert stage24['primary_objective'] == PRIMARY_OBJECTIVE
    assert stage24['first_executable_checkpoint'] == FIRST_CHECKPOINT
    assert stage24['current_checkpoint'] == FINAL_CHECKPOINT
    assert stage24['next_checkpoint'] is None
    assert stage24['roadmap'] == 'docs/ROADMAP.md'
    assert stage24['stage23_closed'] is True
    assert stage24['stage23_readonly_baseline_complete'] is True
    assert stage24['selected_workstream'] == SELECTED_WORKSTREAM
    assert stage24['docs_static_only'] is True
    assert stage24['write_capable_lane_authorized'] is False
    assert stage24['stage19_execution_authorized'] is False
    assert stage24['canonical_apply_authorized'] is False
    assert stage24['rebaseline_authorized'] is False
    assert stage24['scheduler_enabled'] is False
    assert stage24['scheduler_service_authorized'] is False
    assert stage24['db_writes_authorized'] is False
    assert stage24['stage24a_contract_completed'] is True
    assert stage24['stage24b_implementation_started'] is True
    assert stage24['stage24b_implementation_completed'] is True
    assert stage24['stage24c_implementation_started'] is True
    assert stage24['stage24c_implementation_completed'] is True
    assert stage24['stage24d_implementation_started'] is True
    assert stage24['stage24_closed'] is True
    assert stage24['future_control_document_required'] is True
    assert stage24['closeout_mode'] == 'closeout'
    assert stage24['closeout_document'] == (
        'docs/colonisation-redesign/stage-24d-readonly-evidence-adoption-closeout.md'
    )
    assert stage24['no_new_implementation_mixed_in'] is True
    assert stage24['source_files_committed'] is False
    assert stage24['runtime_artifacts_committed'] is False

    assert baseline['status'] == 'completed'
    assert baseline['checkpoint_type'] == 'planning_baseline'
    assert baseline['docs_static_only'] is True
    assert baseline['roadmap'] == 'docs/ROADMAP.md'
    assert baseline['primary_objective'] == PRIMARY_OBJECTIVE
    assert baseline['selected_workstream'] == SELECTED_WORKSTREAM
    assert baseline['first_executable_checkpoint'] == FIRST_CHECKPOINT
    assert baseline['checkpoint_count'] == 4
    assert len(baseline['checkpoints']) == 4
    assert baseline['checkpoints'][0] == FIRST_CHECKPOINT
    assert baseline['closeout_checkpoint'] == FINAL_CHECKPOINT
    assert baseline['stage24_closed'] is True
    assert baseline['future_control_document_required'] is True
    assert baseline['stage23_remains_closed'] is True
    assert baseline['read_only_baseline_preserved'] is True
    assert baseline['bounded_staging_report_only'] is True
    assert baseline['write_capable_lane_authorized'] is False
    assert baseline['stage19_execution_authorized'] is False
    assert baseline['canonical_apply_authorized'] is False
    assert baseline['rebaseline_authorized'] is False
    assert baseline['scheduler_enabled'] is False
    assert baseline['db_writes_authorized'] is False
    assert baseline['source_acquisition_run'] is False
    assert baseline['source_files_committed'] is False
    assert baseline['runtime_artifacts_committed'] is False
    assert baseline['implementation_started'] is False


@pytest.mark.unit
def test_stage24_roadmap_defines_exactly_one_primary_objective_and_candidates():
    roadmap = _squash(_read(STAGE24_ROADMAP_PATH))
    baseline = _json(AUTHORITY_PATH)['stage24_planning_baseline']

    assert STAGE24_ROADMAP_PATH.exists()
    assert roadmap.count('Stage 24 has exactly one primary objective') == 1
    assert 'Turn the completed Stage 23 read-only planner evidence baseline into a' in roadmap
    assert 'discoverable, explainable, and consistently governed product surface without' in roadmap
    assert 'authorizing Stage 19 execution, DB writes, canonical apply, rebaseline, or' in roadmap
    assert 'scheduler/service activation.' in roadmap
    assert '## Candidate Workstream Summary' in _read(STAGE24_ROADMAP_PATH)
    assert 'Read-only planner evidence hardening after Stage 23' in roadmap
    assert 'Canonical promotion / canonical apply planning' in roadmap
    assert 'Production-staging expansion beyond 10,000 rows' in roadmap
    assert 'Scheduler/service activation planning' in roadmap
    assert 'UX/product adoption of the read-only evidence baseline' in roadmap
    assert 'Data-quality/source-governance control' in roadmap
    assert 'The selected Stage 24 workstream is:' in _read(STAGE24_ROADMAP_PATH)
    assert '`UX/product adoption of the read-only evidence baseline`' in _read(STAGE24_ROADMAP_PATH)
    assert baseline['candidate_workstreams_considered'] == [
        'read_only_planner_evidence_hardening_after_stage23',
        'canonical_promotion_canonical_apply_planning',
        'production_staging_expansion_beyond_10000_rows',
        'scheduler_service_activation_planning',
        'ux_product_adoption_of_readonly_evidence_baseline',
        'data_quality_source_governance_control',
    ]


@pytest.mark.unit
def test_stage24_boundaries_keep_stage19_and_write_capable_lanes_closed():
    authority = _json(AUTHORITY_PATH)
    stage24 = authority['stage24']
    baseline = authority['stage24_planning_baseline']
    roadmap = _squash(_read(STAGE24_ROADMAP_PATH))

    for source in (stage24, baseline):
        assert source['stage19_execution_authorized'] is False
        assert source['canonical_apply_authorized'] is False
        assert source['rebaseline_authorized'] is False
        assert source['scheduler_enabled'] is False

    assert stage24['write_capable_lane_authorized'] is False
    assert stage24['db_writes_authorized'] is False
    assert baseline['write_capable_lane_authorized'] is False
    assert baseline['db_writes_authorized'] is False
    assert 'Stage 19 execution.' in _read(STAGE24_ROADMAP_PATH)
    assert 'DB writes.' in _read(STAGE24_ROADMAP_PATH)
    assert 'Canonical apply.' in _read(STAGE24_ROADMAP_PATH)
    assert 'Rebaseline.' in _read(STAGE24_ROADMAP_PATH)
    assert 'Scheduler, service, or timer activation.' in _read(STAGE24_ROADMAP_PATH)
    assert 'Stage 24 does not authorize canonical apply.' in roadmap
    assert 'Stage 24 does not authorize rebaseline.' in roadmap
    assert 'Stage 24 keeps scheduler, service, and timer activation disabled.' in roadmap
    assert 'Stage 19BB remains a completed bounded staging-only evidence dependency.' in roadmap
    assert 'treating bounded staging as full EDSM coverage' in roadmap


@pytest.mark.unit
def test_stage24_is_discoverable_from_stage23_closeout_and_index():
    stage23_roadmap = _squash(_read(STAGE23_ROADMAP_PATH))
    stage23e = _squash(_read(STAGE23E_PATH))
    readme = _squash(_read(README_PATH))

    assert 'Stage 24 - Read-only evidence adoption and governance roadmap' in stage23_roadmap
    assert 'docs/colonisation-redesign/stage-24-roadmap.md' in stage23_roadmap
    assert 'Any further work must begin under a new explicit control document' in stage23e
    assert 'stage-24-roadmap.md' in readme
    assert 'completed post-Stage-23 control baseline' in readme
    assert 'Completed Stage 24 control' in readme


@pytest.mark.unit
def test_stage24_first_executable_checkpoint_and_closeout_criteria_are_explicit():
    roadmap = _read(STAGE24_ROADMAP_PATH)

    assert FIRST_CHECKPOINT in roadmap
    assert 'Stage 24A is now recorded in' in roadmap
    assert 'Stage 24B is complete as the first narrow discoverability implementation slice.' in roadmap
    assert 'Stage 24C is complete as the narrow adjacent-surface consistency slice.' in roadmap
    assert 'Stage 24D is complete as the closeout checkpoint.' in roadmap
    assert 'Stage 24 is closed as the read-only evidence adoption and governance' in roadmap
    assert '## Proposed Checkpoint Plan' in roadmap
    assert 'Stage 24D - Closeout or next-control decision' in roadmap
    assert 'stage-24d-readonly-evidence-adoption-closeout.md' in roadmap
    assert '## Closeout Criteria' in roadmap
    assert 'no write-capable lane has been silently authorized' in roadmap
    assert 'new explicit post-Stage-24' in roadmap
