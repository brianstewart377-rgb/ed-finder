import { afterEach, describe, expect, it, vi } from 'vitest';
import { LIVE_ROUTE_HEAP_BUDGET_BYTES, measureLiveRouteHeap } from './live-route-memory';

afterEach(() => vi.unstubAllGlobals());

describe('Stage 26E live-route heap measurement', () => {
  it('reports a supported bounded sample series', async () => {
    vi.stubGlobal('performance', { memory: { usedJSHeapSize: 64 * 1_048_576 } });
    const measurement = await measureLiveRouteHeap(3, 0);
    expect(measurement).toEqual({
      supported: true,
      budgetBytes: LIVE_ROUTE_HEAP_BUDGET_BYTES,
      sampleCount: 3,
      samplesBytes: [64 * 1_048_576, 64 * 1_048_576, 64 * 1_048_576],
      minBytes: 64 * 1_048_576,
      maxBytes: 64 * 1_048_576,
      spreadBytes: 0,
      withinBudget: true,
    });
  });

  it('does not invent heap evidence when Chromium memory data is unavailable', async () => {
    vi.stubGlobal('performance', {});
    expect(await measureLiveRouteHeap(2, 0)).toMatchObject({
      supported: false,
      sampleCount: 0,
      withinBudget: null,
    });
  });
});
