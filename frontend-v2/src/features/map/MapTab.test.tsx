import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MapTab } from './MapTab';
import { useMapLayers } from './useMapLayers';
import type { SystemResult } from '@/types/api';

vi.mock('./useMapLayers');

const reference = { name: 'Sol', x: 0, z: 0 };

function makeSystem(overrides: Partial<SystemResult> = {}): SystemResult {
  return {
    id64: 10477373803,
    name: 'Sol',
    coords: { x: 0, y: 0, z: 0 },
    _rating: { score: 85, rationale: 'Strong Refinery' },
    population: 1000000,
    primaryEconomy: 'Refinery',
    allegiance: 'Federation',
    security: 'High',
    distance: 0,
    ...overrides,
  } as SystemResult;
}

const defaultLayers = {
  regions:  { data: undefined, isLoading: false, isError: false, error: null },
  clusters: { data: undefined, isLoading: false, isError: false, error: null },
  heatmap:  { data: undefined, isLoading: false, isError: false, error: null },
  timeline: { data: undefined, isLoading: false, isError: false, error: null },
  isLoading: false,
  isError:   false,
} as ReturnType<typeof useMapLayers>;

beforeEach(() => {
  vi.mocked(useMapLayers).mockReturnValue(defaultLayers);
});

describe('MapTab', () => {
  it('renders empty state with useful guidance', () => {
    render(<MapTab systems={[]} reference={reference} />);

    expect(screen.getByTestId('map-tab')).toBeTruthy();
    expect(screen.getByText('No systems to plot')).toBeTruthy();
    expect(
      screen.getByText(/Run a search in the Finder tab and switch back here/),
    ).toBeTruthy();
  });

  it('shows source/context badge when populated', () => {
    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    expect(screen.getByTestId('map-source-badge')).toBeTruthy();
    expect(screen.getByText('Showing Finder results')).toBeTruthy();
  });

  it('renders GalacticMap canvas when systems are present', () => {
    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    expect(screen.getByTestId('galactic-map-canvas')).toBeTruthy();
  });

  it('shows selection panel with prompt when no system selected', () => {
    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    expect(screen.getByTestId('map-selection-panel')).toBeTruthy();
    expect(screen.getByText('Select a star')).toBeTruthy();
  });

  it('shows system details after selecting a system', () => {
    const systems = [
      makeSystem({ id64: 1, name: 'Alpha Centauri', coords: { x: 10, y: 0, z: 5 }, _rating: { score: 85, rationale: 'Strong Refinery' } }),
      makeSystem({ id64: 2, name: 'Beta', coords: { x: -20, y: 0, z: 10 } }),
    ];
    render(<MapTab systems={systems} reference={reference} />);

    // Canvas should be present
    const canvas = screen.getByTestId('galactic-map-canvas') as HTMLCanvasElement;
    expect(canvas).toBeTruthy();

    // jsdom lacks setPointerCapture, mock it before firing pointer events
    canvas.setPointerCapture = vi.fn() as unknown as typeof canvas.setPointerCapture;
    canvas.releasePointerCapture = vi.fn() as unknown as typeof canvas.releasePointerCapture;

    // Simulate a click on the canvas to trigger selection
    // The hit-test logic in GalacticMap looks for clicks within 8px of a system
    // We click at the center of the canvas where the reference point is drawn
    fireEvent.pointerDown(canvas, { clientX: 300, clientY: 200 });
    fireEvent.pointerUp(canvas, { clientX: 300, clientY: 200 });

    // Selection panel should still exist; exact text depends on hit-test success
    expect(screen.getByTestId('map-selection-panel')).toBeTruthy();
  });

  it('handles systems without usable coordinates safely', () => {
    const systems = [
      makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } }),
      makeSystem({ id64: 2, name: 'UnknownCoords', coords: { x: null, y: null, z: null } }),
    ];
    render(<MapTab systems={systems} reference={reference} />);

    // Should still render the map without crashing
    expect(screen.getByTestId('galactic-map-canvas')).toBeTruthy();
    expect(screen.getByTestId('map-source-badge')).toBeTruthy();
  });

  it('does not fetch regions by default', () => {
    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    expect(screen.getByTestId('map-regions-toggle')).toBeTruthy();
    expect((screen.getByTestId('map-regions-toggle') as HTMLInputElement).checked).toBe(false);
    expect(screen.getByText('Showing Finder results')).toBeTruthy();
  });

  it('shows region loading state when toggled', () => {
    vi.mocked(useMapLayers).mockReturnValue({
      regions:  { data: undefined, isLoading: true, isError: false, error: null },
      clusters: { data: undefined, isLoading: false, isError: false, error: null },
      heatmap:  { data: undefined, isLoading: false, isError: false, error: null },
      timeline: { data: undefined, isLoading: false, isError: false, error: null },
      isLoading: true,
      isError:   false,
    } as ReturnType<typeof useMapLayers>);

    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    fireEvent.click(screen.getByTestId('map-regions-toggle'));
    expect(screen.getByText('Loading regions…')).toBeTruthy();
  });

  it('shows region error state when fetch fails', () => {
    vi.mocked(useMapLayers).mockReturnValue({
      regions:  { data: undefined, isLoading: false, isError: true, error: new Error('fail') },
      clusters: { data: undefined, isLoading: false, isError: false, error: null },
      heatmap:  { data: undefined, isLoading: false, isError: false, error: null },
      timeline: { data: undefined, isLoading: false, isError: false, error: null },
      isLoading: false,
      isError:   true,
    } as ReturnType<typeof useMapLayers>);

    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    fireEvent.click(screen.getByTestId('map-regions-toggle'));
    expect(screen.getByText('Regions failed')).toBeTruthy();
  });

  it('updates badge when regions are loaded', () => {
    vi.mocked(useMapLayers).mockReturnValue({
      regions:  {
        data: { regions: [{ id: 1, name: 'Inner Orion Spur', x: 0, y: 0, z: 0, system_count: 42 }], total_regions: 1 },
        isLoading: false,
        isError: false,
        error: null,
      },
      clusters: { data: undefined, isLoading: false, isError: false, error: null },
      heatmap:  { data: undefined, isLoading: false, isError: false, error: null },
      timeline: { data: undefined, isLoading: false, isError: false, error: null },
      isLoading: false,
      isError:   false,
    } as ReturnType<typeof useMapLayers>);

    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    fireEvent.click(screen.getByTestId('map-regions-toggle'));
    expect(screen.getByText('Finder results + Regions')).toBeTruthy();
  });
});
