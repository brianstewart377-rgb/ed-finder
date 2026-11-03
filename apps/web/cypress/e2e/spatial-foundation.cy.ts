type SpatialWindow = Window & { __spatialRuntimeFailures?: string[] };

const canvasSelector = 'canvas[data-spatial-canvas]';
const readySelector = '[role="status"][data-renderer-state="ready"]';

const visitFoundation = () => {
  cy.visit('/spatial-foundation', {
    onBeforeLoad(window) {
      const spatialWindow = window as SpatialWindow;
      spatialWindow.__spatialRuntimeFailures = [];
      window.addEventListener('error', () => {
        spatialWindow.__spatialRuntimeFailures?.push('error');
      });
      window.addEventListener('unhandledrejection', () => {
        spatialWindow.__spatialRuntimeFailures?.push('unhandledrejection');
      });
    },
  });
};

const assertRendererReady = () => {
  cy.get(readySelector, { timeout: 20_000 })
    .should('be.visible')
    .invoke('attr', 'data-renderer-backend')
    .should('match', /^(WEBGPU|WEBGL2)$/);
  cy.get(canvasSelector)
    .should('have.length', 1)
    .and('be.visible')
    .then(([canvas]) => {
      expect((canvas as HTMLCanvasElement).width).to.be.greaterThan(0);
      expect((canvas as HTMLCanvasElement).height).to.be.greaterThan(0);
    });
};

describe('non-product spatial runtime foundation', () => {
  it('stays ready through resize, navigation, and remount', () => {
    cy.viewport(1100, 720);
    visitFoundation();
    cy.contains('NON-PRODUCT diagnostic').should('be.visible');
    assertRendererReady();

    cy.get(canvasSelector).then(([firstCanvas]) => {
      const firstRevision = Number(
        firstCanvas.getAttribute('data-resize-revision'),
      );
      cy.viewport(820, 640);
      cy.get(canvasSelector).should(([resizedCanvas]) => {
        expect(
          Number(resizedCanvas.getAttribute('data-resize-revision')),
        ).to.be.greaterThan(firstRevision);
      });
      cy.get(readySelector).should('be.visible');

      cy.contains('a', 'ED-Finder V3').click();
      cy.location('pathname').should('eq', '/');
      cy.go('back');
      cy.location('pathname').should('eq', '/spatial-foundation');
      assertRendererReady();
      cy.get(canvasSelector).should(([remountedCanvas]) => {
        expect(remountedCanvas).not.to.equal(firstCanvas);
      });
    });

    cy.window().then((window) => {
      expect((window as SpatialWindow).__spatialRuntimeFailures).to.deep.equal(
        [],
      );
    });
  });

  it('captures deterministic diagnostic evidence without a product baseline', () => {
    cy.viewport(1280, 720);
    visitFoundation();
    assertRendererReady();
    cy.document().then((document) => {
      const style = document.createElement('style');
      style.textContent =
        '*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}';
      document.head.append(style);
    });
    cy.screenshot(`spatial-foundation/${Cypress.browser.name}-1280x720`, {
      capture: 'viewport',
      overwrite: true,
    });
  });
});

// Normal Product API + real Babylon. The diagnostic route above remains a
// separate foundation check; these cases exercise Explore's window ownership.
for (const [width, height] of [
  [1280, 800],
  [390, 844],
]) {
  it(`preserves the on-demand map and results at ${width}×${height} with reduced motion`, () => {
    const mapWindow = '[data-explore-map-window]';
    const opener = '[data-explore-map-open]';
    // Use the short seeded name that fits the renderer's phone label bounds.
    // Lossless oversized id64s retain their separate full Product journey.
    const selectedId = '10477373803000';
    const selectedResult = `[data-system-result="${selectedId}"]`;
    let initialCanvas: HTMLCanvasElement;
    let resultScrollTop = 0;
    let query = '';
    let bearing = '';
    let pitch = '';
    const cameraTransitions: string[] = [];
    cy.viewport(width, height);
    cy.intercept('GET', '/api/archetypes/rankings*').as('windowRankings');
    cy.intercept('POST', '/api/local/search').as('windowSearch');
    cy.intercept('GET', '/api/map/heatmap*').as('windowDensity');
    cy.intercept('GET', '/api/map/systems*').as('windowCatalogue');
    cy.intercept('GET', '/assets/edastro-mapcharts-nebulae.json').as(
      'windowNebulae',
    );
    cy.intercept('GET', '/api/archetypes/system/*/explanation*').as(
      'windowExplanation',
    );
    cy.visit('/explore?archetype=flexible&page_size=3', {
      onBeforeLoad(window) {
        const matchMedia = window.matchMedia.bind(window);
        window.matchMedia = (query) => {
          const media = matchMedia(query);
          if (query === '(prefers-reduced-motion: reduce)')
            Object.defineProperty(media, 'matches', { value: true });
          return media;
        };
      },
    });
    cy.wait('@windowRankings', { requestTimeout: 20_000 })
      .its('response.statusCode')
      .should('eq', 200);
    cy.get('[data-system-result]').should('have.length', 3);
    cy.get(mapWindow).should('not.exist');
    cy.get(canvasSelector).should('not.exist');
    cy.get('@windowDensity.all').should('have.length', 0);
    cy.get('@windowCatalogue.all').should('have.length', 0);
    cy.get('@windowNebulae.all').should('have.length', 0);
    cy.window().should((window) => {
      expect(
        window.matchMedia('(prefers-reduced-motion: reduce)').matches,
      ).to.equal(true);
    });
    // One real expanded explanation makes the result list scrollable even
    // with this intentionally small three-system Product fixture.
    cy.get(`${selectedResult} [data-archetype-explanation-toggle]`).click();
    cy.wait('@windowExplanation', { requestTimeout: 20_000 })
      .its('response.statusCode')
      .should('eq', 200);
    cy.get(`${selectedResult} [data-result-select]`).click();
    cy.get('.result-list')
      .scrollTo(0, 120)
      .invoke('scrollTop')
      .then((position) => {
        resultScrollTop = Number(position);
        expect(resultScrollTop).to.be.greaterThan(0);
      });
    cy.location('search').then((search) => {
      query = search;
    });
    cy.document().then((document) => {
      const observer = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
          if (mutation.target.nodeType === 1)
            cameraTransitions.push(
              (mutation.target as Element).getAttribute(
                'data-camera-transition-active',
              ) ?? '',
            );
        }
      });
      observer.observe(document.documentElement, {
        subtree: true,
        attributes: true,
        attributeFilter: ['data-camera-transition-active'],
      });
    });
    cy.get(opener).focus().click();
    cy.get(mapWindow)
      .should('be.visible')
      .and('have.attr', 'aria-modal', 'false');
    cy.get('[data-map-window-close]').should('be.focused');
    if (width < 700) {
      // The phone opens on the map itself, with its controls sharing the
      // workspace; lengthy provenance/region context cannot push it offscreen.
      cy.get(canvasSelector).should(($canvas) => {
        const bounds = $canvas[0].getBoundingClientRect();
        const windowBounds = $canvas[0]
          .closest(mapWindow)!
          .getBoundingClientRect();
        const viewportHeight =
          $canvas[0].ownerDocument.defaultView!.innerHeight;
        const visibleHeight =
          Math.min(bounds.bottom, windowBounds.bottom, viewportHeight) -
          Math.max(bounds.top, windowBounds.top, 0);
        expect(visibleHeight).to.be.at.least(bounds.height * 0.6);
      });
    }
    // The same non-modal contract applies at phone width: focus can leave
    // the map and the surrounding application never becomes inert.
    cy.get('a.brand').parents('[inert]').should('have.length', 0);
    cy.get('a.brand').focus().should('be.focused');
    cy.get(mapWindow).scrollIntoView();
    assertRendererReady();
    cy.get(canvasSelector).scrollIntoView();
    cy.get(canvasSelector).then(([canvas]) => {
      initialCanvas = canvas as HTMLCanvasElement;
    });
    cy.get(`${mapWindow} .spatial-canvas`).should(
      'have.attr',
      'data-camera-transition-active',
      'false',
    );
    // Show on map uses the existing SET_CAMERA path. Verify the selected
    // system is actually centred, independent of FLY_TO completion markers.
    cy.get(`${mapWindow} [data-map-label-key="system:${selectedId}"]`, {
      timeout: 20_000,
    })
      .should('have.attr', 'data-map-label-selected', 'true')
      .should(($label) => {
        const canvas = $label[0]
          .closest('.spatial-canvas')!
          .querySelector('canvas')!;
        expect(Number($label.attr('data-map-label-anchor-x'))).to.be.closeTo(
          canvas.clientWidth / 2,
          2,
        );
        expect(Number($label.attr('data-map-label-anchor-y'))).to.be.closeTo(
          canvas.clientHeight / 2,
          2,
        );
      });
    cy.get(`${mapWindow} [aria-label="Rotate right"]`).click();
    cy.contains(`${mapWindow} button`, /^Top down$/).click();
    cy.get(`${mapWindow} .spatial-canvas`).then(($canvas) => {
      bearing = $canvas.attr('data-camera-bearing') ?? '';
      pitch = $canvas.attr('data-camera-pitch') ?? '';
      expect(Number(pitch)).to.equal(Math.PI / 2);
    });
    cy.get('[data-map-layers-toggle]').click();
    cy.get('[data-nebula-toggle]')
      .should('have.attr', 'aria-checked', 'true')
      .click();
    cy.injectAxe();
    cy.checkA11y(mapWindow);
    // Layers owns the first Escape; the parent window and its one runtime stay.
    cy.press(Cypress.Keyboard.Keys.ESC);
    cy.get('[data-map-layers-dialog]').should('not.exist');
    cy.get('[data-map-layers-toggle]').should('be.focused');
    cy.get(mapWindow).should('be.visible');
    cy.get(canvasSelector).should(([canvas]) => {
      expect(canvas).to.equal(initialCanvas);
    });
    cy.get('[data-map-window-expand]').click();
    cy.get(mapWindow).should('have.attr', 'data-expanded', 'true');
    cy.get('.results-panel').should('not.be.visible');
    cy.get(canvasSelector).should(([canvas]) => {
      expect(canvas).to.equal(initialCanvas);
    });
    cy.get(canvasSelector).then(([canvas]) => {
      const revision = Number(canvas.getAttribute('data-resize-revision'));
      cy.viewport(width - 20, height - 40);
      cy.get(canvasSelector).should(([resized]) => {
        expect(resized).to.equal(initialCanvas);
        expect(
          Number(resized.getAttribute('data-resize-revision')),
        ).to.be.greaterThan(revision);
      });
    });
    cy.viewport(width, height);
    cy.checkA11y(mapWindow);
    cy.screenshot(
      `product/explore-map-expanded-${Cypress.browser.name}-${width}x${height}`,
      {
        capture: 'viewport',
        overwrite: true,
        disableTimersAndAnimations: true,
      },
    );
    cy.get('[data-map-window-close]').click();
    cy.get(mapWindow).should('not.exist');
    cy.get(canvasSelector).should('not.exist');
    cy.get(opener).should('be.focused');
    cy.get('.results-panel').should('be.visible');
    cy.get('.result-list').should(($list) => {
      expect($list[0].scrollTop).to.equal(resultScrollTop);
    });
    cy.get(`${selectedResult} [data-result-select]`).should(
      'have.attr',
      'aria-pressed',
      'true',
    );
    cy.get(`${selectedResult} [data-archetype-explanation-toggle]`).should(
      'have.attr',
      'aria-expanded',
      'true',
    );
    cy.get('input[type="radio"][value="flexible"]').should('be.checked');
    cy.get('.page-size input').should('have.value', '3');
    cy.then(() => cy.location('search').should('eq', query));
    cy.get('@windowRankings.all').should('have.length', 1);
    cy.get('@windowSearch.all').should('have.length', 0);
    const suspendedCounts = new Map<string, number>();
    for (const alias of [
      '@windowDensity.all',
      '@windowCatalogue.all',
      '@windowNebulae.all',
    ]) {
      cy.get(alias).then((requests) => {
        suspendedCounts.set(alias, requests.length);
      });
    }
    // Longer than the existing viewport debounce, bounded to half a second.
    cy.wait(500);
    cy.then(() => {
      for (const [alias, count] of suspendedCounts)
        cy.get(alias).should('have.length', count);
    });
    cy.get(`${selectedResult} [data-result-map-open]`).click();
    assertRendererReady();
    cy.get(mapWindow).should('have.attr', 'data-expanded', 'false');
    cy.get(canvasSelector).should(([canvas]) => {
      expect(canvas).not.to.equal(initialCanvas);
    });
    cy.then(() => {
      cy.get(`${mapWindow} .spatial-canvas`)
        .should('have.attr', 'data-camera-bearing', bearing)
        .and('have.attr', 'data-camera-pitch', pitch)
        .and('have.attr', 'data-camera-transition-active', 'false');
    });
    cy.get('[data-map-layers-toggle]').click();
    cy.get('[data-nebula-toggle]').should('have.attr', 'aria-checked', 'false');
    cy.press(Cypress.Keyboard.Keys.ESC);
    cy.get(mapWindow).should('be.visible');
    cy.press(Cypress.Keyboard.Keys.ESC);
    cy.get(mapWindow).should('not.exist');
    cy.get(canvasSelector).should('not.exist');
    cy.get(`${selectedResult} [data-result-map-open]`).should('be.focused');
    cy.get('@windowRankings.all').should('have.length', 1);
    cy.get('@windowSearch.all').should('have.length', 0);
    cy.then(() => {
      expect(cameraTransitions).not.to.include('true');
    });
    cy.checkA11y();
  });
}
