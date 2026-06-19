import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
README_PATH = DOCS / 'README.md'
STAGE17P_PATH = DOCS / 'stage-17p-current-state-forward-plan.md'
STAGE23_ROADMAP_PATH = DOCS / 'stage-23-roadmap.md'
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
    stage23b = authority['stage23b']

    assert stage22['status'] == 'completed'
    assert stage23['status'] == 'safe_per_system_warehouse_join_expansion_completed'
    assert stage23['planning_authorized'] is True
    assert stage23['implementation_started'] is True
    assert stage23['implementation_authorized'] is True
    assert stage23['first_executable_checkpoint'] == 'Stage 23A - First bounded live per-system evidence provider'
    assert stage23['current_checkpoint'] == 'Stage 23B - Safe per-system warehouse join expansion'
    assert stage23['next_checkpoint'] == 'Stage 23C - Evidence envelope governance and source semantics'
    assert stage23['roadmap'] == 'docs/colonisation-redesign/stage-23-roadmap.md'
    assert stage23['stage22_complete'] is True
    assert stage23['stage23a_live_provider_completed'] is True
    assert stage23['stage19bb_execution_dependency_satisfied'] is True
    assert stage23['stage23b_safe_warehouse_join_expansion_ready'] is True
    assert stage23['stage23b_safe_warehouse_join_expansion_started'] is True
    assert stage23['stage23b_safe_warehouse_join_expansion_completed'] is True
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
    stage23b = ' '.join(_read(STAGE23B_PATH).split())
    stage23a = ' '.join(_read(STAGE23A_PATH).split())
    readme = _read(README_PATH)
    stage17p = _read(STAGE17P_PATH)
    parity = _read(LOCAL_CI_PARITY)

    assert STAGE23_ROADMAP_PATH.exists()
    assert STAGE23B_PATH.exists()
    assert STAGE23A_PATH.exists()

    assert 'Stage 23A is complete' in roadmap
    assert 'Stage 23B is complete' in roadmap
    assert 'The dedicated `warehouse_planner_evidence/v1` endpoint remains the preferred planner evidence path.' in roadmap
    assert 'Unsupported or insufficiently evidenced systems still remain' in roadmap
    assert 'Stage 23C - Evidence envelope governance and source semantics' in roadmap
    assert 'Read-only only.' in roadmap

    assert 'Stage 23B is complete.' in stage23b
    assert 'bounded staging is review context only' in stage23b
    assert 'not canonical truth' in stage23b
    assert 'not evaluated' in stage23b
    assert 'The endpoint is therefore treated as a broader report-only planner evidence envelope' in stage23a
    assert 'at least one real selected system can return non-fixture evidence in normal runtime' in stage23a

    assert 'stage-23-roadmap.md' in readme
    assert 'stage-23b-readonly-per-system-warehouse-join.md' in readme
    assert 'stage-23a-first-live-per-system-evidence-provider.md' in readme
    assert 'active post-22 roadmap and current control baseline' in readme
    assert 'docs/colonisation-redesign/stage-23-roadmap.md' in stage17p
    assert 'docs/colonisation-redesign/stage-23a-first-live-per-system-evidence-provider.md' in stage17p
    assert 'tests/test_stage23_planning_baseline.py' in parity
