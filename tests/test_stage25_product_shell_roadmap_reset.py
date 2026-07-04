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

    assert "Stage 25A is complete." in roadmap
    assert "Stage 25B is complete and merged." in roadmap
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
def test_stage25_roadmap_preserves_product_hierarchy_and_surface_ownership():
    roadmap = read(ROADMAP)

    assert "Explore → Inspect → Plan → Review / Export" in roadmap
    assert "Explore Plan Review" in roadmap
    assert "Inspect remains contextual System Detail, not a competing primary workspace." in roadmap
    assert "System Detail is a contextual Inspect surface" in roadmap
    assert "Colony Planner: `canonical_live`" in roadmap
    assert "Colony Planner is the canonical live planning workspace" in roadmap
    assert "simulation-preview: `reusable_but_unwired`" in roadmap
    assert "must not be wired before Stage 25D" in roadmap


@pytest.mark.unit
def test_stage25_roadmap_keeps_map_secondary_and_blocks_renderer_work():
    roadmap = read(ROADMAP)

    assert "The map is retained as a secondary Explore surface only." in roadmap
    assert "map: `canonical_live` as a secondary Explore surface" in roadmap
    assert "map redesign;" in roadmap
    assert "renderer replacement;" in roadmap
    assert "PixiJS, deck.gl, MapLibre, Leaflet, D3, WebGL, or a new map library." in roadmap
    assert "The current custom canvas renderer remains the default" in roadmap


@pytest.mark.unit
def test_stage25_roadmap_preserves_visual_and_dense_content_boundaries():
    roadmap = read(ROADMAP)

    assert "Stage 25 authorizes a substantial product-shell and visual-system redesign." in roadmap
    assert "This is not a cosmetic reskin." in roadmap
    assert "must not merely add gradients, blur, badges, panels, or new tabs" in roadmap
    assert "restrained cockpit-oriented" in roadmap
    assert "Glass is not authorized on dense evidence cards, tables, planning canvases, map labels, or technical provenance surfaces." in roadmap
    assert "Dense content remains non-glass by default." in roadmap


@pytest.mark.unit
def test_stage25_roadmap_preserves_deferrals_and_safety_boundaries():
    roadmap = read(ROADMAP)

    assert "Mission intelligence remains deferred and unauthorized" in roadmap
    assert "Ring/mining work remains deferred and unauthorized" in roadmap
    assert "A broad standalone facility browser is deferred" in roadmap
    assert "Plan import, persistence, accounts, OAuth, and collaboration are deferred" in roadmap
    assert "Stage 19 remains separately gated." in roadmap
    assert "No database or operational write lane is authorized by this roadmap reset." in roadmap
    assert "Stage 19 execution;" in roadmap
    assert "database commands or database writes;" in roadmap
    assert "canonical apply;" in roadmap
    assert "rebaseline;" in roadmap
    assert "scheduler, service, or timer activation;" in roadmap
    assert "source acquisition;" in roadmap


@pytest.mark.unit
def test_parent_contract_keeps_required_decisions_and_runtime_boundary():
    parent = read(PARENT)

    assert "The problem is not simply the number of top-level tabs." in parent
    assert "Stage 25C has exactly one objective:" in parent
    assert "selected-system context spine" in parent
    assert "persistent selected-system context that the player can see" in parent
    assert "Selected-system context contract" in parent
    assert "selected system, saved candidate, compared system, and active plan" in parent
    assert "profile and sync" in parent
    assert "player/operator boundary" in parent.lower()
    assert "resilience-only" in parent
    assert "Defining either contract does not by itself authorize runtime implementation." in parent
    assert "runtime UI implementation merely by defining this contract." in parent


@pytest.mark.unit
def test_parent_contract_keeps_visual_scope_and_responsive_criteria():
    parent = read(PARENT)

    assert "Visual-System Foundation" in parent
    assert "progressive disclosure" in parent.lower()
    assert "text labels must accompany colour" in parent
    assert "simulation-preview wiring into live routes;" in parent
    assert "map redesign;" in parent
    assert "mission intelligence;" in parent
    assert "mining/ring features;" in parent
    assert "1440x900" in parent
    assert "1280x720" in parent
    assert "390x844" in parent
    assert "planner phone-width is resilience-only" in parent


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
    assert "The active ED-Finder product programme remains **Stage 25**:" in readme
