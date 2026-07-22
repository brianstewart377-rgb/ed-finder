import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Plugin } from 'vite';

type RegionMapBlob = {
  origin: { x: number; z: number };
  pixel_scale: number;
  regions: string[];
  regionmap: Array<Array<[number, number]>>;
};

const frontendRoot = fileURLToPath(new URL('.', import.meta.url));
const defaultSourcePath = path.resolve(frontendRoot, '../apps/importer/src/data/region_map.json');

export function buildAuthoritativeRegionLayer(sourcePath = defaultSourcePath): string {
  const blob = JSON.parse(readFileSync(sourcePath, 'utf8')) as RegionMapBlob;
  if (blob.regions.length !== 43 || blob.regions[0] !== '') {
    throw new Error('Authoritative region source must contain the sentinel plus 42 named regions');
  }
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
  const width = Math.max(...blob.regionmap.map((row) => row.reduce((sum, [length]) => sum + length, 0)));
  let previousRow: Uint8Array | null = null;

  blob.regionmap.forEach((row, pz) => {
    const decoded = new Uint8Array(width);
    let px = 0;
    row.forEach(([runLength, regionId]) => {
      decoded.fill(regionId, px, px + runLength);
      if (regionId > 0) {
        const stats = regionStats[regionId]!;
        stats.count += runLength;
        stats.sumX += runLength * (px + (runLength - 1) / 2);
        stats.sumZ += runLength * pz;
        stats.spans.push({ px: px + runLength / 2, pz });
      }
      if (pz % stride === 0 && px > 0 && regionId !== decoded[px - 1]) {
        boundaries.push({ source: toGalaxy(px, pz), target: toGalaxy(px, pz + stride) });
      }
      px += runLength;
    });
    if (previousRow && pz % stride === 0) {
      for (let x = 0; x < width; x += stride) {
        if (decoded[x] !== previousRow[x] && (decoded[x] > 0 || previousRow[x] > 0)) {
          boundaries.push({ source: toGalaxy(x, pz), target: toGalaxy(Math.min(width, x + stride), pz) });
        }
      }
    }
    previousRow = decoded;
  });

  const labels = blob.regions.slice(1).map((name, offset) => {
    const id = offset + 1;
    const stats = regionStats[id]!;
    const centroid = { px: stats.sumX / stats.count, pz: stats.sumZ / stats.count };
    const interior = stats.spans.reduce<{ px: number; pz: number; distance: number }>((best, span) => {
      const distance = (span.px - centroid.px) ** 2 + (span.pz - centroid.pz) ** 2;
      return distance < best.distance ? { ...span, distance } : best;
    }, { px: 0, pz: 0, distance: Number.POSITIVE_INFINITY });
    return { id, name, position: toGalaxy(interior.px, interior.pz) };
  });
  return JSON.stringify({ labels, boundaries });
}

export function authoritativeRegionLayerPlugin(route: string, name: string): Plugin {
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
  };
}
