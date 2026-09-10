const path = require('node:path');

module.exports = {
  retries: 0,
  video: true,
  screenshotOnRunFailure: true,
  trashAssetsBeforeRuns: true,
  viewportWidth: 1280,
  viewportHeight: 720,
  defaultCommandTimeout: 8000,
  requestTimeout: 10000,
  responseTimeout: 15000,
  pageLoadTimeout: 30000,
  numTestsKeptInMemory: 0,
  chromeWebSecurity: true,
  e2e: {
    baseUrl: process.env.CYPRESS_BASE_URL || 'http://127.0.0.1:4173',
    specPattern: 'cypress/e2e/**/*.cy.js',
    supportFile: 'cypress/support/e2e.js',
    testIsolation: true,
    screenshotsFolder: 'cypress/artifacts/screenshots',
    videosFolder: 'cypress/artifacts/videos',
    downloadsFolder: 'cypress/artifacts/downloads',
    setupNodeEvents(on, config) {
      on('before:browser:launch', (browser, launchOptions) => {
        if (browser.family === 'chromium') {
          launchOptions.args.push('--force-prefers-reduced-motion');
        }
        return launchOptions;
      });
      on('after:spec', (_spec, results) => {
        if (!results) return;
        const failed = results.tests.filter((test) => test.state === 'failed');
        if (failed.length > 0) {
          console.error(`Cypress spec failed: ${failed.length} test(s)`);
        }
      });
      config.projectRoot = path.resolve(__dirname);
      return config;
    },
  },
};
