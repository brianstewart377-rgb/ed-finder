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
