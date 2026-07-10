import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
STAGE24_PATH = DOCS / 'stage-24-roadmap.md'
STAGE24C_PATH = DOCS / 'stage-24c-cross-surface-evidence-consistency.md'
README_PATH = DOCS / 'README.md'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


@pytest.mark.unit
def test_stage24c_authority_records_one_narrow_adjacent_surface_slice():
    authority = _json(AUTHORITY_PATH)
    stage24 = authority['stage24']
    stage24b = authority['stage24b']
    stage24c = authority['stage24c']

    assert stage24['current_checkpoint'] == 'Stage 24D - Closeout'
    assert stage24['next_checkpoint'] is None
    assert stage24['stage24b_implementation_completed'] is True
    assert stage24['stage24c_implementation_started'] is True
    assert stage24['stage24c_implementation_completed'] is True
    assert stage24['stage24d_implementation_started'] is True
    assert stage24['stage24_closed'] is True

    assert stage24b['status'] == 'completed'
    assert stage24b['in_scope_surfaces_only'] is True

    assert stage24c['status'] == 'completed'
    assert stage24c['checkpoint_type'] == 'cross_surface_evidence_consistency'
    assert stage24c['document'] == 'docs/colonisation-redesign/stage-24c-cross-surface-evidence-consistency.md'
    assert stage24c['selected_surface'] == 'system_detail_evidence_mode_provenance_cockpit_panel'
    assert stage24c['supporting_surface'] == 'frontend/src/features/colony-planner/WarehouseEvidenceCard.tsx'
    assert stage24c['candidate_surfaces_considered'] == [
        'system_detail_review_surface',
        'simulation_export_readiness_surface',
        'adjacent_readonly_api_consumer',
    ]
    assert stage24c['dedicated_endpoint_preferred'] is True
    assert stage24c['provenance_fallback_only_on_endpoint_read_failure'] is True
    assert stage24c['available_state_consistent'] is True
    assert stage24c['unavailable_state_consistent'] is True
    assert stage24c['not_evaluated_state_consistent'] is True
    assert stage24c['unknown_state_consistent'] is True
    assert stage24c['canonical_vs_observed_distinct'] is True
    assert stage24c['canonical_vs_bounded_staging_distinct'] is True
    assert stage24c['bounded_staging_report_only_preserved'] is True
    assert stage24c['bounded_staging_never_canonical_truth'] is True
    assert stage24c['bounded_staging_never_implies_full_edsm_coverage'] is True
    assert stage24c['new_endpoint_added'] is False
    assert stage24c['backend_ingestion_added'] is False
    assert stage24c['stage23_remains_closed'] is True
    assert stage24c['stage19_execution_authorized'] is False
    assert stage24c['write_capable_lane_authorized'] is False
    assert stage24c['canonical_apply_authorized'] is False
    assert stage24c['rebaseline_authorized'] is False
    assert stage24c['scheduler_enabled'] is False
    assert stage24c['db_writes_authorized'] is False
    assert stage24c['stage24d_implementation_started'] is False
    assert stage24c['source_files_committed'] is False
    assert stage24c['runtime_artifacts_committed'] is False


@pytest.mark.unit
def test_stage24c_document_records_inventory_selection_and_boundaries():
    text = _read(STAGE24C_PATH)

    assert STAGE24C_PATH.exists()
    assert '## Candidate Surface Inventory' in text
    assert 'ProvenanceCockpitPanel' in text
    assert 'ExportReadinessWorkspaceView' in text
    assert 'Adjacent API consumers / export payload builders' in text
    assert '## Selected Surface' in text
    assert 'system-detail Evidence mode' in text
    assert '## Selection Rationale' in text
    assert '## Reused Evidence Semantics' in text
    assert '## Dedicated Endpoint And Fallback Rule' in text
    assert 'Provenance fallback does not overwrite explicit governed `unavailable`,' in text
    assert '`not_evaluated`, or `unknown` responses.' in text
    assert '## Safety Boundaries' in text
    assert 'Stage 24D is the next checkpoint:' in text


@pytest.mark.unit
def test_stage24c_is_discoverable_from_roadmap_and_readme():
    roadmap = _read(STAGE24_PATH)
    readme = _read(README_PATH)

    assert 'Stage 24C is complete as the narrow adjacent-surface consistency slice.' in roadmap
    assert 'docs/colonisation-redesign/stage-24c-cross-surface-evidence-consistency.md' in roadmap
    assert 'Stage 24D is complete as the closeout checkpoint.' in roadmap
    assert 'stage-24c-cross-surface-evidence-consistency.md' in readme
    assert 'completed Stage 24C slice' in readme
    assert 'Completed Stage 24C implementation record' in readme
