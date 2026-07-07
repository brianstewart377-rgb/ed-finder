import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MapErrorBoundary } from './MapErrorBoundary';

let shouldThrow = true;

function FlakyMap() {
  if (shouldThrow) {
    throw new Error('map render failed');
  }
  return <div data-testid="map-ready">Map ready</div>;
}

describe('MapErrorBoundary', () => {
  it('contains map failures and retries without replacing surrounding UI', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    shouldThrow = true;

    render(
      <section>
        <h2>Map shell</h2>
        <MapErrorBoundary>
          <FlakyMap />
        </MapErrorBoundary>
      </section>,
    );

    expect(screen.getByText('Map shell')).toBeTruthy();
    expect(screen.getByTestId('map-error-boundary')).toBeTruthy();
    expect(screen.getByText('Map temporarily unavailable')).toBeTruthy();

    shouldThrow = false;
    fireEvent.click(screen.getByRole('button', { name: /Retry map/i }));

    expect(screen.getByTestId('map-ready')).toBeTruthy();
    expect(screen.queryByTestId('map-error-boundary')).toBeNull();
    expect(consoleError).toHaveBeenCalled();
    consoleError.mockRestore();
  });
});
