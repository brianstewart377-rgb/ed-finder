from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'apps' / 'web'
PRODUCT_WORKFLOW = ROOT / '.github' / 'workflows' / 'cypress-parity.yml'
PRODUCT_SPECS = (
    WEB / 'cypress' / 'e2e' / 'foundation.cy.ts',
    WEB / 'cypress' / 'e2e' / 'spatial-foundation.cy.ts',
    WEB / 'cypress' / 'e2e' / 'product-journey.cy.ts',
)


@pytest.mark.unit
def test_first_checkpoint_product_journey_keeps_real_v3_browser_coverage():
    workflow = PRODUCT_WORKFLOW.read_text(encoding='utf-8')
    journey = PRODUCT_SPECS[-1].read_text(encoding='utf-8')

    assert 'browser: [chrome, firefox]' in workflow
    assert 'working-directory: apps/web' in workflow
    assert 'pnpm exec cypress run --browser ${{ matrix.browser }}' in workflow

    for contract in (
        "cy.visit('/explore'",
        "cy.intercept('GET', '/api/local/autocomplete*')",
        "cy.intercept('POST', '/api/local/search')",
        'data-system-result',
        'data-last-picked-id64',
        "cy.location('pathname').should('eq', '/inspect')",
        '9007199254740993',
        'data-resize-revision',
        'initialCanvas',
        '__productRuntimeFailures',
        'cy.injectAxe()',
        'cy.checkA11y()',
        'cy.screenshot(',
    ):
        assert contract in journey


@pytest.mark.unit
def test_product_specs_cannot_depend_on_review_lab_runtime_or_synthetic_routes():
    config = (WEB / 'cypress.config.ts').read_text(encoding='utf-8')
    forbidden = (
        'EDFINDER_REVIEW_LAB_RUN',
        'review_main.py',
        'review_environment.py',
        'edfinder-review',
        '/api/review/',
        '__reviewLab',
    )
    violations = []

    for path in PRODUCT_SPECS:
        source = path.read_text(encoding='utf-8')
        assert path.relative_to(WEB).as_posix() in config
        for marker in forbidden:
            if marker in source:
                violations.append(f'{path.relative_to(ROOT)} -> {marker}')

    assert "specPattern: 'cypress/e2e/**/*.cy.ts'" not in config
    assert 'review-lab.cy.ts' not in config
    assert 'review-environment.cy.ts' not in config

    assert not violations, (
        'Normal Product E2E must use the seeded API/apps/web runtime, not '
        'Review Lab markers, routes, or fixtures:\n' + '\n'.join(violations)
    )
