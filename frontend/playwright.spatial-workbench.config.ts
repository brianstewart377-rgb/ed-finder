import { defineConfig } from '@playwright/test';
export default defineConfig({ testDir: './spatial-workbench/e2e', workers: 1, use: { baseURL: 'http://127.0.0.1:4177', browserName: 'chromium' }, webServer: { command: 'vite --config vite.spatial-workbench.config.ts', url: 'http://127.0.0.1:4177/spatial-workbench/index.html', reuseExistingServer: true, timeout: 120_000 } });
