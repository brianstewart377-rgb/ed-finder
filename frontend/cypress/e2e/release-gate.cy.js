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

function crossRealStarLod() {
  const renderer = '.map-foundation-renderer';
  const targetZoom = 1;

  cy.get(renderer).invoke('attr', 'data-camera-zoom').then((beforeValue) => {
    const beforeZoom = Number(beforeValue);
    expect(beforeZoom, 'zoom before deep-zoom gesture').to.be.greaterThan(0);
    if (beforeZoom <= targetZoom) return;

    // The production map's wheel listener forwards deltaY directly into the
    // same smooth-zoom controller used by the +/- buttons. Compute one real
    // wheel delta that lands safely inside the detail LOD instead of paying
    // for 24 separate 500 ms button animations as test setup.
    const deltaY = Math.log(targetZoom / beforeZoom) * 1000;
    cy.get(renderer).then(($renderer) => {
      const win = $renderer[0].ownerDocument.defaultView;
      $renderer[0].dispatchEvent(new win.WheelEvent('wheel', {
        deltaY,
        bubbles: true,
        cancelable: true,
      }));
    });

    cy.get(renderer, { timeout: 2000 }).should(($renderer) => {
      expect(Number($renderer.attr('data-camera-zoom')), 'zoom after deep-zoom gesture')
        .to.be.at.most(targetZoom * 1.05);
    });
  });
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

  it('orders renderer sync invalidation before resize revalidation', () => {
    openProductionMap();
    cy.getByTestId('map-view-galaxy').click();
    cy.get('.map-foundation-renderer canvas').should('have.attr', 'data-drawing-buffer-synced', 'true')
      .then(($canvas) => {
        const canvas = $canvas[0];
        canvas.__resizeTelemetrySequence = [canvas.dataset.drawingBufferSynced ?? 'missing'];
        canvas.__resizeTelemetryObserver = new MutationObserver(() => {
          canvas.__resizeTelemetrySequence.push(canvas.dataset.drawingBufferSynced ?? 'missing');
        });
        canvas.__resizeTelemetryObserver.observe(canvas, {
          attributes: true,
          attributeFilter: ['data-drawing-buffer-synced'],
        });
      });

    cy.viewport(1111, 733);
    cy.get('.map-foundation-renderer canvas').should(($canvas) => {
      const sequence = $canvas[0].__resizeTelemetrySequence ?? [];
      const invalidatedAt = sequence.indexOf('false');
      const revalidatedAt = sequence.indexOf('true', invalidatedAt + 1);
      expect(invalidatedAt, JSON.stringify(sequence)).to.be.at.least(0);
      expect(revalidatedAt, JSON.stringify(sequence)).to.be.greaterThan(invalidatedAt);
    });
  });

  it('does not invalidate renderer sync for a same-size ResizeObserver notification', () => {
    openProductionMap();
    cy.getByTestId('map-view-galaxy').click();
    cy.get('.map-foundation-renderer canvas').should('have.attr', 'data-drawing-buffer-synced', 'true')
      .then(($canvas) => {
        const canvas = $canvas[0];
        const before = canvas.getBoundingClientRect();
        const sequence = [canvas.dataset.drawingBufferSynced ?? 'missing'];
        const observer = new MutationObserver(() => {
          sequence.push(canvas.dataset.drawingBufferSynced ?? 'missing');
        });
        observer.observe(canvas, { attributes: true, attributeFilter: ['data-drawing-buffer-synced'] });
        expect(canvas.ownerDocument.defaultView.__triggerMapResizeObserver).to.be.a('function');
        canvas.ownerDocument.defaultView.__triggerMapResizeObserver();
        cy.wrap(null).then(() => new Cypress.Promise((resolve) => {
          requestAnimationFrame(() => requestAnimationFrame(resolve));
        })).then(() => {
          const after = canvas.getBoundingClientRect();
          observer.disconnect();
          expect({ width: after.width, height: after.height }).to.deep.equal({
            width: before.width, height: before.height,
          });
          expect(sequence.length).to.be.greaterThan(1);
          expect(sequence).not.to.include('false');
        });
      });
  });

  it('meets the automated accessibility gate', () => {
    cy.visit('/');
    cy.injectAxe();
    cy.checkA11y(undefined, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
    });
  });

  it('captures deterministic visual-baseline evidence', () => {
    cy.viewport(1280, 720);
    cy.clock(Date.UTC(2026, 0, 1));
    cy.visit('/', {
      onBeforeLoad(win) {
        win.document.documentElement.dataset.visualBaseline = 'cypress';
      },
    });
    cy.getByTestId('search-submit').should('be.visible');
    cy.document().then((doc) => {
      const style = doc.createElement('style');
      style.textContent = '*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}';
      doc.head.appendChild(style);
    });
    cy.screenshot('release-gate/home-1280x720', { capture: 'viewport', overwrite: true });
  });

  it('crosses the real-star LOD and loads detailed systems', () => {
    cy.intercept('GET', '**/api/map/systems*').as('realStars');
    openProductionMap();
    cy.getByTestId('map-view-galaxy').click();
    cy.getByTestId('map-snap-top-down').click();

    crossRealStarLod();

    // The production hook waits 250 ms for a settled camera before enabling
    // the query. CI WebGL/RAF scheduling can delay that observation, so allow
    // headroom for the request to begin while keeping retries disabled and all
    // response/content assertions intact.
    cy.wait('@realStars', { timeout: 15_000 }).then((interception) => {
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

    crossRealStarLod();

    cy.wait('@realStarsFailure', { timeout: 15_000 });
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

    // Review Lab already locks Escape-to-close as an accessibility contract.
    // Dispatch the key event on window because SystemDetailModal installs its
    // Escape listener there; typing into body depends on browser event routing.
    // The body scroll lock is installed by the same effect, so it is the
    // observable readiness signal that prevents Firefox racing the listener.
    cy.get('body').should(($body) => {
      expect($body[0].style.overflow, 'modal Escape listener readiness').to.eq('hidden');
    });
    cy.window().then((win) => {
      win.dispatchEvent(new win.KeyboardEvent('keydown', {
        key: 'Escape',
        code: 'Escape',
        which: 27,
        keyCode: 27,
        bubbles: true,
        cancelable: true,
      }));
    });
    cy.getByTestId('system-detail-modal').should('not.exist');
    cy.get('body').should(($body) => {
      expect($body[0].style.overflow, 'body overflow restored after modal close').to.eq('');
    });
    cy.location('hash').should('eq', '#finder');
  });

  it('installs and controls through the cache-neutral service worker', () => {
    cy.request('/sw.js').then((response) => {
      expect(response.status).to.equal(200);
      expect(response.headers['content-type']).to.match(/javascript/);
      expect(response.body).to.include('event.waitUntil(self.skipWaiting())');
    });

    cy.visit('/?service-worker-install=clean');
    cy.window({ timeout: 15000 }).should((win) => {
      expect(win.navigator.serviceWorker, 'serviceWorker API').not.to.equal(undefined);
      expect(win.navigator.serviceWorker.controller?.scriptURL, 'active controller')
        .to.match(/\/sw\.js$/);
    });
  });
});
