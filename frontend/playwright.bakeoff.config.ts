import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './bakeoff/e2e',
  timeout: 120_000,
  expect: { timeout: 60_000 },
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:4174',
    browserName: 'chromium',
    headless: true,
    screenshot: 'only-on-failure',
    launchOptions: { args: ['--enable-precise-memory-info'] },
  },
  webServer: {
    command: 'yarn bakeoff:dev',
    url: 'http://127.0.0.1:4174/bakeoff/index.html',
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
