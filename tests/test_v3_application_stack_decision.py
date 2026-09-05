"""Governance contracts for the current V3 documentation authority set."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
ROADMAP = ROOT / "docs" / "ROADMAP.md"
AGENT_CONTRACT = ROOT / "CLAUDE.md"
STACK = ROOT / "docs" / "development" / "v3-application-stack-decision.md"
PRODUCT = (
    ROOT
    / "docs"
    / "colonisation-redesign"
    / "spatial-platform-product-contract.md"
)
ARCHITECTURE = (
    ROOT
    / "docs"
    / "colonisation-redesign"
    / "spatial-platform-architecture-decision.md"
)
BROWSER_LANES = ROOT / "docs" / "development" / "v3-browser-validation-lanes.md"
COORDINATION = ROOT / "docs" / "development" / "v3-coordination-control-plane.md"
INFRASTRUCTURE = ROOT / "docs" / "operations" / "infrastructure-status.md"
ARCHIVE_INDEX = ROOT / "docs" / "archive" / "README.md"

PRIMARY_AUTHORITY_REFERENCES = (
    "docs/ROADMAP.md",
    "docs/development/v3-application-stack-decision.md",
    "docs/colonisation-redesign/spatial-platform-product-contract.md",
    "docs/colonisation-redesign/spatial-platform-architecture-decision.md",
    "docs/development/v3-browser-validation-lanes.md",
    "docs/operations/infrastructure-status.md",
)
CURRENT_AUTHORITY_FILES = (
    README,
    ROADMAP,
    AGENT_CONTRACT,
    STACK,
    PRODUCT,
    ARCHITECTURE,
    BROWSER_LANES,
    INFRASTRUCTURE,
)


def _contract(path: Path) -> str:
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def _lower_contract(path: Path) -> str:
    return _contract(path).lower()


def _assert_near(text: str, first: str, second: str, distance: int = 240) -> None:
    """Require two concepts to be discussed together, in either order."""

    pattern = (
        rf"(?:{re.escape(first)}.{{0,{distance}}}{re.escape(second)}|"
        rf"{re.escape(second)}.{{0,{distance}}}{re.escape(first)})"
    )
    assert re.search(pattern, text, flags=re.IGNORECASE), (
        f"expected {first!r} and {second!r} within {distance} characters"
    )


def test_locked_v3_stack_keeps_its_durable_technology_boundaries():
    decision = _lower_contract(STACK)

    for choice in (
        "apps/web/",
        "typescript 6",
        "svelte 5",
        "sveltekit 2",
        "babylon.js 9",
        "@babylonjs/core",
        "cpython 3.14",
        "uv.lock",
        "postgresql 18",
        "valkey",
        "cypress",
    ):
        assert choice in decision

    assert "no builds, dependency resolution or `git pull` on production" in decision
    assert "immutable oci" in decision
    assert "exact git sha" in decision


def test_babylon_is_renderer_only_behind_renderer_neutral_contracts():
    decision = _lower_contract(STACK)
    architecture = _lower_contract(ARCHITECTURE)

    assert "renderer-neutral" in decision
    assert "babylon types" in decision and "domain contracts" in decision
    assert "domain" in architecture and "must not import babylon" in architecture
    assert "@babylonjs/*" in architecture and "public contracts" in architecture
    for responsibility in ("mechanics", "ranking", "persistence"):
        assert responsibility in architecture
    assert "planning" in architecture or "plan construction" in architecture


def test_route_and_rollback_ownership_remain_explicit():
    decision = _lower_contract(STACK)

    for route in ("/api/*", "/openapi.json", "/s/{id64}"):
        assert route.lower() in decision
    assert "sveltekit" in decision and "catch-all" in decision

    assert "schema compatibility" in decision
    assert "fails closed" in decision
    assert "one-click application-only rollback" in decision


def test_readme_and_agent_contract_publish_the_small_authority_chain():
    readme = _contract(README)
    agent_contract = _contract(AGENT_CONTRACT)

    for reference in PRIMARY_AUTHORITY_REFERENCES:
        assert reference in readme
        assert reference in agent_contract

    coordination = _lower_contract(COORDINATION)
    assert "supporting" in coordination
    assert re.search(r"not product.{0,80}authority", coordination)


def test_archive_and_stage_evidence_cannot_override_current_authority():
    archive = _lower_contract(ARCHIVE_INDEX)
    redesign_index = _lower_contract(
        ROOT / "docs" / "colonisation-redesign" / "README.md"
    )

    for text in (archive, redesign_index):
        assert "historical" in text or "evidence" in text
        assert "roadmap.md" in text
        assert "override" in text or "disagree" in text


def test_apps_web_svelte_and_babylon_are_the_only_v3_browser_target():
    stack = _lower_contract(STACK)
    architecture = _lower_contract(ARCHITECTURE)
    combined = f"{stack} {architecture}"

    _assert_near(stack, "apps/web/", "svelte")
    _assert_near(stack, "apps/web/", "babylon")
    assert "svelte/sveltekit" in architecture
    assert re.search(r"app(?:lication)?(?:/| and )domain orchestration", architecture)
    _assert_near(architecture, "babylon", "spatial")

    _assert_near(combined, "react", "historical", distance=320)
    _assert_near(combined, "r3f", "historical", distance=320)
    assert "current react/r3f application" not in combined
    assert "r3f remains the production" not in combined


def test_v3_production_identity_is_not_v2_or_a_runner_host():
    infrastructure = _lower_contract(INFRASTRUCTURE)
    coordination = _lower_contract(COORDINATION)

    for current_fact in ("ed-finder-prod", "nb79a3d.mevnode.com", "postgresql 18"):
        assert current_fact in infrastructure
    _assert_near(infrastructure, "hetzner", "gone", distance=160)
    _assert_near(infrastructure, "v2", "historical", distance=320)

    assert "contabo" in coordination
    assert re.search(r"three.{0,80}self-hosted.{0,80}codex.{0,40}runners", coordination)
    _assert_near(coordination, "contabo", "not production", distance=240)
    _assert_near(coordination, "checkpoint destination", "explicit decision", distance=320)
    assert "later" in coordination
    assert "contabo live-checkpoint" not in coordination


def test_active_pr_601_is_a_real_slice_with_stabilization_still_open():
    roadmap = _lower_contract(ROADMAP)
    browser = _lower_contract(BROWSER_LANES)
    exact_head = "12eebac48ca9286e0fd8c180cc5f552dc922d07e"

    for current_state in (roadmap, browser):
        assert "#601" in current_state
        assert exact_head in current_state

    for product_fact in ("explore", "finder", "babylon", "inspect", "review lab"):
        assert product_fact in browser
    assert "stabiliz" in browser
    assert "red" in browser or "not green" in browser

    for path in CURRENT_AUTHORITY_FILES:
        text = _lower_contract(path)
        assert not re.search(r"#601.{0,160}foundation[- ]only", text)
        assert not re.search(r"foundation[- ]only.{0,160}#601", text)


def test_product_e2e_and_review_lab_are_separate_babylon_lanes():
    browser = _lower_contract(BROWSER_LANES)

    _assert_near(browser, "product e2e", "review lab", distance=320)
    _assert_near(browser, "product e2e", "separate", distance=320)
    for lane in ("product e2e", "review lab"):
        _assert_near(browser, lane, "apps/web", distance=520)
        _assert_near(browser, lane, "babylon", distance=520)

    _assert_near(browser, "review lab", "synthetic", distance=520)
    assert "environment" in browser or "data" in browser


def test_playwright_is_historical_evidence_not_active_v3_tooling():
    browser = _lower_contract(BROWSER_LANES)

    _assert_near(browser, "playwright", "historical", distance=240)
    _assert_near(browser, "playwright", "not active v3 tooling", distance=240)
