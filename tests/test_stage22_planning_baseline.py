import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
STAGE22_ROADMAP_PATH = DOCS / 'stage-22-roadmap.md'
STAGE21_ROADMAP_PATH = DOCS / 'stage-21-roadmap.md'
STAGE21_CLOSEOUT_PATH = DOCS / 'stage-21-closeout.md'
README_PATH = DOCS / 'README.md'
STAGE17P_PATH = DOCS / 'stage-17p-current-state-forward-plan.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'

PRIMARY_OBJECTIVE = (
    'Create the first post-Stage-18/20/21 control baseline that consolidates the completed historical state, '
    'prioritises the next high-value read-only planner and operator-review improvements, and defines an explicit '
    'separate decision gate for any future Stage 19 production reactivation without silently reopening completed '
    'write lanes.'
)
FIRST_CHECKPOINT = 'Stage 22A - Post-18/20/21 control reset and authority lock'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


def _squash(text: str) -> str:
    return re.sub(r'\s+', ' ', text)


@pytest.mark.unit
def test_stage22_authority_prepares_the_post182021_control_baseline():
    authority = _json(AUTHORITY_PATH)
    stage21 = authority['stage21']
    stage22 = authority['stage22']
    baseline = authority['stage22_planning_baseline']

    assert stage21['status'] == 'completed'
    assert stage21['next_checkpoint'] == FIRST_CHECKPOINT

    assert stage22['status'] == 'completed'
    assert stage22['planning_authorized'] is True
    assert stage22['implementation_started'] is True
    assert stage22['implementation_authorized'] is True
    assert stage22['primary_objective'] == PRIMARY_OBJECTIVE
    assert stage22['first_executable_checkpoint'] == FIRST_CHECKPOINT
    assert stage22['current_checkpoint'] == 'Stage 22E - Deferred Stage 19 decision gate and closeout'
    assert stage22['next_checkpoint'] is None
    assert stage22['roadmap'] == 'docs/ROADMAP.md'
    assert stage22['stage18_complete_for_reviewed_scope'] is True
    assert stage22['stage20_complete'] is True
    assert stage22['stage21_complete'] is True
    assert stage22['stage22a_control_reset_completed'] is True
    assert stage22['stage22b_planner_evidence_simplification_completed'] is True
    assert stage22['stage22c_operator_review_surfaces_completed'] is True
    assert stage22['stage22d_export_governance_consolidation_completed'] is True
    assert stage22['stage22e_reactivation_gate_completed'] is True
    assert stage22['closeout_ready'] is True
    assert stage22['stage22_closed'] is True

    assert baseline['status'] == 'prepared'
    assert baseline['checkpoint_type'] == 'planning_baseline'
    assert baseline['historical_snapshot'] is True
    assert baseline['docs_static_only'] is True
    assert baseline['roadmap'] == 'docs/ROADMAP.md'
    assert baseline['primary_objective'] == PRIMARY_OBJECTIVE
    assert baseline['checkpoint_count'] == 5
    assert len(baseline['checkpoints']) == 5
    assert baseline['checkpoints'][0] == FIRST_CHECKPOINT
    assert baseline['first_executable_checkpoint'] == FIRST_CHECKPOINT
    assert baseline['stage22_implementation_started'] is True


@pytest.mark.unit
def test_stage22_boundaries_keep_stage19_deferred_and_write_paths_false():
    authority = _json(AUTHORITY_PATH)
    stage22 = authority['stage22']
    baseline = authority['stage22_planning_baseline']

    for source in (stage22, baseline):
        assert source['stage19_remains_paused'] is True
        assert source['stage19_production_activation_complete'] is False
        assert source['stage19_production_activation_deferred'] is True
        assert source['next_stage19_write_lane_authorized'] is False
        assert source['canonical_apply_complete'] is False
        assert source['canonical_apply_authorized'] is False
        assert source['rebaseline_complete'] is False
        assert source['rebaseline_authorized'] is False
        assert source['scheduler_enabled'] is False
        assert source['scheduler_service_authorized'] is False

    assert stage22['db_writes_authorized'] is False
    assert stage22['stage19_operator_commands_authorized'] is False
    assert stage22['production_like_db_execution_authorized'] is False
    assert baseline['stage22_db_writes_authorized'] is False
    assert baseline['db_commands_run'] is False
    assert baseline['stage19_operator_commands_run'] is False
    assert baseline['source_acquisition_run'] is False
    assert baseline['staging_loader_run'] is False
    assert baseline['db_mutation_performed'] is False
    assert baseline['runtime_source_files_are_authority'] is False
    assert baseline['operator_artifact_json_committed_as_authority'] is False


@pytest.mark.unit
def test_stage22_roadmap_readme_and_stage17p_make_the_new_control_order_explicit():
    authority = _json(AUTHORITY_PATH)
    baseline = authority['stage22_planning_baseline']
    roadmap = _squash(_read(STAGE22_ROADMAP_PATH))
    stage21_closeout = _squash(_read(STAGE21_CLOSEOUT_PATH))
    readme = _squash(_read(README_PATH))
    stage17p = _squash(_read(STAGE17P_PATH))

    assert STAGE22_ROADMAP_PATH.exists()
    assert STAGE21_ROADMAP_PATH.exists()
    assert STAGE21_CLOSEOUT_PATH.exists()
    assert baseline['workstreams_ranked'] == [
        'post182021_control_reset_authority_lock',
        'current_state_planner_evidence_simplification',
        'operator_artifact_review_audit_surfaces',
        'export_documentation_governance_consolidation',
        'deferred_stage19_reactivation_decision_gate',
        'historical_roadmap_compression_index_hygiene',
    ]
    assert roadmap.count('Stage 22 has exactly one primary objective') == 1
    assert 'Stage 18 is complete for the reviewed warehouse/operator and bounded station-type write chain.' in roadmap
    assert 'Stage 20 is complete.' in roadmap
    assert 'Stage 21 is complete.' in roadmap
    assert 'Stage 22A - Post-18/20/21 control reset and authority lock' in roadmap
    assert 'Stage 22B - Current-state planner/evidence simplification' in roadmap
    assert 'Stage 22C - Operator artifact review and audit surfaces' in roadmap
    assert 'Stage 22D - Export and documentation governance consolidation' in roadmap
    assert 'Stage 22E - Deferred Stage 19 decision gate and closeout' in roadmap
    assert 'Stage 22A is complete' in roadmap
    assert 'Stage 22B is complete' in roadmap
    assert 'Stage 22C is complete' in roadmap
    assert 'Stage 22D is complete' in roadmap
    assert 'Stage 22E is complete' in roadmap
    assert 'This order keeps user clarity and operator review quality ahead of any future production-lane decision.' in roadmap

    assert 'stage-22-roadmap.md' in readme
    assert 'stage-22b-current-state-planner-evidence-hardening.md' in readme
    assert 'stage-22c-operator-artifact-review-and-audit-surfaces.md' in readme
    assert 'stage-22d-export-and-documentation-governance-consolidation.md' in readme
    assert 'stage-22e-deferred-stage19-decision-gate-and-closeout.md' in readme
    assert 'completed post-18/20/21 roadmap and prior control baseline' in readme
    assert 'completed post-20 roadmap and trust/operationalisation plan' in readme
    assert 'active post-22 roadmap and current control baseline' in readme
    assert 'stage-23-roadmap.md' in readme

    assert 'docs/colonisation-redesign/stage-23-roadmap.md' in stage17p
    assert 'docs/colonisation-redesign/stage-22-roadmap.md' in stage17p
    assert 'The next meaningful work should begin from Stage 22A' in stage21_closeout


@pytest.mark.unit
def test_stage22_local_ci_parity_registration_is_static_and_safe():
    parity = _read(LOCAL_CI_PARITY)

    assert 'tests/test_stage22_planning_baseline.py' in parity
    assert '--commit' not in parity
    assert 'psql' not in parity
