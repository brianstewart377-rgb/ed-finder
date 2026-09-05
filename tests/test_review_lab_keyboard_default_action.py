from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
REVIEW_SPEC = ROOT / 'frontend' / 'cypress' / 'e2e' / 'review-environment.cy.js'


@pytest.mark.unit
def test_review_lab_emulates_only_the_missing_native_button_enter_default_action():
    source = REVIEW_SPEC.read_text(encoding='utf-8')
    helper = source[
        source.index('function emulateFocusedButtonEnterDefaultAction'):
        source.index('function supplyPlannerEnterDefaultActionIfNeeded')
    ]

    assert 'control.tagName' in helper
    assert 'control.disabled' in helper
    assert 'control.ownerDocument.activeElement' in helper
    assert "control.addEventListener('click', observeClick, { once: true })" in helper
    assert "new win.KeyboardEvent('keydown'" in helper
    assert 'control.dispatchEvent(keydown)' in helper
    assert 'allowed && !keydown.defaultPrevented && !clickObserved' in helper
    assert 'control.isConnected && !control.disabled' in helper
    assert "new win.MouseEvent('click'" in helper
    assert 'detail: 0' in helper
    assert "new win.KeyboardEvent('keyup'" in helper


@pytest.mark.unit
def test_review_lab_tries_existing_enter_then_default_action_before_panel_assertion():
    source = REVIEW_SPEC.read_text(encoding='utf-8')
    fallback = source[
        source.index('function supplyPlannerEnterDefaultActionIfNeeded'):
        source.index('function planner')
    ]
    planner = source[source.index('function planner'):source.index('function technical')]
    telemetry = source[source.index('function telemetry'):source.index('function profile')]

    synthetic_enter = "cy.focused().type('{enter}')"
    default_action = 'supplyPlannerEnterDefaultActionIfNeeded()'
    panel_assertion = "cy.getByTestId('plan-start-panel').should('be.visible')"
    keyboard_branch = planner[planner.index('if (keyboard)'):planner.index('} else {')]

    assert synthetic_enter in planner
    assert default_action in planner
    assert planner.index(synthetic_enter) < planner.index(default_action)
    assert planner.index(default_action) < planner.index(panel_assertion)
    assert 'cy.press(' not in keyboard_branch
    assert '.click()' not in keyboard_branch

    assert "!$body.find('[data-testid=\"plan-start-panel\"]').length" in fallback
    assert 'cy.focused().then(($control)' in fallback
    assert "emulateFocusedButtonEnterDefaultAction($control[0], 'open-plan-start')" in fallback

    # The telemetry control already activates correctly through the ordinary
    # Cypress Enter path; keep the workaround constrained to planner entry.
    assert "planner-telemetry-dock-toggle" in telemetry
    assert 'supplyPlannerEnterDefaultActionIfNeeded' not in telemetry
    assert telemetry.count(".type('{enter}')") == 2
