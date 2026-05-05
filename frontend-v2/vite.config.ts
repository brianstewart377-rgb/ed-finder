import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
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
// `base: '/v2/'` makes Vite emit assets with that prefix, so the bundle works
// when served from a sub-path. `server.proxy` mirrors that nginx mapping for
// local `yarn dev` so /api calls go to the dev API container.
// ────────────────────────────────────────────────────────────────────────────
export default defineConfig({
  base: '/v2/',
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5174,
    strictPort: true,
    proxy: {
      // Local-dev only: forward /api/* to whatever backend the developer has
      // running. Set VITE_DEV_API_TARGET to override the default localhost:8000.
      '/api': {
        target: process.env.VITE_DEV_API_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    // Smaller chunks fail fewer cache invalidations between deploys.
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom'],
        },
      },
    },
  },
});
