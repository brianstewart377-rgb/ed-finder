import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
STAGE21_ROADMAP_PATH = DOCS / 'stage-21-roadmap.md'
STAGE20_ROADMAP_PATH = DOCS / 'stage-20-roadmap.md'
STAGE21_BURNDOWN_PATH = DOCS / 'stage-21b-to-21f-stage17-stage18-burn-down.md'
STAGE21_CLOSEOUT_PATH = DOCS / 'stage-21-closeout.md'
README_PATH = DOCS / 'README.md'
STAGE17P_PATH = DOCS / 'stage-17p-current-state-forward-plan.md'
STAGE18A_PATH = DOCS / 'stage-18a-enrichment-operator-status.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'

PRIMARY_OBJECTIVE = (
    'Turn the completed Stage 20 cockpit into a trustworthy, operational, provenance-aware planning surface by closing the '
    'highest-value planner trust gaps, replacing fixture-only read paths where safe, and reconciling the roadmap into one '
    'explicit post-20 control document without reopening deferred Stage 19 production lanes.'
)
FIRST_CHECKPOINT = 'Stage 21A - Post-20 roadmap reconciliation and authority lock'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


def _squash(text: str) -> str:
    return re.sub(r'\s+', ' ', text)


@pytest.mark.unit
def test_stage21_authority_prepares_a_post20_control_baseline_without_reopening_stage19():
    authority = _json(AUTHORITY_PATH)
    stage20 = authority['stage20']
    stage21 = authority['stage21']
    baseline = authority['stage21_planning_baseline']
    burndown = authority['stage21_stage17_stage18_burndown']
    closeout = authority['stage21_closeout']

    assert stage20['status'] == 'completed'
    assert stage21['status'] == 'completed'
    assert stage21['planning_authorized'] is True
    assert stage21['implementation_started'] is True
    assert stage21['implementation_authorized'] is True
    assert stage21['primary_objective'] == PRIMARY_OBJECTIVE
    assert stage21['first_executable_checkpoint'] == FIRST_CHECKPOINT
    assert stage21['current_checkpoint'] == 'Stage 21 closeout'
    assert stage21['next_checkpoint'] == 'Stage 18J-P-filter - Strict station-type dry-run filter'
    assert stage21['roadmap'] == 'docs/colonisation-redesign/stage-21-roadmap.md'
    assert stage21['stage20_complete'] is True
    assert stage21['stage21a_roadmap_reconciliation_completed'] is True
    assert stage21['stage21b_planner_trust_audit_advanced'] is True
    assert stage21['stage21c_slot_reasoning_hardening_advanced'] is True
    assert stage21['stage21d_strategy_advisor_advanced'] is True
    assert stage21['stage21e_role_strategy_integration_advanced'] is True
    assert stage21['stage21f_readonly_operationalisation_advanced'] is True
    assert stage21['stage17r_current_baseline_satisfied'] is True
    assert stage21['stage17s_current_baseline_satisfied'] is True
    assert stage21['stage17t_current_baseline_satisfied'] is True
    assert stage21['stage17u_current_baseline_satisfied'] is True
    assert stage21['stage18b_to_18g_delivered_groundwork_reconciled'] is True
    assert stage21['stage18h_live_readonly_bridge_completed'] is True
    assert stage21['closeout_ready'] is True

    assert baseline['status'] == 'completed'
    assert baseline['checkpoint_type'] == 'planning_baseline'
    assert baseline['historical_snapshot'] is True
    assert baseline['roadmap'] == 'docs/colonisation-redesign/stage-21-roadmap.md'
    assert baseline['primary_objective'] == PRIMARY_OBJECTIVE
    assert baseline['stage17q_effectively_complete'] is True
    assert baseline['stage18a_effectively_complete'] is True
    assert baseline['stage17r_planned_in_stage21'] is True
    assert baseline['stage17s_planned_in_stage21'] is True
    assert baseline['stage17t_planned_in_stage21'] is True
    assert baseline['stage17u_planned_in_stage21'] is True
    assert baseline['stage17r_current_baseline_satisfied'] is True
    assert baseline['stage17s_current_baseline_satisfied'] is True
    assert baseline['stage17t_current_baseline_satisfied'] is True
    assert baseline['stage17u_current_baseline_satisfied'] is True
    assert baseline['stage18b_to_18g_delivered_groundwork_reconciled'] is True
    assert baseline['stage18h_live_readonly_bridge_completed'] is True

    assert burndown['status'] == 'recorded'
    assert burndown['document'] == 'docs/colonisation-redesign/stage-21b-to-21f-stage17-stage18-burn-down.md'
    assert burndown['stage17q_complete'] is True
    assert burndown['stage17r_current_baseline_satisfied'] is True
    assert burndown['stage17s_current_baseline_satisfied'] is True
    assert burndown['stage17t_current_baseline_satisfied'] is True
    assert burndown['stage17u_current_baseline_satisfied'] is True
    assert burndown['stage18a_complete'] is True
    assert burndown['stage18b_to_18g_delivered_groundwork_reconciled'] is True

    assert closeout['status'] == 'completed'
    assert closeout['document'] == 'docs/colonisation-redesign/stage-21-closeout.md'
    assert closeout['validation_restored'] is True
    assert closeout['python_static_tests_passed'] is True
    assert closeout['focused_frontend_tests_passed'] is True
    assert closeout['frontend_typecheck_passed'] is True
    assert closeout['git_diff_check_passed'] is True
    assert closeout['post_merge_validation_rerun_completed'] is True
    assert closeout['stage18h_live_readonly_bridge_completed'] is True


@pytest.mark.unit
def test_stage21_boundaries_keep_deferred_stage19_production_paths_false():
    authority = _json(AUTHORITY_PATH)
    stage21 = authority['stage21']
    baseline = authority['stage21_planning_baseline']

    for source in (stage21, baseline):
        assert source['stage19_remains_paused'] is True
        assert source['stage19_production_activation_complete'] is False
        assert source['next_stage19_write_lane_authorized'] is False
        assert source['canonical_apply_complete'] is False
        assert source['canonical_apply_authorized'] is False
        assert source['rebaseline_complete'] is False
        assert source['rebaseline_authorized'] is False
        assert source['scheduler_enabled'] is False
        assert source['scheduler_service_authorized'] is False

    assert stage21['db_writes_authorized'] is False
    assert stage21['stage19_operator_commands_authorized'] is False
    assert stage21['production_like_db_execution_authorized'] is False
    assert baseline['stage21_implementation_started_at_baseline'] is False
    assert baseline['stage21_db_writes_authorized'] is False
    assert baseline['db_commands_run'] is False
    assert baseline['stage19_operator_commands_run'] is False
    assert baseline['source_acquisition_run'] is False
    assert baseline['staging_loader_run'] is False
    assert baseline['db_mutation_performed'] is False


@pytest.mark.unit
def test_stage21_roadmap_reconciles_stage20_stage17p_and_the_post20_queue():
    authority = _json(AUTHORITY_PATH)
    baseline = authority['stage21_planning_baseline']
    roadmap = _squash(_read(STAGE21_ROADMAP_PATH))
    burndown = _squash(_read(STAGE21_BURNDOWN_PATH))
    closeout = _squash(_read(STAGE21_CLOSEOUT_PATH))
    readme = _squash(_read(README_PATH))
    stage17p = _squash(_read(STAGE17P_PATH))

    assert STAGE21_ROADMAP_PATH.exists()
    assert STAGE21_BURNDOWN_PATH.exists()
    assert STAGE21_CLOSEOUT_PATH.exists()
    assert STAGE20_ROADMAP_PATH.exists()
    assert STAGE17P_PATH.exists()
    assert STAGE18A_PATH.exists()
    assert baseline['checkpoint_count'] == 6
    assert len(baseline['checkpoints']) == 6
    assert baseline['checkpoints'][0] == FIRST_CHECKPOINT
    assert baseline['first_executable_checkpoint'] == FIRST_CHECKPOINT
    assert roadmap.count('Stage 21 has exactly one primary objective') == 1
    assert 'Stage 17Q is effectively complete' in roadmap
    assert 'Stage 18A is effectively complete' in roadmap
    assert 'Stage 17R, 17S, 17T, and 17U were the clearest planner-facing unfinished work' in roadmap
    assert 'Stage 18B-18G are substantially represented already' in roadmap
    assert 'Stage 21B - Planner trust audit' in roadmap
    assert 'Stage 21C - Existing infrastructure and slot reasoning hardening' in roadmap
    assert 'Stage 21D - Suggested Builds strategy advisor pass' in roadmap
    assert 'Stage 21E - Role and strategy integration cleanup' in roadmap
    assert 'Stage 21F - Read-only cockpit operationalisation and closeout' in roadmap
    assert 'advanced Stage 18H by wiring a live report-only warehouse bridge' in roadmap
    assert 'Stage 17R/17S/17T/17U are no longer untouched backlog' in burndown
    assert 'Stage 18B-18G should be treated as delivered warehouse/operator groundwork' in burndown
    assert 'Stage 21 is complete.' in closeout
    assert 'stage18h_live_readonly_bridge_completed' not in closeout
    assert 'Stage 18H.1 through 18H.4 are complete' in closeout
    assert 'typed read-only warehouse evidence contract' in closeout
    assert 'Stage 18I is complete as a documentation-only canonical write design review' in closeout
    assert 'Stage 18I.5 is complete as a documentation-only warehouse database boundary' in closeout
    assert 'Stage 18J is complete as a bounded station-type-only canonical pilot' in closeout
    assert 'Stage 18T is complete as the canonical safety test environment' in closeout
    assert 'Stage 18J-Q is complete as an artifact-readiness review' in closeout
    assert 'Stage 18J-Q2 through Stage 18J-Q9 are complete' in closeout

    assert 'stage-21-roadmap.md' in readme
    assert 'stage-21b-to-21f-stage17-stage18-burn-down.md' in readme
    assert 'stage-21-closeout.md' in readme
    assert 'active post-20 roadmap and current control baseline' in readme
    assert 'completed Stage 20 roadmap' in readme
    assert 'its old "next sequence" list is now historical' in stage17p
    assert 'Stage 17R/17S/17T/17U have been advanced substantially' in stage17p


@pytest.mark.unit
def test_stage21_local_ci_parity_registration_is_static_and_safe():
    parity = _read(LOCAL_CI_PARITY)

    assert 'tests/test_stage21_planning_baseline.py' in parity
    assert '--commit' not in parity
    assert 'psql' not in parity
