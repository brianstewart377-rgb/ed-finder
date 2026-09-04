describe('ED-Finder static dynamic-route fallback', () => {
  beforeEach(() => {
    cy.intercept('/api/auth/session', {
      authenticated: false,
      user: null,
      owner_claim_available: false,
    });
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

  it('keeps a near-prefix typo frontend-owned', () => {
    cy.request('/colony-plannerish/system/1').then(({ headers, status }) => {
      expect(status).to.eq(200);
      expect(headers['content-type']).to.include('text/html');
    });
  });
});
