const fs = require('node:fs');
const path = require('node:path');
const base = require('./cypress.config.cjs');

const setupBaseNodeEvents = base.e2e.setupNodeEvents;

function configureReviewArtifacts(config) {
  const outputPath = process.env.EDFINDER_REVIEW_OUTPUT_PATH || '';
  if (!outputPath || !path.isAbsolute(outputPath)) {
    throw new Error('Review Lab summary output path must be absolute.');
  }
  const artifactRoot = path.join(path.dirname(outputPath), 'cypress');
  config.screenshotsFolder = path.join(artifactRoot, 'screenshots');
  config.videosFolder = path.join(artifactRoot, 'videos');
  config.downloadsFolder = path.join(artifactRoot, 'downloads');
  return outputPath;
}

module.exports = {
  ...base,
  // Review Lab passes only its run marker, temporary summary path, and
  // scenario plan through config.env. Keep the normal Cypress release gate
  // locked down; this compatibility switch is scoped to this isolated config.
  allowCypressEnv: true,
  e2e: {
    ...base.e2e,
    specPattern: 'cypress/e2e/review-environment.cy.js',
    setupNodeEvents(on, config) {
      const configured = setupBaseNodeEvents(on, config) || config;
      const configuredOutputPath = configureReviewArtifacts(configured);
      on('before:browser:launch', (browser, launchOptions) => {
        if (browser.family === 'chromium') {
          launchOptions.args.push('--force-device-scale-factor=1');
        }
        return launchOptions;
      });
      on('task', {
        writeReviewSummary({ outputPath, summary }) {
          if (outputPath !== configuredOutputPath) {
            throw new Error('Review Lab summary output path does not match the configured run.');
          }
          fs.mkdirSync(path.dirname(outputPath), { recursive: true });
          fs.writeFileSync(outputPath, `${JSON.stringify(summary, null, 2)}\n`, 'utf8');
          return null;
        },
      });
      configured.env.reviewLabRun = process.env.EDFINDER_REVIEW_LAB_RUN === '1';
      configured.env.reviewOutputPath = configuredOutputPath;
      configured.env.reviewScenariosJson = process.env.EDFINDER_REVIEW_SCENARIOS_JSON || '';
      return configured;
    },
  },
};
