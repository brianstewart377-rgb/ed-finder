describe('ED-Finder V3 foundation', () => {
  it('loads the shell and exercises the real same-origin bootstrap', () => {
    cy.intercept('/api/health').as('health');
    cy.intercept('/api/auth/session').as('session');
    cy.visit('/');
    cy.get('h1').should('contain.text', 'Find your place').and('be.visible');
    cy.wait('@health').its('response.statusCode').should('eq', 200);
    cy.wait('@session').its('response.statusCode').should('eq', 200);
    cy.contains('dd', 'Connected').should('be.visible');
    cy.contains('dd', 'Guest').should('be.visible');
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

    cy.request('/apiary').then(({ headers, status }) => {
      expect(status).to.eq(200);
      expect(headers['content-type']).to.include('text/html');
    });
  });

  it('supports direct navigation and refresh through the SPA fallback', () => {
    cy.visit('/explore');
    cy.get('h1').should('have.text', 'Explore').and('be.visible');
    cy.reload();
    cy.contains('This product surface has not been ported yet.').should(
      'be.visible',
    );
  });

  it('rejects unknown journey routes instead of rendering a placeholder', () => {
    cy.visit('/explroe', { failOnStatusCode: false });
    cy.contains('This product surface has not been ported yet.').should(
      'not.exist',
    );
    cy.contains(/not found/i).should('be.visible');
  });
});
