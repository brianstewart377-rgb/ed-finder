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
