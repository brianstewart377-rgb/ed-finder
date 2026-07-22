import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './map-foundation/e2e',
  testMatch: 'visual.spec.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'line',
  expect: { toHaveScreenshot: { threshold: 0.2 } },
  use: {
    ...devices['Desktop Chrome'],
    baseURL: 'http://127.0.0.1:4175',
    headless: true,
  },
  webServer: {
    command: 'vite --config vite.map-foundation.config.ts',
    url: 'http://127.0.0.1:4175/map-foundation/index.html',
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
