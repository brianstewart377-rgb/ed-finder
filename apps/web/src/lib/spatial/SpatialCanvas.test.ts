import { cleanup, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import SpatialCanvas from './SpatialCanvas.svelte';

const adapter = vi.hoisted(() => ({
  runtimes: [] as Array<{
    resize: ReturnType<typeof vi.fn>;
    dispose: ReturnType<typeof vi.fn>;
  }>,
  create: vi.fn(),
}));

vi.mock('./babylon/adapter', () => ({
  createBabylonSpatialRuntime: adapter.create,
}));

let observerCallback: ResizeObserverCallback;
const observe = vi.fn();
const disconnect = vi.fn();

class ResizeObserverMock {
  constructor(callback: ResizeObserverCallback) {
    observerCallback = callback;
  }

  observe = observe;
  disconnect = disconnect;
  unobserve = vi.fn();
}

describe('SpatialCanvas', () => {
  beforeEach(() => {
    adapter.runtimes.length = 0;
    adapter.create.mockReset();
    observe.mockReset();
    disconnect.mockReset();
    vi.stubGlobal('ResizeObserver', ResizeObserverMock);
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(640);
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(360);
    adapter.create.mockImplementation((_canvas, onStatus) => {
      const record = { resize: vi.fn(), dispose: vi.fn() };
      adapter.runtimes.push(record);
      return {
        getStatus: () => ({ state: 'created' as const }),
        start: vi.fn(async () => {
          onStatus({ state: 'starting' });
          const ready = { state: 'ready' as const, backend: 'WEBGL2' as const };
          onStatus(ready);
          return ready;
        }),
        resize: record.resize,
        dispose: record.dispose,
      };
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('publishes accessible readiness and forwards observed dimensions', async () => {
    render(SpatialCanvas);

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveAttribute(
        'data-renderer-state',
        'ready',
      ),
    );
    expect(screen.getByRole('status')).toHaveTextContent(
      'Renderer ready (WEBGL2)',
    );
    expect(document.querySelector('[data-spatial-canvas]')).toBeTruthy();
    expect(adapter.runtimes[0]?.resize).toHaveBeenCalledWith({
      width: 640,
      height: 360,
      dpr: 1,
    });

    observerCallback(
      [
        {
          contentRect: { width: 800, height: 450 },
        } as unknown as ResizeObserverEntry,
      ],
      {} as ResizeObserver,
    );
    expect(adapter.runtimes[0]?.resize).toHaveBeenLastCalledWith({
      width: 800,
      height: 450,
      dpr: 1,
    });
  });

  it('disconnects observation and disposes each runtime across remounts', async () => {
    const first = render(SpatialCanvas);
    await waitFor(() => expect(adapter.runtimes).toHaveLength(1));
    first.unmount();

    expect(disconnect).toHaveBeenCalledOnce();
    expect(adapter.runtimes[0]?.dispose).toHaveBeenCalledOnce();

    const second = render(SpatialCanvas);
    await waitFor(() => expect(adapter.runtimes).toHaveLength(2));
    second.unmount();

    expect(disconnect).toHaveBeenCalledTimes(2);
    expect(adapter.runtimes[1]?.dispose).toHaveBeenCalledOnce();
  });
});
