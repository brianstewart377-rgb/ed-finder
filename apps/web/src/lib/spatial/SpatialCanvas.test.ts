import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/svelte';
import axe from 'axe-core';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import SpatialCanvas from './SpatialCanvas.svelte';
import { buildGalaxyReviewFixtureScene } from './galaxy-review-fixture';
import * as galaxyLabels from './galaxy-labels';
import type {
  CameraState,
  GalaxySceneContract,
  GalaxySystemPoint,
  RuntimeEventListener,
  SpatialSceneContract,
} from './contracts';

const adapter = vi.hoisted(() => ({
  runtimes: [] as Array<{
    dispatch: ReturnType<typeof vi.fn>;
    dispose: ReturnType<typeof vi.fn>;
    emit: (event: Parameters<RuntimeEventListener>[0]) => void;
  }>,
  create: vi.fn(),
}));

const feature = vi.hoisted(() => ({ finder: false }));

vi.mock('$lib/config', async (importOriginal) => ({
  ...(await importOriginal<typeof import('$lib/config')>()),
  get FINDER_F4_ENABLED() {
    return feature.finder;
  },
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

const catalogueStar: GalaxySystemPoint = {
  systemId64: '9007199254740993',
  name: 'Catalogue Vega',
  positionLy: { x: 0, y: 0, z: 0 },
  primaryStar: { type: 'G2' },
};
const overlappingStar: GalaxySystemPoint = {
  systemId64: '9007199254740994',
  name: 'Nearby companion',
  positionLy: { x: 2, y: 0, z: 0 },
  primaryStar: { type: 'M4' },
};
const finderStar: GalaxySystemPoint = {
  systemId64: '41',
  name: 'Finder Reach',
  positionLy: { x: -180, y: 0, z: 0 },
};

function nearbyScene(): GalaxySceneContract {
  return {
    kind: 'galaxy',
    revision: 1,
    camera: {
      focusLy: { x: 0, y: 0, z: 0 },
      distanceLy: 500,
      bearingRad: 0,
      pitchRad: 0.55,
      projection: 'perspective',
      revision: 1,
    },
    selection: [],
    contributions: [
      {
        id: 'nearby-catalogue',
        owner: 'CATALOGUE',
        revision: 1,
        layers: [
          {
            id: 'catalogue-systems',
            version: 1,
            representation: 'AUTHORITATIVE',
            payload: { systems: [catalogueStar, overlappingStar] },
            targetCount: 2,
            truncated: false,
          },
        ],
      },
      {
        id: 'nearby-finder',
        owner: 'FINDER',
        revision: 1,
        layers: [
          {
            id: 'finder-systems',
            version: 1,
            representation: 'AUTHORITATIVE',
            payload: { systems: [finderStar] },
            targetCount: 1,
            truncated: false,
          },
        ],
      },
    ],
  };
}

describe('SpatialCanvas', () => {
  beforeEach(() => {
    feature.finder = false;
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
    vi.useRealTimers();
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

  it('projects named Finder buttons with selected emphasis and preserved identities', async () => {
    const scene = buildGalaxyReviewFixtureScene();
    const view = render(SpatialCanvas, { props: { scene } });
    await waitFor(() =>
      expect(
        view.container.querySelector('[data-visible-label-count]'),
      ).toHaveAttribute('data-visible-label-count', '3'),
    );
    const systemLabels = view.container.querySelectorAll(
      '[data-map-label-kind="system"]',
    );
    expect(systemLabels).toHaveLength(3);
    expect(
      view.container.querySelector('[data-map-label-selected="true"]'),
    ).toHaveTextContent('Fixture Core');
    for (const label of systemLabels) {
      expect(label.tagName).toBe('BUTTON');
      expect(label).toHaveAttribute('data-system-id64');
      expect(label.closest('[aria-hidden="true"]')).toBeNull();
    }
  });

  it('keeps Nearby systems collapsed and exposes overlapping candidates for keyboard selection and focus', async () => {
    const onRuntimeEvent = vi.fn();
    const view = render(SpatialCanvas, {
      scene: nearbyScene(),
      onRuntimeEvent,
    });
    const summary = await screen.findByText('Nearby systems (3)');
    const disclosure = summary.closest('details')!;
    expect(disclosure).not.toHaveAttribute('open');
    summary.focus();
    expect(summary).toHaveFocus();
    // Native summary/button keyboard activation dispatches a detail: 0 click.
    await fireEvent.click(summary, { detail: 0 });
    expect(disclosure).toHaveAttribute('open');
    const list = await screen.findByRole('list', { name: 'Nearby systems' });
    expect(
      within(list)
        .getAllByRole('button')
        .map((button) => button.dataset.systemId64),
    ).toEqual([
      catalogueStar.systemId64,
      finderStar.systemId64,
      overlappingStar.systemId64,
    ]);
    expect(
      view.container.querySelector(
        `[data-map-label-key="system:${overlappingStar.systemId64}"]`,
      ),
    ).toBeNull();

    const button = within(list).getByRole('button', {
      name: overlappingStar.name,
    });
    button.focus();
    await tick();
    expect(button).toHaveFocus();
    const tooltip = screen.getByRole('tooltip', {
      name: `System ${overlappingStar.name}`,
    });
    expect(button.getAttribute('aria-describedby')?.split(/\s+/u)).toContain(
      tooltip.id,
    );
    expect(tooltip).toHaveAttribute(
      'data-system-id64',
      overlappingStar.systemId64,
    );
    expect(onRuntimeEvent).toHaveBeenCalledWith({
      type: 'TARGET_HOVERED',
      target: {
        kind: 'system',
        systemId64: overlappingStar.systemId64,
        name: overlappingStar.name,
      },
    });
    expect(onRuntimeEvent).not.toHaveBeenCalledWith(
      expect.objectContaining({ type: 'TARGET_PICKED' }),
    );
    await fireEvent.keyDown(button, { key: 'Enter' });
    await fireEvent.click(button, { detail: 0 });
    const target = { kind: 'system', systemId64: overlappingStar.systemId64 };
    expect(onRuntimeEvent).toHaveBeenCalledWith({
      type: 'TARGET_PICKED',
      target,
    });
    expect(adapter.runtimes[0]?.dispatch).toHaveBeenCalledWith({
      type: 'FLY_TO',
      target,
      reducedMotion: true,
    });
    expect(view.container.querySelector('.spatial-canvas')).toHaveAttribute(
      'tabindex',
      '0',
    );
  });

  it('keeps list focus and order through hover ranking and returns from the card on Escape', async () => {
    render(SpatialCanvas, { scene: nearbyScene() });
    await fireEvent.click(await screen.findByText('Nearby systems (3)'));
    const list = await screen.findByRole('list', { name: 'Nearby systems' });
    const originalOrder = within(list).getAllByRole('button');
    const opener = within(list).getByRole('button', {
      name: overlappingStar.name,
    });
    expect(originalOrder.at(-1)).toBe(opener);
    vi.useFakeTimers();
    opener.focus();
    await tick();
    await vi.advanceTimersByTimeAsync(250);
    await tick();
    expect(opener).toHaveFocus();
    expect(within(list).getAllByRole('button')).toEqual(originalOrder);

    await fireEvent.keyDown(opener, { key: 'ArrowRight' });
    await tick();
    const tooltip = screen.getByRole('tooltip', {
      name: `System ${overlappingStar.name}`,
    });
    const select = within(tooltip).getByRole('button', { name: 'Select' });
    expect(select).toHaveFocus();
    // Native Tab navigation remains available inside and outside the card.
    expect(await fireEvent.keyDown(select, { key: 'Tab' })).toBe(true);
    await fireEvent.keyDown(select, { key: 'Escape' });
    await tick();
    expect(opener).toHaveFocus();
    expect(screen.queryByRole('tooltip')).toBeNull();
    await vi.advanceTimersByTimeAsync(250);
    await tick();
    expect(opener).toHaveFocus();
    expect(screen.queryByRole('tooltip')).toBeNull();
    expect(within(list).getAllByRole('button')).toEqual(originalOrder);
  });

  it('preserves the newer region hover when the preceding system card is dismissed', async () => {
    const onRuntimeEvent = vi.fn();
    const view = render(SpatialCanvas, {
      scene: nearbyScene(),
      onRuntimeEvent,
    });
    await screen.findByText('Nearby systems (3)');
    const runtime = adapter.runtimes[0]!;
    runtime.emit({
      type: 'TARGET_HOVERED',
      target: {
        kind: 'system',
        systemId64: catalogueStar.systemId64,
        name: catalogueStar.name,
      },
      screenX: 100,
      screenY: 80,
    });
    await screen.findByRole('tooltip', {
      name: `System ${catalogueStar.name}`,
    });
    vi.useFakeTimers();
    const regionHover = {
      type: 'TARGET_HOVERED',
      target: { kind: 'region', id: '18' },
    } as const;
    onRuntimeEvent.mockClear();
    runtime.emit(regionHover);
    await tick();
    await vi.advanceTimersByTimeAsync(220);
    await tick();
    expect(screen.queryByRole('tooltip')).toBeNull();
    expect(onRuntimeEvent).toHaveBeenLastCalledWith(regionHover);
    expect(view.container.querySelector('.spatial-canvas')).toHaveAttribute(
      'data-last-hovered-region-id',
      '18',
    );
  });

  it('preserves catalogue identity on label hover and click without triggering a canvas pick', async () => {
    const onSystemSelect = vi.fn();
    const onRuntimeEvent = vi.fn();
    const view = render(SpatialCanvas, {
      scene: nearbyScene(),
      onSystemSelect,
      onRuntimeEvent,
    });
    const label = await screen.findByRole('button', {
      name: `Select ${catalogueStar.name}`,
    });
    const runtime = adapter.runtimes[0]!;
    runtime.dispatch.mockClear();
    await fireEvent.pointerEnter(label, {
      clientX: 100,
      clientY: 80,
      pointerType: 'mouse',
    });
    const tooltip = screen.getByRole('tooltip', {
      name: `System ${catalogueStar.name}`,
    });
    expect(label).toHaveAttribute('data-system-id64', catalogueStar.systemId64);
    expect(label.getAttribute('aria-describedby')?.split(/\s+/u)).toContain(
      tooltip.id,
    );
    expect(onRuntimeEvent).toHaveBeenCalledWith({
      type: 'TARGET_HOVERED',
      target: {
        kind: 'system',
        systemId64: catalogueStar.systemId64,
        name: catalogueStar.name,
      },
    });
    expect(within(tooltip).getByText('G2', { exact: true })).toBeVisible();
    expect(within(tooltip).queryByText('G class star')).toBeNull();
    await fireEvent.pointerDown(label, { button: 0, pointerId: 1 });
    await fireEvent.pointerUp(label, { button: 0, pointerId: 1 });
    await fireEvent.click(label);
    expect(onSystemSelect).toHaveBeenCalledExactlyOnceWith(catalogueStar);
    expect(
      runtime.dispatch.mock.calls.some(([command]) => command.type === 'PICK'),
    ).toBe(false);
    expect(view.container.querySelector('.spatial-canvas')).toHaveAttribute(
      'data-last-hovered-system-id',
      catalogueStar.systemId64,
    );
  });

  it('shows renderer hover cards near the pointer and passes axe with the expanded list', async () => {
    const view = render(SpatialCanvas, {
      scene: nearbyScene(),
      anchorPoint: finderStar,
    });
    const summary = await screen.findByText('Nearby systems (3)');
    await fireEvent.click(summary);
    expect(
      await screen.findByRole('list', { name: 'Nearby systems' }),
    ).toBeVisible();
    adapter.runtimes[0]!.emit({
      type: 'TARGET_HOVERED',
      target: {
        kind: 'system',
        systemId64: catalogueStar.systemId64,
        name: catalogueStar.name,
      },
      screenX: 100,
      screenY: 80,
    });
    const tooltip = await screen.findByRole('tooltip', {
      name: `System ${catalogueStar.name}`,
    });
    expect(tooltip.parentElement).toHaveStyle({ left: '114px', top: '94px' });
    expect(within(tooltip).getByText('G2', { exact: true })).toBeVisible();
    expect(
      within(tooltip).getByText('Distance from Finder Reach'),
    ).toBeVisible();
    expect(within(tooltip).getByText('180.0 LY')).toBeVisible();
    expect(
      within(tooltip).getByRole('link', { name: 'Inspect' }),
    ).toHaveAttribute('href', `/inspect?system=${catalogueStar.systemId64}`);
    const result = await axe.run(view.container, {
      rules: { 'color-contrast': { enabled: false } },
    });
    expect(result.violations).toEqual([]);
  });

  it('ranks candidates and resolves overlap only after camera changes settle', async () => {
    const candidates = vi.spyOn(galaxyLabels, 'galaxyLabelCandidates');
    const layout = vi.spyOn(galaxyLabels, 'layoutGalaxyLabels');
    const scene = nearbyScene();
    render(SpatialCanvas, { scene });
    await screen.findByText('Nearby systems (3)');
    candidates.mockClear();
    layout.mockClear();
    vi.useFakeTimers();
    const runtime = adapter.runtimes[0]!;
    for (let revision = 2; revision <= 4; revision += 1) {
      runtime.emit({
        type: 'CAMERA_CHANGED',
        camera: { ...scene.camera, bearingRad: revision / 10, revision },
      });
      await tick();
      await vi.advanceTimersByTimeAsync(100);
      expect(candidates).not.toHaveBeenCalled();
      expect(layout).not.toHaveBeenCalled();
    }
    await vi.advanceTimersByTimeAsync(79);
    expect(candidates).not.toHaveBeenCalled();
    expect(layout).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    await tick();
    expect(candidates).toHaveBeenCalledOnce();
    expect(layout).toHaveBeenCalledOnce();
    expect(candidates.mock.calls[0]?.[0].camera.revision).toBe(4);
    expect(layout.mock.calls[0]?.[0]).toHaveLength(3);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(candidates).toHaveBeenCalledOnce();
    expect(layout).toHaveBeenCalledOnce();
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

  it.each(['overview', 'system focus'] as const)(
    'retains the settled %s camera when Finder data changes during the transition',
    async (movement) => {
      feature.finder = true;
      vi.stubGlobal('matchMedia', () => ({ matches: false }));
      const scene = buildGalaxyReviewFixtureScene();
      const focusTarget = {
        kind: 'system' as const,
        systemId64: '9007199254740994',
      };
      const settledCamera: CameraState = {
        ...scene.camera,
        focusLy: { x: 0, y: -6, z: 70 },
        distanceLy: movement === 'overview' ? 118_000 : 60,
        revision: 21,
      };
      const onTransitionChange = vi.fn();
      const view = render(SpatialCanvas, {
        props: {
          scene,
          onTransitionChange,
          ...(movement === 'overview'
            ? { cameraRequest: settledCamera, cameraRequestRevision: 1 }
            : { focusTarget, focusRevision: 1 }),
        },
      });
      await waitFor(() =>
        expect(view.container.querySelector('.spatial-canvas')).toHaveAttribute(
          'data-camera-transition-active',
          'true',
        ),
      );
      const runtime = adapter.runtimes[0]!;
      runtime.dispatch.mockClear();
      // A real LOAD_SCENE rebuild emits its supplied camera synchronously.
      // Replaying the pre-flight scene camera here would undo the flight.
      runtime.dispatch.mockImplementation((command) => {
        if (command.type === 'LOAD_SCENE') {
          runtime.emit({
            type: 'CAMERA_CHANGED',
            camera: command.scene.camera,
          });
        }
        return { status: 'executed' };
      });
      const refreshedScene: SpatialSceneContract = {
        ...scene,
        revision: scene.revision + 1,
        contributions: [
          ...scene.contributions,
          {
            id: 'new-finder-result',
            owner: 'FINDER',
            revision: 1,
            layers: [
              {
                id: 'finder-systems',
                version: 1,
                representation: 'AUTHORITATIVE',
                targetCount: 1,
                truncated: false,
                payload: {
                  systems: [
                    {
                      systemId64: '10477373803000',
                      name: 'New Finder point',
                      positionLy: { x: 100, y: 30, z: 100 },
                    },
                  ],
                },
              },
            ],
          },
        ],
      };
      await view.rerender({ scene: refreshedScene });
      expect(runtime.dispatch).not.toHaveBeenCalled();

      runtime.emit({ type: 'CAMERA_CHANGED', camera: settledCamera });
      runtime.emit({
        type: 'TRANSITION_FINISHED',
        ...(movement === 'system focus' ? { target: focusTarget } : {}),
      });

      await waitFor(() =>
        expect(runtime.dispatch).toHaveBeenCalledWith({
          type: 'LOAD_SCENE',
          scene: { ...refreshedScene, camera: settledCamera },
        }),
      );
      expect(onTransitionChange).toHaveBeenLastCalledWith(false, settledCamera);
      expect(view.container.querySelector('.spatial-canvas')).toHaveAttribute(
        'data-camera-revision',
        '21',
      );
      expect(view.container.querySelector('.spatial-canvas')).toHaveAttribute(
        'data-system-target-count',
        '4',
      );
      await waitFor(() =>
        expect(
          view.container.querySelector(
            '[data-map-label-key="system:9007199254740994"]',
          ),
        ).toHaveTextContent('Fixture Core'),
      );
    },
  );

  it('keeps the destination camera when a queued scene enters a system', async () => {
    feature.finder = true;
    vi.stubGlobal('matchMedia', () => ({ matches: false }));
    const scene = buildGalaxyReviewFixtureScene();
    const focusTarget = { kind: 'system' as const, systemId64: '42' };
    const view = render(SpatialCanvas, {
      props: { scene, focusTarget, focusRevision: 1 },
    });
    await waitFor(() =>
      expect(view.container.querySelector('.spatial-canvas')).toHaveAttribute(
        'data-camera-transition-active',
        'true',
      ),
    );
    const runtime = adapter.runtimes[0]!;
    runtime.dispatch.mockClear();
    const destination: SpatialSceneContract = {
      kind: 'system',
      revision: 2,
      systemId64: '42',
      fidelity: 'S1',
      camera: {
        systemId64: '42',
        focus: focusTarget,
        semanticDistance: 38,
        bearingRad: -0.85,
        pitchRad: 0.58,
        revision: 2,
      },
      bodies: [],
      infrastructure: [],
      contributions: [],
    };
    await view.rerender({ scene: destination });
    expect(runtime.dispatch).not.toHaveBeenCalled();
    runtime.emit({
      type: 'CAMERA_CHANGED',
      camera: { ...scene.camera, distanceLy: 60, revision: 3 },
    });
    runtime.emit({ type: 'TRANSITION_FINISHED', target: focusTarget });
    await waitFor(() =>
      expect(runtime.dispatch).toHaveBeenCalledWith({
        type: 'LOAD_SCENE',
        scene: destination,
      }),
    );
  });

  it('loads the unchanged queued camera from main when F4 is disabled', async () => {
    vi.stubGlobal('matchMedia', () => ({ matches: false }));
    const scene = buildGalaxyReviewFixtureScene();
    const focusTarget = { kind: 'system' as const, systemId64: '42' };
    const onTransitionChange = vi.fn();
    const view = render(SpatialCanvas, {
      props: { scene, focusTarget, focusRevision: 1, onTransitionChange },
    });
    await waitFor(() =>
      expect(view.container.querySelector('.spatial-canvas')).toHaveAttribute(
        'data-camera-transition-active',
        'true',
      ),
    );
    const runtime = adapter.runtimes[0]!;
    const refreshedScene = { ...scene, revision: scene.revision + 1 };
    await view.rerender({ scene: refreshedScene });
    const settledCamera: CameraState = {
      ...scene.camera,
      focusLy: { x: 12, y: -6, z: 70 },
      distanceLy: 60,
      revision: 21,
    };
    runtime.emit({ type: 'CAMERA_CHANGED', camera: settledCamera });
    runtime.emit({ type: 'TRANSITION_FINISHED', target: focusTarget });

    await waitFor(() =>
      expect(runtime.dispatch).toHaveBeenLastCalledWith({
        type: 'LOAD_SCENE',
        scene: refreshedScene,
      }),
    );
    expect(
      runtime.dispatch.mock.calls.filter(
        ([command]) => command.type === 'LOAD_SCENE',
      ),
    ).toHaveLength(2);
    expect(
      runtime.dispatch.mock.calls.filter(
        ([command]) => command.type === 'FLY_TO',
      ),
    ).toHaveLength(1);
    expect(onTransitionChange).toHaveBeenCalledTimes(2);
    expect(onTransitionChange).toHaveBeenLastCalledWith(false, settledCamera);
  });

  it('keeps density patched during a flight in the queued and recovered F4 scene', async () => {
    feature.finder = true;
    vi.stubGlobal('matchMedia', () => ({ matches: false }));
    const scene = buildGalaxyReviewFixtureScene();
    const focusTarget = { kind: 'system' as const, systemId64: '42' };
    const view = render(SpatialCanvas, {
      props: { scene, focusTarget, focusRevision: 1 },
    });
    await waitFor(() =>
      expect(view.container.querySelector('.spatial-canvas')).toHaveAttribute(
        'data-camera-transition-active',
        'true',
      ),
    );
    const runtime = adapter.runtimes[0]!;
    const contributionPatch = {
      ...scene.contributions[0]!,
      revision: scene.contributions[0]!.revision + 1,
    };
    // The parent snapshots its scene before the asynchronous density arrives.
    const queuedScene = { ...scene, revision: scene.revision + 1 };
    await view.rerender({ scene: queuedScene });
    await view.rerender({ contributionPatch, contributionPatchRevision: 1 });
    expect(
      runtime.dispatch.mock.calls.filter(
        ([command]) => command.type === 'LOAD_SCENE',
      ),
    ).toHaveLength(1);

    const settledCamera: CameraState = {
      ...scene.camera,
      distanceLy: 60,
      revision: 21,
    };
    runtime.emit({ type: 'CAMERA_CHANGED', camera: settledCamera });
    runtime.emit({ type: 'TRANSITION_FINISHED', target: focusTarget });

    const expectedContributions = [
      contributionPatch,
      ...queuedScene.contributions.slice(1),
    ];
    await waitFor(() =>
      expect(runtime.dispatch).toHaveBeenCalledWith({
        type: 'LOAD_SCENE',
        scene: {
          ...queuedScene,
          camera: settledCamera,
          contributions: expectedContributions,
        },
      }),
    );
    expect(
      runtime.dispatch.mock.calls.filter(
        ([command]) => command.type === 'PATCH_CONTRIBUTION',
      ),
    ).toHaveLength(1);

    runtime.emit({ type: 'RECOVERED', detail: 'Test context restored' });
    await waitFor(() =>
      expect(
        runtime.dispatch.mock.calls.filter(
          ([command]) => command.type === 'LOAD_SCENE',
        ),
      ).toHaveLength(3),
    );
    expect(runtime.dispatch).toHaveBeenLastCalledWith({
      type: 'LOAD_SCENE',
      scene: {
        ...queuedScene,
        camera: settledCamera,
        contributions: expectedContributions,
      },
    });
    expect(
      runtime.dispatch.mock.calls.filter(
        ([command]) => command.type === 'PATCH_CONTRIBUTION',
      ),
    ).toHaveLength(1);
  });
});
