/// <reference types="vitest" />
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const rootDir = fileURLToPath(new URL('.', import.meta.url));
const packageJsonPath = path.resolve(rootDir, 'package.json');
const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf-8')) as { version?: string };
const appVersion = packageJson.version ?? '0.0.0';

// ────────────────────────────────────────────────────────────────────────────
// Vite config for ed-finder v2 — Emergent preview / dev variant.
//
// Differences from production config:
//   • `base: '/'` — preview serves the v2 React app at the root, not /v2/.
//   • Port 3000 + 0.0.0.0 host so Emergent's ingress can route to it.
//   • PWA plugin disabled (avoids stale SW caching during rapid iteration).
//   • allowedHosts: 'all' so the preview hostname (*.preview.emergentagent.com)
//     is accepted by Vite's HMR / host-check.
//   • /api proxied to local FastAPI on :8001 (the supervisor backend).
// ────────────────────────────────────────────────────────────────────────────
export default defineConfig(({ mode }) => {
  const loadedEnv = loadEnv(mode, rootDir, '');
  const proxyTarget = loadedEnv.VITE_DEV_API_TARGET
    || process.env.VITE_DEV_API_TARGET
    || 'http://127.0.0.1:8001';
  const publicBase = loadedEnv.VITE_PUBLIC_BASE
    || process.env.VITE_PUBLIC_BASE
    || '/';
  const cacheDir = loadedEnv.VITE_CACHE_DIR
    || process.env.VITE_CACHE_DIR
    || 'node_modules/.vite';

  return {
    base: publicBase,
    cacheDir,
    define: {
      __APP_VERSION__: JSON.stringify(appVersion),
    },
    plugins: [react()],
    resolve: {
      preserveSymlinks: true,
      alias: {
        '@': path.resolve(rootDir, './src'),
      },
    },
    server: {
      host: '0.0.0.0',
      port: 3000,
      strictPort: true,
      allowedHosts: true,
      hmr: {
        clientPort: 443,
        protocol: 'wss',
      },
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
    // Preview server (used by Playwright E2E and `yarn preview`) proxies
    // /api the same way the dev server does. Without this, the production
    // bundle served by `vite preview` would 404 every API call.
    preview: {
      host: '0.0.0.0',
      port: 4173,
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: 'dist',
      emptyOutDir: true,
      sourcemap: true,
      rollupOptions: {
        output: {
          manualChunks: {
            react: ['react', 'react-dom'],
          },
        },
      },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      include: ['src/**/*.test.{ts,tsx}'],
    },
  };
});
