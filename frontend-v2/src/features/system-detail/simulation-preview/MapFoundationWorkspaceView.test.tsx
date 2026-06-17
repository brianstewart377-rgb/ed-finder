import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MapFoundationWorkspaceView } from './MapFoundationWorkspaceView';


vi.mock('@/features/map/MapTab', () => ({
  MapTab: vi.fn(({ systems, reference }) => (
    <div data-testid="map-tab-mock">
      <span>{systems[0]?.name}</span>
      <span>{reference.name}</span>
    </div>
  )),
}));


describe('MapFoundationWorkspaceView', () => {
  it('renders read-only map guidance and passes the current system into MapTab', () => {
    render(
      <MapFoundationWorkspaceView
        system={{
          id64: 12866676218109,
          name: 'Shinrarta Dezhra',
          coords: { x: 12, y: 0, z: 42 },
          _rating: { score: 88, rationale: 'Strong refinery' },
          population: 1000000,
          primaryEconomy: 'Refinery',
          allegiance: 'Pilots Federation',
          security: 'High',
        } as never}
      />,
    );

    expect(screen.getByTestId('map-foundation-workspace-view')).toBeTruthy();
    expect(screen.getByText(/Stage 20C establishes the planner map foundation as a read-only spatial context surface/)).toBeTruthy();
    expect(screen.getByTestId('map-tab-mock')).toBeTruthy();
    expect(screen.getAllByText('Shinrarta Dezhra').length).toBeGreaterThan(0);
  });
});
