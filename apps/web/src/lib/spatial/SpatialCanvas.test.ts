import { cleanup, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import SpatialCanvas from './SpatialCanvas.svelte';
import { buildGalaxyReviewFixtureScene } from './galaxy-review-fixture';
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
    await host?.dispatchEvent(
      new PointerEvent('pointerup', {
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

    adapter.runtimes[0]?.emit({
      type: 'SCENE_APPLIED',
      sceneRevision: 9,
      renderedLayers: [
        {
          contributionId: 'catalogue-density-base',
          contributionRevision: 9,
          layerId: 'catalogue-density',
          layerVersion: 1,
          representation: 'DERIVED',
          acceptedTargetCount: 3,
          renderedTargetCount: 3,
          sourceGeneration: 'fixture:density-v1',
        },
      ],
    });
    await waitFor(() => {
      expect(host).toHaveAttribute('data-applied-scene-revision', '9');
      expect(host).toHaveAttribute(
        'data-rendered-layer-ids',
        'catalogue-density',
      );
    });
  });

  it('forwards a contribution refresh after the scene is ready and mirrors its receipt', async () => {
    const scene = buildGalaxyReviewFixtureScene();
    const contributionPatch = {
      ...scene.contributions[0]!,
      revision: scene.contributions[0]!.revision + 1,
    };
    const view = render(SpatialCanvas, {
      props: {
        scene,
        contributionPatch,
        contributionPatchRevision: 1,
      },
    });
    const host = view.container.querySelector('.spatial-canvas');

    await waitFor(() =>
      expect(adapter.runtimes[0]?.dispatch).toHaveBeenCalledWith({
        type: 'PATCH_CONTRIBUTION',
        contribution: contributionPatch,
      }),
    );
    adapter.runtimes[0]?.emit({
      type: 'CONTRIBUTION_APPLIED',
      contributionId: contributionPatch.id,
      contributionRevision: contributionPatch.revision,
      renderedLayers: [
        {
          contributionId: contributionPatch.id,
          contributionRevision: contributionPatch.revision,
          layerId: 'catalogue-density',
          layerVersion: 1,
          representation: 'DERIVED',
          acceptedTargetCount: 20,
          renderedTargetCount: 20,
          sourceGeneration: 'fixture:galaxy-review-v1',
        },
      ],
    });

    await waitFor(() => {
      expect(host).toHaveAttribute('data-applied-contribution-revision', '2');
      expect(host).toHaveAttribute(
        'data-rendered-layer-ids',
        'catalogue-density',
      );
    });
  });

  it('throttles mouse hover, clears it on leave, and mirrors region events', async () => {
    let hoverCallback: FrameRequestCallback | undefined;
    vi.stubGlobal(
      'requestAnimationFrame',
      vi.fn((callback: FrameRequestCallback) => {
        hoverCallback = callback;
        return 91;
      }),
    );
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
    const eventHandler = vi.fn();
    const view = render(SpatialCanvas, {
      props: { onRuntimeEvent: eventHandler },
    });
    await waitFor(() => expect(adapter.runtimes).toHaveLength(1));
    const host = view.container.querySelector('.spatial-canvas');
    const canvas = view.container.querySelector('canvas');
    expect(host).toBeTruthy();
    expect(canvas).toBeTruthy();
    vi.spyOn(canvas!, 'getBoundingClientRect').mockReturnValue({
      left: 10,
      top: 20,
      right: 650,
      bottom: 380,
      width: 640,
      height: 360,
      x: 10,
      y: 20,
      toJSON: () => ({}),
    });

    host?.dispatchEvent(
      new PointerEvent('pointermove', {
        pointerType: 'mouse',
        clientX: 34,
        clientY: 58,
        bubbles: true,
      }),
    );
    host?.dispatchEvent(
      new PointerEvent('pointermove', {
        pointerType: 'mouse',
        clientX: 46,
        clientY: 72,
        bubbles: true,
      }),
    );
    expect(requestAnimationFrame).toHaveBeenCalledOnce();
    hoverCallback?.(0);
    expect(adapter.runtimes[0]?.dispatch).toHaveBeenCalledWith({
      type: 'HOVER',
      screenX: 36,
      screenY: 52,
    });

    const hovered = {
      type: 'TARGET_HOVERED' as const,
      target: { kind: 'region' as const, id: '18' },
    };
    adapter.runtimes[0]?.emit(hovered);
    expect(eventHandler).toHaveBeenCalledWith(hovered);
    await waitFor(() =>
      expect(host).toHaveAttribute('data-last-hovered-region-id', '18'),
    );

    host?.dispatchEvent(new PointerEvent('pointerleave', { bubbles: true }));
    expect(adapter.runtimes[0]?.dispatch).toHaveBeenCalledWith({
      type: 'CLEAR_HOVER',
    });

    adapter.runtimes[0]?.emit({
      type: 'TARGET_PICKED',
      target: { kind: 'region', id: '18' },
    });
    await waitFor(() =>
      expect(host).toHaveAttribute('data-last-picked-region-id', '18'),
    );
  });

  it('lets keyboard users pan, zoom and rotate with the same neutral camera command', async () => {
    const scene = buildGalaxyReviewFixtureScene();
    const view = render(SpatialCanvas, { props: { scene } });
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Zoom in' })).toBeVisible(),
    );
    await waitFor(() => expect(adapter.runtimes).toHaveLength(1));
    const host = view.container.querySelector('.spatial-canvas')!;
    const runtime = adapter.runtimes[0]!;
    host.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }),
    );
    await waitFor(() =>
      expect(runtime.dispatch).toHaveBeenCalledWith({
        type: 'SET_CAMERA',
        camera: expect.objectContaining({
          focusLy: expect.objectContaining({ x: expect.any(Number) }),
        }),
      }),
    );
    const pan = runtime.dispatch.mock.calls.findLast(
      ([command]) => command.type === 'SET_CAMERA',
    )?.[0];
    expect(pan.camera.focusLy.x).toBeGreaterThan(scene.camera.focusLy.x);
    expect(pan.camera.focusLy.y).toBe(scene.camera.focusLy.y);
    host.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'e', bubbles: true }),
    );
    const rotated = runtime.dispatch.mock.calls.findLast(
      ([command]) => command.type === 'SET_CAMERA',
    )?.[0];
    expect(rotated.camera.bearingRad).toBeCloseTo(0.12);
    screen.getByRole('button', { name: 'Zoom in' }).click();
    const zoomed = runtime.dispatch.mock.calls.findLast(
      ([command]) => command.type === 'SET_CAMERA',
    )?.[0];
    expect(zoomed.camera.distanceLy).toBeLessThan(scene.camera.distanceLy);
    screen.getByRole('button', { name: 'Top down' }).click();
    const top = runtime.dispatch.mock.calls.findLast(
      ([command]) => command.type === 'SET_CAMERA',
    )?.[0];
    expect(top.camera.pitchRad).toBe(Math.PI / 2);
    expect(top.transition).toEqual({ durationMs: 650, reducedMotion: true });
  });

  it('provides orbit, zoom and click controls for a system scene', async () => {
    const scene: SpatialSceneContract = {
      kind: 'system',
      revision: 12,
      systemId64: '42',
      fidelity: 'S1',
      camera: {
        systemId64: '42',
        focus: { kind: 'system', systemId64: '42' },
        semanticDistance: 38,
        bearingRad: -0.85,
        pitchRad: 0.58,
        revision: 12,
      },
      bodies: [],
      infrastructure: [],
      contributions: [],
    };
    const view = render(SpatialCanvas, { props: { scene } });
    await waitFor(() =>
      expect(
        screen.getByRole('application', { name: /Interactive 3D system map/ }),
      ).toBeVisible(),
    );
    await waitFor(() => expect(adapter.runtimes).toHaveLength(1));
    const host = view.container.querySelector('.spatial-canvas')!;
    const runtime = adapter.runtimes[0]!;
    host.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }),
    );
    const rotated = runtime.dispatch.mock.calls.findLast(
      ([command]) => command.type === 'SET_CAMERA',
    )?.[0];
    expect(rotated.camera).toMatchObject({
      systemId64: '42',
      bearingRad: scene.camera.bearingRad + 0.12,
    });
    screen.getByRole('button', { name: 'Zoom in' }).click();
    const zoomed = runtime.dispatch.mock.calls.findLast(
      ([command]) => command.type === 'SET_CAMERA',
    )?.[0];
    expect(zoomed.camera.semanticDistance).toBeLessThan(
      scene.camera.semanticDistance,
    );
    runtime.dispatch.mockClear();
    host.dispatchEvent(
      new PointerEvent('pointerdown', {
        pointerId: 5,
        button: 0,
        clientX: 30,
        clientY: 40,
        bubbles: true,
      }),
    );
    host.dispatchEvent(
      new PointerEvent('pointerup', {
        pointerId: 5,
        button: 0,
        clientX: 30,
        clientY: 40,
        bubbles: true,
      }),
    );
    expect(runtime.dispatch).toHaveBeenCalledWith({
      type: 'PICK',
      screenX: 30,
      screenY: 40,
    });
  });

  it('projects accepted system labels into a collision-managed visual overlay', async () => {
    const scene = buildGalaxyReviewFixtureScene();
    const view = render(SpatialCanvas, { props: { scene } });
    await waitFor(() =>
      expect(
        view.container.querySelector('[data-visible-label-count]'),
      ).toHaveAttribute('data-visible-label-count', '1'),
    );
    const systemLabels = view.container.querySelectorAll(
      '[data-map-label-kind="system"]',
    );
    expect(systemLabels).toHaveLength(1);
    expect(
      view.container.querySelector('[data-map-label-selected="true"]'),
    ).toHaveTextContent('Fixture Core');
    expect(systemLabels[0]?.closest('[aria-hidden="true"]')).toBeTruthy();
  });

  it('distinguishes a click from a pan and cancels interrupted gestures without picking', async () => {
    const scene = buildGalaxyReviewFixtureScene();
    const view = render(SpatialCanvas, { props: { scene } });
    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveAttribute(
        'data-renderer-state',
        'ready',
      ),
    );
    const host = view.container.querySelector('.spatial-canvas')!;
    const runtime = adapter.runtimes[0]!;
    runtime.dispatch.mockClear();
    const pointer = (type: string, x: number) =>
      host.dispatchEvent(
        new PointerEvent(type, {
          pointerId: 1,
          button: 0,
          clientX: x,
          clientY: 100,
          bubbles: true,
        }),
      );
    pointer('pointerdown', 100);
    pointer('pointermove', 180);
    pointer('pointerup', 180);
    expect(
      runtime.dispatch.mock.calls.some(
        ([command]) => command.type === 'SET_CAMERA',
      ),
    ).toBe(true);
    expect(
      runtime.dispatch.mock.calls.some(([command]) => command.type === 'PICK'),
    ).toBe(false);
    pointer('pointerdown', 180);
    pointer('pointercancel', 180);
    pointer('pointerup', 180);
    expect(
      runtime.dispatch.mock.calls.some(([command]) => command.type === 'PICK'),
    ).toBe(false);
    pointer('pointerdown', 200);
    pointer('pointerup', 200);
    expect(runtime.dispatch).toHaveBeenCalledWith({
      type: 'PICK',
      screenX: 200,
      screenY: 100,
    });
  });

  it('queues camera movements until an in-flight transition settles', async () => {
    vi.stubGlobal('matchMedia', () => ({ matches: false }));
    const scene = buildGalaxyReviewFixtureScene();
    const focusTarget = { kind: 'system' as const, systemId64: '42' };
    const view = render(SpatialCanvas, {
      props: { scene, focusTarget, focusRevision: 1 },
    });
    await waitFor(() =>
      expect(adapter.runtimes[0]?.dispatch).toHaveBeenCalledWith({
        type: 'LOAD_SCENE',
        scene,
      }),
    );
    await waitFor(() =>
      expect(adapter.runtimes[0]?.dispatch).toHaveBeenCalledWith({
        type: 'FLY_TO',
        target: focusTarget,
        reducedMotion: false,
      }),
    );

    const host = view.container.querySelector('.spatial-canvas');
    const runtime = adapter.runtimes[0];
    expect(host).toBeTruthy();
    expect(runtime).toBeTruthy();
    runtime?.dispatch.mockClear();

    host?.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }),
    );
    expect(
      runtime?.dispatch.mock.calls.some(
        ([command]) => command.type === 'SET_CAMERA',
      ),
    ).toBe(false);

    runtime?.emit({ type: 'TRANSITION_FINISHED', target: focusTarget });
    await waitFor(() =>
      expect(
        runtime?.dispatch.mock.calls.some(
          ([command]) => command.type === 'SET_CAMERA',
        ),
      ).toBe(true),
    );
  });
});
