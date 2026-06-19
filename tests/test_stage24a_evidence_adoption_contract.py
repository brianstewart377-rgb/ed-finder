import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
STAGE24_ROADMAP_PATH = DOCS / 'stage-24-roadmap.md'
STAGE24A_PATH = DOCS / 'stage-24a-readonly-evidence-adoption-contract.md'
README_PATH = DOCS / 'README.md'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


def _squash(text: str) -> str:
    return re.sub(r'\s+', ' ', text)


@pytest.mark.unit
def test_stage24a_authority_records_a_completed_contract_only_checkpoint():
    authority = _json(AUTHORITY_PATH)
    stage23 = authority['stage23']
    stage24 = authority['stage24']
    stage24a = authority['stage24a']

    assert stage23['status'] == 'completed'
    assert stage23['stage23_closed'] is True

    assert stage24['current_checkpoint'] == 'Stage 24B - Planner evidence discoverability surfaces'
    assert stage24['next_checkpoint'] == 'Stage 24C - Cross-surface evidence consistency'
    assert stage24['stage24a_contract_completed'] is True
    assert stage24['stage24b_implementation_started'] is True
    assert stage24['stage24b_implementation_completed'] is True
    assert stage24['stage24c_implementation_started'] is False

    assert stage24a['status'] == 'completed'
    assert stage24a['checkpoint_type'] == 'implementation_contract'
    assert stage24a['document'] == 'docs/colonisation-redesign/stage-24a-readonly-evidence-adoption-contract.md'
    assert stage24a['contract_only'] is True
    assert stage24a['first_executable_checkpoint_confirmed'] is True
    assert stage24a['next_implementation_checkpoint'] == 'Stage 24B - Planner evidence discoverability surfaces'
    assert stage24a['surfaces_inventory_defined'] is True
    assert stage24a['ownership_map_defined'] is True
    assert stage24a['evidence_state_language_defined'] is True
    assert stage24a['source_semantics_contract_defined'] is True
    assert stage24a['comparison_rules_defined'] is True
    assert stage24a['fixture_test_plan_defined'] is True
    assert stage24a['stage23_remains_closed'] is True
    assert stage24a['stage19_execution_authorized'] is False
    assert stage24a['write_capable_lane_authorized'] is False
    assert stage24a['canonical_apply_authorized'] is False
    assert stage24a['rebaseline_authorized'] is False
    assert stage24a['scheduler_enabled'] is False
    assert stage24a['db_writes_authorized'] is False
    assert stage24a['stage24b_implementation_started'] is False
    assert stage24a['source_files_committed'] is False
    assert stage24a['runtime_artifacts_committed'] is False


@pytest.mark.unit
def test_stage24a_document_defines_one_contract_purpose_and_surface_classes():
    text = _read(STAGE24A_PATH)
    squashed = _squash(text)

    assert STAGE24A_PATH.exists()
    assert 'Stage 24A is complete as a contract-only checkpoint.' in text
    assert 'Stage 24B implementation is not performed here.' in text
    assert '## Purpose' in text
    assert '## Surfaces Inventory' in text
    assert '### In Scope For Stage 24B' in text
    assert '### Candidate For Stage 24C' in text
    assert '### Out Of Scope For Stage 24' in text
    assert 'frontend-v2/src/features/colony-planner/ColonyPlannerWorkspace.tsx' in text
    assert 'frontend-v2/src/features/colony-planner/WarehouseEvidenceCard.tsx' in text
    assert 'frontend-v2/src/features/colony-planner/warehouseEvidenceBridge.ts' in text
    assert 'frontend-v2/src/types/api.ts' in text
    assert 'simulation and export-readiness surfaces' in squashed.lower()
    assert 'Operator-facing execution, ingestion, or activation surfaces.' in text


@pytest.mark.unit
def test_stage24a_document_defines_language_contract_comparison_rules_and_fixture_plan():
    text = _read(STAGE24A_PATH)

    assert '## Evidence-State Language Contract' in text
    assert 'Available. Selected-system evidence is present as read-only review context only.' in text
    assert 'Unavailable. No approved bounded staging evidence is linked to this selected system.' in text
    assert 'Not evaluated in this runtime. The staging boundary was not safely queryable for this request.' in text
    assert 'Unknown. Selected-system evidence has not been established.' in text
    assert 'Canonical evidence' in text
    assert 'Observed facts' in text
    assert 'Bounded staging evidence' in text
    assert 'Derived report' in text
    assert 'Report-only review context' in text
    assert 'Not canonical truth' in text
    assert 'Not full EDSM coverage' in text
    assert '## Comparison Rules' in text
    assert 'Canonical evidence vs observed facts:' in text
    assert 'Canonical evidence vs bounded staging:' in text
    assert 'Unavailable vs not_evaluated:' in text
    assert 'Unknown vs unavailable:' in text
    assert '## Fixture And Test Plan' in text
    assert 'available canonical evidence;' in text
    assert 'bounded staging unavailable;' in text
    assert 'bounded staging not_evaluated;' in text
    assert 'unknown selected-system evidence;' in text
    assert 'explicit no-canonical-truth claim;' in text
    assert 'explicit no-full-coverage claim;' in text


@pytest.mark.unit
def test_stage24a_document_keeps_stage24b_bounded_and_safe():
    text = _read(STAGE24A_PATH)
    squashed = _squash(text)

    assert '## Stage 24B Implementation Boundaries' in text
    assert 'Stage 24B - Planner evidence discoverability surfaces' in text
    assert 'Stage 24B should not:' in text
    assert 'authorize DB writes;' in text
    assert 'authorize canonical apply;' in text
    assert 'authorize rebaseline;' in text
    assert 'enable scheduler/service/timer activation.' in text
    assert '## Safety Boundaries' in text
    assert 'Stage 23 remains closed.' in text
    assert 'Stage 19 remains separately gated.' in text
    assert 'Stage 19 execution;' in text
    assert 'DB writes;' in text
    assert 'canonical apply;' in text
    assert 'rebaseline;' in text
    assert 'source-file commits;' in text
    assert 'runtime-artifact commits.' in text
    assert 'no write-capable lane is silently authorized' in squashed


@pytest.mark.unit
def test_stage24a_is_discoverable_from_stage24_roadmap_and_readme():
    roadmap = _read(STAGE24_ROADMAP_PATH)
    readme = _read(README_PATH)

    assert 'docs/colonisation-redesign/stage-24a-readonly-evidence-adoption-contract.md' in roadmap
    assert 'Stage 24B is complete as the first narrow discoverability implementation slice.' in roadmap
    assert 'stage-24a-readonly-evidence-adoption-contract.md' in readme
    assert 'completed Stage 24A contract checkpoint' in readme
    assert 'Completed Stage 24A contract' in readme
