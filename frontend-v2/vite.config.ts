/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

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
export default defineConfig({
  base: '/',
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
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
        target: process.env.VITE_DEV_API_TARGET || 'http://127.0.0.1:8001',
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
  },
});
