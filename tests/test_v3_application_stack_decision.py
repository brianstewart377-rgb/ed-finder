"""Governance contract for the locked V3 application stack."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DECISION = ROOT / "docs" / "development" / "v3-application-stack-decision.md"
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
