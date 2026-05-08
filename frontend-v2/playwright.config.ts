import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright config for ED Finder v2 E2E tests.
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
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,           // shared backend = sequential is safer
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: 'http://localhost:4173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    // `yarn preview` after `yarn build` — serves the production bundle.
    command: 'yarn preview --port 4173 --strictPort',
    url:     'http://localhost:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
