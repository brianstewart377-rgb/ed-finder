import { fireEvent, render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
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
    });
    const initial = projection();

    expect(initial.worldX).toBe(25.2);
    expect(initial.worldZ).toBe(25_899.9);
    expect(initial.radiusLy).toBe(18_000);
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
    expect(zoomed.screenRadius).toBeGreaterThan(initial.screenRadius * 1.9);

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
