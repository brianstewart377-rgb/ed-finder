from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'apps' / 'web'
PRODUCT_WORKFLOW = ROOT / '.github' / 'workflows' / 'cypress-parity.yml'
PLAN_SPEC = WEB / 'cypress' / 'e2e' / 'plan.cy.ts'
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
        "cy.get('#results-scope')",
        'Within 500 LY of Achenar · sorted by distance',
        'Within 1,000 LY of Achenar · sorted by distance',
        "cy.get('#search-radius').select('1000')",
        "filters: { distance: { min: 0, max: 1000 }, economy: 'any' }",
        "filters: { distance: { min: 0, max: 500 }, economy: 'any' }",
        "cy.get('#search-radius option[value=\"1000\"]').should('be.disabled')",
        "cy.get('#search-radius-capped')",
        "expect(params.getAll('radius')).to.deep.equal(['1000'])",
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
        "cy.wait('@selectedPoint', { requestTimeout })",
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
def test_explore_map_window_product_coverage_keeps_state_and_single_runtime():
    journey = PRODUCT_SPECS[-1].read_text(encoding='utf-8')
    spatial = PRODUCT_SPECS[1].read_text(encoding='utf-8')
    lab = (WEB / 'cypress' / 'e2e' / 'review-lab.cy.ts').read_text(encoding='utf-8')

    for contract in (
        'const openExploreMap = () => {',
        'const showFinderPanel = () => {',
        '[data-explore-map-open]',
        '[data-finder-panel-hide]',
        "'data-finder-panel-open', 'false'",
        "cy.get('[data-finder-panel-hide]').should('be.focused')",
        "cy.get('@search.all').should('have.length', 4)",
        "cy.location('search').should('eq', retainedSearch)",
    ):
        assert contract in journey
    for contract in (
        '[1280, 800]',
        '[390, 844]',
        '[data-explore-map-window]',
        '[data-result-map-open]',
        "'aria-modal', 'false'",
        "cy.get('#finder-panel').should('not.be.visible')",
        'expect(canvas).to.equal(initialCanvas)',
        "cy.get('[inert]').should('not.exist')",
        'expect($list[0].scrollTop).to.equal(resultScrollTop)',
        "cy.get('@windowRankings.all').should('have.length', 1)",
        "cy.get('@windowSearch.all').should('have.length', 0)",
        'expect(requests).to.deep.equal(settled)',
        "'@windowDensity.all'",
        "'@windowCatalogue.all'",
        "'@windowNebulae.all'",
        "cy.get(alias).should('have.length', count)",
        "'data-camera-bearing', bearing",
        "'data-camera-pitch', pitch",
        "'(prefers-reduced-motion: reduce)'",
        "expect(cameraTransitions).not.to.include('true')",
        'cy.press(Cypress.Keyboard.Keys.ESC)',
        'cy.checkA11y(mapWindow)',
        'data-resize-revision',
    ):
        assert contract in spatial
    assert 'const openReviewMap = () => {' in lab
    assert 'openReviewMap();' in lab
    assert 'WEBGL_lose_context' in lab
    assert "'data-scene-target-count', '0'" in lab


@pytest.mark.unit
def test_explore_map_concept_has_measured_product_layout_and_popout_evidence():
    def normalized(source):
        return re.sub(r',(?=\))', '', re.sub(r'\s+', '', source))

    spatial = PRODUCT_SPECS[1].read_text(encoding='utf-8')
    journey = PRODUCT_SPECS[-1].read_text(encoding='utf-8')
    compact = normalized(spatial)

    for contract in (
        'const assertMapWindowLayout = (width: number, height: number) => {',
        "expect(window.scrollHeight, 'window has no inner scrollbar').to.be.at.most( window.clientHeight, );",
        "expect(content.scrollHeight, 'map content has no inner scrollbar').to.be.at.most(content.clientHeight)",
        "expect(bounds.bottom, 'window bottom fits viewport').to.be.at.most(height + 1)",
        'width < 700 ? height * 0.6 : bounds.height * 0.75',
        "expect(controls.top, 'camera controls sit over the canvas').to.be.at.least(canvas.top)",
        "expect(controls.bottom, 'camera controls end inside the canvas').to.be.at.most(canvas.bottom)",
        "expect(controls.left, 'camera controls start inside the canvas').to.be.at.least(canvas.left)",
        "expect(document.documentElement.scrollWidth, 'page has no horizontal overflow') .to.be.at.most(document.documentElement.clientWidth)",
        'cy.viewport(768, 800)',
        'product/explore-map-full-window-${Cypress.browser.name}-${width}x${height}',
        'product/explore-map-finder-hidden-${Cypress.browser.name}-${width}x${height}',
        "'Achenar · Galaxy map'",
        "cy.contains(`${mapWindow} button`, /^Galaxy$/).click(",
        "cy.contains(`${mapWindow} button`, /^Local$/).click(",
        'Centre on Achenar',
        "cy.get('[data-galaxy-region-option]').should('have.length', 42)",
        "cy.get('#explore-region-picker').select('18'",
        "cy.get('[data-map-regions-trigger]').should('be.focused')",
        "cy.get('[data-map-sources-trigger]').should('be.focused')",
        "'contain.text', 'exact catalogue coordinates'",
        "'contain.text', 'pinned in-game source'",
        "cy.get('[data-finder-panel-show]').click(",
        'const layoutRequestCounts = new Map<string, number>();',
        'layoutRequestCounts.set(alias, requests.length)',
        'for (const [alias, count] of layoutRequestCounts)',
        "cy.get(alias).should('have.length', count)",
    ):
        assert normalized(contract) in compact

    # The same numerical layout contract applies with the Finder shown and hidden.
    assert spatial.count('assertMapWindowLayout(width, height);') >= 2
    for tool in ('regions', 'sources'):
        assert f"cy.get('[data-map-{tool}-panel]')" in spatial
        assert f"cy.get('[data-map-{tool}-panel]').should('not.exist')" in spatial

    compact_journey = normalized(journey)
    for contract in (
        'const openMapRegions = () => {',
        'const closeMapRegions = () => {',
        "cy.get(`${mapWindowSelector} h2`).should('have.text', 'Galaxy map')",
        "cy.contains(`${mapWindowSelector} button`, /^Local$/) .should('be.disabled') .and('have.attr', 'aria-describedby')",
        'Select a system to use the Local camera preset.',
        "cy.contains(`${mapWindowSelector} a`, 'Inspect Achenar') .should('have.attr', 'href') .and('include', 'system=10477373803000')",
        "cy.contains(`${mapWindowSelector} a`, 'Inspect Achenar').click(",
        "cy.contains(`${mapWindowSelector} a`, 'Plan here').should('be.visible')",
        "'contain.text', 'EDAstro / CMDR Orvidius'",
    ):
        assert normalized(contract) in compact_journey


@pytest.mark.unit
def test_plan_product_journey_covers_review_focus_and_draft_export_import_reload():
    journey = PLAN_SPEC.read_text(encoding='utf-8')

    for contract in (
        "const reviewDialog = '[data-review-export]'",
        "cy.contains('button', /^Review & export$/)\n        .focus()\n        .click()",
        "'have.attr', 'aria-modal', 'false'",
        '[data-review-kind="build"]',
        '[data-review-kind="unknown-slot"][data-body-ref="star-a"][data-slot-kind="orbital"]',
        '[data-review-kind="prediction"][data-body-ref="planet-1"]',
        "cy.get(systemTab).should('have.attr', 'aria-selected', 'true')",
        "cy.get(orderTab).should('have.attr', 'aria-selected', 'true')",
        "cy.get(reviewDialog).should('be.visible')",
        ".should('be.focused')",
        "cy.checkA11y(reviewDialog)",
        "cy.press(Cypress.Keyboard.Keys.ESC)",
        "cy.get(reviewDialog).should('not.exist')",
        "cy.contains('button', /^Review & export$/).should('be.focused')",
        ".contains('button', /^Export DRAFT plan$/)",
        ".should('have.attr', 'aria-label', 'Export DRAFT plan')",
        'expect(draftFilename).to.equal(`colony-plan-DRAFT-${systemId}.json`)',
        "expect(draftFilename).to.contain('DRAFT')",
        "expect(exported.schema).to.equal('cpe_plan_export_v1')",
        'exported.sites.map((site: { site_id: string }) => site.site_id)',
        'cy.readFile(draftPath, null).should((contents) => {',
        'const exported = JSON.parse(contents.toString())',
        'PLAN_DRAFT_PATH: draftPath',
        "const draftPath = `${Cypress.config('downloadsFolder')}/colony-plan-DRAFT-${systemId}.json`",
        "cy.contains('button', /^Abandon plan$/).click()",
        "cy.get('input[aria-label=\"Import plan file\"]').selectFile(draftPath, {",
        "cy.get('@confirmPlan').should('have.been.calledTwice')",
        'cy.reload()',
        "{ name: 'prefers-reduced-motion', value: 'reduce' }",
        "expect(style.animationName).to.equal('none')",
        "expect(style.transitionDuration).to.equal('0s')",
        '[1280, 900]',
        '[390, 844]',
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

    for path in (*PRODUCT_SPECS, PLAN_SPEC):
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
