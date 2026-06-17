import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
STAGE20_ROADMAP_PATH = DOCS / 'stage-20-roadmap.md'
STAGE20A_CONTRACT_PATH = DOCS / 'stage-20a-provenance-cockpit-implementation-contract.md'
STAGE20B_STATUS_PATH = DOCS / 'stage-20b-readonly-evidence-status-surfaces.md'
STAGE20C_MAP_PATH = DOCS / 'stage-20c-map-planning-surface-foundation.md'
STAGE20D_SEQUENCE_PATH = DOCS / 'stage-20d-planner-sequence-cp-curve-cockpit.md'
STAGE20E_EXPORT_PATH = DOCS / 'stage-20e-export-operator-pack-closeout-readiness.md'
STAGE19_ROADMAP_PATH = DOCS / 'stage-19-data-warehouse-utopia-roadmap.md'
README_PATH = DOCS / 'README.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'

PRIMARY_OBJECTIVE = (
    'Build a provenance-backed colonisation planning cockpit that lets users and operators understand source evidence, '
    'warehouse freshness, map context, and build-sequence tradeoffs through typed, reviewable, read-only contracts before '
    'any production activation or canonical promotion is considered.'
)
FIRST_CHECKPOINT = 'Stage 20A - Provenance cockpit implementation contract'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


def _squash(text: str) -> str:
    return re.sub(r'\s+', ' ', text)


@pytest.mark.unit
def test_stage20_authority_preserves_planning_baseline_after_later_stage20_progress():
    authority = _json(AUTHORITY_PATH)
    stage20 = authority['stage20']
    baseline = authority['stage20_planning_baseline']
    contract = authority['stage20a_implementation_contract']

    assert authority['stage19']['status'] == 'paused'
    assert stage20['status'] == 'completed'
    assert stage20['planning_authorized'] is True
    assert stage20['implementation_started'] is True
    assert stage20['implementation_authorized'] is True
    assert stage20['primary_objective'] == PRIMARY_OBJECTIVE
    assert stage20['first_executable_checkpoint'] == FIRST_CHECKPOINT
    assert stage20['current_checkpoint'] == 'Stage 20E - Export/operator pack and closeout readiness'
    assert stage20['next_checkpoint'] is None
    assert stage20['primary_contract_set'] == 'System provenance cockpit summary contract'
    assert stage20['contract_schema_version'] == 'stage20a_provenance_cockpit/v1'
    assert stage20['stage20a_contract_completed'] is True
    assert stage20['stage20c_map_foundation_completed'] is True
    assert stage20['stage20d_sequence_cp_cockpit_completed'] is True
    assert stage20['stage20e_export_closeout_completed'] is True
    assert stage20['closeout_ready'] is True
    assert stage20['stage20b_read_only_status_surfaces_completed'] is True

    assert baseline['status'] == 'prepared'
    assert baseline['checkpoint_type'] == 'planning_baseline'
    assert baseline['docs_static_only'] is True
    assert baseline['roadmap'] == 'docs/colonisation-redesign/stage-20-roadmap.md'
    assert baseline['stage20_implementation_started'] is False
    assert baseline['stage19_test_environment_safety_programme_complete'] is True
    assert baseline['stage19_remains_paused'] is True
    assert baseline['stage19_production_activation_complete'] is False
    assert baseline['stage19_production_activation_deferred'] is True

    assert contract['status'] == 'completed'
    assert contract['checkpoint_type'] == 'implementation_contract'
    assert contract['docs_static_only'] is True
    assert contract['contract_document'] == 'docs/colonisation-redesign/stage-20a-provenance-cockpit-implementation-contract.md'
    assert contract['primary_contract_set'] == 'System provenance cockpit summary contract'
    assert contract['contract_schema_version'] == 'stage20a_provenance_cockpit/v1'
    assert contract['stage20_implementation_started'] is False
    assert contract['stage20_feature_delivery_started'] is False
    assert contract['next_checkpoint'] == 'Stage 20B - Read-only evidence and status surfaces'


@pytest.mark.unit
def test_stage20_boundaries_keep_deferred_production_paths_false():
    authority = _json(AUTHORITY_PATH)
    stage20 = authority['stage20']
    baseline = authority['stage20_planning_baseline']

    for source in (stage20, baseline):
        assert source['canonical_apply_complete'] is False
        assert source['canonical_apply_authorized'] is False
        assert source['rebaseline_complete'] is False
        assert source['rebaseline_authorized'] is False
        assert source['scheduler_enabled'] is False
        assert source['scheduler_service_authorized'] is False

    assert stage20['db_writes_authorized'] is False
    assert stage20['stage19_operator_commands_authorized'] is False
    assert stage20['production_like_db_execution_authorized'] is False
    assert baseline['stage20_db_writes_authorized'] is False
    assert baseline['db_commands_run'] is False
    assert baseline['stage19_operator_commands_run'] is False
    assert baseline['source_acquisition_run'] is False
    assert baseline['staging_loader_run'] is False
    assert baseline['db_mutation_performed'] is False


@pytest.mark.unit
def test_stage20_roadmap_defines_one_objective_bundled_checkpoints_and_first_executable_checkpoint():
    authority = _json(AUTHORITY_PATH)
    baseline = authority['stage20_planning_baseline']
    roadmap = _squash(_read(STAGE20_ROADMAP_PATH))

    assert STAGE20_ROADMAP_PATH.exists()
    assert STAGE20A_CONTRACT_PATH.exists()
    assert STAGE20B_STATUS_PATH.exists()
    assert STAGE20C_MAP_PATH.exists()
    assert STAGE20D_SEQUENCE_PATH.exists()
    assert STAGE20E_EXPORT_PATH.exists()
    assert baseline['primary_objective'] == PRIMARY_OBJECTIVE
    assert roadmap.count('Stage 20 has exactly one primary objective') == 1
    assert 'Build a provenance-backed colonisation planning cockpit' in roadmap
    assert 'source evidence, warehouse freshness, map context' in roadmap
    assert 'production activation or canonical promotion' in roadmap

    assert baseline['checkpoint_count'] == 5
    assert len(baseline['checkpoints']) == 5
    assert 3 <= baseline['checkpoint_count'] <= 6
    assert baseline['checkpoints'][0] == FIRST_CHECKPOINT
    assert baseline['first_executable_checkpoint'] == FIRST_CHECKPOINT
    assert 'Stage 20A is not another empty decision checkpoint.' in roadmap
    assert 'stage-20a-provenance-cockpit-implementation-contract.md' in roadmap
    assert 'stage-20b-readonly-evidence-status-surfaces.md' in roadmap
    assert 'stage-20c-map-planning-surface-foundation.md' in roadmap
    assert 'stage-20d-planner-sequence-cp-curve-cockpit.md' in roadmap
    assert 'stage-20e-export-operator-pack-closeout-readiness.md' in roadmap
    assert 'tests/fixtures/stage20a/' in roadmap


@pytest.mark.unit
def test_stage20_workstreams_and_scope_are_explicit():
    authority = _json(AUTHORITY_PATH)
    baseline = authority['stage20_planning_baseline']
    roadmap = _squash(_read(STAGE20_ROADMAP_PATH))

    assert baseline['workstreams_ranked'] == [
        'api_ui_contract_runtime_validation',
        'read_only_source_run_warehouse_status_integration',
        'map_architecture_performance_foundation',
        'planner_data_model_build_sequence_ux',
        'export_operator_pack_builder',
        'data_freshness_source_scheduling_preparation',
        'canonical_promotion_preparation',
        'search_discovery_retuning',
    ]

    for fragment in (
        '## In Scope',
        '## Out Of Scope Unless Separately Approved',
        'Stage 19 canonical apply.',
        'Stage 19 rebaseline.',
        'Stage 19 production activation.',
        'Production scheduler, timer, or service enablement.',
        'Unbounded source ingestion.',
        'Silent planner mutation from imported, observed, projected, inferred, or warehouse evidence.',
        'Automatic Simulation Preview execution.',
        'Automatic Suggested Build generation, loading, or ranking changes.',
    ):
        assert fragment in roadmap


@pytest.mark.unit
def test_stage20_is_discoverable_from_stage19_roadmap_and_index():
    stage19 = _squash(_read(STAGE19_ROADMAP_PATH))
    readme = _squash(_read(README_PATH))

    assert '### Stage 20 planning kickoff' in _read(STAGE19_ROADMAP_PATH)
    assert 'stage-21-roadmap.md' in readme
    assert 'docs/colonisation-redesign/stage-20-roadmap.md' in stage19
    assert 'The first executable checkpoint is Stage 20A, the provenance cockpit implementation contract.' in stage19
    assert 'stage-20-roadmap.md' in readme
    assert 'stage-20a-provenance-cockpit-implementation-contract.md' in readme
    assert 'stage-20b-readonly-evidence-status-surfaces.md' in readme
    assert 'stage-20c-map-planning-surface-foundation.md' in readme
    assert 'stage-20d-planner-sequence-cp-curve-cockpit.md' in readme
    assert 'stage-20e-export-operator-pack-closeout-readiness.md' in readme
    assert 'completed Stage 20 roadmap' in readme
    assert 'Stage 19 deferred-production boundaries' in readme


@pytest.mark.unit
def test_stage20_planning_does_not_commit_runtime_or_operator_artifact_authority():
    authority = _json(AUTHORITY_PATH)
    baseline = authority['stage20_planning_baseline']
    roadmap = _squash(_read(STAGE20_ROADMAP_PATH))

    assert baseline['runtime_source_files_are_authority'] is False
    assert baseline['operator_artifact_json_committed_as_authority'] is False
    assert 'Export/operator packs' in roadmap
    assert 'avoid secrets/private runtime paths' in roadmap
    assert 'redacted paths, fixture data, and tests for secret/path handling' in roadmap


@pytest.mark.unit
def test_stage20_local_ci_parity_registration_is_static_only():
    parity = _read(LOCAL_CI_PARITY)

    assert 'tests/test_stage20_planning_baseline.py' in parity
    assert 'tests/test_stage21_planning_baseline.py' in parity
    assert 'tests/test_stage20a_implementation_contract.py' in parity
    assert 'tests/test_stage20b_readonly_status_surfaces.py' in parity
    assert 'tests/test_stage20c_map_foundation.py' in parity
    assert 'tests/test_stage20d_sequence_cp_cockpit.py' in parity
    assert 'tests/test_stage20e_export_closeout.py' in parity
    assert 'scripts/operator/stage19' not in parity
    assert '--commit' not in parity
    assert 'psql' not in parity
