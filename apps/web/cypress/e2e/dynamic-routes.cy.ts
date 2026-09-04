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

  it('does not turn a near-prefix typo into a successful SPA response', () => {
    cy.request({
      url: '/colony-plannerish/system/1',
      failOnStatusCode: false,
    }).then(({ status }) => {
      expect(status).to.eq(404);
    });
  });
});
