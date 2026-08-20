import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, type MapViewportResponse } from '@/lib/api';
import {
  realStarViewportBox,
  shouldEnableRealStarDetail,
  useViewportSystems,
} from './viewportSystems';

const viewport = { width: 1_000, height: 800 };

function response(id64: number, name: string): MapViewportResponse {
  return {
    systems: [{
      id64,
      name,
      x: id64,
      y: 0,
      z: 0,
      main_star_class: 'G',
      populated: false,
    }],
    truncated: false,
  };
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

afterEach(() => vi.restoreAllMocks());

describe('real-star viewport runtime contract', () => {
  it('uses distinct enter and exit thresholds at the LOD boundary', () => {
    const boundaryCamera = {
      center: { x: 0, z: 0 },
      zoom: 3, // Thresholds are 5000/8000 LY, so ~3 LY/px sits in hysteresis
      pitchDeg: 0.5,
    };

    expect(shouldEnableRealStarDetail(boundaryCamera, viewport, false)).toBe(false);
    expect(shouldEnableRealStarDetail(boundaryCamera, viewport, true)).toBe(true);
  });

  it('accounts for the tilted-camera ground footprint', () => {
    const topDown = realStarViewportBox(
      { center: { x: 0, z: 0 }, zoom: 1, pitchDeg: 0.5 },
      viewport,
    );
    const tilted = realStarViewportBox(
      { center: { x: 0, z: 0 }, zoom: 1, pitchDeg: 42 },
      viewport,
    );

    expect(topDown).not.toBeNull();
    expect(tilted).toBeNull();
  });

  it('drops old stars immediately while a panned viewport settles', async () => {
    let resolveSecond: ((value: MapViewportResponse) => void) | undefined;
    vi.spyOn(api, 'mapSystems')
      .mockResolvedValueOnce(response(1, 'First viewport'))
      .mockImplementationOnce(() => new Promise((resolve) => { resolveSecond = resolve; }));

    const initial = { center: { x: 0, z: 0 }, zoom: 1, pitchDeg: 42 };
    const hook = renderHook(
      ({ camera }) => useViewportSystems({ camera, viewport }),
      { wrapper, initialProps: { camera: initial } },
    );

    await waitFor(() => expect(hook.result.current.systems?.[0]?.name).toBe('First viewport'));

    hook.rerender({ camera: { ...initial, center: { x: 5_000, z: 0 } } });
    expect(hook.result.current.systems).toBeNull();
    expect(hook.result.current.isLoading).toBe(true);

    await waitFor(() => expect(api.mapSystems).toHaveBeenCalledTimes(2));
    resolveSecond?.(response(2, 'Second viewport'));
    await waitFor(() => expect(hook.result.current.systems?.[0]?.name).toBe('Second viewport'));
  });

  it('surfaces a current-viewport request failure', async () => {
    vi.spyOn(api, 'mapSystems').mockRejectedValue(new Error('detail lane failed'));
    const camera = { center: { x: 0, z: 0 }, zoom: 1, pitchDeg: 42 };
    const hook = renderHook(
      () => useViewportSystems({ camera, viewport }),
      { wrapper },
    );

    await waitFor(() => expect(hook.result.current.isError).toBe(true));
    expect(hook.result.current.error?.message).toBe('detail lane failed');
    expect(hook.result.current.systems).toBeNull();
  });
});
