import { defineConfig, devices } from '@playwright/test';

const isCI = process.env.CI === 'true' || process.env.GITHUB_ACTIONS === 'true';
const reviewLabRun = process.env.EDFINDER_REVIEW_LAB_RUN === '1';

/**
 * Playwright config for ED Finder E2E tests.
 *
 * Audit fix (2026-05-08, AUDIT_REPORT.md §Phase 6): replaces the
 * hand-rolled "open the prod URL and click around" QA loop with
 * automated browser tests that run in CI.
 *
 * Two-part topology:
 *   1. Vite preview server (yarn build && yarn preview --port 4173)
 *      serves the static SPA. Started by Playwright's webServer below.
 *   2. The FastAPI backend is started separately by the integration
 *      test infra. Vite's proxy forwards /api/* to it.
 *
 * Run locally:
 *   yarn build && yarn preview --port 4173 &
 *   uvicorn main:app --port 8001 &
 *   yarn e2e
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 15_000,
  globalTimeout: isCI ? 10 * 60_000 : undefined,
  expect: { timeout: 5_000 },
  // Playwright creates a fresh BrowserContext for every test. Keep the suite
  // parallel and rely on that runner-level isolation instead of ad-hoc storage
  // cleanup inside individual specs.
  fullyParallel: true,
  workers: isCI ? 2 : undefined,
  forbidOnly: isCI,
  // Cypress now owns these release-gate journeys in CI. Keep the Playwright
  // versions available for local diagnostics during the migration, but do not
  // let their obsolete camera-driving assumptions block the replacement gate.
  grepInvert: isCI
    ? /loads the real-star detail endpoint after crossing the deep-zoom LOD|handles real-stars endpoint error gracefully/
    : undefined,
  // One retry classifies intermittent failures and produces retry traces, but a
  // test that only passes on retry still fails CI instead of normalising flakes.
  retries: isCI ? 1 : 0,
  retryStrategy: isCI ? 'isolated' : 'immediate',
  failOnFlakyTests: isCI,
  reportSlowTests: { max: 5, threshold: 10_000 },
  reporter: isCI
    ? [
        ['dot'],
        ['html', { open: 'never', outputFolder: 'playwright-report' }],
      ]
    : 'list',
  globalSetup: './e2e/globalSetup.ts',
  outputDir: 'test-results',
  preserveOutput: 'failures-only',
  use: {
    baseURL: 'http://localhost:4173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    // Firefox and MSEdge run locally only; CI uses chromium for speed
    ...(!isCI ? [
      {
        name: 'firefox',
        use: {
          ...devices['Desktop Firefox'],
          launchOptions: {
            headless: true,
            firefoxUserPrefs: {
              'webgl.force-enabled': true,
              'webgl.forbid-software': false,
            },
          },
        },
      },
      {
        name: 'msedge',
        use: {
          ...devices['Desktop Edge'],
          channel: 'msedge',
        },
      },
    ] : []),
  ],
  webServer: reviewLabRun ? undefined : {
    // `yarn preview` after `yarn build` — serves the production bundle.
    command: 'yarn preview --port 4173 --strictPort',
    url: 'http://localhost:4173',
    reuseExistingServer: !isCI,
    timeout: 60_000,
    env: {
      ...process.env,
      // Allow forcing full restart by setting PLAYWRIGHT_NO_REUSE_SERVER=1
      ...(process.env.PLAYWRIGHT_NO_REUSE_SERVER && { FORCE_REBUILD: '1' }),
    },
  },
});
