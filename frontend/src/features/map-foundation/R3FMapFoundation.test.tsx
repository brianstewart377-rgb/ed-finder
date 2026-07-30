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

describe('R3F document-scoped keyboard controls', () => {
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

  it('works from the document on mount without focus or a prior click', () => {
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

    expect(document.activeElement).not.toBe(renderer);
    fireEvent.keyDown(document, { key: 'w' });
    advanceFrame(50);
    fireEvent.keyUp(document, { key: 'w' });

    const cameraEvent = onInteraction.mock.calls.at(-1)?.[0];
    expect(cameraEvent).toEqual({
      type: 'cameraChanged',
      camera: expect.objectContaining({ bearingDeg: 0 }),
    });
    expect(cameraEvent.camera.center.x).toBe(5_000);
    expect(cameraEvent.camera.center.z).toBeGreaterThan(5_000);
  });

  it.each([
    ['w', 'z', 1],
    ['a', 'x', -1],
    ['s', 'z', -1],
    ['d', 'x', 1],
  ] as const)('pans with %s in its screen-relative direction without map focus', (key, axis, direction) => {
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
    expect(container.querySelector('.map-foundation-renderer')).not.toBe(document.activeElement);
    fireEvent.keyDown(document, { key });
    advanceFrame(50);
    fireEvent.keyUp(document, { key });

    const cameraEvent = onInteraction.mock.calls.at(-1)?.[0];
    expect(cameraEvent.camera.bearingDeg).toBe(0);
    expect(Math.sign(cameraEvent.camera.center[axis] - 5_000)).toBe(direction);
    expect(cameraEvent.camera.center[axis === 'x' ? 'z' : 'x']).toBe(5_000);
  });

  it('uses the drag-pan bounds for keyboard panning', () => {
    const onInteraction = vi.fn();
    render(
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
    fireEvent.keyDown(document, { key: 'd' });
    for (let frame = 0; frame < 12; frame += 1) advanceFrame(50);
    fireEvent.keyUp(document, { key: 'd' });

    expect(onInteraction).toHaveBeenCalledWith({
      type: 'cameraChanged',
      camera: expect.objectContaining({
        center: { x: 10_610, z: 5_000 },
        bearingDeg: 0,
      }),
    });
  });

  it('ramps pan velocity, coasts on release, and blends a direction reversal', () => {
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
    const velocity = () => Number(renderer.dataset.keyboardPanVelocityZ);
    fireEvent.keyDown(document, { key: 'w' });
    const accelerating = Array.from({ length: 6 }, () => {
      advanceFrame(50);
      return velocity();
    });
    expect(accelerating[0]).toBeGreaterThan(0);
    expect(accelerating[0]).toBeLessThan(accelerating[3]!);
    expect(accelerating[3]).toBeLessThanOrEqual(480);
    expect(accelerating.at(-1)).toBe(480);

    fireEvent.keyUp(document, { key: 'w' });
    const coasting = Array.from({ length: 7 }, () => {
      advanceFrame(50);
      return velocity();
    });
    expect(coasting[0]).toBeLessThan(480);
    expect(coasting[0]).toBeGreaterThan(coasting[4]!);
    expect(coasting.at(-1)).toBe(0);
    expect(renderer.dataset.keyboardPanPhase).toBe('idle');
    const completedTrace = JSON.parse(renderer.dataset.keyboardPanLastTrace ?? '[]') as Array<{
      centerZ: number;
      velocityZ: number;
      phase: string;
    }>;
    expect(completedTrace.some((sample) => sample.phase === 'accelerating')).toBe(true);
    expect(completedTrace.some((sample) => sample.phase === 'decelerating')).toBe(true);
    expect(completedTrace.at(-1)?.velocityZ).toBe(0);
    expect(completedTrace.at(-1)?.centerZ).toBeGreaterThan(completedTrace[0]!.centerZ);

    fireEvent.keyDown(document, { key: 'w' });
    for (let frame = 0; frame < 6; frame += 1) advanceFrame(50);
    fireEvent.keyUp(document, { key: 'w' });
    fireEvent.keyDown(document, { key: 's' });
    const reversing = Array.from({ length: 5 }, () => {
      advanceFrame(50);
      return velocity();
    });
    expect(reversing[0]).toBeGreaterThan(0);
    expect(reversing.at(-1)).toBeLessThan(0);
    expect(reversing.every((value, index) => (
      index === 0 || Math.abs(value - reversing[index - 1]!) < 480
    ))).toBe(true);
  });

  it('skips keyboard-pan easing when reduced motion is requested', () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: true,
      media: '(prefers-reduced-motion: reduce)',
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
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

    fireEvent.keyDown(document, { key: 'w' });
    expect(renderer.dataset.keyboardPanVelocityZ).toBe('480.000');
    advanceFrame(50);
    expect(onInteraction.mock.calls.at(-1)?.[0].camera.center.z).toBe(5_024);

    fireEvent.keyUp(document, { key: 'w' });
    expect(renderer.dataset.keyboardPanVelocityZ).toBe('0.000');
    expect(renderer.dataset.keyboardPanPhase).toBe('idle');
    expect(frames.size).toBe(0);
  });

  it('repeats Z-in and X-out zoom intents while keys are held', () => {
    const onZoomIntent = vi.fn();
    render(
      <R3FMapFoundation
        scene={scene}
        regions={{ labels: [], boundaries: [] }}
        viewport={{ width: 1_280, height: 720 }}
        onInteraction={vi.fn()}
        onZoomIntent={onZoomIntent}
      />,
    );
    fireEvent.keyDown(document, { key: 'z' });
    expect(onZoomIntent).toHaveBeenLastCalledWith(-80);
    advanceFrame(50);
    advanceFrame(50);
    expect(onZoomIntent.mock.calls).toEqual([[-80], [-60], [-60]]);
    fireEvent.keyUp(document, { key: 'z' });
    expect(frames.size).toBe(0);

    fireEvent.keyDown(document, { key: 'x' });
    expect(onZoomIntent).toHaveBeenLastCalledWith(80);
    fireEvent.keyUp(document, { key: 'x' });
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
    expect(view.container.querySelector('.map-foundation-control-hint')?.textContent)
      .toMatch(/Z in \/ X out/);
    expect(document.activeElement).toBe(preservedInput);

    fireEvent.keyDown(document, { key: 'w' });
    fireEvent.keyDown(preservedInput, { key: 'w' });
    fireEvent.input(preservedInput, { target: { value: 'wasdzx' } });

    expect((preservedInput as HTMLInputElement).value).toBe('wasdzx');
    expect(onInteraction).not.toHaveBeenCalled();
    expect(onZoomIntent).not.toHaveBeenCalled();
  });

  it('does not steal focus when a view preset changes', () => {
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

    expect(document.activeElement).toBe(modeButton);
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
    const indicator = () => view.container.querySelector(
      '.map-foundation-labels span.is-current-region',
    )!;

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
    expect(view.container.querySelector('.map-foundation-current-region')).toBeNull();
  });
});
