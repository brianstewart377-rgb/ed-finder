"""Durable governance contracts for the V3 documentation authority set."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
ROADMAP = ROOT / "docs" / "ROADMAP.md"
DECISION = ROOT / "docs" / "development" / "v3-application-stack-decision.md"
PRODUCT = (
    ROOT / "docs" / "colonisation-redesign" / "spatial-platform-product-contract.md"
)
ARCHITECTURE = (
    ROOT
    / "docs"
    / "colonisation-redesign"
    / "spatial-platform-architecture-decision.md"
)
BROWSER_LANES = ROOT / "docs" / "development" / "v3-browser-validation-lanes.md"
INFRASTRUCTURE = ROOT / "docs" / "operations" / "infrastructure-status.md"
AGENT_CONTRACT = ROOT / "CLAUDE.md"
ARCHIVE_README = ROOT / "docs" / "archive" / "README.md"

PRIMARY_AUTHORITIES = (
    README,
    ROADMAP,
    DECISION,
    PRODUCT,
    ARCHITECTURE,
    BROWSER_LANES,
    INFRASTRUCTURE,
)


def _contract(path: Path) -> str:
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _terms_are_near(text: str, left: str, right: str, distance: int = 160) -> bool:
    return bool(
        re.search(rf"{left}.{{0,{distance}}}{right}", text)
        or re.search(rf"{right}.{{0,{distance}}}{left}", text)
    )


def test_primary_current_authority_set_is_small_complete_and_discoverable():
    assert len(PRIMARY_AUTHORITIES) == 7
    assert all(path.is_file() for path in PRIMARY_AUTHORITIES)

    readme = _contract(README)
    agent_contract = _contract(AGENT_CONTRACT)
    for path in PRIMARY_AUTHORITIES[1:]:
        relative_path = _relative(path)
        assert relative_path in readme
        assert relative_path in agent_contract

    archive_readme = _contract(ARCHIVE_README).lower()
    assert "historical" in archive_readme
    assert re.search(
        r"(?:never|does not).{0,100}(?:override|current authority)", archive_readme
    )


def test_locked_frontend_and_browser_destination():
    decision = _contract(DECISION)
    decision_lower = decision.lower()

    for choice in ("typescript", "svelte 5", "sveltekit 2", "apps/web"):
        assert choice in decision_lower
    assert _terms_are_near(
        decision_lower, "apps/web", r"(?:sole|only).{0,30}browser", distance=100
    )
    assert "cypress" in decision_lower


def test_babylon_stays_fresh_modular_and_behind_renderer_neutral_contracts():
    decision = _contract(DECISION)
    architecture = _contract(ARCHITECTURE)
    combined = f"{decision} {architecture}".lower()

    assert "@babylonjs/core" in decision
    assert re.search(r"(?:fresh|greenfield).{0,80}babylon", combined)
    assert "domain and feature code **must not import babylon**" in architecture.lower()
    assert re.search(
        r"(?:no.{0,30}babylon.{0,40}type.{0,80}leak|"
        r"babylon.{0,40}type.{0,80}(?:must not|may not|cannot|never).{0,40}leak)",
        combined,
    )


def test_svelte_owns_application_domain_and_accessible_dom():
    architecture = _contract(ARCHITECTURE).lower()

    assert "svelte/sveltekit owns" in architecture
    for responsibility in ("app/domain orchestration", "accessible dom", "routing"):
        assert responsibility in architecture
    assert "renderer-neutral domain handlers" in architecture
    assert "revisioned contributions" in architecture


def test_react_r3f_and_three_are_historical_evidence_not_v3_target_authority():
    current_docs = " ".join(_contract(path) for path in PRIMARY_AUTHORITIES).lower()
    architecture = _contract(ARCHITECTURE).lower()

    assert "react" in current_docs and "r3f" in current_docs and "three" in current_docs
    evidence_terms = r"(?:historical|migration|evidence)"
    assert _terms_are_near(current_docs, "react", evidence_terms)
    assert _terms_are_near(current_docs, "r3f", evidence_terms)
    assert _terms_are_near(
        architecture,
        "stage 26",
        r"(?:r3f.{0,40}selected|selected.{0,40}r3f)",
    )
    assert "r3f remains production" not in current_docs
    assert "r3f remains the production" not in current_docs
    assert "current react/r3f application" not in current_docs


def test_locked_backend_data_service_and_release_baseline():
    decision = _contract(DECISION).lower()

    for choice in (
        "cpython 3.14",
        "uv",
        "pyproject.toml",
        "uv.lock",
        "postgresql 18",
        "valkey",
        "one dedicated eddn worker service",
    ):
        assert choice in decision
    assert "no builds, dependency resolution or `git pull` on production" in decision
    assert "immutable oci" in decision
    assert "exact git sha" in decision


def test_backend_owned_non_api_routes_are_explicit_and_bounded():
    decision = _contract(DECISION)

    for route in ("`/api/*`", "`/openapi.json`", "`/s/{id64}`"):
        assert route in decision
    assert "SvelteKit retains every other application/static route" in decision
    assert "no backend catch-all may steal SvelteKit routes" in decision
    assert "FastAPI OpenAPI for CI and client generation" in decision
    assert "OpenGraph share stop page" in decision


def test_rollback_requires_proven_schema_compatibility():
    decision = _contract(DECISION).lower()

    assert (
        "backward compatibility with the current database schema has been proved"
        in decision
    )
    assert "migration-set/schema identity" in decision
    assert "schema-compatibility evidence" in decision
    assert "promotion of the old application fails closed" in decision
    assert "incompatible or destructive migrations" in decision


def test_current_production_authority_is_v3_pg18_and_not_a_runner_host():
    infrastructure = _contract(INFRASTRUCTURE).lower()

    assert "ed-finder-prod" in infrastructure
    assert "nb79a3d.mevnode.com" in infrastructure
    assert "postgresql 18" in infrastructure
    assert "hetzner" in infrastructure and "historical" in infrastructure
    assert "contabo" in infrastructure
    assert _terms_are_near(
        infrastructure, "contabo", r"not (?:ed-finder )?production", distance=100
    )


def test_browser_product_acceptance_and_review_lab_are_separate_babylon_lanes():
    browser_lanes = _contract(BROWSER_LANES).lower()

    assert "product e2e" in browser_lanes
    assert "visual acceptance" in browser_lanes
    assert "review lab" in browser_lanes
    assert "separate" in browser_lanes or "distinct" in browser_lanes
    assert browser_lanes.count("apps/web") >= 2
    assert browser_lanes.count("babylon") >= 2


def test_pr_601_is_described_as_an_active_product_integration_lane():
    roadmap = _contract(ROADMAP).lower()

    assert "#601" in roadmap and "active" in roadmap
    for product_slice in ("finder", "inspect", "babylon"):
        assert product_slice in roadmap
    assert not re.search(r"#601.{0,160}foundation[- ]only", roadmap)
    assert not re.search(r"#601.{0,240}(?:finder|inspect).{0,100}come later", roadmap)


def test_primary_authorities_do_not_restore_superseded_stage_or_checkpoint_claims():
    current_docs = " ".join(_contract(path) for path in PRIMARY_AUTHORITIES).lower()

    forbidden_claims = (
        r"(?:archived?|historical) (?:documents?|docs).{0,80}(?:are|as) "
        r"(?:the )?(?:current|primary) authority",
        r"contabo live[- ]checkpoint",
        r"contabo.{0,80}live[- ]checkpoint environment",
        r"contabo is (?:the |a )?(?:live[- ]?)?checkpoint",
        r"checkpoint (?:target|destination|environment) is contabo",
        r"27a.{0,80}only authori[sz]es 27b",
        r"babylon runtime is not authori[sz]ed in this stage",
        r"(?:#601|apps/web).{0,120}foundation[- ]only",
        r"(?:#601|apps/web).{0,120}non[- ]product",
        r"finder.{0,40}inspect.{0,100}come later",
        r"inspect.{0,40}finder.{0,100}come later",
    )
    for claim in forbidden_claims:
        assert not re.search(claim, current_docs)
