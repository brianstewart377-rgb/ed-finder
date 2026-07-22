import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  AUTHORITATIVE_REGION_BOUNDARY_LIMIT,
  fetchAuthoritativeRegionLayer,
  validateAuthoritativeRegionLayer,
} from './production-regions';

function layer() {
  return {
    labels: Array.from({ length: 42 }, (_, index) => ({
      id: index + 1,
      name: `Region ${index + 1}`,
      position: [index, index + 1, 0],
    })),
    boundaries: [{ source: [0, 0, 0], target: [1, 1, 0] }],
  };
}

afterEach(() => vi.restoreAllMocks());

describe('production authoritative region layer', () => {
  it('fetches and validates the bounded build asset', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(layer()), { status: 200 }));

    const result = await fetchAuthoritativeRegionLayer();

    expect(result.labels).toHaveLength(42);
    expect(result.boundaries).toHaveLength(1);
    expect(fetch).toHaveBeenCalledWith('/stage26e/authoritative-regions.json', { cache: 'no-cache' });
  });

  it('rejects duplicate labels and excessive boundary arrays', () => {
    const duplicateLabels = layer();
    duplicateLabels.labels[1]!.id = duplicateLabels.labels[0]!.id;
    expect(() => validateAuthoritativeRegionLayer(duplicateLabels)).toThrow('label ids must be unique');

    const excessive = layer();
    excessive.boundaries = Array.from(
      { length: AUTHORITATIVE_REGION_BOUNDARY_LIMIT + 1 },
      () => ({ source: [0, 0, 0], target: [1, 1, 0] }),
    );
    expect(() => validateAuthoritativeRegionLayer(excessive)).toThrow('exceeds 25000 boundaries');
  });

  it('rejects a response above the four-MiB transport budget', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(' '.repeat(4 * 1_048_576 + 1), { status: 200 }));

    await expect(fetchAuthoritativeRegionLayer()).rejects.toThrow('exceeds its response budget');
  });
});
