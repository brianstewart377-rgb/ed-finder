import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './stage26e-route/e2e',
  timeout: 180_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: 'http://127.0.0.1:4174',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [{
    name: 'chromium-precise-memory',
    use: {
      ...devices['Desktop Chrome'],
      launchOptions: {
        args: ['--enable-precise-memory-info'],
      },
    },
  }],
  webServer: {
    command: 'yarn stage26e-route:build && yarn stage26e-route:preview --port 4174 --strictPort',
    url: 'http://127.0.0.1:4174',
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
