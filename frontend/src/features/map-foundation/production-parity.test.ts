import { describe, expect, it } from 'vitest';
import { reduceScene } from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';
import type { MapClusterHull, MapHeatmapResponse, MapTimelineResponse } from '../../lib/api';
import { createFoundationDemoScene } from './demo-scene';
import {
  PRODUCTION_PARITY_LIMITS,
  adaptAggregateHulls,
  adaptHeatmap,
  applyViewPreset,
  cameraForViewPreset,
  composeProductionParity,
  resolveProductionSurfaceState,
  summarizeTimeline,
} from './production-parity';

function heatmap(cellCount: number): MapHeatmapResponse {
  return {
    voxel_size: 200,
    voxel_bucket: 200,
    economy: null,
    count: cellCount,
    max_cells: PRODUCTION_PARITY_LIMITS.heatmapCells,
    truncated: false,
    cells: Array.from({ length: cellCount }, (_, index) => ({
      cx: index * 200,
      cy: 0,
      cz: index * -200,
      n: 5,
      avg_score: index % 100,
      max_score: 100,
    })),
  };
}

function hulls(hullCount: number): MapClusterHull[] {
  return Array.from({ length: hullCount }, (_, index) => ({
    anchor_id64: index,
    anchor_name: `Hull ${index}`,
    x: index * 500,
    y: 0,
    z: index * -500,
    radius_ly: 500,
    system_count: 3,
    top_economy: null,
    top_score: 80,
  }));
}

describe('Stage 26E production parity composition', () => {
  it('normalizes and bounds live overlay shapes within the typed-buffer budget', () => {
    const composition = composeProductionParity({
      systemCount: PRODUCTION_PARITY_LIMITS.finderSystems,
      heatmap: heatmap(PRODUCTION_PARITY_LIMITS.heatmapCells + 10),
      hulls: hulls(PRODUCTION_PARITY_LIMITS.aggregateHulls + 10),
      timeline: {
        bucket: 'month',
        total: 42,
        points: [{ date: '2026-06-01', count: 20 }, { date: '2026-07-01', count: 22 }],
      },
    });

    expect(composition.overlays.heatmap?.cellCount).toBe(PRODUCTION_PARITY_LIMITS.heatmapCells);
    expect(composition.overlays.heatmap?.omittedCellCount).toBe(10);
    expect(composition.overlays.heatmap?.sourceTruncated).toBe(false);
    expect(composition.overlays.aggregateHulls?.hullCount).toBe(PRODUCTION_PARITY_LIMITS.aggregateHulls);
    expect(composition.overlays.aggregateHulls?.omittedHullCount).toBe(10);
    expect(composition.timeline).toEqual({
      bucket: 'month', total: 42, pointCount: 2, latestDate: '2026-07-01', omittedPointCount: 0,
    });
    expect(composition.surface).toEqual({ kind: 'ready', systemCount: 500 });
    expect(composition.estimatedOverlayBufferBytes).toBe(4_272_000);
    expect(composition.withinOverlayBufferBudget).toBe(true);
  });

  it('rejects invalid coordinates without inventing positions', () => {
    const invalidHeatmap = heatmap(2);
    invalidHeatmap.cells[0]!.cx = Number.NaN;
    invalidHeatmap.truncated = true;
    const invalidHulls = hulls(2);
    invalidHulls[0]!.x = null;

    expect(adaptHeatmap(invalidHeatmap)).toMatchObject({ cellCount: 1, sourceTruncated: true });
    expect(adaptAggregateHulls(invalidHulls)?.hullCount).toBe(1);
  });

  it('retains the newest bounded timeline summary and exposes empty/error composition', () => {
    const timeline: MapTimelineResponse = {
      bucket: 'month', total: 3,
      points: [
        { date: '2026-05-01', count: 1 },
        { date: '2026-06-01', count: 1 },
        { date: '2026-07-01', count: 1 },
      ],
    };
    expect(summarizeTimeline(timeline, 'quarter', 2)).toEqual({
      bucket: 'quarter', total: 3, pointCount: 2, latestDate: '2026-07-01', omittedPointCount: 1,
    });
    expect(resolveProductionSurfaceState(0)).toEqual({
      kind: 'empty', message: 'Run a Finder search to plot systems on the map.',
    });
    expect(resolveProductionSurfaceState(0, 'Finder request failed')).toEqual({
      kind: 'error', message: 'Finder request failed',
    });
  });

  it('maps Results, Galaxy, and Reference to one-time camera intents', () => {
    const scene = createFoundationDemoScene(100_000);
    const viewport = { width: 1280, height: 720 };
    const reference = { x: 100, z: -200 };

    expect(cameraForViewPreset('galaxy', scene.systems, reference, viewport).center).toEqual({ x: 0, z: 0 });
    expect(cameraForViewPreset('reference', scene.systems, reference, viewport).center).toEqual(reference);
    expect(cameraForViewPreset('results', scene.systems, reference, viewport).center).toEqual(reference);
    const largeResultSet = Array.from({ length: 500_001 }, () => scene.systems[0]!);
    expect(cameraForViewPreset('results', largeResultSet, reference, viewport).center).toEqual(reference);

    const fitted = applyViewPreset(scene, 'reference', reference, viewport);
    expect(fitted.camera.center).toEqual(reference);
    expect(fitted.cameraIntent).toBe('autoFit');
    expect(fitted.oneTimeFitIntent).toBeNull();

    const dragged = reduceScene(fitted, { type: 'dragCamera', newCenter: { x: 300, z: 400 } });
    const selected = reduceScene(dragged, { type: 'selectSystem', systemId64: scene.systems[4]!.id64 });
    expect(selected.camera.center).toEqual({ x: 300, z: 400 });
    expect(selected.cameraIntent).toBe('user');
  });
});
