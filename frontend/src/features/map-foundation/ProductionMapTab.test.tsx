import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ProductionMapTab } from './ProductionMapTab';
import { useMapLayers } from '@/features/map/useMapLayers';
import { useAuthoritativeRegionLayer } from './production-regions';
import type { SystemResult } from '@/types/api';

vi.mock('@/features/map/useMapLayers');
vi.mock('./production-regions');
vi.mock('./R3FMapFoundation', () => ({
  R3FMapFoundation: ({ scene, regions, productionOverlays, onInteraction }: {
    scene: {
      systems: Array<{ id64: number }>;
      camera: { bearingDeg: number; pitchDeg: number };
    };
    regions: { labels: unknown[]; boundaries: unknown[] };
    productionOverlays: { heatmap: { cellCount: number } | null; aggregateHulls: { hullCount: number } | null };
    onInteraction: (event: { type: 'selectSystem'; systemId64: number; clusterAnchorId64: null }) => void;
  }) => (
    <div
      data-testid="r3f-production-renderer"
      data-system-count={scene.systems.length}
      data-region-label-count={regions.labels.length}
      data-region-boundary-count={regions.boundaries.length}
      data-camera-bearing={scene.camera.bearingDeg}
      data-camera-pitch={scene.camera.pitchDeg}
      data-heatmap-count={productionOverlays.heatmap?.cellCount ?? 0}
      data-hull-count={productionOverlays.aggregateHulls?.hullCount ?? 0}
    >
      <button type="button" onClick={() => onInteraction({ type: 'selectSystem', systemId64: scene.systems[0]?.id64 ?? 0, clusterAnchorId64: null })}>
        Select first
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
});

afterEach(() => {
  delete window.__stage26eProductionMap;
});

describe('Stage 26E production route composition', () => {
  it('bounds Finder systems and composes authoritative regions plus enabled live overlays', () => {
    render(<ProductionMapTab systems={Array.from({ length: 510 }, (_, index) => system(index))} reference={{ name: 'Sol', x: 0, z: 0 }} />);

    expect(screen.getByTestId('stage26e-production-map').className).toContain('h-full');
    expect(screen.getByRole('heading', { name: 'Galactic Map' })).toBeTruthy();
    expect(screen.getByText('About')).toBeTruthy();
    expect(screen.getByTestId('stage26e-route-flag-state').textContent).toContain('Stage 26E production map active');
    expect((screen.getByTestId('stage26e-map-regions-toggle') as HTMLInputElement).checked).toBe(true);
    const renderer = screen.getByTestId('r3f-production-renderer');
    expect(renderer.getAttribute('data-system-count')).toBe('500');
    expect(renderer.getAttribute('data-region-label-count')).toBe('42');
    expect(renderer.getAttribute('data-region-boundary-count')).toBe('1');
    expect(renderer.getAttribute('data-heatmap-count')).toBe('0');
    expect(renderer.getAttribute('data-hull-count')).toBe('0');

    fireEvent.click(screen.getByTestId('stage26e-map-heatmap-toggle'));
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

  it('offers explicit flat and oblique tabletop projections without changing map data', () => {
    render(<ProductionMapTab systems={[system(0)]} reference={{ name: 'Sol', x: 0, z: 0 }} />);

    const renderer = screen.getByTestId('r3f-production-renderer');
    expect(screen.getByTestId('map-projection-2d').getAttribute('aria-pressed')).toBe('true');
    expect(renderer.getAttribute('data-camera-pitch')).toBe('0');

    fireEvent.click(screen.getByTestId('map-projection-3d'));
    expect(screen.getByTestId('map-projection-3d').getAttribute('aria-pressed')).toBe('true');
    expect(renderer.getAttribute('data-camera-bearing')).toBe('-18');
    expect(renderer.getAttribute('data-camera-pitch')).toBe('46');
    expect(renderer.getAttribute('data-system-count')).toBe('1');

    fireEvent.click(screen.getByTestId('map-projection-2d'));
    expect(screen.getByTestId('map-projection-2d').getAttribute('aria-pressed')).toBe('true');
    expect(renderer.getAttribute('data-camera-bearing')).toBe('0');
    expect(renderer.getAttribute('data-camera-pitch')).toBe('0');
  });
});
