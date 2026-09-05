import { defineConfig } from 'cypress';
export default defineConfig({
  video: true,
  screenshotOnRunFailure: true,
  screenshotsFolder: 'cypress/artifacts/screenshots',
  videosFolder: 'cypress/artifacts/videos',
  e2e: {
    baseUrl: process.env.CYPRESS_BASE_URL ?? 'http://127.0.0.1:4174',
    // Product E2E is deliberately enumerated. Review Lab has its own Cypress
    // config and trusted handshake; adding a lab spec must never make the
    // normal seeded product lane collect it through a broad glob.
    specPattern: [
      'cypress/e2e/foundation.cy.ts',
      'cypress/e2e/spatial-foundation.cy.ts',
      'cypress/e2e/product-journey.cy.ts',
    ],
    supportFile: 'cypress/support/e2e.ts',
  },
});
