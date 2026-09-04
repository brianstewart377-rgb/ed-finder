describe('ED-Finder V3 foundation', () => {
  it('loads the shell and exercises the real same-origin bootstrap', () => {
    cy.intercept('/api/health').as('health');
    cy.intercept('/api/auth/session').as('session');
    cy.visit('/');
    cy.get('h1').should('contain.text', 'Find your place').and('be.visible');
    cy.wait('@health').its('response.statusCode').should('eq', 200);
    cy.wait('@session').its('response.statusCode').should('eq', 200);
  });
  it('supports direct navigation and refresh through the SPA fallback', () => {
    cy.visit('/explore');
    cy.get('h1').should('have.text', 'Explore').and('be.visible');
    cy.reload();
    cy.contains('This product surface has not been ported yet.').should(
      'be.visible',
    );
  });
});
