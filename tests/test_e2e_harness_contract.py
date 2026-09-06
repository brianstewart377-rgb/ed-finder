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
PRODUCT_SPECS = "cypress/e2e/auth-owner-access.cy.js,cypress/e2e/release-gate.cy.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_cypress_is_the_only_active_strict_browser_release_gate():
    cypress_config = _read(FRONTEND / "cypress.config.cjs")
    assert "retries: 0" in cypress_config
    package = _read(FRONTEND / "package.json")
    assert f'"e2e": "cypress run --browser chrome --spec {PRODUCT_SPECS}"' in package
    assert f'"e2e:firefox": "cypress run --browser firefox --spec {PRODUCT_SPECS}"' in package
    assert "playwright" not in package.lower()


def test_cypress_gate_preserves_browser_accessibility_visual_and_renderer_coverage():
    workflow = _read(WORKFLOWS / "cypress-parity.yml")
    release_spec = _read(FRONTEND / "cypress/e2e/release-gate.cy.js")
    assert "browser: [chrome, firefox]" in workflow
    assert f"--spec {PRODUCT_SPECS}" in workflow
    assert "review-environment.cy.js" not in workflow
    assert "cypress-axe" in _read(FRONTEND / "cypress/support/e2e.js")
    assert "cy.checkA11y" in release_spec
    assert "home-1280x720" in release_spec
    assert "orders renderer sync invalidation before resize revalidation" in release_spec
    assert "same-size ResizeObserver notification" in release_spec


def test_system_detail_escape_uses_the_modal_window_keyboard_path():
    release_spec = _read(FRONTEND / "cypress/e2e/release-gate.cy.js")
    test_body = release_spec[
        release_spec.index("it('opens and closes a system detail modal from a real search result'"):
        release_spec.index("it('installs and controls through the cache-neutral service worker'")
    ]
    dispatch = "win.dispatchEvent(new win.KeyboardEvent('keydown'"
    readiness = ".to.eq('hidden')"
    assert readiness in test_body
    assert dispatch in test_body
    assert ".style.overflow" in test_body
    assert test_body.index(readiness) < test_body.index(dispatch)
    for option in (
        "key: 'Escape'",
        "code: 'Escape'",
        "which: 27",
        "keyCode: 27",
        "bubbles: true",
        "cancelable: true",
    ):
        assert option in test_body
    modal_absent = "cy.getByTestId('system-detail-modal').should('not.exist')"
    overflow_restored = ".to.eq('')"
    route_restored = "cy.location('hash').should('eq', '#finder')"
    assert modal_absent in test_body
    assert overflow_restored in test_body
    assert route_restored in test_body
    assert test_body.index(dispatch) < test_body.index(modal_absent) < test_body.index(overflow_restored) < test_body.index(route_restored)


def test_review_lab_runner_is_the_only_lane_selecting_the_collector():
    runner = _read(ROOT / "scripts/dev/review_lab/browser_runner.py")
    review_workflow = _read(WORKFLOWS / 'review-lab.yml')
    assert "'--spec', 'cypress/e2e/review-lab.cy.ts'" in runner
    assert "'--config-file', 'cypress.review.config.ts'" in runner
    assert 'working-directory: apps/web' in review_workflow
    assert not (FRONTEND / 'cypress/e2e/review-environment.cy.js').exists()
    assert "playwright" not in runner.lower()


def test_required_check_compatibility_alias_is_backed_by_real_cypress_job():
    workflow = _read(WORKFLOWS / "cypress-parity.yml")
    assert "Frontend E2E (Cypress, ${{ matrix.browser }})" in workflow
    assert "name: Frontend v2 E2E (Playwright)" in workflow
    assert "needs: [cypress-release-gate]" in workflow
    assert 'test "$CYPRESS_RESULT" = success' in workflow
    assert workflow.lower().count("playwright") == 1


def test_stage26_browser_harnesses_are_static_history_not_runnable_specs():
    assert not list(FRONTEND.glob("playwright*.ts"))
    scripts = _read(FRONTEND / "package.json")
    assert "bakeoff:" not in scripts
    assert "map-foundation:dev" not in scripts
    assert "stage26e-route:" not in scripts
    assert not (FRONTEND / "vite.bakeoff.config.ts").exists()
    assert not (FRONTEND / "vite.map-foundation.config.ts").exists()
    for historical_dir in (FRONTEND / "bakeoff", FRONTEND / "map-foundation", FRONTEND / "stage26e-route"):
        assert not list(historical_dir.rglob("*.spec.*"))


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
