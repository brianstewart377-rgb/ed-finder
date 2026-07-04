import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "colonisation-redesign"
ROADMAP = DOCS / "stage-25-roadmap.md"
PARENT = DOCS / "stage-25c-product-shell-shared-context-contract.md"
SLICE = DOCS / "stage-25c-selected-system-context-slice.md"
README = DOCS / "README.md"


def read(path: Path) -> str:
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


@pytest.mark.unit
def test_stage25_control_docs_exist():
    assert ROADMAP.exists()
    assert PARENT.exists()
    assert SLICE.exists()
    assert README.exists()


@pytest.mark.unit
def test_stage25c_status_records_merged_slice1_and_pending_slice2():
    roadmap = read(ROADMAP)
    parent = read(PARENT)
    slice_doc = read(SLICE)

    assert "Stage 25C Slice 1 merged later via PR #262." in roadmap
    assert "Stage 25 is not complete." in roadmap
    assert "Slice 1 — product shell and navigation hierarchy: `complete_merged` in PR #262." in parent
    assert "Slice 2 — selected-system context spine: `contract_defined_pending_implementation`." in parent
    assert "slice_1_in_progress_pending_review" in parent
    assert "Stage 25C Slice 2 - Selected-System Context Spine (Contract)" in slice_doc


@pytest.mark.unit
def test_stage25c_parent_contract_indexes_slice2():
    parent = read(PARENT)

    assert "stage-25c-selected-system-context-slice.md" in parent
    assert "The detailed controlling contract for Slice 2 is" in parent
    assert "exact selected-system state, route, transition, failure, and no-active-plan rules" in parent


@pytest.mark.unit
def test_slice2_separates_selection_from_related_state():
    doc = read(SLICE)

    for heading in [
        "Selected system",
        "Inspection state",
        "Saved candidate",
        "Compared system",
        "Active planner project",
    ]:
        assert heading in doc
    assert "must not silently infer one state from another" in doc
    assert "Saving or unsaving a system must not change selected-system context." in doc
    assert "Adding or removing a system from comparison must not change selected-system context." in doc


@pytest.mark.unit
def test_slice2_requires_a_non_modal_context_route_and_truthful_failures():
    doc = read(SLICE)

    assert "#finder/context/{id64}" in doc
    assert "#finder/system/{id64}" in doc
    assert "#colony-planner/system/{id64}" in doc
    assert "Plan → Finder" in doc
    assert "must not reopen System Detail unexpectedly." in doc
    assert "must clear any previous available selected-system identity" in doc
    assert "must never retain a prior system name, evidence posture, or project" in doc


@pytest.mark.unit
def test_slice2_requires_explicit_no_draft_and_accessible_context_bar():
    doc = read(SLICE)

    assert "No active draft for this system" in doc
    assert "Create draft" in doc
    assert "must never silently create a project" in doc
    assert "System name first" in doc
    assert "concise evidence posture second" in doc
    assert "ID64 as supporting technical detail" in doc
    assert "keyboard reachable" in doc


@pytest.mark.unit
def test_slice2_preserves_scope_and_verification_gates():
    roadmap = read(ROADMAP)
    parent = read(PARENT)
    doc = read(SLICE)

    assert "Explore → Inspect → Plan → Review / Export" in roadmap
    assert "Stage 19 remains separately gated." in roadmap
    assert "simulation-preview wiring into live routes;" in parent
    assert "map redesign;" in parent
    assert "database or Stage 19 activity." in parent
    assert "1440x900 and 1280x720" in doc
    assert "390x844" in doc
    assert "Direct selected-context link" in doc
    assert "Invalid / unavailable link" in doc
    assert "no runtime change is claimed as part of this PR." in doc


@pytest.mark.unit
def test_stage25_docs_stay_navigable():
    readme = read(README)
    assert "stage-25-roadmap.md" in readme
    assert "stage-25c-product-shell-shared-context-contract.md" in readme
