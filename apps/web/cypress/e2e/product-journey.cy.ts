import { GALAXY_REGION_NAMES } from '../../src/lib/spatial/galaxy-regions';
import type {
  RankingIdentity,
  SystemArchetypeExplanationResponse,
} from '../../src/lib/api/generated/types.gen';

type ProductWindow = Window & { __productRuntimeFailures?: string[] };

const readySelector = '[role="status"][data-renderer-state="ready"]';
const canvasSelector = 'canvas[data-spatial-canvas]';
const requestTimeout = 20_000;
const ARCHETYPE_KEYS = [
  'paradise',
  'mining_hub',
  'manufacturing_hub',
  'megacomplex',
  'research_hub',
  'stronghold',
  'population_capital',
  'flexible',
] as const;

const visitExplore = (path = '/explore') => {
  cy.intercept('GET', '/api/local/autocomplete*').as('autocomplete');
  cy.intercept('POST', '/api/local/search').as('search');
  cy.visit(path, {
    onBeforeLoad(window) {
      const productWindow = window as ProductWindow;
      productWindow.__productRuntimeFailures = [];
      window.addEventListener('error', () => {
        productWindow.__productRuntimeFailures?.push('error');
      });
      window.addEventListener('unhandledrejection', () => {
        productWindow.__productRuntimeFailures?.push('unhandledrejection');
      });
    },
  });
};

const assertSpatialResultsReady = () => {
  cy.get(readySelector, { timeout: 20_000 }).should('be.visible');
  cy.get('.spatial-canvas')
    .invoke('attr', 'data-scene-target-count')
    .then((count) => expect(Number(count)).to.be.greaterThan(0));
};

// URL reads use browser automation, which can stall while the scene renders.
// Wait on DOM readiness first, then allow the URL read its own retry window.
const waitForExploreSettled = () => {
  cy.get('.results-panel', { timeout: 20_000 }).should(
    'have.attr',
    'aria-busy',
    'false',
  );
  cy.get(`.map-panel ${readySelector}`, { timeout: 20_000 }).should(
    'be.visible',
  );
  cy.get('.map-panel .spatial-canvas', { timeout: 20_000 }).should(
    'have.attr',
    'data-camera-transition-active',
    'false',
  );
};

const waitForInspectSettled = () => {
  cy.get('.inspect-page [data-system-id64]', { timeout: 20_000 }).should(
    'have.attr',
    'aria-busy',
    'false',
  );
  cy.get(`.inspect-page ${readySelector}`, { timeout: 20_000 }).should(
    'be.visible',
  );
};

const keyboardChooseAnchor = (query: string) => {
  cy.get('#system-search').clear().type(query);
  cy.wait('@autocomplete').its('response.statusCode').should('eq', 200);
  cy.get('[role="listbox"] [role="option"]', { timeout: 10_000 }).should(
    'have.length.greaterThan',
    0,
  );
  cy.get('#system-search').type('{downArrow}{enter}');
  cy.wait('@search').its('response.statusCode').should('eq', 200);
};

// PostgreSQL fixture-output authority: tests/test_seed_cypress_v3_generation.py,
// EXPECTED_FLEXIBLE_B_ROWS / EXPECTED_SUMMARY / EXPECTED_WIDE_ARCHETYPES and
// EXPECTED_B_FLOOR_ORDER. All eight scores are pinned there already. The best
// other non-Flexible scores are Research Hub 82, Stronghold 74 and Stronghold
// 57; each Flexible score clears its rival by >= 3 (section 9, 2026-10-31).
const FLEXIBLE_B_FIXTURE_ROWS = [
  {
    id64: '9007199254740993',
    name: 'V3 Lossless Reach',
    score: 100,
    tier: 'S',
    overall: 100,
    confidence: 0.8665,
    completeness: 0.6481,
    secondary: 'Research Hub',
    rival: 'research_hub',
    rivalScore: 82,
    fitLabel: 'Clear fit',
    evidence: 'Fit confidence 87%; evidence 65% complete',
  },
  {
    id64: '10477373803000',
    name: 'Achenar',
    score: 100,
    tier: 'S',
    overall: 100,
    confidence: 0.8486,
    completeness: 0.6356,
    secondary: 'Stronghold',
    rival: 'stronghold',
    rivalScore: 74,
    fitLabel: 'Clear fit',
    evidence: 'Fit confidence 85%; evidence 64% complete',
  },
  {
    id64: '158872029',
    name: 'HD 38179',
    score: 75,
    tier: 'B',
    overall: 75,
    confidence: 0.803,
    completeness: 0.631,
    secondary: 'Stronghold',
    rival: 'stronghold',
    rivalScore: 57,
    fitLabel: 'Clear fit',
    evidence: 'Fit confidence 80%; evidence 63% complete',
  },
] as const;

const assertFinderUrl = (
  archetype: 'any' | 'flexible',
  offset: number,
  selected: string | null,
  minimumTier: 'B' | 'A' = 'B',
  overlay = false,
) => {
  waitForExploreSettled();
  cy.location('pathname', { timeout: 15_000 }).should('eq', '/explore');
  cy.location('search', { timeout: 15_000 }).should((search) => {
    const params = new URLSearchParams(search);
    expect(params.get('archetype')).to.equal(
      archetype === 'any' ? null : archetype,
    );
    expect(params.get('min-tier')).to.equal(
      archetype === 'any' || minimumTier === 'B' ? null : minimumTier,
    );
    expect(params.get('page_size')).to.equal('1');
    expect(params.get('offset')).to.equal(offset === 0 ? null : String(offset));
    expect(params.getAll('selected')).to.deep.equal(selected ? [selected] : []);
    expect(params.getAll('system')).to.deep.equal(
      overlay && selected ? [selected] : [],
    );
  });
  cy.get(`input[type="radio"][value="${archetype}"]`).should('be.checked');
  if (archetype === 'any') cy.get('.minimum-tier').should('not.exist');
  else cy.get('.minimum-tier select').should('have.value', minimumTier);
  cy.get('.page-size input').should('have.value', '1');
};

const assertRankingsRequest = (
  offset: number,
  minimumTier: 'B' | 'A' = 'B',
) => {
  const expected = FLEXIBLE_B_FIXTURE_ROWS[offset];
  return cy
    .wait('@rankings', { requestTimeout })
    .then(({ request, response }) => {
      const params = new URL(request.url).searchParams;
      expect(Object.fromEntries(params)).to.deep.equal({
        archetype: 'flexible',
        min_score: minimumTier === 'B' ? '60' : '76',
        limit: '1',
        offset: String(offset),
      });
      expect(response?.statusCode).to.equal(200);
      expect(response?.body).to.include({
        archetype: 'flexible',
        count: 1,
        total: minimumTier === 'B' ? 3 : 2,
        is_truncated: false,
      });
      expect(response?.body.results).to.have.length(1);
      // Cypress's JSON decoder cannot preserve the unsafe integer ID64. Its
      // exact identity is checked on the DOM and URL, never rounded here.
      expect(response?.body.results[0]).to.include({
        name: expected.name,
        score: expected.score,
        tier: expected.tier,
        selected_archetype: 'flexible',
        primary_archetype: 'flexible',
        secondary_archetype: expected.rival,
        confidence: expected.confidence,
        completeness: expected.completeness,
        overall_development_potential: expected.overall,
        rival_archetype: expected.rival,
        rival_score: expected.rivalScore,
      });
    });
};

const assertFlexiblePage = (
  offset: number,
  total = 3,
  selected: string | null = null,
) => {
  const expected = FLEXIBLE_B_FIXTURE_ROWS[offset];
  cy.get('.results-panel').should('have.attr', 'aria-busy', 'false');
  cy.get('[data-system-result]').should('have.length', 1);
  cy.get(`[data-system-result="${expected.id64}"]`).within(() => {
    cy.get('.result-title').should('contain.text', expected.name);
    cy.get('.selected-fit')
      .should(
        'contain.text',
        `Flexible Multi-Role Colony fit: ${expected.score}`,
      )
      .find('[data-tier]')
      .should('have.attr', 'data-tier', expected.tier)
      .and('have.text', `Tier ${expected.tier}`)
      .and('have.css', 'white-space', 'nowrap');
    cy.get('.overall-potential')
      .should('contain.text', `Best Colony Potential: ${expected.overall}`)
      .find('[data-tier]')
      .should('not.exist'); // Slice 1b has not supplied best_tier.
    cy.get('.classification-types')
      .should('contain.text', 'Primary: Flexible Multi-Role Colony;')
      .and('contain.text', `Secondary: ${expected.secondary}`);
    cy.get('.fit-label').should('have.text', expected.fitLabel);
    cy.get('.evidence-badge').should('have.text', 'Fit confidence: moderate');
    cy.get('.evidence-description').should('have.text', expected.evidence);
    cy.get('[data-result-select]').should(
      'have.attr',
      'aria-pressed',
      String(selected === expected.id64),
    );
  });
  cy.get('.ranking-summary').should(
    'contain.text',
    `Showing 1 of ${total} (results ${offset + 1}–${offset + 1})`,
  );
  assertSpatialResultsReady();
  cy.get('.spatial-canvas').should(
    'have.attr',
    'data-system-target-count',
    selected && selected !== expected.id64 ? '2' : '1',
  );
};

const assertAnyPage = (selected: string | null) => {
  cy.wait('@search', { requestTimeout }).then(({ request, response }) => {
    expect(request.body).to.deep.equal({
      galaxy_wide: true,
      sort_by: 'development',
      size: 1,
      from: 0,
    });
    expect(request.body).not.to.have.property('min_development_score');
    expect(response?.statusCode).to.equal(200);
    expect(response?.body).to.include({ total: 3, count: 1 });
    expect(response?.body.results[0].name).to.equal('V3 Lossless Reach');
  });
  assertFinderUrl('any', 0, selected);
  cy.contains('label', 'Minimum tier').should('not.exist');
  cy.get('.results-panel').should('have.attr', 'aria-busy', 'false');
  cy.get('[data-system-result]').should('have.length', 1);
  cy.get('[data-system-result="9007199254740993"]').within(() => {
    cy.get('.selected-fit, .fit-label').should('not.exist');
    cy.get('.evidence-badge').should(
      'have.text',
      'Evidence confidence: moderate',
    );
    cy.get('.evidence-description').should(
      'have.text',
      'Evidence confidence 82%; evidence 65% complete',
    );
    cy.get('[data-result-select]').should(
      'have.attr',
      'aria-pressed',
      String(selected === '9007199254740993'),
    );
  });
  cy.get('.ranking-summary').should(
    'contain.text',
    'Showing 1 of 3 (results 1–1)',
  );
  assertSpatialResultsReady();
  cy.get('.spatial-canvas').should(
    'have.attr',
    'data-system-target-count',
    '1',
  );
};

const assertRetainedSelection = () => {
  const selected = FLEXIBLE_B_FIXTURE_ROWS[0];
  cy.get('[data-testid="selected-system-context"]').should(
    'contain.text',
    selected.id64,
  );
  cy.get(`[data-selected-system-card="${selected.id64}"]`)
    .should('have.length', 1)
    .and('contain.text', selected.name);
  cy.get(`[data-map-label-key="system:${selected.id64}"]`, { timeout: 20_000 })
    .should('have.length', 1)
    .and('be.visible')
    .and('have.attr', 'data-map-label-selected', 'true')
    .and('contain.text', selected.name);
};

const captureFinder = (state: 'any' | 'flexible' | 'flexible-explanation') => {
  cy.get('[data-region-resource-state="ready"]', { timeout: 20_000 }).should(
    'contain.text',
    '42/42 regions',
  );
  cy.get('[data-nebula-resource-state="ready"]', { timeout: 20_000 }).should(
    'contain.text',
    '5,842 EDAstro nebula landmarks',
  );
  cy.document().then((document) => {
    const style = document.createElement('style');
    style.textContent =
      '*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}';
    document.head.append(style);
  });
  for (const [width, height] of [
    [1280, 800],
    [390, 844],
  ]) {
    cy.viewport(width, height);
    cy.get('.results-panel').scrollIntoView();
    cy.get('.spatial-canvas', { timeout: 20_000 }).should(
      'have.attr',
      'data-camera-transition-active',
      'false',
    );
    cy.screenshot(
      `product/finder-${state}-${Cypress.browser.name}-${width}x${height}`,
      {
        capture: 'viewport',
        overwrite: true,
        disableTimersAndAnimations: true,
      },
    );
    if (state === 'flexible-explanation') {
      cy.get('[data-system-result]').screenshot(
        `product/finder-expanded-card-${Cypress.browser.name}-${width}x${height}`,
        { overwrite: true, disableTimersAndAnimations: true },
      );
    }
  }
  cy.viewport(1280, 800);
};

describe('V3 Explore to Inspect product checkpoint', () => {
  it('ranks the pinned Flexible B corpus, retains URL selection and restores Finder history', () => {
    const selectedId = FLEXIBLE_B_FIXTURE_ROWS[0].id64;
    let copiedExploreUrl = '';
    let copiedExploreQuery = '';
    let rankingIdentity: RankingIdentity;
    cy.viewport(1280, 800);
    // Observe real API traffic only: the Product lane never supplies a response.
    cy.intercept('GET', '/api/archetypes/rankings*').as('rankings');
    cy.intercept('GET', '/api/archetypes/system/*/explanation*').as(
      'archetypeExplanation',
    );
    cy.intercept('GET', /\/api\/archetypes\/system\/\d+(?:\?.*)?$/).as(
      'legacyArchetype',
    );
    visitExplore('/explore?page_size=1');

    // Section 7 steps 1–3: Any is floor-free; keyboard selection commits the
    // default B floor and the bounded one-row ranking request.
    assertAnyPage(null);
    captureFinder('any');
    cy.get('input[type="radio"][value="flexible"]')
      .focus()
      .should('be.focused');
    cy.press(Cypress.Keyboard.Keys.SPACE);
    cy.get('input[type="radio"][value="flexible"]').should('be.checked');
    assertRankingsRequest(0).then(({ response }) => {
      rankingIdentity = response?.body.ranking;
    });
    assertFinderUrl('flexible', 0, null);
    waitForExploreSettled();
    cy.location('search', { timeout: 15_000 }).should(
      'eq',
      '?archetype=flexible&page_size=1',
    );
    assertFlexiblePage(0);

    // F4e: opening the sibling disclosure fetches the real, version-pinned
    // explanation lazily without selecting the card. The endpoint verifies
    // recomputation against all eight stored archetype scores and tiers.
    const card = `[data-system-result="${selectedId}"]`;
    const explanationRegion = `${card} [data-archetype-explanation]`;
    cy.get('@archetypeExplanation.all').should('have.length', 0);
    cy.get(`${card} [data-archetype-explanation-toggle]`)
      .should('have.attr', 'aria-expanded', 'false')
      .click()
      .should('have.attr', 'aria-expanded', 'true');
    cy.wait('@archetypeExplanation', { requestTimeout }).then(
      ({ request, response }) => {
        const url = new URL(request.url);
        expect(url.pathname).to.equal(
          `/api/archetypes/system/${selectedId}/explanation`,
        );
        expect(Object.fromEntries(url.searchParams)).to.deep.equal({
          expected_generation_id: rankingIdentity.derived_generation_id,
          expected_archetype_version: rankingIdentity.archetype_version,
          expected_manifest_sha256: rankingIdentity.archetype_manifest_sha256,
        });
        expect(response?.statusCode).to.equal(200);
        const explanation: SystemArchetypeExplanationResponse = response?.body;
        expect(explanation.ranking).to.deep.equal(rankingIdentity);
        expect(explanation.archetypes.map(({ key }) => key)).to.have.members([
          ...ARCHETYPE_KEYS,
        ]);
        expect(explanation.archetypes).to.have.length(8);
        const flexible = explanation.archetypes.find(
          ({ key }) => key === 'flexible',
        );
        expect(flexible).to.include({
          score: FLEXIBLE_B_FIXTURE_ROWS[0].score,
          tier: FLEXIBLE_B_FIXTURE_ROWS[0].tier,
        });
        cy.get(`${card} .selected-fit`)
          .should(
            'contain.text',
            `Flexible Multi-Role Colony fit: ${flexible?.score}`,
          )
          .find('[data-tier]')
          .should('have.attr', 'data-tier', flexible?.tier);
        for (const entry of explanation.archetypes) {
          cy.get(
            `${explanationRegion} [data-explanation-archetype="${entry.key}"]`,
          ).within(() => {
            cy.get('.explanation-score').should(
              'have.text',
              String(entry.score),
            );
            cy.get('[data-tier]')
              .should('have.attr', 'data-tier', entry.tier)
              .and('have.text', `Tier ${entry.tier}`);
          });
        }
      },
    );
    cy.get(`${explanationRegion} [data-explanation-archetype]`).should(
      ($sections) => {
        expect(
          [...$sections].map((section) => section.dataset.explanationArchetype),
        ).to.have.members([...ARCHETYPE_KEYS]);
      },
    );
    cy.get(`${card} [data-result-select]`).should(
      'have.attr',
      'aria-pressed',
      'false',
    );
    cy.get('@legacyArchetype.all').should('have.length', 0);
    cy.injectAxe();
    cy.checkA11y(explanationRegion);
    captureFinder('flexible-explanation');
    cy.get(`${card} [data-archetype-explanation-toggle]`)
      .click()
      .should('have.attr', 'aria-expanded', 'false');

    // Steps 4–5: the current page owns the results, while selected= owns the
    // retained point independently. All three pages come from PostgreSQL.
    cy.get(`[data-system-result="${selectedId}"] [data-result-select]`).click();
    assertFinderUrl('flexible', 0, selectedId);
    assertRetainedSelection();
    cy.get('[data-testid="system-detail-modal"]').should('not.exist');
    for (const offset of [1, 2]) {
      cy.contains('[aria-label="Result pages"] button', 'Next').click();
      assertRankingsRequest(offset);
      assertFinderUrl('flexible', offset, selectedId);
      assertFlexiblePage(offset, 3, selectedId);
      cy.get(`[data-system-result="${selectedId}"]`).should('not.exist');
      assertRetainedSelection();
      cy.get('[data-testid="system-detail-modal"]').should('not.exist');
    }
    cy.contains('[aria-label="Result pages"] button', 'Next').should(
      'be.disabled',
    );
    waitForExploreSettled();
    cy.location({ timeout: 15_000 }).then(({ pathname, search }) => {
      copiedExploreUrl = `${pathname}${search}`;
      copiedExploreQuery = search.slice(1);
      const inspect = `/inspect?${new URLSearchParams({
        system: selectedId,
        from: copiedExploreQuery,
      })}`;
      cy.get('[data-testid="selected-system-context"] a')
        .first()
        .should('have.attr', 'href', inspect);
      cy.get(`[data-selected-system-card="${selectedId}"] a`)
        .first()
        .should('have.attr', 'href', inspect);
    });

    // F4 design section 7, step 5: a full document load drops in-memory
    // result/camera/query state and both persistence stores. The facade now
    // reads the V3 system route to reconstruct the omitted selected point.
    cy.intercept('GET', `/api/v1/systems/${selectedId}`).as('selectedPoint');
    cy.clearLocalStorage();
    cy.window().then((window) => window.sessionStorage.clear());
    cy.then(() => {
      cy.visit(copiedExploreUrl, {
        onBeforeLoad(window) {
          window.localStorage.clear();
          window.sessionStorage.clear();
        },
      });
    });
    assertRankingsRequest(2);
    cy.wait('@selectedPoint', { requestTimeout })
      .its('response.statusCode')
      .should('eq', 200);
    assertFinderUrl('flexible', 2, selectedId);
    assertFlexiblePage(2, 3, selectedId);
    cy.get(`[data-system-result="${selectedId}"]`).should('not.exist');
    assertRetainedSelection();
    cy.get('[data-testid="system-detail-modal"]').should('not.exist');
    cy.then(() => {
      const inspect = `/inspect?${new URLSearchParams({
        system: selectedId,
        from: copiedExploreQuery,
      })}`;
      cy.get('[data-testid="selected-system-context"] a')
        .first()
        .should('have.attr', 'href', inspect)
        .click();
    });
    waitForInspectSettled();
    cy.location('pathname', { timeout: 15_000 }).should('eq', '/inspect');
    cy.location('search', { timeout: 15_000 }).should((search) => {
      const params = new URLSearchParams(search);
      expect(params.get('system')).to.equal(selectedId);
      expect(params.get('from')).to.equal(copiedExploreQuery);
    });
    cy.get(`[data-system-id64="${selectedId}"]`, { timeout: 20_000 }).should(
      'contain.text',
      'V3 Lossless Reach',
    );
    cy.contains('a', 'Open in Explore').click();
    assertRankingsRequest(2);
    assertFinderUrl('flexible', 2, selectedId, 'B', true);
    assertFlexiblePage(2, 3, selectedId);
    assertRetainedSelection();
    cy.get('[data-testid="system-detail-modal"]').should('be.visible');
    cy.get('[aria-label="Close system detail"]').click();
    assertFinderUrl('flexible', 2, selectedId);
    cy.get('[data-testid="system-detail-modal"]').should('not.exist');
    assertRetainedSelection();
    cy.injectAxe();
    cy.checkA11y();

    // Step 6: picker, a non-default tier, and pagination each create history.
    // Back/Forward must refetch the request encoded by every restored URL;
    // selection survives Any, reranking and pages that omit the selected row.
    cy.get('input[type="radio"][value="any"]').check();
    assertAnyPage(selectedId);
    assertRetainedSelection();
    cy.get('input[type="radio"][value="flexible"]').check();
    assertRankingsRequest(0);
    assertFinderUrl('flexible', 0, selectedId);
    assertFlexiblePage(0, 3, selectedId);
    cy.get('.minimum-tier select').select('A');
    assertRankingsRequest(0, 'A');
    assertFinderUrl('flexible', 0, selectedId, 'A');
    assertFlexiblePage(0, 2, selectedId);
    cy.contains('[aria-label="Result pages"] button', 'Next').click();
    assertRankingsRequest(1, 'A');
    assertFinderUrl('flexible', 1, selectedId, 'A');
    assertFlexiblePage(1, 2, selectedId);
    assertRetainedSelection();

    const restoredStates = [
      {
        direction: 'back',
        archetype: 'flexible',
        offset: 0,
        tier: 'A',
        total: 2,
      },
      {
        direction: 'back',
        archetype: 'flexible',
        offset: 0,
        tier: 'B',
        total: 3,
      },
      { direction: 'back', archetype: 'any', offset: 0, tier: 'B', total: 3 },
      {
        direction: 'back',
        archetype: 'flexible',
        offset: 2,
        tier: 'B',
        total: 3,
      },
      {
        direction: 'forward',
        archetype: 'any',
        offset: 0,
        tier: 'B',
        total: 3,
      },
      {
        direction: 'forward',
        archetype: 'flexible',
        offset: 0,
        tier: 'B',
        total: 3,
      },
      {
        direction: 'forward',
        archetype: 'flexible',
        offset: 0,
        tier: 'A',
        total: 2,
      },
      {
        direction: 'forward',
        archetype: 'flexible',
        offset: 1,
        tier: 'A',
        total: 2,
      },
    ] as const;
    for (const state of restoredStates) {
      cy.go(state.direction);
      if (state.archetype === 'any') assertAnyPage(selectedId);
      else {
        assertRankingsRequest(state.offset, state.tier);
        assertFinderUrl(state.archetype, state.offset, selectedId, state.tier);
        assertFlexiblePage(state.offset, state.total, selectedId);
      }
      assertRetainedSelection();
      cy.get('[data-testid="system-detail-modal"]').should('not.exist');
    }

    // Step 7: desktop/phone evidence for the selected card and retained point.
    cy.injectAxe();
    cy.checkA11y();
    captureFinder('flexible');
  });

  it('discovers, selects, spatially picks, inspects, resizes and remounts real systems', () => {
    let initialCanvas!: HTMLCanvasElement;
    let originatingExploreQuery = '';
    cy.viewport(1280, 800);
    cy.intercept('GET', '/api/archetypes/rankings*').as('idleRankings');
    visitExplore();
    cy.get('.results-panel').should('have.attr', 'aria-busy', 'false');
    cy.get('#results-title').should('contain.text', 'Systems');
    cy.contains(
      '.results-panel',
      'Search for a system above to see what is near it.',
    ).should('be.visible');
    cy.get('[data-system-result]').should('not.exist');
    cy.get('@search.all').should('have.length', 0);
    cy.get('@idleRankings.all').should('have.length', 0);
    keyboardChooseAnchor('Achenar');
    cy.get('#results-title').should('contain.text', 'Near Achenar');
    cy.get('[data-system-result="10477373803000"] [data-result-select]', {
      timeout: 15_000,
    })
      .should('be.focused')
      .and('have.attr', 'aria-pressed', 'true');
    cy.get('h1')
      .should('contain.text', 'Chart a promising system')
      .and('be.visible');
    cy.get('[data-system-result]', { timeout: 15_000 }).should(
      'have.length.greaterThan',
      0,
    );
    assertSpatialResultsReady();
    cy.get('[data-region-resource-state="ready"]', { timeout: 20_000 }).should(
      'contain.text',
      '42/42 regions',
    );
    cy.get('[data-nebula-resource-state="ready"]', { timeout: 20_000 })
      .should('contain.text', '5,842 EDAstro nebula landmarks')
      .and('contain.text', 'EDAstro / CMDR Orvidius')
      .and('contain.text', 'source CSV');
    cy.get('[data-galaxy-region-option]').should('have.length', 42);
    cy.get('.spatial-canvas')
      .should('have.attr', 'data-rendered-layer-ids')
      .and('contain', 'galaxy-regions')
      .and('contain', 'galaxy-nebulae')
      .and('contain', 'finder-systems');
    cy.get('.spatial-canvas')
      .invoke('attr', 'data-system-target-count')
      .then((count) => expect(Number(count)).to.be.greaterThan(0));
    cy.contains('button', 'All 42 regions').click();
    cy.get('[data-map-label-kind="region"]', { timeout: 20_000 })
      .should('have.length', 42)
      .then(($labels) => {
        const names = $labels
          .toArray()
          .map((label) => label.textContent?.trim())
          .sort();
        expect(names).to.deep.equal([...GALAXY_REGION_NAMES].sort());
      });
    cy.get('#explore-region-picker').select('18');
    cy.get('[data-selected-region-id="18"]').should(
      'contain.text',
      'Inner Orion Spur',
    );
    cy.get(canvasSelector).then(([canvas]) => {
      initialCanvas = canvas as HTMLCanvasElement;
      const initialRevision = Number(
        initialCanvas.getAttribute('data-resize-revision'),
      );
      cy.viewport(1180, 720);
      cy.get(canvasSelector).should(([resizedCanvas]) => {
        expect(resizedCanvas).to.equal(initialCanvas);
        expect(
          Number(resizedCanvas.getAttribute('data-resize-revision')),
        ).to.be.greaterThan(initialRevision);
      });
      cy.get(readySelector).should('be.visible');
    });
    cy.viewport(1280, 800);
    cy.get(canvasSelector).should(([restoredCanvas]) => {
      expect(restoredCanvas).to.equal(initialCanvas);
    });

    cy.get('[data-testid="selected-system-context"]')
      .should('contain.text', '10477373803000')
      .and('be.visible');

    let keyboardSelectedId!: string;
    cy.get('[data-system-result]')
      .eq(1)
      .then(($result) => {
        keyboardSelectedId = $result.attr('data-system-result') ?? '';
        expect(keyboardSelectedId).to.match(/^\d+$/);
        expect(keyboardSelectedId).not.to.equal('10477373803000');
        cy.get(
          `[data-system-result="${keyboardSelectedId}"] [data-result-select]`,
        )
          .focus()
          .should('be.focused')
          .type('{enter}');
        cy.get('[data-testid="selected-system-context"]').should(
          'contain.text',
          keyboardSelectedId,
        );
        cy.get(
          `[data-system-result="${keyboardSelectedId}"] [data-result-select]`,
        ).should('have.attr', 'aria-pressed', 'true');
      });
    cy.get('[data-system-result="10477373803000"] [data-result-select]')
      .focus()
      .type('{enter}')
      .should('have.attr', 'aria-pressed', 'true');
    cy.then(() => {
      cy.get(
        `[data-system-result="${keyboardSelectedId}"] [data-result-select]`,
      ).should('have.attr', 'aria-pressed', 'false');
    });

    cy.get('.spatial-canvas', { timeout: 20_000 }).should(($canvas) => {
      expect($canvas.attr('data-camera-transition-active')).to.equal('false');
      expect($canvas.attr('data-last-settled-focus-id64')).to.equal(
        '10477373803000',
      );
    });

    cy.get('[data-map-label-key="system:10477373803000"]', {
      timeout: 20_000,
    })
      .should('be.visible')
      .then(($label) => {
        const anchorX = Number($label.attr('data-map-label-anchor-x'));
        const anchorY = Number($label.attr('data-map-label-anchor-y'));
        expect(Number.isFinite(anchorX)).to.equal(true);
        expect(Number.isFinite(anchorY)).to.equal(true);
        expect(anchorX).to.be.greaterThan(0);
        expect(anchorY).to.be.greaterThan(0);
        cy.get(canvasSelector).click(anchorX, anchorY);
      });
    // The timeout must be on cy.get (its retry window covers the chained
    // assertions); passing it as a 4th arg to .should() is silently ignored and
    // falls back to the 4s default, which a firefox WebGL pick can exceed.
    cy.get('.selection-status', { timeout: 20_000 })
      .should('have.attr', 'data-last-picked-id64', '10477373803000')
      .and('contain.text', 'Spatial pick selected');
    cy.get('[data-system-result="10477373803000"] [data-result-select]').should(
      'have.attr',
      'aria-pressed',
      'true',
    );
    cy.get('[data-result-select][aria-pressed="true"]').should(
      'have.length',
      1,
    );
    cy.get('[data-selected-system-card="10477373803000"]')
      .should('be.visible')
      .and('contain.text', 'Achenar')
      .and('contain.text', 'Primary star');
    cy.get('[data-commander-history-toggle]')
      .should('have.attr', 'aria-pressed', 'false')
      .click()
      .should('have.attr', 'aria-pressed', 'true');

    cy.injectAxe();
    cy.checkA11y();
    cy.document().then((document) => {
      const style = document.createElement('style');
      style.textContent =
        '*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}';
      document.head.append(style);
    });
    cy.screenshot(`product/explore-achenar-${Cypress.browser.name}-1280x800`, {
      capture: 'viewport',
      overwrite: true,
    });

    // F4 design section 6, "Detail overlay": Inspect carries the originating
    // Explore query in `from` so its return links restore the Finder state.
    waitForExploreSettled();
    cy.location('search', { timeout: 15_000 }).then((search) => {
      originatingExploreQuery = search.slice(1);
    });
    cy.get('[data-system-result="10477373803000"] .inspect-link').click();
    waitForInspectSettled();
    cy.location('pathname', { timeout: 15_000 }).should('eq', '/inspect');
    cy.location('search', { timeout: 15_000 }).should((search) => {
      const params = new URLSearchParams(search);
      expect(params.get('system')).to.equal('10477373803000');
      expect(params.get('from')).to.equal(originatingExploreQuery);
    });
    cy.get('[data-system-id64="10477373803000"]', { timeout: 20_000 })
      .should('contain.text', 'Achenar')
      .and('contain.text', '10477373803000');
    cy.contains('h2', 'Explore Achenar').should('be.visible');
    cy.contains(
      'Body classes, radii, arrival distances, and known ring state come from the catalogue.',
    ).should('be.visible');
    cy.get('[aria-label="System camera controls"]').should('be.visible');
    cy.get('[aria-label="System bodies"] button')
      .should('have.length.greaterThan', 0)
      .first()
      .click()
      .should('have.attr', 'aria-pressed', 'true');
    cy.get('[data-selected-body-id]').should('be.visible');
    cy.injectAxe();
    cy.checkA11y();

    cy.viewport(820, 640);
    cy.contains('a', 'Back to Explore').click();
    waitForExploreSettled();
    cy.location('pathname', { timeout: 15_000 }).should('eq', '/explore');
    assertSpatialResultsReady();
    cy.get(canvasSelector).should(([remountedCanvas]) => {
      expect(remountedCanvas).not.to.equal(initialCanvas);
    });
    cy.window().then((window) => {
      expect((window as ProductWindow).__productRuntimeFailures).to.deep.equal(
        [],
      );
    });
  });

  it('opens a real system directly in Inspect from the V3 canonical generation', () => {
    // Release-smoke candidate: one real system page, read only through the
    // generation-pinned V3 routes. The V2-backed /api/system route (absent
    // tables in V3 production) must never be called.
    cy.intercept('GET', '/api/system/*').as('legacySystem');
    cy.intercept('GET', '/api/v1/systems/10477373803000').as('v3System');
    cy.intercept('GET', '/api/v1/systems/10477373803000/bodies').as('v3Bodies');
    cy.intercept('GET', '/api/v1/systems/10477373803000/rings').as('v3Rings');
    cy.intercept('GET', '/api/v1/systems/10477373803000/stations').as(
      'v3Stations',
    );
    cy.intercept('GET', '/api/ratings/v4/systems/10477373803000').as(
      'v4Ratings',
    );
    cy.intercept(
      'GET',
      '/api/ratings/v4/systems/10477373803000/explanation',
    ).as('v4Explanation');
    cy.visit('/inspect?system=10477373803000');
    for (const alias of [
      '@v3System',
      '@v3Bodies',
      '@v3Rings',
      '@v3Stations',
      '@v4Ratings',
    ])
      cy.wait(alias).its('response.statusCode').should('eq', 200);
    cy.get('[data-system-id64="10477373803000"]', { timeout: 20_000 })
      .should('contain.text', 'Achenar')
      .and('contain.text', '10477373803000');
    cy.focused().should('have.prop', 'tagName', 'H1');
    cy.contains('dt', 'Main star').next('dd').should('have.text', 'G2 V');
    cy.contains('dt', 'Bodies returned').next('dd').should('have.text', '41');
    cy.get('[data-unavailable-fields]')
      .should('have.length', 2)
      .each(($row) => expect($row).to.contain.text('Not available yet'));
    cy.get('[aria-label="System bodies"] button')
      .first()
      .should('contain.text', 'Star · G2 V');
    // Ratings V4: all seven economies from the published derived generation,
    // and an explanation fetched only when one is opened.
    cy.get('[data-rating-economy]').should('have.length', 7);
    cy.get('@v4Explanation.all').should('have.length', 0);
    cy.get('[data-rating-economy] .rating-why')
      .first()
      .click()
      .should('have.attr', 'aria-expanded', 'true');
    cy.wait('@v4Explanation').its('response.statusCode').should('eq', 200);
    cy.contains('.rating-explanation dt', 'Evidence known').should(
      'be.visible',
    );
    // Visual evidence for the Inspect ratings section, desktop then phone.
    cy.get('.system-ratings').screenshot(
      `product/inspect-achenar-ratings-${Cypress.browser.name}`,
      { overwrite: true },
    );
    cy.injectAxe();
    cy.checkA11y();
    cy.viewport(375, 812);
    cy.get('.system-ratings').screenshot(
      `product/inspect-achenar-ratings-${Cypress.browser.name}-375w`,
      { overwrite: true },
    );
    cy.viewport(
      Cypress.config('viewportWidth'),
      Cypress.config('viewportHeight'),
    );

    cy.intercept('GET', '/api/v1/systems/4242').as('v3Missing');
    cy.visit('/inspect?system=4242');
    cy.wait('@v3Missing').its('response.statusCode').should('eq', 404);
    cy.contains('h1', 'System not found').should('be.visible');
    cy.get('@legacySystem.all').should('have.length', 0);
  });

  it('preserves an unsafe-sized id64 through API, selection, route, detail and reload', () => {
    const unsafeId = '9007199254740993';
    let originatingExploreQuery = '';
    visitExplore();
    keyboardChooseAnchor('V3 Lossless');

    cy.get('[data-testid="selected-system-context"]').should(
      'contain.text',
      unsafeId,
    );
    waitForExploreSettled();
    cy.location('search', { timeout: 15_000 }).then((search) => {
      originatingExploreQuery = search.slice(1);
    });
    cy.get(`[data-system-result="${unsafeId}"] .inspect-link`).click();
    cy.get(`[data-system-id64="${unsafeId}"]`, { timeout: 20_000 })
      .should('contain.text', 'V3 Lossless Reach')
      .and('contain.text', unsafeId);
    waitForInspectSettled();
    cy.location('search', { timeout: 15_000 }).should((search) => {
      const params = new URLSearchParams(search);
      expect(params.get('system')).to.equal(unsafeId);
      expect(params.get('from')).to.equal(originatingExploreQuery);
    });
    cy.reload();
    cy.get(`[data-system-id64="${unsafeId}"]`, { timeout: 10_000 })
      .should('contain.text', 'V3 Lossless Reach')
      .and('contain.text', unsafeId);
    cy.get('[data-testid="selected-system-context"]', {
      timeout: 10_000,
    }).should('contain.text', unsafeId);
  });
});
