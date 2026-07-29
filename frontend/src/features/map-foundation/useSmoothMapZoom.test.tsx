import { act, fireEvent, render, renderHook, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useState } from 'react';
import type { CameraState } from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';
import { useSmoothMapZoom } from './useSmoothMapZoom';

const INITIAL_CAMERA: CameraState = {
  center: { x: 4_200, z: -1_700 },
  zoom: 100,
  pitchDeg: 42,
  bearingDeg: -12,
};

function ZoomHarness() {
  const [camera, setCamera] = useState(INITIAL_CAMERA);
  const zoom = useSmoothMapZoom({ camera, onCameraChange: setCamera });
  return (
    <div>
      <output data-testid="zoom">{camera.zoom}</output>
      <output data-testid="centre">{camera.center.x},{camera.center.z}</output>
      <button type="button" onClick={() => zoom.requestDelta(-220)}>Zoom in</button>
      <button type="button" onClick={() => zoom.requestDelta(220)}>Zoom out</button>
      <button type="button" onClick={zoom.cancel}>Cancel zoom</button>
    </div>
  );
}

describe('retargetable smooth map zoom', () => {
  let now = 0;
  let nextFrameId = 1;
  let frames = new Map<number, FrameRequestCallback>();

  function advanceFrame(milliseconds: number) {
    now += milliseconds;
    const pending = [...frames.values()];
    frames = new Map();
    pending.forEach((callback) => callback(now));
  }

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
    vi.stubGlobal('matchMedia', () => ({
      matches: false,
      media: '(prefers-reduced-motion: reduce)',
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('eases for 500ms in log space and preserves the camera focal point', () => {
    render(<ZoomHarness />);
    fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }));

    expect(Number(screen.getByTestId('zoom').textContent)).toBe(100);
    act(() => advanceFrame(250));
    const midpoint = Number(screen.getByTestId('zoom').textContent);
    const target = 100 * Math.exp(-0.22);
    expect(midpoint).toBeLessThan(100);
    expect(midpoint).toBeCloseTo(Math.sqrt(100 * target));
    expect(screen.getByTestId('centre').textContent).toBe('4200,-1700');

    act(() => advanceFrame(250));
    expect(Number(screen.getByTestId('zoom').textContent)).toBeCloseTo(target);
    expect(screen.getByTestId('centre').textContent).toBe('4200,-1700');
  });

  it('retargets the in-flight movement without snapping or queueing', () => {
    render(<ZoomHarness />);
    fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }));
    act(() => advanceFrame(200));
    const beforeRetarget = Number(screen.getByTestId('zoom').textContent);

    fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }));
    expect(Number(screen.getByTestId('zoom').textContent)).toBe(beforeRetarget);

    act(() => advanceFrame(250));
    const afterRetarget = Number(screen.getByTestId('zoom').textContent);
    expect(afterRetarget).toBeLessThan(beforeRetarget);

    act(() => advanceFrame(250));
    expect(Number(screen.getByTestId('zoom').textContent))
      .toBeCloseTo(100 * Math.exp(-0.44));
    expect(frames.size).toBe(0);
  });

  it('does not cancel when React commits one of its own earlier animation frames', () => {
    const emitted: CameraState[] = [];
    const onCameraChange = (camera: CameraState) => emitted.push(camera);
    const { result, rerender } = renderHook(
      ({ camera }) => useSmoothMapZoom({ camera, onCameraChange }),
      { initialProps: { camera: INITIAL_CAMERA } },
    );

    act(() => result.current.requestDelta(-220));
    act(() => advanceFrame(100));
    act(() => advanceFrame(100));
    expect(emitted).toHaveLength(2);

    rerender({ camera: emitted[0] });
    act(() => advanceFrame(100));

    expect(emitted).toHaveLength(3);
    expect(emitted[2].zoom).toBeLessThan(emitted[1].zoom);
  });

  it('stops at the current camera when a non-zoom action cancels the transition', () => {
    render(<ZoomHarness />);
    fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }));
    act(() => advanceFrame(200));
    const zoomAtCancel = Number(screen.getByTestId('zoom').textContent);

    fireEvent.click(screen.getByRole('button', { name: 'Cancel zoom' }));
    act(() => advanceFrame(500));

    expect(Number(screen.getByTestId('zoom').textContent)).toBe(zoomAtCancel);
    expect(frames.size).toBe(0);
  });

  it('settles immediately when reduced motion is requested', () => {
    vi.stubGlobal('matchMedia', () => ({
      matches: true,
      media: '(prefers-reduced-motion: reduce)',
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));

    render(<ZoomHarness />);
    fireEvent.click(screen.getByRole('button', { name: 'Zoom out' }));

    expect(Number(screen.getByTestId('zoom').textContent))
      .toBeCloseTo(100 * Math.exp(0.22));
    expect(frames.size).toBe(0);
  });
});
