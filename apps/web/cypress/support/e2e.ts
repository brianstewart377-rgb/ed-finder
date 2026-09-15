import 'cypress-axe';

const A11Y_TIMEOUT_MS = 60_000;

Cypress.Commands.overwrite(
  'checkA11y',
  (originalFn, context, options, violationCallback, skipFailures) => {
    const previousTimeout = Cypress.config('defaultCommandTimeout');

    cy.then(() => {
      Cypress.config('defaultCommandTimeout', A11Y_TIMEOUT_MS);
    });
    originalFn(context, options, violationCallback, skipFailures);
    cy.then(() => {
      Cypress.config('defaultCommandTimeout', previousTimeout);
    });
  },
);
