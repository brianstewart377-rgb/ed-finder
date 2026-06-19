import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
README_PATH = DOCS / 'README.md'
STAGE17P_PATH = DOCS / 'stage-17p-current-state-forward-plan.md'
STAGE23_ROADMAP_PATH = DOCS / 'stage-23-roadmap.md'
STAGE23D_PATH = DOCS / 'stage-23d-planner-evidence-ux-follow-through.md'
STAGE23C_PATH = DOCS / 'stage-23c-evidence-envelope-governance.md'
STAGE23B_PATH = DOCS / 'stage-23b-readonly-per-system-warehouse-join.md'
STAGE23A_PATH = DOCS / 'stage-23a-first-live-per-system-evidence-provider.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


@pytest.mark.unit
def test_stage23_authority_activates_the_next_post22_control_baseline():
    authority = _json(AUTHORITY_PATH)
    stage22 = authority['stage22']
    stage23 = authority['stage23']
    baseline = authority['stage23_planning_baseline']
    stage23d = authority['stage23d']
    stage23c = authority['stage23c']
    stage23b = authority['stage23b']

    assert stage22['status'] == 'completed'
    assert stage23['status'] == 'readonly_planner_evidence_ux_followthrough_completed'
    assert stage23['planning_authorized'] is True
    assert stage23['implementation_started'] is True
    assert stage23['implementation_authorized'] is True
    assert stage23['first_executable_checkpoint'] == 'Stage 23A - First bounded live per-system evidence provider'
    assert stage23['current_checkpoint'] == 'Stage 23D - Read-only planner evidence UX follow-through'
    assert stage23['next_checkpoint'] == 'Stage 23E - Closeout or next-control handoff'
    assert stage23['roadmap'] == 'docs/colonisation-redesign/stage-23-roadmap.md'
    assert stage23['stage22_complete'] is True
    assert stage23['stage23a_live_provider_completed'] is True
    assert stage23['stage19bb_execution_dependency_satisfied'] is True
    assert stage23['stage23b_safe_warehouse_join_expansion_ready'] is True
    assert stage23['stage23b_safe_warehouse_join_expansion_started'] is True
    assert stage23['stage23b_safe_warehouse_join_expansion_completed'] is True
    assert stage23['stage23c_evidence_envelope_governance_started'] is True
    assert stage23['stage23c_evidence_envelope_governance_completed'] is True
    assert stage23['stage23d_readonly_ux_followthrough_started'] is True
    assert stage23['stage23d_readonly_ux_followthrough_completed'] is True
    assert stage23['closeout_ready'] is False
    assert stage23['stage19_remains_paused'] is True
    assert stage23['db_writes_authorized'] is False

    assert stage23b['status'] == 'completed'
    assert stage23b['checkpoint_type'] == 'safe_per_system_warehouse_join_expansion'
    assert stage23b['document'] == 'docs/colonisation-redesign/stage-23b-readonly-per-system-warehouse-join.md'
    assert stage23b['stage19bb_closeout_dependency_satisfied'] is True
    assert stage23b['bounded_staging_provenance_exposed'] is True
    assert stage23b['bounded_staging_status_exposed'] is True
    assert stage23b['bounded_staging_report_only'] is True
    assert stage23b['bounded_staging_never_canonical_truth'] is True
    assert stage23b['bounded_staging_never_implies_full_edsm_coverage'] is True
    assert stage23b['selected_system_unavailable_state_supported'] is True
    assert stage23b['safe_query_path_only'] is True
    assert stage23b['private_runtime_artifacts_not_read'] is True
    assert stage23b['db_writes_performed'] is False
    assert stage23b['canonical_apply_authorized'] is False
    assert stage23b['rebaseline_authorized'] is False
    assert stage23b['scheduler_enabled'] is False

    assert stage23c['status'] == 'completed'
    assert stage23c['checkpoint_type'] == 'evidence_envelope_governance'
    assert stage23c['document'] == 'docs/colonisation-redesign/stage-23c-evidence-envelope-governance.md'
    assert stage23c['evidence_envelope_exposed'] is True
    assert stage23c['evidence_status_model_exposed'] is True
    assert stage23c['source_semantics_exposed'] is True
    assert stage23c['canonical_evidence_distinct_from_bounded_staging'] is True
    assert stage23c['observed_evidence_distinct_from_bounded_staging'] is True
    assert stage23c['bounded_staging_labels_preserved'] is True
    assert stage23c['selected_system_unavailable_state_supported'] is True
    assert stage23c['selected_system_not_evaluated_state_supported'] is True
    assert stage23c['stage19_execution_run'] is False
    assert stage23c['db_writes_performed'] is False
    assert stage23c['canonical_apply_authorized'] is False
    assert stage23c['rebaseline_authorized'] is False
    assert stage23c['scheduler_enabled'] is False

    assert stage23d['status'] == 'completed'
    assert stage23d['checkpoint_type'] == 'readonly_planner_evidence_ux_followthrough'
    assert stage23d['document'] == 'docs/colonisation-redesign/stage-23d-planner-evidence-ux-follow-through.md'
    assert stage23d['evidence_envelope_consumed_directly'] is True
    assert stage23d['source_semantics_rendered'] is True
    assert stage23d['bounded_staging_wording_explicit'] is True
    assert stage23d['unavailable_state_wording_explicit'] is True
    assert stage23d['not_evaluated_state_wording_explicit'] is True
    assert stage23d['unknown_state_wording_explicit'] is True
    assert stage23d['provenance_fallback_only_on_endpoint_read_failure'] is True
    assert stage23d['bounded_staging_never_canonical_truth'] is True
    assert stage23d['bounded_staging_never_implies_full_edsm_coverage'] is True
    assert stage23d['stage19_execution_run'] is False
    assert stage23d['db_writes_performed'] is False
    assert stage23d['canonical_apply_authorized'] is False
    assert stage23d['rebaseline_authorized'] is False
    assert stage23d['scheduler_enabled'] is False

    assert baseline['status'] == 'prepared'
    assert baseline['checkpoint_type'] == 'planning_baseline'
    assert baseline['historical_snapshot'] is True
    assert baseline['docs_static_only'] is True
    assert baseline['roadmap'] == 'docs/colonisation-redesign/stage-23-roadmap.md'
    assert baseline['first_executable_checkpoint'] == 'Stage 23A - First bounded live per-system evidence provider'
    assert baseline['stage22_complete'] is True
    assert baseline['stage23_implementation_started'] is True


@pytest.mark.unit
def test_stage23_docs_readme_and_stage17p_make_the_new_control_order_explicit():
    roadmap = ' '.join(_read(STAGE23_ROADMAP_PATH).split())
    stage23d = ' '.join(_read(STAGE23D_PATH).split())
    stage23c = ' '.join(_read(STAGE23C_PATH).split())
    stage23b = ' '.join(_read(STAGE23B_PATH).split())
    stage23a = ' '.join(_read(STAGE23A_PATH).split())
    readme = _read(README_PATH)
    stage17p = _read(STAGE17P_PATH)
    parity = _read(LOCAL_CI_PARITY)

    assert STAGE23_ROADMAP_PATH.exists()
    assert STAGE23D_PATH.exists()
    assert STAGE23C_PATH.exists()
    assert STAGE23B_PATH.exists()
    assert STAGE23A_PATH.exists()

    assert 'Stage 23A is complete' in roadmap
    assert 'Stage 23B is complete' in roadmap
    assert 'Stage 23C is complete' in roadmap
    assert 'Stage 23D is complete' in roadmap
    assert 'The dedicated `warehouse_planner_evidence/v1` endpoint remains the preferred planner evidence path.' in roadmap
    assert 'Unsupported or insufficiently evidenced systems still remain' in roadmap
    assert 'Stage 23E - Closeout or next-control handoff' in roadmap
    assert 'Read-only only.' in roadmap

    assert 'Stage 23D is complete.' in stage23d
    assert 'evidence status' in stage23d
    assert 'Bounded staging evidence' in stage23d
    assert 'Not evaluated in this runtime' in stage23d
    assert 'Stage 23C is complete.' in stage23c
    assert 'status' in stage23c
    assert 'source_classes' in stage23c
    assert 'canonical, observed-facts, bounded-staging, unavailable, and not-evaluated evidence are distinct' in stage23c
    assert 'Stage 23B is complete.' in stage23b
    assert 'bounded staging is review context only' in stage23b
    assert 'not canonical truth' in stage23b
    assert 'not evaluated' in stage23b
    assert 'The endpoint is therefore treated as a broader report-only planner evidence envelope' in stage23a
    assert 'at least one real selected system can return non-fixture evidence in normal runtime' in stage23a

    assert 'stage-23-roadmap.md' in readme
    assert 'stage-23d-planner-evidence-ux-follow-through.md' in readme
    assert 'stage-23c-evidence-envelope-governance.md' in readme
    assert 'stage-23b-readonly-per-system-warehouse-join.md' in readme
    assert 'stage-23a-first-live-per-system-evidence-provider.md' in readme
    assert 'active post-22 roadmap and current control baseline' in readme
    assert 'docs/colonisation-redesign/stage-23-roadmap.md' in stage17p
    assert 'docs/colonisation-redesign/stage-23a-first-live-per-system-evidence-provider.md' in stage17p
    assert 'tests/test_stage23_planning_baseline.py' in parity
