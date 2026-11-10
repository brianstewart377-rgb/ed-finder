import { captureSubmittedBabylonFrame } from '../support/babylon-frame';

const canvasSelector = 'canvas[data-spatial-canvas]';

function dragMap(x: number, y: number, shiftKey = false): void {
  cy.get<HTMLElement>('.spatial-canvas').then(([$host]) => {
    const window = $host.ownerDocument.defaultView!;
    const bounds = $host.getBoundingClientRect();
    const startX = bounds.left + bounds.width / 2;
    const startY = bounds.top + bounds.height / 2;
    const pointer = (type: string, clientX: number, clientY: number) =>
      new window.PointerEvent(type, {
        bubbles: true,
        pointerId: 72,
        pointerType: 'mouse',
        button: 0,
        clientX,
        clientY,
        shiftKey,
      });
    $host.dispatchEvent(pointer('pointerdown', startX, startY));
    window.dispatchEvent(pointer('pointermove', startX + x, startY + y));
    window.dispatchEvent(pointer('pointerup', startX + x, startY + y));
  });
}

describe('V3 map on local real catalogue data', () => {
  it('keeps populated density and exact stars visible while navigating', () => {
    const failures: string[] = [];
    cy.viewport(1280, 800);
    cy.intercept('GET', '/api/map/heatmap*').as('heatmap');
    cy.intercept('GET', '/api/map/systems*').as('systems');
    cy.intercept('POST', '/api/local/search').as('search');
    cy.visit('/explore', {
      onBeforeLoad(window) {
        window.addEventListener('error', () => failures.push('error'));
        window.addEventListener('unhandledrejection', () =>
          failures.push('unhandledrejection'),
        );
      },
    });
    cy.get('[role="status"][data-renderer-state="ready"]', {
      timeout: 30_000,
    }).should('be.visible');
    cy.wait('@heatmap', { timeout: 45_000 })
      .its('response.statusCode')
      .should('eq', 200);
    cy.get('[data-density-state]', { timeout: 45_000 }).should(($density) => {
      expect($density.attr('data-density-state')).to.be.oneOf([
        'ready',
        'truncated',
      ]);
      expect(
        Number($density.attr('data-density-cell-count')),
      ).to.be.greaterThan(1_000);
    });
    captureSubmittedBabylonFrame('map-real-data/galaxy-density');

    // This is an ordinary Product search against the local normal API, not a
    // Cypress fixture. The published catalogue must yield a populated star view.
    cy.intercept({
      method: 'GET',
      pathname: '/api/local/autocomplete',
      query: { q: 'Achenar' },
    }).as('anchor');
    cy.get('#system-search').clear().type('Achenar');
    cy.wait('@anchor').its('response.statusCode').should('eq', 200);
    cy.get('[role="listbox"] [role="option"]', { timeout: 15_000 }).should(
      'have.length.greaterThan',
      0,
    );
    cy.get('#system-search').type('{downArrow}{enter}');
    cy.wait('@search', { timeout: 45_000 })
      .its('response.statusCode')
      .should('eq', 200);
    cy.wait('@systems', { timeout: 45_000 })
      .its('response.statusCode')
      .should('eq', 200);
    cy.get('[data-testid="selected-system-context"]').should(
      'contain.text',
      '10477373803000',
    );
    cy.get('.spatial-canvas', { timeout: 30_000 }).should(
      'have.attr',
      'data-camera-transition-active',
      'false',
    );
    cy.get('[data-catalogue-star-count]', { timeout: 45_000 }).should(
      ($stars) => {
        expect(
          Number($stars.attr('data-catalogue-star-count')),
        ).to.be.greaterThan(100);
      },
    );
    captureSubmittedBabylonFrame('map-real-data/achenar-stars');

    let canvas!: HTMLCanvasElement;
    let previousDistance = 0;
    let focusBeforePan = '';
    cy.get<HTMLCanvasElement>(canvasSelector).then(([element]) => {
      canvas = element;
    });
    cy.get('[data-camera-distance]').then(($distance) => {
      previousDistance = Number($distance.attr('data-camera-distance'));
    });
    for (let step = 1; step <= 6; step += 1) {
      cy.get('.spatial-canvas').then(($host) => {
        const bounds = $host[0]!.getBoundingClientRect();
        cy.wrap($host).trigger('wheel', {
          deltaY: -140,
          deltaMode: 0,
          clientX: bounds.left + bounds.width * 0.55,
          clientY: bounds.top + bounds.height * 0.45,
        });
      });
      cy.get('[data-camera-distance]')
        .should(($distance) => {
          expect(Number($distance.attr('data-camera-distance'))).to.be.lessThan(
            previousDistance,
          );
        })
        .then(($distance) => {
          previousDistance = Number($distance.attr('data-camera-distance'));
        });
      captureSubmittedBabylonFrame(`map-real-data/zoom-${step}`);
    }

    cy.get('[aria-label="Focus coordinates"]').then(($focus) => {
      focusBeforePan = $focus.text();
    });
    dragMap(80, 45);
    cy.get('[aria-label="Focus coordinates"]').should(($focus) => {
      expect($focus.text()).not.to.equal(focusBeforePan);
    });
    captureSubmittedBabylonFrame('map-real-data/pan');

    cy.contains('[aria-label="Camera angle"] button', 'Tilted').click();
    cy.get('.spatial-canvas').should('have.attr', 'data-camera-pitch', '0.55');
    dragMap(40, 30, true);
    cy.get('.spatial-canvas').should(($host) => {
      expect(Number($host.attr('data-camera-pitch'))).to.be.greaterThan(0.55);
    });
    captureSubmittedBabylonFrame('map-real-data/tilt');
    cy.get<HTMLCanvasElement>(canvasSelector).should(([element]) => {
      expect(element).to.equal(canvas);
    });
    cy.then(() => expect(failures).to.deep.equal([]));
  });
});
