from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
REVIEW_SPEC = ROOT / 'frontend' / 'cypress' / 'e2e' / 'review-environment.cy.js'


@pytest.mark.unit
def test_review_lab_uses_native_enter_only_when_synthetic_enter_did_not_open_planner():
    source = REVIEW_SPEC.read_text(encoding='utf-8')
    helper = source[
        source.index('function pressNativeEnterIfPlannerDidNotOpen'):
        source.index('function planner')
    ]

    assert "cy.get('body').then(($body)" in helper
    assert "!$body.find('[data-testid=\"plan-start-panel\"]').length" in helper
    assert 'cy.press(Cypress.Keyboard.Keys.ENTER)' in helper
    assert '.click()' not in helper


@pytest.mark.unit
def test_review_lab_tries_existing_enter_then_native_fallback_before_panel_assertion():
    source = REVIEW_SPEC.read_text(encoding='utf-8')
    planner = source[source.index('function planner'):source.index('function technical')]
    telemetry = source[source.index('function telemetry'):source.index('function profile')]

    synthetic_enter = "cy.focused().type('{enter}')"
    native_fallback = 'pressNativeEnterIfPlannerDidNotOpen()'
    panel_assertion = "cy.getByTestId('plan-start-panel').should('be.visible')"

    assert synthetic_enter in planner
    assert native_fallback in planner
    assert planner.index(synthetic_enter) < planner.index(native_fallback)
    assert planner.index(native_fallback) < planner.index(panel_assertion)
    assert 'cy.press(' not in planner
    assert '.click()' not in planner[planner.index('if (keyboard)'):planner.index('} else {')]

    # The telemetry control already activates correctly through the existing
    # Cypress type path; do not broaden the workaround to working controls.
    assert "planner-telemetry-dock-toggle" in telemetry
    assert 'pressNativeEnterIfPlannerDidNotOpen' not in telemetry
    assert telemetry.count(".type('{enter}')") == 2
