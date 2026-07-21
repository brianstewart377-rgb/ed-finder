import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin } from 'vite';

type RegionMapBlob = {
  origin: { x: number; z: number };
  pixel_scale: number;
  regions: string[];
  regionmap: Array<Array<[number, number]>>;
};

const frontendRoot = fileURLToPath(new URL('.', import.meta.url));
const sourcePath = path.resolve(frontendRoot, '../apps/importer/src/data/region_map.json');

function buildRegionLayer() {
  const blob = JSON.parse(readFileSync(sourcePath, 'utf8')) as RegionMapBlob;
  const toGalaxy = (px: number, pz: number): [number, number, number] => [
    px * blob.pixel_scale + blob.origin.x,
    pz * blob.pixel_scale + blob.origin.z,
    0,
  ];
  const regionStats = Array.from({ length: blob.regions.length }, () => ({
    count: 0,
    sumX: 0,
    sumZ: 0,
    spans: [] as Array<{ px: number; pz: number }>,
  }));
  const boundaries: Array<{ source: [number, number, number]; target: [number, number, number] }> = [];
  const stride = 4;

  blob.regionmap.forEach((row, pz) => {
    let px = 0;
    row.forEach(([runLength, regionId]) => {
      if (regionId > 0) {
        const stats = regionStats[regionId];
        stats.count += runLength;
        stats.sumX += runLength * (px + (runLength - 1) / 2);
        stats.sumZ += runLength * pz;
        stats.spans.push({ px: px + runLength / 2, pz });
      }
      if (pz % stride === 0 && regionId > 0) {
        if (px > 0) boundaries.push({ source: toGalaxy(px, pz), target: toGalaxy(px, pz + stride) });
      }
      px += runLength;
    });
  });

  const labels = blob.regions.slice(1).map((name, offset) => {
    const id = offset + 1;
    const stats = regionStats[id];
    const centroid = { px: stats.sumX / stats.count, pz: stats.sumZ / stats.count };
    const interior = stats.spans.reduce<{ px: number; pz: number; distance: number }>((best, span) => {
      const distance = (span.px - centroid.px) ** 2 + (span.pz - centroid.pz) ** 2;
      return distance < best.distance ? { ...span, distance } : best;
    }, { px: 0, pz: 0, distance: Number.POSITIVE_INFINITY });
    return { id, name, position: toGalaxy(interior.px, interior.pz) };
  });
  return JSON.stringify({ labels, boundaries });
}

function regionLayerPlugin(): Plugin {
  const body = buildRegionLayer();
  return {
    name: 'stage26b-authoritative-region-layer',
    configureServer(server) {
      server.middlewares.use('/__stage26b/regions', (_request, response) => {
        response.statusCode = 200;
        response.setHeader('Content-Type', 'application/json');
        response.setHeader('Cache-Control', 'no-store');
        response.end(body);
      });
    },
  };
}

export default defineConfig({
  root: frontendRoot,
  plugins: [react(), regionLayerPlugin()],
  server: { host: '127.0.0.1', port: 4174, strictPort: true },
  build: {
    outDir: 'dist-bakeoff',
    emptyOutDir: true,
    sourcemap: true,
    rollupOptions: { input: path.resolve(frontendRoot, 'bakeoff/index.html') },
  },
});
