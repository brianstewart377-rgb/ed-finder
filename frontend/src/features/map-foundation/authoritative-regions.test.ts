import { describe, expect, it } from 'vitest';
import {
  buildAuthoritativeRegionLayerFromBlob,
  decodeAuthoritativeRegionLookup,
  findAuthoritativeRegionAt,
  type RegionMapBlob,
} from './authoritative-regions';

function fixture(regionmap: RegionMapBlob['regionmap']): RegionMapBlob {
  return {
    origin: { x: 0, z: 0 },
    pixel_scale: 1,
    regions: ['', ...Array.from({ length: 42 }, (_, index) => `Region ${index + 1}`)],
    regionmap,
  };
}

describe('authoritative region boundaries', () => {
  it('merges straight cell edges instead of emitting sampled dashes', () => {
    const layer = buildAuthoritativeRegionLayerFromBlob(fixture([
      [[2, 1], [2, 2]],
      [[2, 1], [2, 2]],
      [[4, 1]],
      [[4, 1]],
    ]));

    expect(layer.boundaries).toEqual([
      { source: [2, 0, 0], target: [2, 2, 0] },
      { source: [2, 2, 0], target: [4, 2, 0] },
    ]);
  });

  it('joins a stepped boundary with a horizontal bridge', () => {
    const layer = buildAuthoritativeRegionLayerFromBlob(fixture([
      [[2, 1], [2, 2]],
      [[2, 1], [2, 2]],
      [[3, 1], [1, 2]],
      [[3, 1], [1, 2]],
    ]));

    expect(layer.boundaries).toEqual([
      { source: [2, 0, 0], target: [2, 2, 0] },
      { source: [3, 2, 0], target: [3, 4, 0] },
      { source: [2, 2, 0], target: [3, 2, 0] },
    ]);
  });

  it('decodes the existing RLE grid once for constant-time camera-centre lookup', () => {
    const decoded = decodeAuthoritativeRegionLookup(fixture([
      [[2, 1], [2, 2]],
      [[1, 1], [3, 2]],
    ]));

    expect(findAuthoritativeRegionAt(decoded, { x: 0.5, z: 0.5 })).toEqual({
      id: 1,
      name: 'Region 1',
    });
    expect(findAuthoritativeRegionAt(decoded, { x: 2.5, z: 0.5 })).toEqual({
      id: 2,
      name: 'Region 2',
    });
    expect(findAuthoritativeRegionAt(decoded, { x: -1, z: 0 })).toBeNull();
    expect(findAuthoritativeRegionAt(decoded, { x: 4, z: 0 })).toBeNull();
  });
});
