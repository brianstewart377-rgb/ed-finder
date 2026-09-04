describe('Svelte direct-cutover vertical', () => {
  beforeEach(() => {
    cy.intercept('GET', '/api/auth/session', {
      authenticated: false,
      user: null,
      owner_claim_available: false,
    });
    cy.intercept('GET', '/api/v2/watchlist/*', { watchlist: [] });
  });
  it('renders the accessible shell and Finder', () => {
    cy.visit('/');
    cy.get('[data-testid=app-shell]').should('be.visible');
    cy.contains('a', 'Skip to main content').focus().should('be.visible');
    cy.get('[data-testid=finder-page-heading]').should(
      'contain',
      'System Finder',
    );
  });
  it('redirects legacy hashes without retaining hash routing', () => {
    cy.visit('/#watchlist');
    cy.location('pathname').should('eq', '/my-work');
    cy.location('hash').should('eq', '');
    cy.contains('h1', 'My Work').should('be.visible');
  });
  it('preserves legacy bare-array pins', () => {
    cy.visit('/my-work', {
      onBeforeLoad(win) {
        win.localStorage.setItem(
          'ed_pinned',
          JSON.stringify([{ id64: '9223372036854775807', name: 'Far Reach' }]),
        );
      },
    });
    cy.contains('Far Reach').should('be.visible');
    cy.reload();
    cy.contains('Far Reach').should('be.visible');
  });
  it('searches, pins and uses the scoped watchlist contract', () => {
    cy.intercept('POST', '/api/local/search', {
      count: 1,
      total: 1,
      results: [{ id64: 9223372036854775807, name: 'Far Reach' }],
    }).as('search');
    cy.intercept('POST', '/api/v2/watchlist/*/9223372036854775807', {
      ok: true,
    }).as('save');
    cy.visit('/finder');
    cy.get('[data-testid=search-submit]').click();
    cy.wait('@search');
    cy.contains('Far Reach').should('be.visible');
    cy.get('[data-testid=pin-system]')
      .click()
      .should('have.attr', 'aria-pressed', 'true');
    cy.get('[data-testid=watchlist-system]').click();
    cy.wait('@save');
  });
  it('gates admin and survives direct refresh', () => {
    cy.visit('/admin');
    cy.get('[data-testid=owner-sign-in-required]').should('be.visible');
    cy.reload();
    cy.get('[data-testid=owner-sign-in-required]').should('be.visible');
  });
});
