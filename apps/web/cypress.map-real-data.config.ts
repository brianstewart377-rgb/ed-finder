import { defineConfig } from 'cypress';

// Optional Product map acceptance on the isolated local V3 stack. This is not
// the Review Lab collector and never supplies API fixtures or intercept stubs.
export default defineConfig({
  retries: 0,
  video: true,
  screenshotOnRunFailure: true,
  screenshotsFolder: 'cypress/artifacts/map-real-data/screenshots',
  videosFolder: 'cypress/artifacts/map-real-data/videos',
  e2e: {
    baseUrl: 'http://127.0.0.1:4175',
    specPattern: 'cypress/e2e/map-real-data.cy.ts',
    supportFile: 'cypress/support/e2e.ts',
  },
});
