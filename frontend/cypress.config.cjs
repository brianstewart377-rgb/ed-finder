const path = require('node:path');
const fs = require('node:fs/promises');

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
  allowCypressEnv: false,
  e2e: {
    baseUrl: process.env.CYPRESS_BASE_URL || 'http://127.0.0.1:4173',
    specPattern: 'cypress/e2e/**/*.cy.js',
    supportFile: 'cypress/support/e2e.js',
    testIsolation: true,
    screenshotsFolder: 'cypress/artifacts/screenshots',
    videosFolder: 'cypress/artifacts/videos',
    downloadsFolder: 'cypress/artifacts/downloads',
    setupNodeEvents(on, config) {
      const reviewLabRun = process.env.EDFINDER_REVIEW_LAB_RUN === '1';
      config.env.reviewLabRun = reviewLabRun;
      config.env.reviewOutputPath = process.env.EDFINDER_REVIEW_OUTPUT_PATH || '';
      config.env.reviewScenariosJson = process.env.EDFINDER_REVIEW_SCENARIOS_JSON || '';
      on('task', {
        async writeReviewLabSummary({ outputPath, summary }) {
          if (!reviewLabRun || outputPath !== process.env.EDFINDER_REVIEW_OUTPUT_PATH) {
            throw new Error('Refusing an unverified Review Lab summary path.');
          }
          await fs.mkdir(path.dirname(outputPath), { recursive: true });
          await fs.writeFile(outputPath, `${JSON.stringify(summary, null, 2)}\n`, 'utf8');
          return null;
        },
      });
      on('before:browser:launch', (browser, launchOptions) => {
        if (browser.family === 'chromium') {
          // E2E should assert the observable final camera state rather than race
          // the 500 ms cosmetic zoom transition. Animation maths stays covered
          // by the focused Vitest camera/useSmoothMapZoom tests.
          launchOptions.args.push('--force-prefers-reduced-motion');
        }
        return launchOptions;
      });

      on('after:spec', (_spec, results) => {
        if (!results) return;
        const failed = results.tests.filter((test) => test.state === 'failed');
        if (failed.length > 0) {
          // Keep a terse machine-readable signal in the Actions log while the
          // screenshots/video retain full browser evidence.
          console.error(`Cypress spec failed: ${failed.length} test(s)`);
        }
      });

      config.projectRoot = path.resolve(__dirname);
      return config;
    },
  },
};
