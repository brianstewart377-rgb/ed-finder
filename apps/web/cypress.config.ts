import { defineConfig } from 'cypress';
export default defineConfig({
  allowCypressEnv: false,
  video: true,
  screenshotOnRunFailure: true,
  screenshotsFolder: 'cypress/artifacts/screenshots',
  videosFolder: 'cypress/artifacts/videos',
  e2e: {
    baseUrl: process.env.CYPRESS_BASE_URL ?? 'http://127.0.0.1:4174',
    specPattern: 'cypress/e2e/**/*.cy.ts',
    supportFile: false,
  },
});
