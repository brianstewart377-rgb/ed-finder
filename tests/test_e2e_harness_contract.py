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


def test_cypress_owns_generic_browser_release_gate():
    ci_workflow = _read(WORKFLOWS / "ci.yml")
    cypress_config = _read(FRONTEND / "cypress.config.cjs")
    playwright_config = _read(FRONTEND / "playwright.config.ts")

    # Ordinary PR CI must not grow a second browser release gate again.
    assert "Frontend v2 E2E (Playwright)" not in ci_workflow
    assert "yarn playwright install" not in ci_workflow
    assert "ms-playwright" not in ci_workflow
    assert "yarn e2e --shard=" not in ci_workflow

    # Cypress is the authoritative release signal and therefore remains strict:
    # no test retries are allowed to turn a failing journey green.
    assert "retries: 0" in cypress_config

    # Review Lab still uses the transitional Playwright collector and remains
    # strict until that isolated acceptance path is migrated as well.
    assert "failOnFlakyTests: reviewLabRun" in playwright_config


def test_e2e_backend_lifecycle_is_ownership_aware_and_non_destructive():
    setup = _read(E2E / "globalSetup.ts")

    assert "EDFINDER_E2E_BACKEND_MODE" in setup
    assert "externally managed; verifying readiness" in setup
    assert "return async () =>" in setup
    assert "down --remove-orphans" in setup
    assert "down --volumes" not in setup


def test_e2e_specs_do_not_use_never_resolving_promises_as_failure_simulation():
    offenders = []
    for spec in sorted(E2E.glob("*.spec.*")):
        text = _read(spec)
        if "new Promise(() => {})" in text or "new Promise(() => { })" in text:
            offenders.append(spec.name)

    assert not offenders, (
        "E2E specs must use bounded browser route abort/fulfill behaviour, "
        "not a Promise that can strand a worker until the job timeout: "
        + ", ".join(offenders)
    )


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
