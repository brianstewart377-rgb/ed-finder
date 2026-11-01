from pathlib import Path
import re

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
        "const visitExplore = (path = '/explore')",
        "cy.intercept('GET', '/api/local/autocomplete*')",
        "cy.intercept('POST', '/api/local/search')",
        'data-system-result',
        'data-last-picked-id64',
        '9007199254740993',
        'data-resize-revision',
        'initialCanvas',
        '__productRuntimeFailures',
        'cy.injectAxe()',
        'cy.checkA11y()',
        'cy.screenshot(',
    ):
        assert contract in journey

    assert re.search(
        r"cy\.location\('pathname', \{ timeout: \d+_?\d* \}\)\.should\('eq', '/inspect'\)",
        journey,
    )


@pytest.mark.unit
def test_f4_product_journey_covers_fixture_ranking_and_url_owned_selection():
    journey = PRODUCT_SPECS[-1].read_text(encoding='utf-8')

    for contract in (
        'tests/test_seed_cypress_v3_generation.py',
        'FLEXIBLE_B_FIXTURE_ROWS',
        'EXPECTED_WIDE_ARCHETYPES',
        'assertRankingsRequest',
        'assertFlexiblePage',
        'assertRetainedSelection',
        "'min_development_score'",
        "min_score: minimumTier === 'B' ? '60' : '76'",
        "limit: '1'",
        'offset: String(offset)',
        'Best Colony Potential:',
        'Primary: Flexible Multi-Role Colony;',
        'Secondary:',
        'Fit confidence: moderate',
        "fitLabel: 'Clear fit'",
        "cy.intercept('GET', `/api/v1/systems/${selectedId}`).as('selectedPoint')",
        "cy.wait('@selectedPoint')",
        'window.localStorage.clear()',
        'window.sessionStorage.clear()',
        'from: copiedExploreQuery',
        "cy.contains('a', 'Open in Explore').click()",
        "cy.get('[data-testid=\"system-detail-modal\"]').should('not.exist')",
        'cy.go(state.direction)',
        'assertRankingsRequest(state.offset, state.tier)',
        '[1280, 800]',
        '[390, 844]',
        'disableTimersAndAnimations: true',
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
