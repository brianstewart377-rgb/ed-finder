import path from 'node:path';
import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
const root = fileURLToPath(new URL('.', import.meta.url));
export default defineConfig({ root, plugins: [react()], server: { host: '127.0.0.1', port: 4177, strictPort: true }, build: { outDir: 'dist-spatial-workbench', emptyOutDir: true, sourcemap: true, rollupOptions: { input: path.resolve(root, 'spatial-workbench/index.html') } } });
