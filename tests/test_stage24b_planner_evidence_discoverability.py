import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
STAGE24_PATH = DOCS / 'stage-24-roadmap.md'
STAGE24B_PATH = DOCS / 'stage-24b-planner-evidence-discoverability.md'
README_PATH = DOCS / 'README.md'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


def _squash(text: str) -> str:
    return re.sub(r'\s+', ' ', text)


@pytest.mark.unit
def test_stage24b_authority_records_a_narrow_in_scope_discoverability_slice():
    authority = _json(AUTHORITY_PATH)
    stage24 = authority['stage24']
    stage24a = authority['stage24a']
    stage24b = authority['stage24b']

    assert stage24['status'] == 'in_progress'
    assert stage24['implementation_started'] is True
    assert stage24['implementation_authorized'] is True
    assert stage24['current_checkpoint'] == 'Stage 24B - Planner evidence discoverability surfaces'
    assert stage24['next_checkpoint'] == 'Stage 24C - Cross-surface evidence consistency'
    assert stage24['docs_static_only'] is False
    assert stage24['stage24a_contract_completed'] is True
    assert stage24['stage24b_implementation_started'] is True
    assert stage24['stage24b_implementation_completed'] is True
    assert stage24['stage24c_implementation_started'] is False

    assert stage24a['status'] == 'completed'
    assert stage24a['contract_only'] is True
    assert stage24a['stage24b_implementation_started'] is False

    assert stage24b['status'] == 'completed'
    assert stage24b['checkpoint_type'] == 'planner_evidence_discoverability_surfaces'
    assert stage24b['document'] == 'docs/colonisation-redesign/stage-24b-planner-evidence-discoverability.md'
    assert stage24b['in_scope_surfaces_only'] is True
    assert stage24b['candidate_stage24c_surfaces_touched'] is False
    assert stage24b['out_of_scope_surfaces_touched'] is False
    assert stage24b['primary_planner_workspace_surface_updated'] is True
    assert stage24b['planner_evidence_card_updated'] is True
    assert stage24b['bridge_mapping_updated'] is False
    assert stage24b['type_contract_updated'] is False
    assert stage24b['dedicated_endpoint_preferred'] is True
    assert stage24b['provenance_fallback_only_on_endpoint_read_failure'] is True
    assert stage24b['available_state_rendered'] is True
    assert stage24b['unavailable_state_rendered'] is True
    assert stage24b['not_evaluated_state_rendered'] is True
    assert stage24b['unknown_state_rendered'] is True
    assert stage24b['bounded_staging_report_only_preserved'] is True
    assert stage24b['bounded_staging_never_canonical_truth'] is True
    assert stage24b['bounded_staging_never_implies_full_edsm_coverage'] is True
    assert stage24b['stage23_remains_closed'] is True
    assert stage24b['stage19_execution_authorized'] is False
    assert stage24b['write_capable_lane_authorized'] is False
    assert stage24b['canonical_apply_authorized'] is False
    assert stage24b['rebaseline_authorized'] is False
    assert stage24b['scheduler_enabled'] is False
    assert stage24b['db_writes_authorized'] is False
    assert stage24b['stage24c_implementation_started'] is False
    assert stage24b['source_files_committed'] is False
    assert stage24b['runtime_artifacts_committed'] is False


@pytest.mark.unit
def test_stage24b_document_defines_scope_boundaries_and_stable_wording():
    text = _read(STAGE24B_PATH)
    squashed = _squash(text)

    assert STAGE24B_PATH.exists()
    assert 'Stage 24B is complete.' in text
    assert '## Scope' in text
    assert 'ColonyPlannerWorkspace.tsx' in text
    assert 'WarehouseEvidenceCard.tsx' in text
    assert 'warehouseEvidenceBridge.ts' in text
    assert '## Delivered discoverability changes' in text
    assert '## Preserved Stage 24A contract boundary' in text
    assert 'Available. Selected-system evidence is present as read-only review context only.' in text
    assert 'Unavailable. No approved bounded staging evidence is linked to this selected system.' in text
    assert 'Not evaluated in this runtime. The staging boundary was not safely queryable for this request.' in text
    assert 'Unknown. Selected-system evidence has not been established.' in text
    assert 'Bounded staging evidence' in text
    assert 'Report-only review context' in text
    assert 'Not canonical truth' in text
    assert 'Not full EDSM coverage' in text
    assert 'Limited to approved Stage 19BB row-cap evidence' in text
    assert 'system-detail review surfaces' in squashed
    assert 'Stage 24B does not implement Stage 24C.' in text


@pytest.mark.unit
def test_stage24b_boundaries_keep_stage23_closed_and_write_lanes_unauthorized():
    text = _read(STAGE24B_PATH)

    assert 'Stage 23 remains closed.' in text
    assert 'Stage 19 remains separately gated.' in text
    assert 'rerun Stage 19BB;' in text
    assert 'create any new Stage 19 execution lane;' in text
    assert 'perform DB writes;' in text
    assert 'perform canonical apply;' in text
    assert 'perform rebaseline;' in text
    assert 'enable scheduler, service, or timer activation;' in text
    assert 'commit source files;' in text
    assert 'commit runtime artifacts;' in text


@pytest.mark.unit
def test_stage24b_is_discoverable_from_roadmap_and_readme():
    roadmap = _read(STAGE24_PATH)
    readme = _read(README_PATH)

    assert 'Stage 24B is complete as the first narrow discoverability implementation slice.' in roadmap
    assert 'docs/colonisation-redesign/stage-24b-planner-evidence-discoverability.md' in roadmap
    assert 'Stage 24C is the next implementation checkpoint.' in roadmap
    assert 'stage-24b-planner-evidence-discoverability.md' in readme
    assert 'completed Stage 24B slice' in readme
    assert 'Completed Stage 24B implementation record' in readme
