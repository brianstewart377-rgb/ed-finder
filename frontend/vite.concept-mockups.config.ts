import path from 'node:path';
import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Isolated Vite entry for the UI concept mockup gallery.
//
// This mirrors the existing `vite.bakeoff.config.ts` / `vite.map-foundation.config.ts`
// isolation pattern. It is a design-exploration surface only: it does not touch
// canonical routes, hooks, stores, APIs, datasets, the map engine, or
// deployment configuration, and it is never part of the production `build`
// script. The gallery renders representative local mock data only.
const frontendRoot = fileURLToPath(new URL('.', import.meta.url));

export default defineConfig({
  root: frontendRoot,
  // Dedicated optimize cache so this entry never shares a (possibly stale)
  // dependency pre-bundle with the main app / other isolated entries, which
  // otherwise causes a duplicate-React "Invalid hook call".
  cacheDir: 'node_modules/.vite-concept-mockups',
  define: {
    __APP_VERSION__: JSON.stringify('concept-gallery'),
  },
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(frontendRoot, './src'),
    },
    // Guarantee a single React instance for the isolated bundle.
    dedupe: ['react', 'react-dom'],
  },
  optimizeDeps: {
    include: ['react', 'react-dom', 'react-dom/client', 'react/jsx-runtime', 'react/jsx-dev-runtime'],
  },
  server: { host: '127.0.0.1', port: 4176, strictPort: true },
  build: {
    outDir: 'dist-concept-mockups',
    emptyOutDir: true,
    sourcemap: true,
    rollupOptions: { input: path.resolve(frontendRoot, 'concept-mockups/index.html') },
  },
});
