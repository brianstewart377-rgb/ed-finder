import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
ROADMAP_PATH = DOCS / 'stage-25-roadmap.md'
CONTRACT_PATH = DOCS / 'stage-25c-product-shell-shared-context-contract.md'
README_PATH = DOCS / 'README.md'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _squash(text: str) -> str:
    return re.sub(r'\s+', ' ', text)


@pytest.mark.unit
def test_stage25_reset_docs_exist():
    assert ROADMAP_PATH.exists()
    assert CONTRACT_PATH.exists()
    assert README_PATH.exists()


@pytest.mark.unit
def test_stage25_reset_records_corrected_stage_statuses():
    roadmap = _squash(_read(ROADMAP_PATH))

    assert 'Stage 25A is complete.' in roadmap
    assert 'Stage 25B is complete and merged.' in roadmap
    assert 'Stage 25C Slice 1 is in progress and pending review.' in roadmap
    assert 'Stage 25D, Stage 25E, Stage 25F, Stage 25G, and Stage 25H are unstarted.' in roadmap


@pytest.mark.unit
def test_stage25_reset_corrects_stage25b_pending_review_status():
    roadmap = _squash(_read(ROADMAP_PATH))

    # The roadmap must no longer describe Stage 25B as pending review.
    assert 'Stage 25B is no longer `implemented_in_this_pr_pending_review`.' in roadmap
    assert 'Stage 25B is complete and merged' in roadmap
    assert 'PR #259' in roadmap
    # The roadmap must not falsely claim manual visual verification.
    assert 'No manual visual verification is claimed' in roadmap


@pytest.mark.unit
def test_stage25_reset_defines_product_journey_and_future_hierarchy():
    roadmap = _squash(_read(ROADMAP_PATH))

    assert 'Explore → Inspect → Plan → Review / Export' in roadmap
    # Future top-level hierarchy is explicit.
    assert 'Explore Plan Review' in roadmap
    assert 'the future top-level hierarchy `Explore`, `Plan`, `Review` is explicit' in roadmap


@pytest.mark.unit
def test_stage25_reset_records_surface_ownership():
    roadmap = _squash(_read(ROADMAP_PATH))

    # System Detail is contextual Inspect, not a competing primary workspace.
    assert 'Inspect remains contextual System Detail, not a competing primary workspace.' in roadmap
    assert 'System Detail is a contextual Inspect surface' in roadmap
    # Colony Planner remains canonical live.
    assert 'Colony Planner: `canonical_live`' in roadmap
    assert 'Colony Planner is the canonical live planning workspace' in roadmap
    # simulation-preview remains reusable but unwired.
    assert 'simulation-preview: `reusable_but_unwired`' in roadmap
    assert 'must not be wired before Stage 25D' in roadmap


@pytest.mark.unit
def test_stage25_reset_keeps_map_secondary_and_blocks_map_work():
    roadmap = _squash(_read(ROADMAP_PATH))

    assert 'The map is retained as a secondary Explore surface only.' in roadmap
    assert 'map: `canonical_live` as a secondary Explore surface' in roadmap
    # No map redesign or renderer replacement is authorized.
    assert 'map redesign;' in roadmap
    assert 'renderer replacement;' in roadmap
    assert 'PixiJS, deck.gl, MapLibre, Leaflet, D3, WebGL, or a new map library.' in roadmap
    assert 'The current custom canvas renderer remains the default' in roadmap


@pytest.mark.unit
def test_stage25_reset_frames_visual_redesign_not_reskin():
    roadmap = _squash(_read(ROADMAP_PATH))

    assert 'Stage 25 authorizes a substantial product-shell and visual-system redesign.' in roadmap
    assert 'This is not a cosmetic reskin.' in roadmap
    assert 'must not merely add gradients, blur, badges, panels, or new tabs' in roadmap
    assert 'restrained cockpit-oriented' in roadmap


@pytest.mark.unit
def test_stage25_reset_keeps_dense_content_non_glass():
    roadmap = _squash(_read(ROADMAP_PATH))

    assert 'Glass is not authorized on dense evidence cards, tables, planning canvases, map labels, or technical provenance surfaces.' in roadmap
    assert 'Dense content remains non-glass by default.' in roadmap


@pytest.mark.unit
def test_stage25_reset_preserves_deferrals():
    roadmap = _squash(_read(ROADMAP_PATH))

    assert 'Mission intelligence remains deferred and unauthorized' in roadmap
    assert 'Ring/mining work remains deferred and unauthorized' in roadmap
    assert 'A broad standalone facility browser is deferred' in roadmap
    assert 'Plan import, persistence, accounts, OAuth, and collaboration are deferred' in roadmap


@pytest.mark.unit
def test_stage25_reset_preserves_safety_boundaries():
    roadmap = _squash(_read(ROADMAP_PATH))

    assert 'Stage 19 remains separately gated.' in roadmap
    assert 'No database or operational write lane is authorized by this roadmap reset.' in roadmap
    assert 'Stage 19 execution;' in roadmap
    assert 'database commands or database writes;' in roadmap
    assert 'canonical apply;' in roadmap
    assert 'rebaseline;' in roadmap
    assert 'scheduler, service, or timer activation;' in roadmap
    assert 'source acquisition;' in roadmap


@pytest.mark.unit
def test_stage25_reset_does_not_authorize_runtime_by_defining_contract():
    roadmap = _squash(_read(ROADMAP_PATH))
    contract = _squash(_read(CONTRACT_PATH))

    assert 'The full Stage 25C implementation contract lives in' in roadmap
    assert (
        'defining the Stage 25C contract does not by itself authorize runtime implementation.'
        in roadmap
    )
    assert 'Stage 25C is `slice_1_in_progress_pending_review`.' in contract
    assert 'Defining this contract did not authorize any runtime implementation by itself.' in contract
    assert 'runtime UI implementation merely by defining this contract.' in contract


@pytest.mark.unit
def test_stage25c_contract_defines_problem_objective_and_required_decisions():
    contract = _squash(_read(CONTRACT_PATH))

    # The problem is framed as fragmentation, not tab count alone.
    assert 'The problem is not simply the number of top-level tabs.' in contract
    assert 'Stage 25C has exactly one objective:' in contract
    assert 'selected-system context spine' in contract
    assert 'persistent selected-system context that the player can see' in contract
    assert 'Selected-system context contract' in contract
    assert 'selected system, saved candidate, compared system, and active plan' in contract
    assert 'profile and sync' in contract
    assert 'player/operator boundary' in contract.lower()
    assert 'resilience-only' in contract


@pytest.mark.unit
def test_stage25c_contract_defines_visual_foundation_and_scope_and_criteria():
    contract = _squash(_read(CONTRACT_PATH))

    assert 'Visual-System Foundation' in contract
    assert 'progressive disclosure' in contract.lower()
    assert 'text labels must accompany colour' in contract
    # Out-of-scope guards.
    assert 'simulation-preview wiring into live routes;' in contract
    assert 'map redesign;' in contract
    assert 'mission intelligence;' in contract
    assert 'mining/ring features;' in contract
    # Desktop/mobile criteria.
    assert '1440x900' in contract
    assert '1280x720' in contract
    assert '390x844' in contract
    assert 'planner phone-width is resilience-only' in contract


@pytest.mark.unit
def test_stage25_reset_indexed_in_readme():
    readme = _squash(_read(README_PATH))

    assert '../ROADMAP.md' in readme
    assert 'stage-25c-product-shell-shared-context-contract.md' in readme
    assert 'Active Stage 25 Control' in readme
