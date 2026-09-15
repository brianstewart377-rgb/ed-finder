describe('ED-Finder V3 foundation', () => {
  for (const [width, height] of [
    [1280, 800],
    [390, 844],
  ] as const) {
    it(`keeps home and guest account usable at ${width}x${height}`, () => {
      cy.viewport(width, height);
      cy.intercept('GET', '/api/v1/auth/session').as('accountSession');
      cy.visit('/');
      cy.wait('@accountSession').its('response.statusCode').should('eq', 200);
      cy.contains('button', 'Sign in with Frontier').should('be.visible');
      cy.get('.workspace-header nav a').should('have.length', 2);
      cy.injectAxe();
      cy.checkA11y();
      cy.document().should((document) => {
        expect(document.documentElement.scrollWidth).to.be.at.most(width);
      });
      cy.screenshot(`account/home-${Cypress.browser.name}-${width}x${height}`, {
        capture: 'fullPage',
        overwrite: true,
      });

      cy.visit('/account');
      cy.wait('@accountSession').its('response.statusCode').should('eq', 200);
      cy.contains('h2', 'Sign in to manage your account').should('be.visible');
      cy.contains('button', 'Sign in with Frontier')
        .focus()
        .should('be.focused');
      cy.injectAxe();
      cy.checkA11y();
      cy.document().should((document) => {
        expect(document.documentElement.scrollWidth).to.be.at.most(width);
      });
      cy.screenshot(
        `account/guest-${Cypress.browser.name}-${width}x${height}`,
        {
          capture: 'fullPage',
          overwrite: true,
        },
      );
      cy.reload();
      cy.wait('@accountSession').its('response.statusCode').should('eq', 200);
      cy.contains('h2', 'Sign in to manage your account').should('be.visible');
      cy.get('.workspace-header nav a')
        .contains('Explore')
        .focus()
        .should('be.focused');
      cy.press(Cypress.Keyboard.Keys.ENTER);
      cy.location('pathname').should('eq', '/explore');
      cy.get('h1').should('contain.text', 'Chart a promising system');
    });
  }

  it('loads the shell and exercises the real same-origin bootstrap', () => {
    cy.intercept('/api/health').as('health');
    cy.intercept('/api/v1/auth/session').as('session');
    cy.visit('/');
    cy.get('h1').should('contain.text', 'Search the galaxy').and('be.visible');
    cy.wait('@health').its('response.statusCode').should('eq', 200);
    cy.wait('@session').its('response.statusCode').should('eq', 200);
    cy.contains('dd', 'Connected').should('be.visible');
    cy.contains('dd', 'Guest').should('be.visible');
    cy.contains('button', 'Sign in with Frontier').should('be.visible');
  });

  it('proxies backend-owned routes to the disposable FastAPI service', () => {
    cy.request('/openapi.json?format=json').then(
      ({ body, headers, status }) => {
        expect(status).to.eq(200);
        expect(headers['content-type']).to.include('application/json');
        expect(body.paths).to.have.property('/api/health');
      },
    );

    cy.request({
      url: '/s/0?utm=x',
      followRedirect: false,
      failOnStatusCode: false,
    }).then(({ headers, status }) => {
      // FastAPI currently owns this valid numeric share route and redirects
      // browser user agents. A Svelte fallback would instead return HTML 200.
      expect(status).to.eq(302);
      expect(headers.location).to.include('/#system/0');
    });

    cy.request({ url: '/apiary', failOnStatusCode: false }).then(
      ({ headers, status }) => {
        // This near-prefix must remain on the Svelte side. Because it is not a
        // real application route, the correct frontend response is its HTML 404.
        expect(status).to.eq(404);
        expect(headers['content-type']).to.include('text/html');
      },
    );
  });

  it('supports direct navigation and refresh through the SPA fallback', () => {
    cy.visit('/explore');
    cy.get('h1')
      .should('contain.text', 'Chart a promising system')
      .and('be.visible');
    cy.get('[role="status"][data-renderer-state="ready"]', {
      timeout: 20_000,
    }).should('be.visible');
    // Babylon lazily imports shader chunks as effects compile, so one can
    // still be in flight when the page reloads. Firefox rejects the aborted
    // import() with a TypeError; that is the navigation cancelling the
    // request, not an application failure, and is scoped to this reload only.
    cy.on('uncaught:exception', (error) =>
      /dynamically imported module/i.test(error.message) ? false : undefined,
    );
    cy.reload();
    cy.get('h1')
      .should('contain.text', 'Chart a promising system')
      .and('be.visible');
  });

  it('rejects unknown journey routes instead of rendering a placeholder', () => {
    cy.visit('/explroe', { failOnStatusCode: false });
    cy.contains('Chart a promising system').should('not.exist');
    cy.contains(/not found/i).should('be.visible');
  });
});
