import { QueryClient } from '@tanstack/svelte-query';
import { cleanup, render, screen, waitFor } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '$lib/api/client';
import { queryKeys } from '$lib/api/query';
import { parseId64 } from '$lib/domain/id64';
import type { CameraState } from './contracts';
import GalaxyStarQueryTestHost from './GalaxyStarQueryTestHost.svelte';
import {
  GALAXY_STAR_CELL_CACHE_LIMIT,
  MAX_GALAXY_STAR_ACTIVE_CELLS,
} from './galaxy-star-cells';
import { galaxyStarViewport } from './galaxy-star-stream';

vi.mock('$lib/api/client', async (loadOriginal) => ({
  ...(await loadOriginal<typeof import('$lib/api/client')>()),
  getCatalogueViewportSystems: vi.fn(),
}));

const queryPrefix = [...queryKeys.all, 'map', 'catalogue-stars'];
const viewportSize = { width: 1_200, height: 800 };
const camera = (x = 100, z = 300, distanceLy = 1_000): CameraState => ({
  focusLy: { x, y: 0, z },
  distanceLy,
  bearingRad: 0,
  pitchRad: Math.PI / 2,
  projection: 'perspective',
  revision: 1,
});
const props = (client: QueryClient, state: CameraState) => ({
  client,
  viewport: galaxyStarViewport(state, 'local', viewportSize),
  focus: state.focusLy,
});

function packet(): api.CatalogueViewportResponse | undefined {
  const text = screen.getByTestId('catalogue-packet').textContent;
  return text ? JSON.parse(text) : undefined;
}

async function settled(): Promise<void> {
  await waitFor(() => {
    expect(screen.getByTestId('catalogue-packet')).toHaveAttribute(
      'data-pending',
      'false',
    );
    expect(screen.getByTestId('catalogue-packet')).toHaveAttribute(
      'data-fetching',
      'false',
    );
    expect(packet()).toBeDefined();
  });
}

describe('catalogue cell query integration', () => {
  let client: QueryClient;
  let responseSequence: number;

  beforeEach(() => {
    client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    responseSequence = 0;
    vi.mocked(api.getCatalogueViewportSystems).mockReset();
    vi.mocked(api.getCatalogueViewportSystems).mockImplementation(
      async (request) => ({
        systems: [
          {
            id64: parseId64(String(++responseSequence)),
            name: `Cell system ${responseSequence}`,
            x: (request.minX + request.maxX) / 2,
            y: (request.minY + request.maxY) / 2,
            z: (request.minZ + request.maxZ) / 2,
            populated: false,
          },
        ],
        truncated: false,
      }),
    );
  });

  afterEach(() => {
    cleanup();
    client.clear();
    vi.restoreAllMocks();
  });

  it('reuses cached cells across a small pan and when returning to a previous view', async () => {
    const initial = props(client, camera());
    const view = render(GalaxyStarQueryTestHost, initial);
    await settled();
    const initialCalls = vi.mocked(api.getCatalogueViewportSystems).mock.calls
      .length;
    expect(initialCalls).toBeGreaterThan(0);
    expect(initialCalls).toBeLessThanOrEqual(MAX_GALAXY_STAR_ACTIVE_CELLS);

    await view.rerender(props(client, camera(150, 350)));
    await settled();
    expect(api.getCatalogueViewportSystems).toHaveBeenCalledTimes(initialCalls);

    const footprint = initial.viewport!;
    await view.rerender(
      props(
        client,
        camera(
          100 + footprint.maxX - footprint.minX,
          300 + footprint.maxZ - footprint.minZ,
        ),
      ),
    );
    await settled();
    const movedCalls = vi.mocked(api.getCatalogueViewportSystems).mock.calls
      .length;
    expect(movedCalls).toBeGreaterThan(initialCalls);

    await view.rerender(props(client, camera()));
    await settled();
    expect(api.getCatalogueViewportSystems).toHaveBeenCalledTimes(movedCalls);
    expect(
      client.getQueryCache().findAll({ queryKey: queryPrefix }).length,
    ).toBeLessThanOrEqual(GALAXY_STAR_CELL_CACHE_LIMIT);
  });

  it('publishes successful cells and marks the packet incomplete when one sibling fails', async () => {
    vi.mocked(api.getCatalogueViewportSystems).mockRejectedValueOnce(
      new Error('One cell unavailable'),
    );
    render(GalaxyStarQueryTestHost, props(client, camera()));
    await settled();
    const response = packet()!;
    expect(screen.getByTestId('catalogue-packet')).toHaveAttribute(
      'data-error',
      'true',
    );
    expect(response.truncated).toBe(true);
    expect(response.systems.length).toBeGreaterThan(0);
    expect(response.systems.length).toBe(
      vi.mocked(api.getCatalogueViewportSystems).mock.calls.length - 1,
    );
  });

  it('bounds dense cached packets without lowering the API detail-band limit', async () => {
    vi.mocked(api.getCatalogueViewportSystems).mockImplementation(
      async (request) => {
        const cellSequence = ++responseSequence;
        return {
          systems: Array.from({ length: 6_000 }, (_, index) => ({
            id64: parseId64(String(cellSequence * 10_000 + index)),
            name: `Dense cell ${cellSequence} star ${index}`,
            x:
              request.minX +
              ((index + 0.5) / 6_000) * (request.maxX - request.minX),
            y: (request.minY + request.maxY) / 2,
            z:
              request.minZ +
              ((((index * 31) % 6_000) + 0.5) / 6_000) *
                (request.maxZ - request.minZ),
            populated: false,
          })),
          truncated: false,
        };
      },
    );
    render(GalaxyStarQueryTestHost, props(client, camera(100, 300, 4_000)));
    await settled();
    expect(
      vi
        .mocked(api.getCatalogueViewportSystems)
        .mock.calls.every(([request]) => request.limit === 40_000),
    ).toBe(true);
    const cached = client
      .getQueryCache()
      .findAll({ queryKey: queryPrefix })
      .map((query) => query.state.data as api.CatalogueViewportResponse);
    expect(cached.length).toBeGreaterThan(0);
    expect(cached.every((data) => data.systems.length <= 5_000)).toBe(true);
    expect(cached.every((data) => data.truncated)).toBe(true);
    expect(packet()!.systems.length).toBeLessThanOrEqual(
      MAX_GALAXY_STAR_ACTIVE_CELLS * 5_000,
    );
    expect(packet()!.truncated).toBe(true);
  });

  it('evicts distant query packets after sustained travel while keeping the active view', async () => {
    let now = Date.now();
    vi.spyOn(Date, 'now').mockImplementation(() => now);
    const view = render(
      GalaxyStarQueryTestHost,
      props(client, camera(-40_000)),
    );
    await settled();
    const firstHashes = client
      .getQueryCache()
      .findAll({ queryKey: queryPrefix })
      .map((query) => query.queryHash);
    for (let index = 1; index <= 20; index++) {
      // Separate real navigation visits in time without waiting on the route's
      // minute-based request budget in a unit test.
      now += 61_000;
      await view.rerender(props(client, camera(-40_000 + index * 4_000)));
      await settled();
      const retained = client
        .getQueryCache()
        .findAll({ queryKey: queryPrefix });
      expect(retained.length).toBeLessThanOrEqual(GALAXY_STAR_CELL_CACHE_LIMIT);
      expect(
        retained
          .filter((query) => query.isActive())
          .every((query) => query.state.data),
      ).toBe(true);
    }
    expect(
      vi.mocked(api.getCatalogueViewportSystems).mock.calls.length,
    ).toBeGreaterThan(GALAXY_STAR_CELL_CACHE_LIMIT);
    expect(firstHashes.every((hash) => !client.getQueryCache().get(hash))).toBe(
      true,
    );
  });

  it('aborts active downloads, cancels queued cells and removes only its packets on unmount', async () => {
    const signals: AbortSignal[] = [];
    vi.mocked(api.getCatalogueViewportSystems).mockImplementation(
      (_request, signal) => {
        signals.push(signal!);
        return new Promise((_resolve, reject) => {
          signal!.addEventListener(
            'abort',
            () => reject(new DOMException('Aborted', 'AbortError')),
            { once: true },
          );
        });
      },
    );
    client.setQueryData(['unrelated'], 'keep');
    const state = camera(5_000, 5_000, 9_000);
    const view = render(GalaxyStarQueryTestHost, {
      ...props(client, state),
      viewport: galaxyStarViewport(state, 'local', {
        width: 2_100,
        height: 900,
      }),
    });
    await waitFor(() => expect(signals).toHaveLength(4));
    expect(
      client.getQueryCache().findAll({ queryKey: queryPrefix }).length,
    ).toBeGreaterThan(4);

    view.unmount();
    await tick();
    await waitFor(() =>
      expect(signals.every((signal) => signal.aborted)).toBe(true),
    );
    expect(api.getCatalogueViewportSystems).toHaveBeenCalledTimes(4);
    expect(
      client.getQueryCache().findAll({ queryKey: queryPrefix }),
    ).toHaveLength(0);
    expect(client.getQueryData(['unrelated'])).toBe('keep');
  });
});
