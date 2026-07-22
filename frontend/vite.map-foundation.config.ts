import path from 'node:path';
import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import { authoritativeRegionLayerPlugin } from './vite.authoritative-regions';

const frontendRoot = fileURLToPath(new URL('.', import.meta.url));

export default defineConfig({
  root: frontendRoot,
  plugins: [react(), authoritativeRegionLayerPlugin('/__stage26c/regions', 'stage26c-authoritative-region-layer')],
  server: { host: '127.0.0.1', port: 4175, strictPort: true },
  build: {
    outDir: 'dist-map-foundation',
    emptyOutDir: true,
    sourcemap: true,
    rollupOptions: { input: path.resolve(frontendRoot, 'map-foundation/index.html') },
  },
});
