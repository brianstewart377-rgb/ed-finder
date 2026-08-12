import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ProductionMapTab } from './ProductionMapTab';
import { useMapLayers } from '@/features/map/useMapLayers';
import { useViewportSystems } from '@/features/map/viewportSystems';
import { useExplorationLayers } from '@/features/map/useExplorationLayers';
import { usePowerplayLayer } from '@/features/map/usePowerplayLayer';
import { useAuthoritativeRegionLayer } from './production-regions';
import type { SystemResult } from '@/types/api';

vi.mock('@/lib/api', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...original,
    api: {
      ...original.api,
      listRoutes: vi.fn(async () => ({ routes: [], count: 0 })),
      getRoute: vi.fn(),
    },
  };
});

vi.mock('@/features/map/useMapLayers');
vi.mock('@/features/map/viewportSystems');
vi.mock('@/features/map/useExplorationLayers');
vi.mock('@/features/map/usePowerplayLayer');
vi.mock('./production-regions');
vi.mock('./R3FMapFoundation', () => ({
  R3FMapFoundation: ({ scene, regions, productionOverlays, viewPreset, onInteraction, onZoomIntent, onViewportSystemSelect }: {
    scene: {
      systems: Array<{ id64: number }>;
      camera: { bearingDeg: number; pitchDeg: number; zoom: number };
    };
    regions: { labels: unknown[]; boundaries: unknown[] };
    productionOverlays: { heatmap: { cellCount: number } | null; aggregateHulls: { hullCount: number } | null };
    viewPreset: string;
    onInteraction: (event: { type: 'selectSystem'; systemId64: number; clusterAnchorId64: null }) => void;
    onZoomIntent?: (deltaY: number) => void;
    onViewportSystemSelect?: (system: {
      id64: number; name: string; x: number; y: number; z: number;
      star: string | null; populated: boolean; galaxy_region_id: number | null;
    }) => void;
  }) => (
    <div
      data-testid="r3f-production-renderer"
      data-system-count={scene.systems.length}
      data-region-label-count={regions.labels.length}
      data-region-boundary-count={regions.boundaries.length}
      data-camera-bearing={scene.camera.bearingDeg}
      data-camera-pitch={scene.camera.pitchDeg}
      data-camera-zoom={scene.camera.zoom}
      data-view-preset={viewPreset}
      data-heatmap-count={productionOverlays.heatmap?.cellCount ?? 0}
      data-hull-count={productionOverlays.aggregateHulls?.hullCount ?? 0}
    >
      <button type="button" onClick={() => onInteraction({ type: 'selectSystem', systemId64: scene.systems[0]?.id64 ?? 0, clusterAnchorId64: null })}>
        Select first
      </button>
      <button type="button" onClick={() => onZoomIntent?.(-120)}>
        Simulate wheel zoom
      </button>
      <button type="button" onClick={() => onViewportSystemSelect?.({
        id64: 777, name: 'Viewport Star', x: 7, y: 8, z: 9,
        star: 'G', populated: false, galaxy_region_id: 12,
      })}>
        Pick viewport star
      </button>
    </div>
  ),
}));

const layers = {
  regions: { data: undefined, isLoading: false, isError: false, error: null },
  heatmap: {
    data: {
      voxel_size: 200,
      voxel_bucket: 200,
      economy: null,
      count: 1,
      max_cells: 50_000,
      truncated: false,
      cells: [{ cx: 0, cy: 0, cz: 0, n: 10, avg_score: 80, max_score: 90 }],
    },
    isLoading: false,
    isError: false,
    error: null,
  },
  clusters: {
    data: {
      count: 1,
      min_count: 3,
      cached: false,
      clusters: [{
        anchor_id64: 99,
        anchor_name: 'Hull',
        x: 0,
        y: 0,
        z: 0,
        radius_ly: 500,
        system_count: 5,
        top_economy: null,
        top_score: 82,
      }],
    },
    isLoading: false,
    isError: false,
    error: null,
  },
  timeline: {
    data: { bucket: 'month', total: 3, points: [{ date: '2026-07-01', count: 3 }] },
    isLoading: false,
    isError: false,
    error: null,
  },
  isLoading: false,
  isError: false,
} as ReturnType<typeof useMapLayers>;

const regionLayer = {
  data: {
    labels: Array.from({ length: 42 }, (_, index) => ({
      id: index + 1,
      name: `Region ${index + 1}`,
      position: [index, index, 0] as [number, number, number],
    })),
    boundaries: [{ source: [0, 0, 0] as [number, number, number], target: [1, 1, 0] as [number, number, number] }],
  },
  isLoading: false,
  isError: false,
  error: null,
} as ReturnType<typeof useAuthoritativeRegionLayer>;

function system(index: number): SystemResult {
  return {
    id64: index + 1,
    name: `System ${index + 1}`,
    coords: { x: index, y: 0, z: -index },
    population: 0,
    distance: index,
  } as SystemResult;
}

beforeEach(() => {
  vi.mocked(useMapLayers).mockReturnValue(layers);
  vi.mocked(useAuthoritativeRegionLayer).mockReturnValue(regionLayer);
  vi.mocked(useViewportSystems).mockReturnValue({ systems: null, truncated: false });
  vi.mocked(useExplorationLayers).mockReturnValue({
    facts: { data: undefined, isLoading: false, isError: false, error: null },
    viewportVisits: { data: undefined, isLoading: false, isError: false, error: null },
    trail: { data: undefined, isLoading: false, isError: false, error: null },
    summary: { data: undefined, isLoading: false, isError: false, error: null },
  } as ReturnType<typeof useExplorationLayers>);
  vi.mocked(usePowerplayLayer).mockReturnValue({
    systems: { data: undefined, isLoading: false, isError: false, error: null },
    commander: { data: undefined, isLoading: false, isError: false, error: null },
  } as ReturnType<typeof usePowerplayLayer>);
});

afterEach(() => {
  delete window.__stage26eProductionMap;
  vi.unstubAllGlobals();
});

describe('Stage 26E production route composition', () => {
  it('keeps the whole-galaxy chart available before Finder has results', () => {
    render(<ProductionMapTab systems={[]} reference={{ name: 'Sol', x: 0, z: 0 }} />);

    expect(screen.getByTestId('map-view-galaxy').getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByTestId('r3f-production-renderer')).toBeTruthy();
  });

  it('keeps galaxy framing on a cold open with no Finder systems', () => {
    render(<ProductionMapTab systems={[]} reference={{ name: 'Sol', x: 0, z: 0 }} />);

    expect(screen.getByTestId('r3f-production-renderer').getAttribute('data-view-preset')).toBe('galaxy');
    expect(screen.queryByText('No systems to map yet')).toBeNull();
  });

  it('shows the empty state for Finder results with no systems', () => {
    render(<ProductionMapTab systems={[]} reference={{ name: 'Sol', x: 0, z: 0 }} />);

    fireEvent.click(screen.getByTestId('map-view-results'));
    expect(screen.getByText('No systems to map yet')).toBeTruthy();
  });

  it('bounds Finder systems and composes authoritative regions plus enabled live overlays', () => {
    render(<ProductionMapTab systems={Array.from({ length: 510 }, (_, index) => system(index))} reference={{ name: 'Sol', x: 0, z: 0 }} />);

    expect(screen.getByTestId('stage26e-route-flag-state').textContent).toContain('Live map');
    expect((screen.getByTestId('stage26e-map-regions-toggle') as HTMLInputElement).checked).toBe(true);
    expect((screen.getByTestId('stage26e-map-heatmap-toggle') as HTMLInputElement).checked).toBe(true);
    expect((screen.getByTestId('stage26e-map-clusters-toggle') as HTMLInputElement).checked).toBe(false);
    expect((screen.getByTestId('stage26e-map-timeline-toggle') as HTMLInputElement).checked).toBe(false);
    expect((screen.getByTestId('map-visited-systems-toggle') as HTMLInputElement).checked).toBe(true);
    expect((screen.getByTestId('map-travel-trail-toggle') as HTMLInputElement).checked).toBe(false);
    expect((screen.getByTestId('map-completeness-toggle') as HTMLInputElement).checked).toBe(false);
    expect(vi.mocked(useMapLayers)).toHaveBeenCalledWith(expect.objectContaining({
      heatmap: { enabled: true, max_cells: 50_000 },
    }));
    const renderer = screen.getByTestId('r3f-production-renderer');
    expect(renderer.getAttribute('data-system-count')).toBe('500');
    expect(renderer.getAttribute('data-region-label-count')).toBe('42');
    expect(renderer.getAttribute('data-region-boundary-count')).toBe('1');
    expect(renderer.getAttribute('data-heatmap-count')).toBe('1');
    expect(renderer.getAttribute('data-hull-count')).toBe('0');

    fireEvent.click(screen.getByTestId('stage26e-map-heatmap-toggle'));
    expect((screen.getByTestId('stage26e-map-heatmap-toggle') as HTMLInputElement).checked).toBe(false);
    expect(renderer.getAttribute('data-heatmap-count')).toBe('0');
    fireEvent.click(screen.getByTestId('stage26e-map-heatmap-toggle'));
    expect((screen.getByTestId('stage26e-map-heatmap-toggle') as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByTestId('stage26e-map-clusters-toggle'));
    fireEvent.click(screen.getByTestId('stage26e-map-timeline-toggle'));

    expect(renderer.getAttribute('data-heatmap-count')).toBe('1');
    expect(renderer.getAttribute('data-hull-count')).toBe('1');
    expect(screen.getByTestId('stage26e-map-timeline-summary').textContent).toContain('3 discoveries tracked');
    expect(window.__stage26eProductionMap?.snapshot()).toMatchObject({
      renderer: 'r3f',
      routeFlagEnabled: true,
      finderSystemCount: 500,
      finderResponseTruncated: true,
      heatmapCellCount: 1,
      aggregateHullCount: 1,
      timelinePointCount: 1,
      regionGeometryExposed: true,
      regionGeometryVisible: true,
      regionLabelCount: 42,
      regionBoundaryCount: 1,
      regionPositionBytes: 24,
      overlayBufferWithinBudget: true,
    });

    fireEvent.click(screen.getByTestId('stage26e-map-regions-toggle'));
    expect(renderer.getAttribute('data-region-label-count')).toBe('0');
    expect(window.__stage26eProductionMap?.snapshot().regionGeometryVisible).toBe(false);
  });

  it('preserves selection and inspect hand-off on the candidate route', () => {
    const onOpenSelectedSystem = vi.fn();
    render(
      <ProductionMapTab
        systems={[system(0), system(1)]}
        reference={{ name: 'Sol', x: 0, z: 0 }}
        onOpenSelectedSystem={onOpenSelectedSystem}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Select first' }));
    expect(screen.getByTestId('map-selection-panel').textContent).toContain('System 1');
    fireEvent.click(screen.getByTestId('map-open-selected-system'));
    expect(onOpenSelectedSystem).toHaveBeenCalledWith(1);
  });

  it('promotes GPU-picked viewport stars into selectable inspect context', () => {
    const onOpenSelectedSystem = vi.fn();
    render(
      <ProductionMapTab
        systems={[]}
        reference={{ name: 'Sol', x: 0, z: 0 }}
        onOpenSelectedSystem={onOpenSelectedSystem}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Pick viewport star' }));
    expect(screen.getByTestId('map-selection-panel').textContent).toContain('Viewport Star');
    fireEvent.click(screen.getByTestId('map-open-selected-system'));
    expect(onOpenSelectedSystem).toHaveBeenCalledWith(777);
  });

  it('uses one continuous camera and offers a top-down snap without replacing the renderer', () => {
    let resize: ResizeObserverCallback | null = null;
    class ResizeObserverMock {
      constructor(callback: ResizeObserverCallback) {
        resize = callback;
      }

      observe() {}

      unobserve() {}

      disconnect() {}
    }
    vi.stubGlobal('ResizeObserver', ResizeObserverMock);
    vi.stubGlobal('matchMedia', () => ({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));

    render(<ProductionMapTab systems={[system(0)]} reference={{ name: 'Sol', x: 0, z: 0 }} />);

    const renderer = screen.getByTestId('r3f-production-renderer');
    expect(screen.queryByTestId('map-projection-2d')).toBeNull();
    expect(screen.queryByTestId('map-projection-3d')).toBeNull();
    expect(renderer.getAttribute('data-camera-bearing')).toBe('0');
    expect(renderer.getAttribute('data-camera-pitch')).toBe('42');
    const initialZoom = Number(renderer.getAttribute('data-camera-zoom'));
    expect(renderer.getAttribute('data-system-count')).toBe('1');

    fireEvent.click(screen.getByTestId('map-zoom-in'));
    expect(Number(renderer.getAttribute('data-camera-zoom'))).toBeLessThan(initialZoom);
    fireEvent.click(screen.getByTestId('map-zoom-out'));
    expect(Number(renderer.getAttribute('data-camera-zoom'))).toBeCloseTo(initialZoom);
    fireEvent.click(screen.getByRole('button', { name: 'Simulate wheel zoom' }));
    expect(Number(renderer.getAttribute('data-camera-zoom'))).toBeLessThan(initialZoom);

    fireEvent.click(screen.getByTestId('map-snap-top-down'));
    expect(renderer.getAttribute('data-camera-pitch')).toBe('0.5');
    expect(renderer.getAttribute('data-system-count')).toBe('1');

    act(() => {
      resize?.([{
        contentRect: { width: 1059, height: 520 },
      } as ResizeObserverEntry], {} as ResizeObserver);
    });
    expect(renderer.getAttribute('data-camera-bearing')).toBe('0');
    expect(renderer.getAttribute('data-camera-pitch')).toBe('0.5');
  });

  it('explains every optional data layer using its underlying data semantics', () => {
    render(<ProductionMapTab systems={[system(0)]} reference={{ name: 'Sol', x: 0, z: 0 }} />);

    expect(screen.getByText(/rated-system density grouped into 3d voxels/i)).toBeTruthy();
    expect(screen.getByText(/500 LY bubbles around top anchors/i)).toBeTruthy();
    expect(screen.getByText(/first-discovery date/i)).toBeTruthy();
    expect(screen.getByText(/42 canonical named regions/i)).toBeTruthy();
  });
});
