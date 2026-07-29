import { fireEvent, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { MapSceneState } from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';
import { R3FMapFoundation } from './R3FMapFoundation';

vi.mock('@react-three/fiber', () => ({
  Canvas: () => <div data-testid="mock-three-canvas" />,
  useThree: vi.fn(),
}));

const scene: MapSceneState = {
  sceneRevision: 1,
  oneTimeFitIntent: null,
  cameraIntent: 'user',
  camera: {
    center: { x: 1_000, z: 2_000 },
    zoom: 20,
    pitchDeg: 42,
    bearingDeg: 0,
  },
  origin: { x: 0, z: 0 },
  systems: [],
  selectedSystemId64: null,
  selectedDetailOverride: null,
  highlights: [],
  clusters: [],
  routes: [],
  annotations: [],
  layers: [],
  returnWorkflow: null,
  keyboardCompanion: { phase: { type: 'idle' } },
  boundedResponse: { count: 0, truncated: false, continuationToken: null },
  guaranteedSystemIds: [],
};

function dispatchPointer(
  element: Element,
  type: 'pointerdown' | 'pointermove' | 'pointerup',
  init: MouseEventInit & { pointerId: number },
) {
  const event = new MouseEvent(type, { bubbles: true, cancelable: true, ...init });
  Object.defineProperty(event, 'pointerId', { value: init.pointerId });
  fireEvent(element, event);
}

describe('R3F map north lock', () => {
  it('keeps bearingDeg at zero through both pan-drag and shift-drag tilt', () => {
    const onInteraction = vi.fn();
    const { container } = render(
      <R3FMapFoundation
        scene={scene}
        regions={{ labels: [], boundaries: [] }}
        viewport={{ width: 1_280, height: 720 }}
        onInteraction={onInteraction}
      />,
    );
    const renderer = container.querySelector('.map-foundation-renderer');
    expect(renderer).not.toBeNull();
    Object.defineProperty(renderer, 'setPointerCapture', { value: vi.fn() });

    dispatchPointer(renderer!, 'pointerdown', {
      clientX: 100,
      clientY: 100,
      pointerId: 1,
      buttons: 1,
    });
    dispatchPointer(renderer!, 'pointermove', {
      clientX: 130,
      clientY: 115,
      pointerId: 1,
      buttons: 1,
    });

    expect(onInteraction).toHaveBeenLastCalledWith({
      type: 'cameraChanged',
      camera: {
        ...scene.camera,
        center: { x: 400, z: 2_300 },
        bearingDeg: 0,
      },
    });

    dispatchPointer(renderer!, 'pointerup', { pointerId: 1 });
    dispatchPointer(renderer!, 'pointerdown', {
      clientX: 100,
      clientY: 100,
      pointerId: 2,
      buttons: 1,
    });
    dispatchPointer(renderer!, 'pointermove', {
      clientX: 130,
      clientY: 120,
      pointerId: 2,
      buttons: 1,
      shiftKey: true,
    });

    expect(onInteraction).toHaveBeenLastCalledWith({
      type: 'cameraChanged',
      camera: {
        ...scene.camera,
        bearingDeg: 0,
        pitchDeg: 46,
      },
    });
    expect(
      onInteraction.mock.calls.map(([event]) => event.camera.bearingDeg),
    ).toEqual([0, 0]);
  });
});

describe('R3F focused keyboard controls', () => {
  let now = 0;
  let nextFrameId = 1;
  let frames = new Map<number, FrameRequestCallback>();

  beforeEach(() => {
    now = 0;
    nextFrameId = 1;
    frames = new Map();
    vi.spyOn(performance, 'now').mockImplementation(() => now);
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      const id = nextFrameId;
      nextFrameId += 1;
      frames.set(id, callback);
      return id;
    });
    vi.stubGlobal('cancelAnimationFrame', (id: number) => {
      frames.delete(id);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  function advanceFrame(milliseconds: number) {
    now += milliseconds;
    const pending = [...frames.values()];
    frames = new Map();
    pending.forEach((callback) => callback(now));
  }

  it('auto-focuses on mount so keyboard controls work without a prior click', () => {
    const onInteraction = vi.fn();
    const { container } = render(
      <R3FMapFoundation
        scene={{
          ...scene,
          camera: {
            ...scene.camera,
            center: { x: 5_000, z: 5_000 },
            zoom: 1,
          },
        }}
        regions={{ labels: [], boundaries: [] }}
        viewport={{ width: 1_000, height: 1_000 }}
        onInteraction={onInteraction}
      />,
    );
    const renderer = container.querySelector<HTMLElement>('.map-foundation-renderer')!;

    expect(document.activeElement).toBe(renderer);
    fireEvent.keyDown(renderer, { key: 'w' });
    fireEvent.keyUp(renderer, { key: 'w' });

    expect(onInteraction).toHaveBeenCalledWith({
      type: 'cameraChanged',
      camera: expect.objectContaining({
        center: { x: 5_000, z: 5_032 },
        bearingDeg: 0,
      }),
    });
  });

  it.each([
    ['w', { x: 5_000, z: 5_032 }],
    ['a', { x: 4_968, z: 5_000 }],
    ['s', { x: 5_000, z: 4_968 }],
    ['d', { x: 5_032, z: 5_000 }],
  ])('pans with %s in its screen-relative direction while focused', (key, center) => {
    const onInteraction = vi.fn();
    const { container } = render(
      <R3FMapFoundation
        scene={{
          ...scene,
          camera: {
            ...scene.camera,
            center: { x: 5_000, z: 5_000 },
            zoom: 1,
            bearingDeg: 0,
          },
        }}
        regions={{ labels: [], boundaries: [] }}
        viewport={{ width: 1_000, height: 1_000 }}
        onInteraction={onInteraction}
      />,
    );
    const renderer = container.querySelector<HTMLElement>('.map-foundation-renderer')!;
    renderer.focus();

    fireEvent.keyDown(renderer, { key });
    fireEvent.keyUp(renderer, { key });

    expect(onInteraction).toHaveBeenCalledWith({
      type: 'cameraChanged',
      camera: expect.objectContaining({ center, bearingDeg: 0 }),
    });
  });

  it('uses the drag-pan bounds for keyboard panning', () => {
    const onInteraction = vi.fn();
    const { container } = render(
      <R3FMapFoundation
        scene={{
          ...scene,
          camera: {
            ...scene.camera,
            center: { x: 10_490, z: 5_000 },
            zoom: 1,
            bearingDeg: 0,
          },
        }}
        regions={{ labels: [], boundaries: [] }}
        viewport={{ width: 1_000, height: 1_000 }}
        galaxyBounds={{ minX: 0, maxX: 10_000, minZ: 0, maxZ: 10_000 }}
        onInteraction={onInteraction}
      />,
    );
    const renderer = container.querySelector<HTMLElement>('.map-foundation-renderer')!;
    renderer.focus();

    fireEvent.keyDown(renderer, { key: 'd' });
    fireEvent.keyUp(renderer, { key: 'd' });

    expect(onInteraction).toHaveBeenCalledWith({
      type: 'cameraChanged',
      camera: expect.objectContaining({
        center: { x: 10_500, z: 5_000 },
        bearingDeg: 0,
      }),
    });
  });

  it('repeats Z-in and X-out zoom intents while keys are held', () => {
    const onZoomIntent = vi.fn();
    const { container } = render(
      <R3FMapFoundation
        scene={scene}
        regions={{ labels: [], boundaries: [] }}
        viewport={{ width: 1_280, height: 720 }}
        onInteraction={vi.fn()}
        onZoomIntent={onZoomIntent}
      />,
    );
    const renderer = container.querySelector<HTMLElement>('.map-foundation-renderer')!;
    renderer.focus();

    fireEvent.keyDown(renderer, { key: 'z' });
    expect(onZoomIntent).toHaveBeenLastCalledWith(-80);
    advanceFrame(50);
    advanceFrame(50);
    expect(onZoomIntent.mock.calls).toEqual([[-80], [-60], [-60]]);
    fireEvent.keyUp(renderer, { key: 'z' });
    expect(frames.size).toBe(0);

    fireEvent.keyDown(renderer, { key: 'x' });
    expect(onZoomIntent).toHaveBeenLastCalledWith(80);
    fireEvent.keyUp(renderer, { key: 'x' });
  });

  it('does not steal focus from an active form field and leaves its typing alone', () => {
    const onInteraction = vi.fn();
    const onZoomIntent = vi.fn();
    const view = render(<input aria-label="Unrelated finder field" />);
    const input = view.getByRole('textbox', { name: 'Unrelated finder field' });
    input.focus();
    view.rerender(
      <>
        <input aria-label="Unrelated finder field" />
        <R3FMapFoundation
          scene={scene}
          regions={{ labels: [], boundaries: [] }}
          viewport={{ width: 1_280, height: 720 }}
          onInteraction={onInteraction}
          onZoomIntent={onZoomIntent}
        />
      </>,
    );
    const renderer = view.container.querySelector<HTMLElement>('.map-foundation-renderer')!;
    const preservedInput = view.getByRole('textbox', { name: 'Unrelated finder field' });
    expect(renderer.getAttribute('aria-keyshortcuts')).toBe('W A S D Z X');
    expect(view.getByText(/Z in \/ X out/)).toBeTruthy();
    expect(document.activeElement).toBe(preservedInput);

    fireEvent.keyDown(renderer, { key: 'w' });
    fireEvent.keyDown(preservedInput, { key: 'w' });
    fireEvent.input(preservedInput, { target: { value: 'wasdzx' } });

    expect((preservedInput as HTMLInputElement).value).toBe('wasdzx');
    expect(onInteraction).not.toHaveBeenCalled();
    expect(onZoomIntent).not.toHaveBeenCalled();
  });

  it('restores map focus after a view preset control activates a new view', () => {
    const renderView = (viewPreset: 'results' | 'galaxy') => (
      <>
        <button type="button">Whole galaxy</button>
        <R3FMapFoundation
          scene={scene}
          regions={{ labels: [], boundaries: [] }}
          viewport={{ width: 1_280, height: 720 }}
          viewPreset={viewPreset}
          onInteraction={vi.fn()}
        />
      </>
    );
    const view = render(renderView('results'));
    const modeButton = view.getByRole('button', { name: 'Whole galaxy' });
    modeButton.focus();

    view.rerender(renderView('galaxy'));

    expect(document.activeElement).toBe(
      view.container.querySelector('.map-foundation-renderer'),
    );
  });
});

describe('R3F galactic core glow', () => {
  it('keeps one real-world core position while its projection follows pan, zoom, and tilt', () => {
    const coreScene: MapSceneState = {
      ...scene,
      camera: {
        center: { x: 25.2, z: 25_899.9 },
        zoom: 150,
        pitchDeg: 42,
        bearingDeg: 0,
      },
    };
    const view = render(
      <R3FMapFoundation
        scene={coreScene}
        regions={{ labels: [], boundaries: [] }}
        viewport={{ width: 1_280, height: 720 }}
        onInteraction={vi.fn()}
      />,
    );
    const renderer = () => view.container.querySelector('.map-foundation-renderer')!;
    const projection = () => ({
      worldX: Number(renderer().getAttribute('data-galactic-core-world-x')),
      worldZ: Number(renderer().getAttribute('data-galactic-core-world-z')),
      radiusLy: Number(renderer().getAttribute('data-galactic-core-radius-ly')),
      screenX: Number(renderer().getAttribute('data-galactic-core-screen-x')),
      screenY: Number(renderer().getAttribute('data-galactic-core-screen-y')),
      screenRadius: Number(renderer().getAttribute('data-galactic-core-screen-radius')),
      opacity: Number(renderer().getAttribute('data-galactic-core-opacity')),
    });
    const initial = projection();

    expect(initial.worldX).toBe(25.2);
    expect(initial.worldZ).toBe(25_899.9);
    expect(initial.radiusLy).toBe(10_000);
    expect(initial.opacity).toBe(0.38);
    expect(initial.screenX).toBeCloseTo(640);

    view.rerender(
      <R3FMapFoundation
        scene={{
          ...coreScene,
          camera: {
            ...coreScene.camera,
            center: { x: 12_025.2, z: 25_899.9 },
          },
        }}
        regions={{ labels: [], boundaries: [] }}
        viewport={{ width: 1_280, height: 720 }}
        onInteraction={vi.fn()}
      />,
    );
    const panned = projection();
    expect(panned.worldX).toBe(initial.worldX);
    expect(panned.worldZ).toBe(initial.worldZ);
    expect(panned.screenX).toBeLessThan(initial.screenX);

    view.rerender(
      <R3FMapFoundation
        scene={{
          ...coreScene,
          camera: { ...coreScene.camera, zoom: 75 },
        }}
        regions={{ labels: [], boundaries: [] }}
        viewport={{ width: 1_280, height: 720 }}
        onInteraction={vi.fn()}
      />,
    );
    const zoomed = projection();
    expect(zoomed.worldX).toBe(initial.worldX);
    expect(zoomed.worldZ).toBe(initial.worldZ);
    expect(zoomed.radiusLy).toBeGreaterThan(17_800);
    expect(zoomed.opacity).toBeGreaterThan(0.67);
    expect(zoomed.screenRadius).toBeGreaterThan(initial.screenRadius * 3.5);

    view.rerender(
      <R3FMapFoundation
        scene={{
          ...coreScene,
          camera: { ...coreScene.camera, pitchDeg: 60 },
        }}
        regions={{ labels: [], boundaries: [] }}
        viewport={{ width: 1_280, height: 720 }}
        onInteraction={vi.fn()}
      />,
    );
    const tilted = projection();
    expect(tilted.worldX).toBe(initial.worldX);
    expect(tilted.worldZ).toBe(initial.worldZ);
    expect(tilted.screenY).not.toBeCloseTo(initial.screenY);
  });
});

describe('R3F current-region indicator', () => {
  const regionNames = ['', 'Inner Orion Spur', 'Outer Scutum-Centaurus Arm'];
  const regions = {
    labels: [
      { id: 1, name: regionNames[1]!, position: [50, 50, 0] as [number, number, number] },
      { id: 2, name: regionNames[2]!, position: [150, 50, 0] as [number, number, number] },
    ],
    boundaries: [],
    lookup: {
      origin: { x: 0, z: 0 },
      pixel_scale: 100,
      regions: regionNames,
      regionmap: [[[1, 1], [1, 2]]] as Array<Array<[number, number]>>,
    },
  };

  it('bypasses normal decluttering and updates from the camera-centre grid cell', () => {
    const cameraAt = (x: number, zoom: number): MapSceneState => ({
      ...scene,
      camera: {
        ...scene.camera,
        center: { x, z: 50 },
        zoom,
      },
    });
    const view = render(
      <R3FMapFoundation
        scene={cameraAt(50, 150)}
        regions={regions}
        viewPreset="galaxy"
        viewport={{ width: 1_280, height: 720 }}
        onInteraction={vi.fn()}
      />,
    );
    const renderer = () => view.container.querySelector('.map-foundation-renderer')!;
    const indicator = () => view.container.querySelector('.map-foundation-current-region span')!;

    expect(renderer().getAttribute('data-current-region-name')).toBe('Inner Orion Spur');
    expect(indicator().textContent).toBe('Inner Orion Spur');

    view.rerender(
      <R3FMapFoundation
        scene={cameraAt(150, 20)}
        regions={regions}
        viewPreset="galaxy"
        viewport={{ width: 1_280, height: 720 }}
        onInteraction={vi.fn()}
      />,
    );

    expect(renderer().getAttribute('data-current-region-id')).toBe('2');
    expect(renderer().getAttribute('data-current-region-name')).toBe('Outer Scutum-Centaurus Arm');
    expect(indicator().textContent).toBe('Outer Scutum-Centaurus Arm');
    expect(indicator().getAttribute('style')).toContain('--region-label-scale');
  });
});
