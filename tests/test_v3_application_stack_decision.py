"""Governance contract for the locked V3 application stack."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DECISION = ROOT / "docs" / "development" / "v3-application-stack-decision.md"
README = ROOT / "README.md"
ROADMAP = ROOT / "docs" / "ROADMAP.md"
AGENT_CONTRACT = ROOT / "CLAUDE.md"
ARCHITECTURE = (
    ROOT
    / "docs"
    / "colonisation-redesign"
    / "spatial-platform-architecture-decision.md"
)
INHERITANCE = (
    ROOT
    / "docs"
    / "colonisation-redesign"
    / "stage-27a-stage26-inheritance-matrix.md"
)


def _contract(path: Path) -> str:
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def test_locked_frontend_and_browser_authority():
    decision = _contract(DECISION)

    for choice in ("**TypeScript**", "**Svelte 5**", "**SvelteKit 2**"):
        assert choice in decision
    assert "**Cypress is the protected browser/E2E authority**" in decision
    assert "Existing Playwright coverage is migration evidence, not future authority" in decision


def test_babylon_stays_modular_and_behind_renderer_neutral_contracts():
    decision = _contract(DECISION)
    architecture = _contract(ARCHITECTURE)

    assert "Modular **`@babylonjs/*`** packages; start with `@babylonjs/core`" in decision
    assert "does not permit Babylon types to leak into domain contracts" in decision
    assert "Domain and feature code **must not import Babylon**" in architecture
    assert "No `@babylonjs/*` type may leak into public contracts" in architecture


def test_locked_backend_data_and_service_baseline():
    decision = _contract(DECISION)

    for choice in (
        "**CPython 3.14**",
        "**uv + `pyproject.toml` + `uv.lock`**",
        "**PostgreSQL 18**",
        "**Valkey** for the new baseline",
        "**Not in the baseline**; reintroduce only if a future requirement demonstrates",
        "**One dedicated EDDN worker service**",
    ):
        assert choice in decision


def test_production_releases_are_immutable_ci_built_artifacts():
    decision = _contract(DECISION)

    assert "**No builds, dependency resolution or `git pull` on production**" in decision
    assert (
        "Immutable OCI web/backend images plus a release manifest containing exact Git SHA"
        in decision
    )
    assert "reproducible CI build from frozen pnpm/uv locks" in decision


def test_backend_owned_non_api_routes_are_explicit_and_bounded():
    decision = _contract(DECISION)

    assert "`/api/*`, exact `/openapi.json` and numeric `/s/{id64}` route to FastAPI" in decision
    assert "SvelteKit retains every other application/static route" in decision
    assert "no backend catch-all may steal SvelteKit routes" in decision
    assert "same-origin routing sends `/api/*`, exact `/openapi.json` and numeric `/s/{id64}`" in decision
    assert "FastAPI OpenAPI for CI and client generation" in decision
    assert "OpenGraph share stop page" in decision


def test_rollback_requires_proven_schema_compatibility():
    decision = _contract(DECISION)

    assert "backward compatibility with the current database schema has been proved" in decision
    assert "migration-set/schema identity, schema-compatibility evidence and rollback eligibility" in decision
    assert "promotion of the old application fails closed" in decision
    assert "Incompatible or destructive migrations must never advertise one-click application-only rollback" in decision
    assert "does not invent the currently absent executable V3 database recovery procedure" in decision


def test_authority_chain_registers_stack_lock_and_distinguishes_current_from_target():
    decision_path = "docs/development/v3-application-stack-decision.md"
    readme = _contract(README)
    roadmap = _contract(ROADMAP)
    agent_contract = _contract(AGENT_CONTRACT)

    assert readme.index("docs/ROADMAP.md") < readme.index(decision_path)
    assert readme.index(decision_path) < readme.index("CLAUDE.md")
    assert agent_contract.index("docs/ROADMAP.md") < agent_contract.index(decision_path)
    assert agent_contract.index(decision_path) < agent_contract.index("this file")

    assert "authoritative for new V3 application implementation" in roadmap
    assert "checked-in React/Yarn and Python 3.12 implementation remains migration/reference and current-validation reality" in roadmap
    assert "does not open Stage 27B, authorize a Babylon runtime" in roadmap
    assert "checked-in frontend" in readme and "React/TypeScript" in readme
    assert "locked target for new V3 application implementation is Svelte 5/SvelteKit 2/TypeScript 6" in readme
    assert "checked-in backend validation path remains on Python 3.12" in readme
    assert "targets CPython 3.14 with uv" in readme
    assert "Use these legacy-toolchain commands only to validate" in agent_contract
    assert "checked-in backend still uses Python 3.12" in agent_contract
    assert "targets CPython 3.14 with uv" in agent_contract


def test_stage_27_docs_assign_future_application_ownership_to_svelte():
    architecture = _contract(ARCHITECTURE)
    inheritance = _contract(INHERITANCE)

    assert (
        "Svelte/SvelteKit owns app/domain orchestration, routing, panels, accessible DOM UI, "
        "keyboard and text"
    ) in architecture
    assert (
        "Renderer-neutral domain handlers decide whether an explicit action is allowed"
        in architecture
    )
    assert "The Svelte/SvelteKit application sends revisioned contributions" in architecture
    assert "Svelte/SvelteKit owns app/domain orchestration" in inheritance
    assert "Svelte/SvelteKit owns accessible DOM UI" in inheritance

    assert "R3F was not a failure and Babylon did not win Stage 26" in architecture
    assert "selected R3F/Three.js" in inheritance
    assert "R3F remains the production baseline and rollback" in inheritance


def test_stack_lock_does_not_authorize_later_stage_27_implementation_or_cutover():
    decision = _contract(DECISION)
    architecture = _contract(ARCHITECTURE)
    inheritance = _contract(INHERITANCE)

    assert (
        "does not itself authorize production deployment, database mutation, a Babylon production "
        "cutover, or any later Stage 27 slice"
    ) in decision
    assert "Babylon runtime is not authorized in this stage" in architecture
    assert "**27B:** isolated runtime workbench; no production wiring" in architecture
    assert "27A does not authorize these implementations" in architecture
    assert (
        "not authorization to implement Babylon, alter the production map, remove the "
        "R3F/Three.js map, or begin Stage 27B"
    ) in inheritance
    assert "Production cutover, rollback retirement and R3F deletion remain later" in inheritance
