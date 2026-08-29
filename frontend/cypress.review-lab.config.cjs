const base = require('./cypress.config.cjs');

module.exports = {
  ...base,
  e2e: {
    ...base.e2e,
    specPattern: 'cypress/e2e/review-environment.cy.js',
  },
};
