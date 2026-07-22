export type RegionMapBlob = {
  origin: { x: number; z: number };
  pixel_scale: number;
  regions: string[];
  regionmap: Array<Array<[number, number]>>;
};

type GalaxyPoint = [number, number, number];
type RegionBoundary = { source: GalaxyPoint; target: GalaxyPoint };
type RegionLayer = {
  labels: Array<{ id: number; name: string; position: GalaxyPoint }>;
  boundaries: RegionBoundary[];
};

function boundaryPair(left: number, right: number): string {
  return left < right ? `${left}:${right}` : `${right}:${left}`;
}

export function buildAuthoritativeRegionLayerFromBlob(blob: RegionMapBlob): RegionLayer {
  if (blob.regions.length !== 43 || blob.regions[0] !== '') {
    throw new Error('Authoritative region source must contain the sentinel plus 42 named regions');
  }
  const toGalaxy = (px: number, pz: number): GalaxyPoint => [
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
  const boundaries: RegionBoundary[] = [];
  const width = Math.max(...blob.regionmap.map((row) => row.reduce((sum, [length]) => sum + length, 0)));
  const decodedRows = blob.regionmap.map((row, pz) => {
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
      px += runLength;
    });
    return decoded;
  });

  // Merge consecutive cell edges into continuous line segments. The previous
  // stride sampler left three-pixel gaps between every four-pixel fragment,
  // which made correct region outlines look like broken Morse-code strokes.
  const activeVertical = new Map<string, { px: number; startPz: number }>();
  decodedRows.forEach((row, pz) => {
    const present = new Set<string>();
    for (let px = 1; px < width; px += 1) {
      const left = row[px - 1]!;
      const right = row[px]!;
      if (left === right || (left === 0 && right === 0)) continue;
      const key = `${px}:${boundaryPair(left, right)}`;
      present.add(key);
      if (!activeVertical.has(key)) activeVertical.set(key, { px, startPz: pz });
    }
    activeVertical.forEach((segment, key) => {
      if (present.has(key)) return;
      boundaries.push({
        source: toGalaxy(segment.px, segment.startPz),
        target: toGalaxy(segment.px, pz),
      });
      activeVertical.delete(key);
    });
  });
  activeVertical.forEach((segment) => boundaries.push({
    source: toGalaxy(segment.px, segment.startPz),
    target: toGalaxy(segment.px, decodedRows.length),
  }));

  for (let pz = 1; pz < decodedRows.length; pz += 1) {
    const previous = decodedRows[pz - 1]!;
    const current = decodedRows[pz]!;
    let runStart = 0;
    let activePair = '';
    for (let px = 0; px <= width; px += 1) {
      const above = px < width ? previous[px]! : 0;
      const below = px < width ? current[px]! : 0;
      const pair = px < width && above !== below && (above > 0 || below > 0)
        ? boundaryPair(above, below)
        : '';
      if (pair === activePair) continue;
      if (activePair) {
        boundaries.push({ source: toGalaxy(runStart, pz), target: toGalaxy(px, pz) });
      }
      runStart = px;
      activePair = pair;
    }
  }

  const labels = blob.regions.slice(1).map((name, offset) => {
    const id = offset + 1;
    const stats = regionStats[id]!;
    if (stats.count === 0) return { id, name, position: toGalaxy(0, 0) };
    const centroid = { px: stats.sumX / stats.count, pz: stats.sumZ / stats.count };
    const interior = stats.spans.reduce<{ px: number; pz: number; distance: number }>((best, span) => {
      const distance = (span.px - centroid.px) ** 2 + (span.pz - centroid.pz) ** 2;
      return distance < best.distance ? { ...span, distance } : best;
    }, { px: 0, pz: 0, distance: Number.POSITIVE_INFINITY });
    return { id, name, position: toGalaxy(interior.px, interior.pz) };
  });
  return { labels, boundaries };
}
