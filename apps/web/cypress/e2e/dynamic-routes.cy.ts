describe('ED-Finder static dynamic-route fallback', () => {
  beforeEach(() => {
    cy.intercept('/api/auth/session', {
      authenticated: false,
      user: null,
      owner_claim_available: false,
    });
  });

  it('serves and refreshes a maximum-width System Detail route', () => {
    const route = '/system/18446744073709551615';

    cy.visit(route);
    cy.get('[data-testid="system-detail-page"]')
      .should('contain.text', 'System Detail')
      .and('contain.text', '18446744073709551615');

    cy.reload();
    cy.location('pathname').should('eq', route);
    cy.get('[data-testid="system-detail-page"]').should('be.visible');
  });

  it('serves and refreshes a nested Colony Planner route', () => {
    const route =
      '/colony-planner/system/18446744073709551615/project/project-1/mode/preview';

    cy.visit(route);
    cy.get('h1').should('have.text', 'Colony Planner');
    cy.contains(
      'System 18446744073709551615 · project project-1 · preview.',
    ).should('be.visible');

    cy.reload();
    cy.location('pathname').should('eq', route);
    cy.get('h1').should('have.text', 'Colony Planner');
  });

  it('canonicalises a legacy planner detail path without rounding either id', () => {
    const canonical =
      '/colony-planner/system/18446744073709551615/project/project-1/mode/preview';

    cy.visit(`${canonical}/detail/9007199254740993?view=compact&system=42`);
    cy.location('pathname').should('eq', canonical);
    cy.location('search').should('include', 'view=compact');
    cy.location('search').should('include', 'system=9007199254740993');
    cy.get('[data-testid="system-detail-modal"]')
      .should('contain.text', '9007199254740993')
      .and('be.visible');
  });

  it('keeps near-prefixes and unknown frontend routes application-owned', () => {
    const routes = [
      '/apiary',
      '/openapi.jsonx',
      '/s/1x',
      '/colony-plannerish/system/1',
      '/unknown-frontend-route',
    ];

    for (const route of routes) {
      cy.request(route).then(({ headers, status }) => {
        expect(status, route).to.eq(200);
        expect(headers['content-type'], route).to.include('text/html');
      });
    }
  });
});
