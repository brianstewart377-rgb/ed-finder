from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
REVIEW_SPEC = ROOT / 'frontend' / 'cypress' / 'e2e' / 'review-environment.cy.js'


@pytest.mark.unit
def test_review_lab_supplies_only_the_missing_button_enter_default_action():
    source = REVIEW_SPEC.read_text(encoding='utf-8')
    helper = source[
        source.index('function armFocusedButtonEnterDefaultAction'):
        source.index('function planner')
    ]

    assert "control.tagName" in helper
    assert "control.addEventListener('click', observeClick, { once: true })" in helper
    assert "control.addEventListener('keydown'" in helper
    assert "event.key !== 'Enter'" in helper
    assert '!event.defaultPrevented' in helper
    assert '!clickObserved' in helper
    assert 'control.ownerDocument.activeElement === control' in helper
    assert 'control.isConnected' in helper
    assert '!control.disabled' in helper
    assert 'win.queueMicrotask' in helper
    assert 'control.click();' in helper


@pytest.mark.unit
def test_review_lab_arms_planner_and_telemetry_buttons_before_enter():
    source = REVIEW_SPEC.read_text(encoding='utf-8')
    planner = source[source.index('function planner'):source.index('function technical')]
    telemetry = source[source.index('function telemetry'):source.index('function profile')]

    assert "armFocusedButtonEnterDefaultAction($control[0], 'open-plan-start')" in planner
    assert planner.index('armFocusedButtonEnterDefaultAction') < planner.index("cy.focused().type('{enter}')")
    assert telemetry.count(
        "armFocusedButtonEnterDefaultAction($control[0], 'planner telemetry toggle')"
    ) == 2
    assert telemetry.count(".type('{enter}', { force: true })") == 2
    assert telemetry.index("aria-expanded', 'true'") < telemetry.index("aria-expanded', 'false'")
