import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AuthoritativeRegionMap } from './AuthoritativeRegionMap';

const camera = {
  center: { x: 0, z: 0 },
  zoom: 217.88,
  pitchDeg: 0,
  bearingDeg: 0,
};

const sol = {
  id64: 1,
  name: 'Sol',
  coords: { x: 0, z: 0 },
  developmentScore: null,
  primaryEconomy: null,
  population: null,
};

describe('AuthoritativeRegionMap', () => {
  it('projects Sol into the lower half of the source SVG coordinate system', () => {
    render(
      <AuthoritativeRegionMap
        camera={camera}
        systems={[sol]}
        selectedSystemId64={null}
        viewport={{ width: 1058, height: 519 }}
        viewPreset="galaxy"
        showRegions
        onInteraction={vi.fn()}
      />,
    );

    const marker = screen.getByRole('button', { name: 'Select Sol' });
    expect(Number.parseFloat(marker.style.left)).toBeCloseTo(49.46, 1);
    expect(Number.parseFloat(marker.style.top)).toBeCloseTo(76.15, 1);
  });

  it('emits a zoom-only camera change from the locked whole-galaxy surface', () => {
    const onInteraction = vi.fn();
    render(
      <AuthoritativeRegionMap
        camera={camera}
        systems={[]}
        selectedSystemId64={null}
        viewport={{ width: 1058, height: 519 }}
        viewPreset="galaxy"
        showRegions
        onInteraction={onInteraction}
      />,
    );

    fireEvent.wheel(
      screen.getByLabelText('Authoritative Elite Dangerous region map'),
      { deltaY: -200 },
    );

    expect(onInteraction).toHaveBeenCalledWith({
      type: 'cameraChanged',
      camera: {
        ...camera,
        zoom: expect.any(Number),
      },
    });
    expect(onInteraction.mock.calls[0][0].camera.center).toEqual(camera.center);
  });

  it('draws enabled heatmap and cluster geometry over the authoritative SVG', () => {
    const gradient = { addColorStop: vi.fn() };
    const context = {
      setTransform: vi.fn(),
      clearRect: vi.fn(),
      createRadialGradient: vi.fn(() => gradient),
      beginPath: vi.fn(),
      arc: vi.fn(),
      fill: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      stroke: vi.fn(),
      globalCompositeOperation: 'source-over',
      fillStyle: '',
      strokeStyle: '',
      lineWidth: 1,
      shadowColor: '',
      shadowBlur: 0,
    } as unknown as CanvasRenderingContext2D;
    const originalGetContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = vi.fn(() => context) as unknown as typeof originalGetContext;

    render(
      <AuthoritativeRegionMap
        camera={camera}
        systems={[sol]}
        selectedSystemId64={null}
        viewport={{ width: 1058, height: 519 }}
        viewPreset="galaxy"
        showRegions
        productionOverlays={{
          heatmap: {
            positions: new Float32Array([0, 0, -2]),
            colors: new Float32Array([1, 0.5, 0.2]),
            voxelSize: 200,
            cellCount: 1,
            omittedCellCount: 0,
            sourceTruncated: false,
          },
          aggregateHulls: {
            linePositions: new Float32Array([0, 0, -1, 500, 0, -1]),
            lineColors: new Float32Array([1, 0.5, 0.2, 1, 0.5, 0.2]),
            hullCount: 1,
            omittedHullCount: 0,
          },
        }}
        onInteraction={vi.fn()}
      />,
    );

    expect(screen.getByTestId('authoritative-map-heatmap').getAttribute('data-cell-count')).toBe('1');
    expect(screen.getByTestId('authoritative-map-clusters').getAttribute('data-hull-count')).toBe('1');
    expect(context.arc).toHaveBeenCalled();
    expect(context.stroke).toHaveBeenCalled();
    HTMLCanvasElement.prototype.getContext = originalGetContext;
  });
});
