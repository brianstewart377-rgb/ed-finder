import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './map-foundation/e2e',
  testMatch: 'foundation.spec.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: 'line',
  use: {
    baseURL: 'http://127.0.0.1:4175',
    browserName: 'chromium',
    headless: true,
  },
  webServer: {
    command: 'vite --config vite.map-foundation.config.ts',
    url: 'http://127.0.0.1:4175/map-foundation/index.html',
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
