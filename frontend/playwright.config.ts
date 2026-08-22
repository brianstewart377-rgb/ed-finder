import { defineConfig, devices } from '@playwright/test';

const reviewLabRun = process.env.EDFINDER_REVIEW_LAB_RUN === '1';
const externalPreviewRun = process.env.EDFINDER_E2E_EXTERNAL_PREVIEW === '1';
const e2eBaseUrl = process.env.EDFINDER_E2E_BASE_URL || 'http://localhost:4173';

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
  expect: { timeout: 5_000 },
  fullyParallel: true,           // tests have proper isolation via beforeEach
  workers: process.env.CI ? 2 : undefined, // 2 workers in CI for parallelization
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? 'github' : 'list',
  // Review Lab owns an isolated Docker stack, API, and preview lifecycle.
  // Running the ordinary E2E setup as well starts a second local Compose
  // stack, waits for an API that setup never launches, and leaks that stack
  // into Review Lab's Docker-baseline check.
  globalSetup: reviewLabRun || externalPreviewRun ? undefined : './e2e/globalSetup.ts',
  use: {
    baseURL: e2eBaseUrl,
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
    ...(!process.env.CI ? [
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
  webServer: reviewLabRun || externalPreviewRun ? undefined : {
    // `yarn preview` after `yarn build` — serves the production bundle.
    command: 'yarn preview --port 4173 --strictPort',
    url:     'http://localhost:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    // Validate server is actually responding before reusing
    env: {
      ...process.env,
      // Allow forcing full restart by setting PLAYWRIGHT_NO_REUSE_SERVER=1
      ...(process.env.PLAYWRIGHT_NO_REUSE_SERVER && { FORCE_REBUILD: '1' }),
    },
  },
});
