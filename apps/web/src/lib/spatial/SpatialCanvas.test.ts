import { cleanup, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import SpatialCanvas from './SpatialCanvas.svelte';
import type { RuntimeEventListener, SpatialSceneContract } from './contracts';

const adapter = vi.hoisted(() => ({
  runtimes: [] as Array<{
    dispatch: ReturnType<typeof vi.fn>;
    dispose: ReturnType<typeof vi.fn>;
    emit: (event: Parameters<RuntimeEventListener>[0]) => void;
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
    vi.stubGlobal('matchMedia', () => ({ matches: true }));
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(640);
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(360);
    adapter.create.mockImplementation((_canvas, onStatus) => {
      let listener: RuntimeEventListener = () => undefined;
      const record = {
        dispatch: vi.fn(() => ({ status: 'executed' as const })),
        dispose: vi.fn(),
        emit: (event: Parameters<RuntimeEventListener>[0]) => listener(event),
      };
      adapter.runtimes.push(record);
      return {
        getStatus: () => ({ state: 'created' as const }),
        start: vi.fn(async () => {
          onStatus({ state: 'starting' });
          const ready = { state: 'ready' as const, backend: 'WEBGL2' as const };
          onStatus(ready);
          return ready;
        }),
        dispatch: record.dispatch,
        subscribe: vi.fn((next: RuntimeEventListener) => {
          listener = next;
          return vi.fn();
        }),
        resize: vi.fn(),
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
    expect(adapter.runtimes[0]?.dispatch).toHaveBeenCalledWith({
      type: 'RESIZE',
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
    expect(adapter.runtimes[0]?.dispatch).toHaveBeenLastCalledWith({
      type: 'RESIZE',
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

  it('loads product scenes, focuses targets, and forwards neutral picks from the stable host', async () => {
    const scene: SpatialSceneContract = {
      kind: 'galaxy',
      revision: 9,
      camera: {
        focusLy: { x: 0, y: 0, z: 0 },
        distanceLy: 30,
        bearingRad: 0,
        pitchRad: 0.5,
        projection: 'perspective',
        revision: 9,
      },
      selection: [],
      contributions: [],
    };
    const eventHandler = vi.fn();
    const focusTarget = { kind: 'system' as const, systemId64: '42' };
    const view = render(SpatialCanvas, {
      props: {
        scene,
        focusTarget,
        focusRevision: 1,
        onRuntimeEvent: eventHandler,
      },
    });
    await waitFor(() =>
      expect(adapter.runtimes[0]?.dispatch).toHaveBeenCalledWith({
        type: 'LOAD_SCENE',
        scene,
      }),
    );
    expect(adapter.runtimes[0]?.dispatch).toHaveBeenCalledWith({
      type: 'FLY_TO',
      target: focusTarget,
      reducedMotion: true,
    });

    const host = view.container.querySelector('.spatial-canvas');
    expect(host).toBeTruthy();
    await host?.dispatchEvent(
      new PointerEvent('pointerdown', {
        button: 0,
        clientX: 12,
        clientY: 18,
        bubbles: true,
      }),
    );
    expect(adapter.runtimes[0]?.dispatch).toHaveBeenCalledWith({
      type: 'PICK',
      screenX: 12,
      screenY: 18,
    });

    const picked = {
      type: 'TARGET_PICKED' as const,
      target: { kind: 'system' as const, systemId64: '42' },
    };
    adapter.runtimes[0]?.emit(picked);
    expect(eventHandler).toHaveBeenCalledWith(picked);
    await waitFor(() =>
      expect(host).toHaveAttribute('data-last-picked-id64', '42'),
    );
  });
});
