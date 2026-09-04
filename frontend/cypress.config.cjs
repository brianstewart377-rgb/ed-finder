const path = require('node:path');
const fs = require('node:fs/promises');
const { randomUUID } = require('node:crypto');

const REVIEW_LAB_ROOT = '/tmp/edfinder-local-review';
const REVIEW_LAB_SUMMARY_SCHEMA_VERSION = 1;

function isWithinReviewLabRoot(candidate) {
  const relative = path.relative(REVIEW_LAB_ROOT, candidate);
  return relative !== '' && relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative);
}

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
      // Snapshot the trusted runner-owned handshake before any spec executes.
      // None of these values travel through Cypress.env(); browser specs receive
      // Review Lab authority only through this trusted Node-task handshake.
      const reviewLabMarker = process.env.EDFINDER_REVIEW_LAB_RUN || '';
      const configuredOutputPath = process.env.EDFINDER_REVIEW_OUTPUT_PATH || '';
      const configuredScenariosJson = process.env.EDFINDER_REVIEW_SCENARIOS_JSON || '';
      on('task', {
        getReviewLabConfig() {
          return {
            reviewLabRun: reviewLabMarker === '1',
            reviewOutputPath: configuredOutputPath,
            reviewScenariosJson: configuredScenariosJson,
          };
        },
        async writeReviewLabSummary({ outputPath, summary }) {
          const outputIsTrusted = reviewLabMarker === '1'
            && outputPath === configuredOutputPath
            && path.isAbsolute(outputPath)
            && path.resolve(outputPath) === outputPath
            && isWithinReviewLabRoot(outputPath);
          const summaryIsValid = summary !== null
            && typeof summary === 'object'
            && !Array.isArray(summary)
            && summary.summarySchemaVersion === REVIEW_LAB_SUMMARY_SCHEMA_VERSION
            && summary.reviewLabRun === true;
          if (!outputIsTrusted || !summaryIsValid) {
            throw new Error('Refusing an unverified Review Lab summary path.');
          }
          const outputDirectory = path.dirname(outputPath);
          await fs.mkdir(outputDirectory, { recursive: true });
          const [realRoot, realOutputDirectory] = await Promise.all([
            fs.realpath(REVIEW_LAB_ROOT),
            fs.realpath(outputDirectory),
          ]);
          if (!isWithinReviewLabRoot(realOutputDirectory) || realRoot !== path.resolve(REVIEW_LAB_ROOT)) {
            throw new Error('Refusing a Review Lab summary path outside the owned temporary root.');
          }
          const temporaryPath = path.join(outputDirectory, `.${path.basename(outputPath)}.${randomUUID()}.tmp`);
          try {
            await fs.writeFile(temporaryPath, `${JSON.stringify(summary, null, 2)}\n`, { encoding: 'utf8', flag: 'wx' });
            await fs.rename(temporaryPath, outputPath);
          } catch (error) {
            await fs.rm(temporaryPath, { force: true });
            throw error;
          }
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
