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
  coords: { x: 0, y: 0, z: 0 },
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
});
