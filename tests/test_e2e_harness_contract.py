"""Regression contracts for the Svelte/Cypress browser and coverage harness.

These checks intentionally protect test-infrastructure behaviour rather than
product behaviour. A harness regression can make a healthy product look red,
or worse, make a broken product look green, so the machinery itself needs a
small fail-closed contract suite.
"""
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web"
WORKFLOWS = ROOT / ".github" / "workflows"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_cypress_is_the_only_active_browser_release_gate_for_svelte_web():
    cypress_config = _read(WEB / "cypress.config.ts")
    package = _read(WEB / "package.json")

    assert '"test:e2e": "cypress run --browser chrome"' in package
    assert "cypress" in package.lower()
    assert "playwright" not in package.lower()
    for spec in (
        "foundation.cy.ts",
        "spatial-foundation.cy.ts",
        "product-journey.cy.ts",
        "account-journal.cy.ts",
    ):
        assert f"cypress/e2e/{spec}" in cypress_config
    assert "tmp-label-debug.cy.ts" not in cypress_config


def test_cypress_gate_preserves_browser_accessibility_visual_and_renderer_coverage():
    workflow = _read(WORKFLOWS / "cypress-parity.yml")
    foundation_spec = _read(WEB / "cypress" / "e2e" / "foundation.cy.ts")
    support = _read(WEB / "cypress" / "support" / "e2e.ts")

    assert "browser: [chrome, firefox]" in workflow
    assert "working-directory: apps/web" in workflow
    assert "pnpm exec cypress run" in workflow
    assert "cypress-axe" in support
    assert "cy.checkA11y" in foundation_spec
    assert "cy.screenshot" in foundation_spec
    assert "account/home-" in foundation_spec


def test_system_detail_escape_uses_the_modal_window_keyboard_path():
    overlay = _read(WEB / "src" / "lib" / "components" / "SystemOverlay.svelte")

    assert "event.key === 'Escape'" in overlay
    assert 'data-testid="system-detail-modal"' in overlay


def test_review_lab_runner_is_the_only_lane_selecting_the_collector():
    runner = _read(ROOT / "scripts" / "dev" / "review_lab" / "browser_runner.py")
    review_workflow = _read(WORKFLOWS / "review-lab.yml")

    assert "'--spec', 'cypress/e2e/review-lab.cy.ts'" in runner
    assert "'--config-file', 'cypress.review.config.ts'" in runner
    assert "working-directory: apps/web" in review_workflow
    assert not (WEB / "cypress" / "e2e" / "review-environment.cy.js").exists()
    assert "playwright" not in runner.lower()


def test_svelte_web_cypress_job_is_the_only_product_e2e_lane_name():
    workflow = _read(WORKFLOWS / "cypress-parity.yml")

    assert "name: Svelte Web E2E (Cypress, ${{ matrix.browser }})" in workflow
    assert "name: Frontend v2 E2E (Playwright)" not in workflow
    assert "playwright" not in workflow.lower()


def test_stage26_browser_harnesses_are_static_history_not_runnable_specs():
    assert not list((ROOT / "frontend").glob("playwright*.ts"))
    scripts = _read(ROOT / "frontend" / "package.json")
    assert "bakeoff:" not in scripts
    assert "map-foundation:dev" not in scripts
    assert "stage26e-route:" not in scripts
    assert not (ROOT / "frontend" / "vite.bakeoff.config.ts").exists()
    assert not (ROOT / "frontend" / "vite.map-foundation.config.ts").exists()
    for historical_dir in (
        ROOT / "frontend" / "bakeoff",
        ROOT / "frontend" / "map-foundation",
        ROOT / "frontend" / "stage26e-route",
    ):
        assert not list(historical_dir.rglob("*.spec.*"))


def test_coverage_workflow_uses_an_explicit_svelte_web_coverage_runner():
    workflow_text = _read(WORKFLOWS / "coverage.yml")
    package = _read(WEB / "package.json")

    assert "pnpm test:coverage" in workflow_text
    assert "@vitest/coverage-v8" in package
    assert "--coverage.provider=v8" in package
    assert "--coverage.reportOnFailure" in package


def test_backend_coverage_reuses_the_seeded_ci_integration_contract():
    workflow = yaml.safe_load(_read(WORKFLOWS / "coverage.yml"))
    steps = workflow["jobs"]["backend-coverage"]["steps"]
    names = [step.get("name", "") for step in steps]

    assert names.index("Apply schema + seed") < names.index("Run unit coverage")
    assert names.index("Validate seeded coverage database") < names.index(
        "Append integration coverage"
    )
    assert "tests/integration/" in next(
        step["run"] for step in steps if step.get("name") == "Append integration coverage"
    )


def test_coverage_summary_fails_closed_when_a_lane_is_red():
    workflow_text = _read(WORKFLOWS / "coverage.yml")

    assert "BACKEND_RESULT: ${{ needs.backend-coverage.result }}" in workflow_text
    assert "WEB_RESULT: ${{ needs.web-coverage.result }}" in workflow_text
    assert (
        'if [[ "$BACKEND_RESULT" != "success" || "$WEB_RESULT" != "success" ]]'
        in workflow_text
    )
