import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/svelte';
import axe from 'axe-core';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { registerPopout, isTopmostPopout } from '$lib/components/popout-stack';
import type {
  CameraState,
  RuntimeCommand,
  RuntimeEventListener,
  SpatialRuntimeStatusListener,
} from '$lib/spatial/contracts';
import { buildGalaxyReviewFixtureScene } from '$lib/spatial/galaxy-review-fixture';
import {
  createManagedSpatialRuntime,
  type SpatialBackendResourceListener,
  type SpatialBackendSession,
} from '$lib/spatial/lifecycle';
import ExploreMapWindow from './ExploreMapWindow.svelte';
import BodyFilters from './BodyFilters.svelte';

const adapter = vi.hoisted(() => ({ create: vi.fn() }));
vi.mock('$lib/spatial/babylon/adapter', () => ({
  createBabylonSpatialRuntime: adapter.create,
}));

function managedSession(onStatus: SpatialRuntimeStatusListener) {
  const frames = new Map<number, () => void>();
  let nextFrame = 0;
  let emit: RuntimeEventListener = () => undefined;
  let resources: SpatialBackendResourceListener = () => undefined;
  const unsubscribeResources = vi.fn();
  const session = {
    backend: 'WEBGL2' as const,
    subscribeResourceEvents: vi.fn(
      (listener: SpatialBackendResourceListener) => {
        resources = listener;
        return unsubscribeResources;
      },
    ),
    execute: vi.fn(
      (
        command: Exclude<RuntimeCommand, { type: 'RESIZE' }>,
        listener: RuntimeEventListener,
      ) => {
        emit = listener;
        if (command.type === 'LOAD_SCENE' || command.type === 'SET_CAMERA') {
          listener({
            type: 'CAMERA_CHANGED',
            camera:
              command.type === 'LOAD_SCENE'
                ? command.scene.camera
                : command.camera,
          });
        }
        return { status: 'executed' as const };
      },
    ),
    render: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
  } satisfies SpatialBackendSession;
  const scheduler = {
    request: vi.fn((callback: () => void) => {
      frames.set(++nextFrame, callback);
      return nextFrame;
    }),
    cancel: vi.fn((handle: number) => frames.delete(handle)),
  };
  const runtime = createManagedSpatialRuntime(
    { createWebGpu: async () => null, createWebGl2: () => session },
    onStatus,
    scheduler,
  );
  const subscribe = runtime.subscribe.bind(runtime);
  const unsubscribed = vi.fn();
  runtime.subscribe = vi.fn((listener) => {
    const unsubscribe = subscribe(listener);
    return () => {
      unsubscribed();
      unsubscribe();
    };
  });
  return {
    runtime,
    session,
    frames,
    scheduler,
    unsubscribed,
    unsubscribeResources,
    emit: (event: Parameters<RuntimeEventListener>[0]) => emit(event),
    resource: (state: 'lost' | 'recovered') =>
      resources({ state, detail: 'window-lifecycle-test' }),
  };
}

describe('Explore map window', () => {
  let sessions: ReturnType<typeof managedSession>[];
  let disconnect: ReturnType<typeof vi.fn>;
  let opener: HTMLButtonElement;

  beforeEach(() => {
    sessions = [];
    disconnect = vi.fn();
    opener = document.createElement('button');
    opener.textContent = 'Show on map';
    document.body.append(opener);
    opener.focus();
    vi.stubGlobal('matchMedia', () => ({ matches: true }));
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe = vi.fn();
        disconnect = disconnect;
      },
    );
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(640);
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(360);
    adapter.create.mockReset().mockImplementation((_canvas, onStatus) => {
      const record = managedSession(onStatus);
      sessions.push(record);
      return record.runtime;
    });
  });

  afterEach(() => {
    cleanup();
    opener.remove();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  async function ready() {
    await waitFor(() =>
      expect(document.querySelector('[data-renderer-state]')).toHaveAttribute(
        'data-renderer-state',
        'ready',
      ),
    );
    expect(document.querySelectorAll('[data-spatial-canvas]')).toHaveLength(1);
  }

  it('keeps one non-modal canvas through Expand and restores focus after Close', async () => {
    const onClose = vi.fn(() => view.unmount());
    const onExpand = vi.fn(() => view.rerender({ expanded: true }));
    const view = render(ExploreMapWindow, {
      canvasProps: { scene: buildGalaxyReviewFixtureScene() },
      expanded: false,
      opener,
      onClose,
      onExpand,
    });
    await ready();
    const dialog = screen.getByRole('dialog', { name: 'Map window' });
    expect(dialog).toHaveAttribute('aria-modal', 'false');
    expect(dialog).toHaveAttribute('data-expanded', 'false');
    expect(screen.getByRole('button', { name: 'Close map' })).toHaveFocus();
    expect(document.querySelector('[inert]')).toBeNull();
    const canvas = dialog.querySelector('canvas');
    await fireEvent.click(
      within(dialog).getByRole('button', { name: 'Expand' }),
    );
    expect(dialog).toHaveAttribute('data-expanded', 'true');
    expect(dialog.querySelector('canvas')).toBe(canvas);
    expect(adapter.create).toHaveBeenCalledOnce();
    expect(sessions[0]!.runtime.subscribe).toHaveBeenCalledOnce();
    expect(sessions[0]!.session.dispose).not.toHaveBeenCalled();
    opener.focus();
    await fireEvent.keyDown(opener, { key: 'Tab' });
    expect(opener).toHaveFocus();
    await fireEvent.click(
      within(dialog).getByRole('button', { name: 'Close map' }),
    );
    expect(onClose).toHaveBeenCalledOnce();
    await waitFor(() => expect(opener).toHaveFocus());
    expect(document.querySelector('[data-spatial-canvas]')).toBeNull();
    expect(sessions[0]!.session.dispose).toHaveBeenCalledOnce();
    expect(sessions[0]!.unsubscribeResources).toHaveBeenCalledOnce();
    expect(sessions[0]!.unsubscribed).toHaveBeenCalledOnce();
    expect(disconnect).toHaveBeenCalledOnce();
  });

  it('handles Escape only at the top of the shared tool stack and unregisters on close', async () => {
    const onClose = vi.fn(() => view.unmount());
    const view = render(ExploreMapWindow, {
      canvasProps: {},
      expanded: false,
      opener,
      onClose,
      onExpand: vi.fn(),
    });
    await ready();
    const dialog = screen.getByRole('dialog', { name: 'Map window' });
    expect(isTopmostPopout(dialog)).toBe(true);
    const tool = document.createElement('div');
    document.body.append(tool);
    const unregister = registerPopout(tool);
    await fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
    unregister();
    tool.remove();
    await fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledOnce();
    await waitFor(() => expect(opener).toHaveFocus());
    expect(isTopmostPopout(dialog)).toBe(false);
  });

  it('allows the background Body filters tool to own Escape without closing the map', async () => {
    const onClose = vi.fn();
    render(ExploreMapWindow, {
      canvasProps: {},
      expanded: false,
      opener,
      onClose,
      onExpand: vi.fn(),
    });
    await ready();
    render(BodyFilters, {
      value: {},
      onapply: vi.fn(),
      onremove: vi.fn(),
      onclear: vi.fn(),
    });
    const trigger = screen.getByRole('button', { name: 'Body filters' });
    await fireEvent.click(trigger);
    const filters = screen.getByRole('dialog', { name: 'Body filters' });
    expect(isTopmostPopout(filters)).toBe(true);
    await fireEvent.keyDown(window, { key: 'Escape' });
    expect(filters).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(onClose).not.toHaveBeenCalled();
    expect(
      screen.getByRole('dialog', { name: 'Map window' }),
    ).toBeInTheDocument();
  });

  it('lets expanded background autocomplete consume Escape before closing the map', async () => {
    const input = document.createElement('input');
    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-expanded', 'true');
    const dismissSuggestions = vi.fn((event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      input.setAttribute('aria-expanded', 'false');
      event.preventDefault();
    });
    input.addEventListener('keydown', dismissSuggestions);
    document.body.append(input);
    const onClose = vi.fn(() => view.unmount());
    const view = render(ExploreMapWindow, {
      canvasProps: {},
      expanded: false,
      opener,
      onClose,
      onExpand: vi.fn(),
    });
    await ready();
    input.focus();
    await fireEvent.keyDown(input, { key: 'Escape' });
    expect(dismissSuggestions).toHaveBeenCalledOnce();
    expect(input).toHaveAttribute('aria-expanded', 'false');
    expect(input).toHaveFocus();
    expect(onClose).not.toHaveBeenCalled();
    expect(
      screen.getByRole('dialog', { name: 'Map window' }),
    ).toBeInTheDocument();
    await fireEvent.keyDown(input, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledOnce();
    await waitFor(() => expect(opener).toHaveFocus());
    input.remove();
  });

  it('keeps the existing hover card Escape before closing its enclosing map', async () => {
    const scene = buildGalaxyReviewFixtureScene();
    const onClose = vi.fn(() => view.unmount());
    const view = render(ExploreMapWindow, {
      canvasProps: { scene },
      expanded: false,
      opener,
      onClose,
      onExpand: vi.fn(),
    });
    await ready();
    sessions[0]!.emit({ type: 'TARGET_HOVERED', target: scene.selection[0] });
    const tooltip = await screen.findByRole('tooltip');
    within(tooltip).getByRole('button', { name: 'Select' }).focus();
    await fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole('application')).toHaveFocus();
    await fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('returns focus to the stable fallback if the opening result has been replaced', async () => {
    const fallback = document.createElement('input');
    document.body.append(fallback);
    const view = render(ExploreMapWindow, {
      canvasProps: {},
      expanded: false,
      opener,
      fallbackFocus: fallback,
      onClose: () => view.unmount(),
      onExpand: vi.fn(),
    });
    await ready();
    opener.remove();
    await fireEvent.click(screen.getByRole('button', { name: 'Close map' }));
    await waitFor(() => expect(fallback).toHaveFocus());
    fallback.remove();
  });

  it('disposes managed GPU sessions, observers and queued frames before rebuilding retained CPU context', async () => {
    const original = buildGalaxyReviewFixtureScene();
    let retainedCamera = original.camera;
    const events = vi.fn((event: Parameters<RuntimeEventListener>[0]) => {
      if (event.type === 'CAMERA_CHANGED' && 'focusLy' in event.camera)
        retainedCamera = event.camera;
    });
    let scene = original;
    for (let cycle = 0; cycle < 3; cycle += 1) {
      const view = render(ExploreMapWindow, {
        canvasProps: { scene, onRuntimeEvent: events },
        expanded: cycle === 1,
        opener,
        onClose: () => view.unmount(),
        onExpand: vi.fn(),
      });
      await ready();
      const record = sessions[cycle]!;
      expect(
        sessions.filter(
          ({ session }) => session.dispose.mock.calls.length === 0,
        ),
      ).toHaveLength(1);
      expect(record.session.execute).toHaveBeenCalledWith(
        { type: 'LOAD_SCENE', scene },
        expect.any(Function),
      );
      expect(record.runtime.subscribe).toHaveBeenCalledOnce();
      const moved: CameraState = {
        ...retainedCamera,
        focusLy: { x: 120 + cycle, y: 48, z: -90 },
        bearingRad: 0.8,
        distanceLy: 640,
        revision: 9 + cycle,
      };
      record.emit({ type: 'CAMERA_CHANGED', camera: moved });
      await fireEvent.click(screen.getByRole('button', { name: 'Close map' }));
      expect(retainedCamera).toEqual(moved);
      expect(record.session.dispose).toHaveBeenCalledOnce();
      expect(record.unsubscribeResources).toHaveBeenCalledOnce();
      expect(record.unsubscribed).toHaveBeenCalledOnce();
      expect(record.frames.size).toBe(0);
      const previousCount = events.mock.calls.length;
      record.emit({ type: 'CAMERA_CHANGED', camera: original.camera });
      record.resource('recovered');
      expect(events).toHaveBeenCalledTimes(previousCount);
      scene = { ...original, camera: retainedCamera };
    }
    expect(adapter.create).toHaveBeenCalledTimes(3);
    expect(disconnect).toHaveBeenCalledTimes(3);
  });

  it('forwards reduced-motion camera requests without starting a flight', async () => {
    const scene = buildGalaxyReviewFixtureScene();
    const cameraRequest = { ...scene.camera, distanceLy: 600, revision: 2 };
    render(ExploreMapWindow, {
      canvasProps: {
        scene,
        cameraRequest,
        cameraRequestRevision: 1,
        focusTarget: scene.selection[0],
        focusRevision: 1,
      },
      expanded: false,
      onClose: vi.fn(),
      onExpand: vi.fn(),
    });
    await ready();
    await waitFor(() =>
      expect(sessions[0]!.session.execute).toHaveBeenCalledWith(
        {
          type: 'SET_CAMERA',
          camera: cameraRequest,
          transition: { durationMs: 650, reducedMotion: true },
        },
        expect.any(Function),
      ),
    );
    expect(sessions[0]!.session.execute).toHaveBeenCalledWith(
      { type: 'FLY_TO', target: scene.selection[0], reducedMotion: true },
      expect.any(Function),
    );
    expect(
      document.querySelector('[data-camera-transition-active]'),
    ).toHaveAttribute('data-camera-transition-active', 'false');
  });

  it('keeps the original Reset view camera through a suspended canvas rebuild', async () => {
    const original = buildGalaxyReviewFixtureScene();
    const resetCamera = original.camera;
    const first = render(ExploreMapWindow, {
      canvasProps: { scene: original, resetCamera },
      expanded: false,
      onClose: () => first.unmount(),
      onExpand: vi.fn(),
    });
    await ready();
    await fireEvent.click(screen.getByRole('button', { name: 'Close map' }));
    const currentCamera = {
      ...resetCamera,
      focusLy: { x: 600, y: 50, z: 80 },
      distanceLy: 400,
      revision: 8,
    };
    render(ExploreMapWindow, {
      canvasProps: {
        scene: { ...original, camera: currentCamera },
        resetCamera,
      },
      expanded: false,
      onClose: vi.fn(),
      onExpand: vi.fn(),
    });
    await ready();
    await fireEvent.click(screen.getByRole('button', { name: 'Reset view' }));
    expect(sessions[1]!.session.execute).toHaveBeenCalledWith(
      {
        type: 'SET_CAMERA',
        camera: { ...resetCamera, revision: currentCamera.revision + 1 },
        transition: { durationMs: 650, reducedMotion: true },
      },
      expect.any(Function),
    );
    expect(sessions[0]!.session.dispose).toHaveBeenCalledOnce();
  });

  it('has no axe violations with the real canvas controls in the non-modal window', async () => {
    const { container } = render(ExploreMapWindow, {
      canvasProps: { scene: buildGalaxyReviewFixtureScene() },
      expanded: false,
      onClose: vi.fn(),
      onExpand: vi.fn(),
    });
    await ready();
    const result = await axe.run(container, {
      rules: { 'color-contrast': { enabled: false } },
    });
    expect(result.violations).toEqual([]);
  });
});
