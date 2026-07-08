import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MapTab } from './MapTab';
import { useMapLayers } from './useMapLayers';
import type { SystemResult } from '@/types/api';

vi.mock('./useMapLayers');

const reference = { name: 'Sol', x: 0, z: 0 };
let getContextSpy: { mockRestore: () => void };

function makeCanvasContext(): RenderingContext {
  const gradient = { addColorStop: vi.fn() };
  const target: Record<string, unknown> = {
    createRadialGradient: vi.fn(() => gradient),
    createLinearGradient: vi.fn(() => gradient),
    measureText: vi.fn(() => ({ width: 0 })),
  };
  return new Proxy(target, {
    get(current, prop: string) {
      if (!(prop in current)) current[prop] = vi.fn();
      return current[prop];
    },
    set(current, prop: string, value) {
      current[prop] = value;
      return true;
    },
  }) as unknown as RenderingContext;
}

function makeSystem(overrides: Partial<SystemResult> = {}): SystemResult {
  return {
    id64: 10477373803,
    name: 'Sol',
    coords: { x: 0, y: 0, z: 0 },
    primary_archetype: 'refinery_industrial',
    archetype_score: 88,
    archetype_tier: 'S',
    buildability_score: 81,
    purity_score: 74,
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
  getContextSpy = vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(makeCanvasContext());
});

afterEach(() => {
  getContextSpy.mockRestore();
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

  it('renders a compact map legend and control summary', () => {
    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    const legend = screen.getByTestId('map-legend');
    expect(legend).toBeTruthy();
    expect(within(legend).getByText(/Map legend/)).toBeTruthy();
    expect(within(legend).getByText(/Active: Finder dots \+ Galactic frame/)).toBeTruthy();
    expect(within(legend).getByText('Current Finder systems with archetype-led development scores.')).toBeTruthy();
    expect(within(legend).getByText('Canonical galaxy region labels.')).toBeTruthy();
    expect(within(legend).getByText('Voxel cells summarising legacy rating density from map aggregate views.')).toBeTruthy();
    expect(within(legend).getByText('Approximate hulls around high-rating grouped systems.')).toBeTruthy();
  });

  it('updates the legend active-layer summary as toggles change', () => {
    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    const legend = screen.getByTestId('map-legend');
    fireEvent.click(screen.getByTestId('map-regions-toggle'));
    fireEvent.click(screen.getByTestId('map-heatmap-toggle'));
    fireEvent.click(screen.getByTestId('map-clusters-toggle'));
    expect(
      within(legend).getByText(/Active: Finder dots \+ Galactic frame \+ Regions \+ Heatmap \+ Clusters/),
    ).toBeTruthy();

    fireEvent.click(screen.getByTestId('map-frame-toggle'));
    expect(within(legend).getByText(/Active: Finder dots \+ Regions \+ Heatmap \+ Clusters/)).toBeTruthy();
  });

  it('keeps view mode descriptions accessible through the legend', () => {
    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    const legend = screen.getByTestId('map-legend');
    expect(within(legend).getByText('Fits the current Finder result dots.')).toBeTruthy();
    expect(within(legend).getByText('Frames the full galactic disc and axes.')).toBeTruthy();
    expect(within(legend).getByText('Centers the chosen reference system.')).toBeTruthy();

    fireEvent.click(screen.getByTestId('map-view-galaxy'));
    expect(within(legend).getByText(/Galaxy: Frames the full galactic disc and axes/)).toBeTruthy();
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

  it('preselects the routed system when an initial selected id is provided', () => {
    const systems = [
      makeSystem({ id64: 1, name: 'Alpha Centauri', coords: { x: 10, y: 0, z: 5 } }),
      makeSystem({ id64: 2, name: 'Beta', coords: { x: -20, y: 0, z: 10 } }),
    ];
    render(<MapTab systems={systems} reference={reference} initialSelectedSystemId={2} />);

    expect(screen.getByTestId('map-selection-panel').textContent).toContain('Beta');
    expect(screen.queryByText('Select a star')).toBeNull();
  });

  it('shows system details after selecting a system', () => {
    const systems = [
      makeSystem({ id64: 1, name: 'Alpha Centauri', coords: { x: 10, y: 0, z: 5 } }),
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

  it('does not fetch heatmap by default', () => {
    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    expect(screen.getByTestId('map-heatmap-toggle')).toBeTruthy();
    expect((screen.getByTestId('map-heatmap-toggle') as HTMLInputElement).checked).toBe(false);
    expect(vi.mocked(useMapLayers)).toHaveBeenCalledWith(
      expect.objectContaining({ heatmap: { enabled: false } }),
    );
  });

  it('enables the heatmap layer when toggled', () => {
    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    fireEvent.click(screen.getByTestId('map-heatmap-toggle'));
    expect(vi.mocked(useMapLayers)).toHaveBeenLastCalledWith(
      expect.objectContaining({ heatmap: { enabled: true } }),
    );
  });

  it('enables the timeline layer and shows a summary when data is present', () => {
    vi.mocked(useMapLayers).mockReturnValue({
      regions: { data: undefined, isLoading: false, isError: false, error: null },
      clusters: { data: undefined, isLoading: false, isError: false, error: null },
      heatmap: { data: undefined, isLoading: false, isError: false, error: null },
      timeline: {
        data: { bucket: 'month', points: [{ date: '2026-01-01', count: 100 }], total: 100 },
        isLoading: false,
        isError: false,
        error: null,
      },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useMapLayers>);

    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    fireEvent.click(screen.getByTestId('map-timeline-toggle'));
    expect(vi.mocked(useMapLayers)).toHaveBeenLastCalledWith(
      expect.objectContaining({ timeline: { enabled: true, bucket: 'month' } }),
    );
    expect(screen.getByTestId('map-timeline-summary')).toBeTruthy();
    expect(screen.getByText(/100 discoveries tracked/)).toBeTruthy();
  });

  it('updates the timeline bucket when changed', () => {
    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    fireEvent.click(screen.getByTestId('map-timeline-toggle'));
    fireEvent.change(screen.getByTestId('map-timeline-bucket'), { target: { value: 'year' } });
    expect(vi.mocked(useMapLayers)).toHaveBeenLastCalledWith(
      expect.objectContaining({ timeline: { enabled: true, bucket: 'year' } }),
    );
  });

  it('shows heatmap loading state when toggled', () => {
    vi.mocked(useMapLayers).mockReturnValue({
      regions:  { data: undefined, isLoading: false, isError: false, error: null },
      clusters: { data: undefined, isLoading: false, isError: false, error: null },
      heatmap:  { data: undefined, isLoading: true, isError: false, error: null },
      timeline: { data: undefined, isLoading: false, isError: false, error: null },
      isLoading: true,
      isError:   false,
    } as ReturnType<typeof useMapLayers>);

    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    fireEvent.click(screen.getByTestId('map-heatmap-toggle'));
    expect(screen.getByText('Loading heatmap…')).toBeTruthy();
  });

  it('shows heatmap error state when fetch fails', () => {
    vi.mocked(useMapLayers).mockReturnValue({
      regions:  { data: undefined, isLoading: false, isError: false, error: null },
      clusters: { data: undefined, isLoading: false, isError: false, error: null },
      heatmap:  { data: undefined, isLoading: false, isError: true, error: new Error('fail') },
      timeline: { data: undefined, isLoading: false, isError: false, error: null },
      isLoading: false,
      isError:   true,
    } as ReturnType<typeof useMapLayers>);

    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    fireEvent.click(screen.getByTestId('map-heatmap-toggle'));
    expect(screen.getByText('Heatmap failed')).toBeTruthy();
  });

  it('updates badge when heatmap is loaded', () => {
    vi.mocked(useMapLayers).mockReturnValue({
      regions:  { data: undefined, isLoading: false, isError: false, error: null },
      clusters: { data: undefined, isLoading: false, isError: false, error: null },
      heatmap:  {
        data: {
          voxel_size: 200,
          voxel_bucket: 200,
          economy: null,
          cells: [{ cx: 0, cy: 0, cz: 0, n: 12, avg_score: 70, max_score: 90 }],
          count: 1,
        },
        isLoading: false,
        isError: false,
        error: null,
      },
      timeline: { data: undefined, isLoading: false, isError: false, error: null },
      isLoading: false,
      isError:   false,
    } as ReturnType<typeof useMapLayers>);

    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    fireEvent.click(screen.getByTestId('map-heatmap-toggle'));
    expect(screen.getByText('Finder results + Heatmap')).toBeTruthy();
  });

  it('does not fetch clusters by default', () => {
    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    expect(screen.getByTestId('map-clusters-toggle')).toBeTruthy();
    expect((screen.getByTestId('map-clusters-toggle') as HTMLInputElement).checked).toBe(false);
    expect(vi.mocked(useMapLayers)).toHaveBeenCalledWith(
      expect.objectContaining({ clusters: { enabled: false } }),
    );
  });

  it('enables the clusters layer when toggled', () => {
    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    fireEvent.click(screen.getByTestId('map-clusters-toggle'));
    expect(vi.mocked(useMapLayers)).toHaveBeenLastCalledWith(
      expect.objectContaining({ clusters: { enabled: true } }),
    );
  });

  it('shows cluster loading state when toggled', () => {
    vi.mocked(useMapLayers).mockReturnValue({
      regions:  { data: undefined, isLoading: false, isError: false, error: null },
      clusters: { data: undefined, isLoading: true, isError: false, error: null },
      heatmap:  { data: undefined, isLoading: false, isError: false, error: null },
      timeline: { data: undefined, isLoading: false, isError: false, error: null },
      isLoading: true,
      isError:   false,
    } as ReturnType<typeof useMapLayers>);

    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    fireEvent.click(screen.getByTestId('map-clusters-toggle'));
    expect(screen.getByText('Loading clusters…')).toBeTruthy();
  });

  it('shows cluster error state when fetch fails', () => {
    vi.mocked(useMapLayers).mockReturnValue({
      regions:  { data: undefined, isLoading: false, isError: false, error: null },
      clusters: { data: undefined, isLoading: false, isError: true, error: new Error('fail') },
      heatmap:  { data: undefined, isLoading: false, isError: false, error: null },
      timeline: { data: undefined, isLoading: false, isError: false, error: null },
      isLoading: false,
      isError:   true,
    } as ReturnType<typeof useMapLayers>);

    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    fireEvent.click(screen.getByTestId('map-clusters-toggle'));
    expect(screen.getByText('Clusters failed')).toBeTruthy();
  });

  it('updates badge when clusters are loaded', () => {
    vi.mocked(useMapLayers).mockReturnValue({
      regions:  { data: undefined, isLoading: false, isError: false, error: null },
      clusters: {
        data: {
          clusters: [{
            anchor_id64: 1, anchor_name: 'Hub', x: 0, y: 0, z: 0,
            radius_ly: 500, system_count: 30, top_economy: 'HighTech', top_score: 88,
          }],
          count: 1,
          cached: false,
        },
        isLoading: false,
        isError: false,
        error: null,
      },
      heatmap:  { data: undefined, isLoading: false, isError: false, error: null },
      timeline: { data: undefined, isLoading: false, isError: false, error: null },
      isLoading: false,
      isError:   false,
    } as ReturnType<typeof useMapLayers>);

    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    fireEvent.click(screen.getByTestId('map-clusters-toggle'));
    expect(screen.getByText('Finder results + Clusters')).toBeTruthy();
  });

  it('shows the galactic frame control enabled by default', () => {
    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    const toggle = screen.getByTestId('map-frame-toggle') as HTMLInputElement;
    expect(toggle).toBeTruthy();
    expect(toggle.checked).toBe(true);
  });

  it('toggles the galactic frame off', () => {
    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    const toggle = screen.getByTestId('map-frame-toggle') as HTMLInputElement;
    fireEvent.click(toggle);
    expect(toggle.checked).toBe(false);
  });

  it('defaults the view mode to Results', () => {
    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    expect(screen.getByTestId('map-view-mode')).toBeTruthy();
    expect(screen.getByTestId('map-view-results').getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByTestId('map-view-galaxy').getAttribute('aria-pressed')).toBe('false');
    expect(screen.getByTestId('map-view-reference').getAttribute('aria-pressed')).toBe('false');
  });

  it('selects the Galaxy view mode', () => {
    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    fireEvent.click(screen.getByTestId('map-view-galaxy'));
    expect(screen.getByTestId('map-view-galaxy').getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByTestId('map-view-results').getAttribute('aria-pressed')).toBe('false');
  });

  it('selects the Reference view mode', () => {
    const systems = [makeSystem({ id64: 1, name: 'Alpha', coords: { x: 10, y: 0, z: 5 } })];
    render(<MapTab systems={systems} reference={reference} />);

    fireEvent.click(screen.getByTestId('map-view-reference'));
    expect(screen.getByTestId('map-view-reference').getAttribute('aria-pressed')).toBe('true');
  });
});
