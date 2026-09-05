type ProductWindow = Window & { __productRuntimeFailures?: string[] };

const readySelector = '[role="status"][data-renderer-state="ready"]';
const canvasSelector = 'canvas[data-spatial-canvas]';

const visitExplore = () => {
  cy.intercept('GET', '/api/local/autocomplete*').as('autocomplete');
  cy.intercept('POST', '/api/local/search').as('search');
  cy.visit('/explore', {
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

const keyboardChooseAnchor = (query: string) => {
  cy.get('#system-search').clear().type(query);
  cy.wait('@autocomplete').its('response.statusCode').should('eq', 200);
  cy.get('[role="listbox"] [role="option"]').should(
    'have.length.greaterThan',
    0,
  );
  cy.get('#system-search').type('{downArrow}{enter}');
  cy.wait('@search').its('response.statusCode').should('eq', 200);
};

describe('V3 Explore to Inspect product checkpoint', () => {
  it('discovers, selects, spatially picks, inspects, resizes and remounts real systems', () => {
    let initialCanvas!: HTMLCanvasElement;
    cy.viewport(1280, 800);
    visitExplore();
    cy.wait('@search').its('response.statusCode').should('eq', 200);
    cy.get('h1')
      .should('contain.text', 'Chart a promising system')
      .and('be.visible');
    cy.get('[data-system-result]').should('have.length.greaterThan', 0);
    assertSpatialResultsReady();
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

    keyboardChooseAnchor('Achenar');
    cy.get('[data-system-result="10477373803000"] [data-result-select]')
      .should('be.focused')
      .and('have.attr', 'aria-pressed', 'true');
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
        cy.wrap($result).find('[data-result-select]').focus().type('{enter}');
        cy.get('[data-testid="selected-system-context"]').should(
          'contain.text',
          keyboardSelectedId,
        );
        cy.wrap($result)
          .find('[data-result-select]')
          .should('have.attr', 'aria-pressed', 'true');
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

    cy.get(canvasSelector).click('center');
    cy.get('.selection-status')
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

    cy.get('[data-system-result="10477373803000"] .inspect-link').click();
    cy.location('pathname').should('eq', '/inspect');
    cy.location('search').should('eq', '?system=10477373803000');
    cy.get('[data-system-id64="10477373803000"]')
      .should('contain.text', 'Achenar')
      .and('contain.text', '10477373803000');
    cy.injectAxe();
    cy.checkA11y();

    cy.viewport(820, 640);
    cy.contains('a', 'Back to Explore').click();
    cy.location('pathname').should('eq', '/explore');
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

  it('preserves an unsafe-sized id64 through API, selection, route, detail and reload', () => {
    const unsafeId = '9007199254740993';
    visitExplore();
    cy.wait('@search').its('response.statusCode').should('eq', 200);
    keyboardChooseAnchor('V3 Lossless');

    cy.get('[data-testid="selected-system-context"]').should(
      'contain.text',
      unsafeId,
    );
    cy.get(`[data-system-result="${unsafeId}"] .inspect-link`).click();
    cy.location('search').should('eq', `?system=${unsafeId}`);
    cy.get(`[data-system-id64="${unsafeId}"]`)
      .should('contain.text', 'V3 Lossless Reach')
      .and('contain.text', unsafeId);
    cy.reload();
    cy.get(`[data-system-id64="${unsafeId}"]`, { timeout: 10_000 })
      .should('contain.text', 'V3 Lossless Reach')
      .and('contain.text', unsafeId);
    cy.get('[data-testid="selected-system-context"]').should(
      'contain.text',
      unsafeId,
    );
  });
});
