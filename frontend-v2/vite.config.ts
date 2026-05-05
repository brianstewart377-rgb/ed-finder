/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
import path from 'node:path';

// ────────────────────────────────────────────────────────────────────────────
// Vite config for ed-finder v2.
// ────────────────────────────────────────────────────────────────────────────
//
// Deployment model:
//   /            → existing vanilla JS frontend (production today).
//   /v2/         → this React app, served by nginx from `dist/`.
//   /api/*       → FastAPI backend (unchanged).
//
// `base: '/v2/'` makes Vite emit assets with that prefix. The PWA plugin's
// `scope: '/v2/'` and `start_url: '/v2/'` keep the service worker confined
// to v2 so it can't accidentally intercept legacy / paths during the
// soft-launch window.
// ────────────────────────────────────────────────────────────────────────────
export default defineConfig({
  base: '/v2/',
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      // Confine the SW to /v2/ so it never claims root or /v1/.
      scope: '/v2/',
      base:  '/v2/',
      includeAssets: ['favicon.svg'],
      manifest: {
        name:             'ED:Finder',
        short_name:       'ED:Finder',
        description:      'Elite Dangerous system finder & colonisation planner',
        theme_color:      '#ff6a00',
        background_color: '#0d0d0d',
        display:          'standalone',
        scope:            '/v2/',
        start_url:        '/v2/',
        icons: [
          { src: 'pwa-icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any maskable' },
        ],
      },
      workbox: {
        // Don't precache source maps or icon SVGs over 5 MB.
        maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
        // API responses are highly dynamic; cache them with NetworkFirst,
        // 5s timeout, 24h max age. Static /v2/ assets get StaleWhileRevalidate.
        runtimeCaching: [
          {
            urlPattern: /\/api\/.*$/,
            handler:    'NetworkFirst',
            options: {
              cacheName: 'api',
              networkTimeoutSeconds: 5,
              expiration: { maxEntries: 200, maxAgeSeconds: 60 * 60 * 24 },
            },
          },
        ],
      },
      devOptions: { enabled: false },   // PWA off in dev — too easy to confuse stale state with bugs
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5174,
    strictPort: true,
    proxy: {
      '/api': {
        target: process.env.VITE_DEV_API_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
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
    // Tests don't need the heavy PWA build pipeline.
    deps: { inline: ['vite-plugin-pwa'] },
  },
});
