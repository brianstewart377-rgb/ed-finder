import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Plugin } from 'vite';
import {
  buildAuthoritativeRegionLayerFromBlob,
  type RegionMapBlob,
} from './src/features/map-foundation/authoritative-regions';

const frontendRoot = fileURLToPath(new URL('.', import.meta.url));
const defaultSourcePath = path.resolve(frontendRoot, '../apps/importer/src/data/region_map.json');

export function buildAuthoritativeRegionLayer(sourcePath = defaultSourcePath): string {
  const blob = JSON.parse(readFileSync(sourcePath, 'utf8')) as RegionMapBlob;
  return JSON.stringify(buildAuthoritativeRegionLayerFromBlob(blob));
}

export function authoritativeRegionLayerPlugin(
  route: string,
  name: string,
  assetFileName?: string,
): Plugin {
  const body = buildAuthoritativeRegionLayer();
  return {
    name,
    configureServer(server) {
      server.middlewares.use(route, (_request, response) => {
        response.statusCode = 200;
        response.setHeader('Content-Type', 'application/json');
        response.setHeader('Cache-Control', 'no-store');
        response.end(body);
      });
    },
    generateBundle() {
      if (!assetFileName) return;
      this.emitFile({ type: 'asset', fileName: assetFileName, source: body });
    },
  };
}
