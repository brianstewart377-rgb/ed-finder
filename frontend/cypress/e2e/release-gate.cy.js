const SEARCH_PAYLOAD = {
  reference_coords: { x: 0, y: 0, z: 0 },
  filters: { distance: { min: 0, max: 1000 } },
  size: 5,
};

const KNOWN_SEED_NAMES = [
  'Sol', 'Achenar', 'Lave', 'Procyon', 'Alioth',
  'Wolf', 'HIP', 'Sothis', 'Pleione', 'Diaguandri',
];

function assertSearchBackendReady() {
  cy.request({
    method: 'POST',
    url: '/api/local/search',
    body: SEARCH_PAYLOAD,
    retryOnNetworkFailure: true,
    retryOnStatusCodeFailure: true,
  }).then((response) => {
    expect(response.status).to.equal(200);
    expect(response.body).to.have.property('results').and.to.be.an('array');
    expect(response.body.source).to.equal('local_db');
  });
}

function runSearch() {
  assertSearchBackendReady();
  cy.visit('/');
  cy.getByTestId('search-submit').should('be.enabled').click();
  cy.getByTestId('search-summary').should('be.visible');
}

function openProductionMap() {
  cy.intercept('GET', '**/stage26e/authoritative-regions.json').as('regions');
  cy.intercept('GET', '**/api/map/heatmap*').as('heatmap');
  cy.visit('/');
  cy.getByTestId('nav-map').click();
  cy.wait('@regions').then((interception) => {
    // Vite correctly returns 304 after Chrome has cached the immutable region
    // asset from an earlier isolated test. Both 200 and 304 prove the same
    // browser-facing contract; rejecting 304 turns browser caching into a
    // false failure.
    expect([200, 304], 'authoritative region response status')
      .to.include(interception.response?.statusCode);
  });
  cy.wait('@heatmap').its('response.statusCode').should('eq', 200);
  cy.getByTestId('stage26e-production-map').should('be.visible');
}

function clickDeepZoom(count = 24) {
  for (let index = 0; index < count; index += 1) {
    cy.getByTestId('map-zoom-in').click();
  }
}

describe('ED Finder release gate — Cypress parity', () => {
  it('boots the production SPA and exposes primary navigation', () => {
    cy.visit('/');
    cy.title().should('match', /ED:?Finder/i);
    cy.contains(/Finder/i).should('be.visible');
    cy.getByTestId('search-submit').should('be.visible');
  });

  it('runs search end-to-end against the seeded API', () => {
    runSearch();
    cy.get('body').should(($body) => {
      const text = $body.text();
      expect(
        KNOWN_SEED_NAMES.some((name) => text.includes(name)),
        'at least one known seeded system should render',
      ).to.equal(true);
    });
  });

  it('hydrates persisted pinned systems into My Work', () => {
    cy.visit('/', {
      onBeforeLoad(win) {
        win.localStorage.setItem('ed_pinned', JSON.stringify([{
          id64: 12345,
          name: 'Persisted',
          x: 0,
          y: 0,
          z: 0,
          population: 0,
          is_colonised: false,
          rating: 80,
          economy: 'Tourism',
          pinned_at: '2025-01-01T00:00:00Z',
        }]));
      },
    });

    cy.getByTestId('nav-my-work').click();
    cy.getByTestId('my-work-workspace').should('be.visible');
    cy.getByTestId('saved-system-12345')
      .should('contain.text', 'Persisted')
      .and('contain.text', 'Favourite');
  });

  it('preserves the legacy watchlist retirement contract', () => {
    cy.request({ url: '/api/watchlist', failOnStatusCode: false }).then((response) => {
      expect(response.status).to.equal(410);
      expect(JSON.stringify(response.body.detail)).to.include('sync_key');
    });
  });

  it('returns the local-search API envelope', () => {
    assertSearchBackendReady();
  });

  it('returns bounded heatmap data from the map API', () => {
    cy.request('/api/map/heatmap?voxel_size=200&min_systems=1').then((response) => {
      expect(response.status).to.equal(200);
      expect(response.body).to.have.property('voxel_bucket');
      expect([200, 500, 1000]).to.include(response.body.voxel_bucket);
    });
  });

  it('activates the production map and keeps its renderer synchronized', () => {
    openProductionMap();

    cy.getByTestId('stage26e-route-flag-state').should('contain.text', 'Live map');
    cy.getByTestId('stage26e-map-regions-toggle').should('be.checked');
    cy.getByTestId('stage26e-map-heatmap-toggle').should('be.checked');

    cy.getByTestId('map-view-galaxy').click();
    cy.get('.map-foundation-renderer')
      .should('have.attr', 'data-projection', 'perspective')
      .and('have.attr', 'data-camera-pitch', '42')
      .and('have.attr', 'data-galaxy-point-count', '18000');
    cy.assertCanvasSynced();

    cy.get('.map-foundation-renderer')
      .invoke('attr', 'data-camera-zoom')
      .then((initialValue) => {
        const initialZoom = Number(initialValue);
        expect(initialZoom).to.be.greaterThan(0);
        cy.getByTestId('map-zoom-in').click();
        cy.get('.map-foundation-renderer').should(($renderer) => {
          expect(Number($renderer.attr('data-camera-zoom'))).to.be.lessThan(initialZoom);
        });
      });

    cy.getByTestId('map-snap-top-down').click();
    cy.get('.map-foundation-renderer')
      .should('have.attr', 'data-camera-pitch', '0.5')
      .and('have.attr', 'data-projection', 'perspective');

    cy.viewport(1111, 733);
    cy.assertCanvasSynced();
  });

  it('crosses the real-star LOD and loads detailed systems', () => {
    cy.intercept('GET', '**/api/map/systems*').as('realStars');
    openProductionMap();
    cy.getByTestId('map-view-galaxy').click();
    cy.getByTestId('map-snap-top-down').click();

    clickDeepZoom();

    cy.wait('@realStars', { timeout: 30000 }).then((interception) => {
      expect(interception.response?.statusCode).to.equal(200);
      expect(interception.response?.body.systems).to.be.an('array');
      expect(interception.response?.body.truncated).to.be.a('boolean');
    });
    cy.assertCanvasSynced();
    cy.contains(/detailed star layer could not be loaded/i).should('not.exist');
  });

  it('keeps the map usable when detailed-star loading fails', () => {
    cy.intercept('GET', '**/api/map/systems*', { forceNetworkError: true }).as('realStarsFailure');
    openProductionMap();
    cy.getByTestId('map-view-galaxy').click();
    cy.getByTestId('map-snap-top-down').click();

    clickDeepZoom();

    cy.wait('@realStarsFailure', { timeout: 30000 });
    cy.get('.map-foundation-renderer canvas').should('be.visible');
    cy.contains(/detailed star layer could not be loaded/i).should('be.visible');
  });

  it('keeps the map shell usable when heatmap loading fails', () => {
    cy.intercept('GET', '**/api/map/heatmap*', { forceNetworkError: true }).as('heatmapFailure');
    cy.visit('/');
    cy.getByTestId('nav-map').click();
    cy.wait('@heatmapFailure');
    cy.getByTestId('stage26e-production-map').should('be.visible');
    cy.get('.map-foundation-renderer canvas').should('be.visible');
  });

  it('opens and closes a system detail modal from a real search result', () => {
    runSearch();

    cy.get('[data-testid^="result-card-"]').first().as('firstResult');
    cy.get('@firstResult').should('be.visible');
    cy.get('@firstResult').find('h3').invoke('text').then((name) => {
      const systemName = name.trim();
      expect(systemName).not.to.equal('');

      cy.get('@firstResult').find('header').click();
      cy.get('@firstResult').contains('button', 'Inspect system').should('be.visible').click();
      cy.getByTestId('system-detail-modal')
        .should('be.visible')
        .and('contain.text', systemName);
    });

    cy.get('body').then(($body) => {
      // Cypress `cy.get()` is an assertion that an element exists, so it
      // cannot be used to implement Playwright-style optional lookup. Inspect
      // the current DOM first, then use the supported backdrop fallback when
      // this modal variant has no explicit close button.
      const $close = $body.find('[data-testid="modal-close"]');
      if ($close.length > 0 && $close.is(':visible')) {
        cy.wrap($close).click();
      } else {
        cy.getByTestId('system-detail-modal-backdrop').click('topLeft');
      }
    });
    cy.getByTestId('system-detail-modal').should('not.exist');
  });

  it('installs and controls through the cache-neutral service worker', () => {
    cy.request('/sw.js').then((response) => {
      expect(response.status).to.equal(200);
      expect(response.headers['content-type']).to.match(/javascript/);
      expect(response.body).to.include('event.waitUntil(self.skipWaiting())');
    });

    cy.visit('/?service-worker-install=clean');
    cy.window({ timeout: 15000 }).should((win) => {
      expect(win.navigator.serviceWorker, 'serviceWorker API').to.exist;
      expect(win.navigator.serviceWorker.controller?.scriptURL, 'active controller')
        .to.match(/\/sw\.js$/);
    });
  });
});
