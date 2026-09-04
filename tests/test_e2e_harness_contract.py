"""Regression contracts for the browser/coverage test harness.

These checks intentionally protect test-infrastructure behaviour rather than
product behaviour. A harness regression can make a healthy product look red,
or worse, make a broken product look green, so the machinery itself needs a
small fail-closed contract suite.
"""
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
E2E = FRONTEND / "e2e"
WORKFLOWS = ROOT / ".github" / "workflows"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_cypress_is_the_only_runnable_browser_authority():
    cypress_config = _read(FRONTEND / "cypress.config.cjs")
    package = _read(FRONTEND / "package.json")

    assert "retries: 0" in cypress_config
    assert '"cypress"' in package
    assert '"cypress-axe"' in package
    assert "playwright" not in package.lower()
    assert not list(FRONTEND.glob("playwright*.config.*"))


def test_cypress_has_accessibility_and_deterministic_visual_evidence_capabilities():
    support = _read(FRONTEND / "cypress" / "support" / "e2e.js")
    specs = "\n".join(_read(path) for path in sorted((FRONTEND / "cypress" / "e2e").glob("*.cy.js")))

    assert "cypress-axe" in support
    assert "injectAxe" in specs
    assert "checkA11y" in specs
    assert "captureDeterministicBaseline" in specs
    assert "cy.screenshot" in support


def test_cypress_specs_do_not_use_never_resolving_promises_as_failure_simulation():
    offenders = []
    for spec in sorted((FRONTEND / "cypress" / "e2e").glob("*.cy.js")):
        text = _read(spec)
        if "new Promise(() => {})" in text or "new Promise(() => { })" in text:
            offenders.append(spec.name)

    assert not offenders, (
        "E2E specs must use bounded Cypress intercept behaviour, "
        "not a Promise that can strand a worker until the job timeout: "
        + ", ".join(offenders)
    )


def test_protected_cypress_job_covers_chrome_and_firefox_under_compatibility_label():
    workflow = _read(WORKFLOWS / "cypress-parity.yml")

    assert "Compatibility label only: this job is Cypress-only" in workflow
    assert "name: Frontend v2 E2E (Playwright)" in workflow
    assert "--browser chrome" in workflow
    assert "--browser firefox" in workflow
    assert "playwright install" not in workflow.lower()


def test_coverage_workflow_uses_an_explicit_frontend_coverage_runner():
    workflow_text = _read(WORKFLOWS / "coverage.yml")

    # Passing --coverage to a chained yarn script only reaches the tail command
    # and silently produces partial coverage. Coverage must be its own run.
    assert "yarn test:ci --coverage" not in workflow_text
    assert "@vitest/coverage-v8@4.1.10" in workflow_text
    assert "node scripts/run-vitest.mjs run" in workflow_text
    assert "--coverage.provider=v8" in workflow_text
    assert "--coverage.reportOnFailure" in workflow_text


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

    assert 'BACKEND_RESULT: ${{ needs.backend-coverage.result }}' in workflow_text
    assert 'FRONTEND_RESULT: ${{ needs.frontend-coverage.result }}' in workflow_text
    assert 'if [[ "$BACKEND_RESULT" != "success" || "$FRONTEND_RESULT" != "success" ]]' in workflow_text
