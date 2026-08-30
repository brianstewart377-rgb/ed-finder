const sessions = {
  signedOut: {
    authenticated: false,
    user: null,
    owner_claim_available: false,
  },
  nonOwner: {
    authenticated: true,
    user: { commander_name: 'Visiting Cmdr', is_owner: false },
    owner_claim_available: false,
  },
  owner: {
    authenticated: true,
    user: { commander_name: 'Owner Cmdr', is_owner: true },
    owner_claim_available: false,
  },
};

function visitAdminWithSession(session) {
  cy.intercept('GET', '**/api/auth/session', {
    statusCode: 200,
    body: session,
  }).as('authSession');
  cy.visit('/#admin');
  cy.wait('@authSession');
}

describe('Frontier owner access', () => {
  it('asks a signed-out visitor to use Frontier before opening Admin', () => {
    visitAdminWithSession(sessions.signedOut);

    cy.getByTestId('owner-sign-in-required').should('be.visible');
    cy.contains('button', 'Sign in with Frontier').should('be.visible');
  });

  it('denies Admin to an authenticated non-owner commander', () => {
    visitAdminWithSession(sessions.nonOwner);

    cy.getByTestId('owner-access-denied')
      .should('be.visible')
      .and('contain.text', 'This Frontier account is signed in, but it is not linked');
  });

  it('opens owner controls for the linked Frontier commander', () => {
    visitAdminWithSession(sessions.owner);

    cy.getByTestId('frontier-account-name').should('contain.text', 'CMDR Owner Cmdr');
    cy.getByTestId('owner-open-ops').should('be.visible');
    cy.getByTestId('owner-sign-in-required').should('not.exist');
    cy.getByTestId('owner-access-denied').should('not.exist');
  });
});
