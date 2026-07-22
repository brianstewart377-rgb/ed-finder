import type { CameraState, MapSceneState, SystemRecord } from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';
import { reduceScene } from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';
import type { MapClusterHull, MapHeatmapResponse, MapTimelineResponse } from '../../lib/api';
import type {
  ProductionAggregateHullGeometry,
  ProductionHeatmapGeometry,
  ProductionMapOverlays,
  ViewportSize,
} from './types';

export const PRODUCTION_PARITY_LIMITS = {
  finderSystems: 500,
  heatmapCells: 50_000,
  aggregateHulls: 2_000,
  timelinePoints: 1_200,
  overlayBufferBytes: 8 * 1_048_576,
} as const;

export type MapViewPreset = 'results' | 'galaxy' | 'reference';
export type TimelineBucket = 'month' | 'quarter' | 'year';

export type ProductionTimelineSummary = {
  bucket: TimelineBucket;
  total: number;
  pointCount: number;
  latestDate: string | null;
  omittedPointCount: number;
};

export type ProductionSurfaceState =
  | { kind: 'ready'; systemCount: number }
  | { kind: 'empty'; message: string }
  | { kind: 'error'; message: string };

export type ProductionParityComposition = {
  overlays: ProductionMapOverlays;
  timeline: ProductionTimelineSummary | null;
  surface: ProductionSurfaceState;
  estimatedOverlayBufferBytes: number;
  withinOverlayBufferBudget: boolean;
};

const HULL_SEGMENTS = 32;

function finite(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function colorForScore(score: number | null): [number, number, number] {
  if (score != null && score >= 80) return [0.24, 0.86, 0.82];
  if (score != null && score >= 60) return [0.24, 0.82, 0.52];
  if (score != null && score >= 40) return [1, 0.71, 0.33];
  return [0.56, 0.68, 0.75];
}

export function adaptHeatmap(
  response: MapHeatmapResponse | undefined,
  limit: number = PRODUCTION_PARITY_LIMITS.heatmapCells,
): ProductionHeatmapGeometry | null {
  if (!response || !finite(response.voxel_size) || response.voxel_size <= 0) return null;
  if (!Number.isInteger(limit) || limit < 1) throw new Error('heatmap limit must be a positive integer');

  const capacity = Math.min(response.cells.length, limit);
  const positions = new Float32Array(capacity * 3);
  const colors = new Float32Array(capacity * 3);
  let validCount = 0;
  let retainedCount = 0;
  for (const cell of response.cells) {
    if (!finite(cell.cx) || !finite(cell.cz)) continue;
    validCount += 1;
    if (retainedCount >= limit) continue;
    positions.set([cell.cx, cell.cz, -2], retainedCount * 3);
    colors.set(colorForScore(cell.avg_score), retainedCount * 3);
    retainedCount += 1;
  }
  return {
    positions: positions.subarray(0, retainedCount * 3),
    colors: colors.subarray(0, retainedCount * 3),
    voxelSize: response.voxel_size,
    cellCount: retainedCount,
    omittedCellCount: Math.max(0, validCount - limit),
    sourceTruncated: response.truncated,
  };
}

export function adaptAggregateHulls(
  hulls: MapClusterHull[] | undefined,
  limit: number = PRODUCTION_PARITY_LIMITS.aggregateHulls,
): ProductionAggregateHullGeometry | null {
  if (!hulls) return null;
  if (!Number.isInteger(limit) || limit < 1) throw new Error('aggregate hull limit must be a positive integer');

  const capacity = Math.min(hulls.length, limit) * HULL_SEGMENTS * 6;
  const linePositions = new Float32Array(capacity);
  const lineColors = new Float32Array(capacity);
  let validCount = 0;
  let retainedCount = 0;
  for (const hull of hulls) {
    if (!finite(hull.x) || !finite(hull.z) || !finite(hull.radius_ly) || hull.radius_ly <= 0) continue;
    validCount += 1;
    if (retainedCount >= limit) continue;
    retainedCount += 1;
    const color = colorForScore(hull.top_score);
    for (let segment = 0; segment < HULL_SEGMENTS; segment += 1) {
      const start = segment * Math.PI * 2 / HULL_SEGMENTS;
      const end = (segment + 1) * Math.PI * 2 / HULL_SEGMENTS;
      const offset = ((retainedCount - 1) * HULL_SEGMENTS + segment) * 6;
      linePositions.set([
        hull.x + Math.cos(start) * hull.radius_ly,
        hull.z + Math.sin(start) * hull.radius_ly,
        -1,
        hull.x + Math.cos(end) * hull.radius_ly,
        hull.z + Math.sin(end) * hull.radius_ly,
        -1,
      ], offset);
      lineColors.set([...color, ...color], offset);
    }
  }
  return {
    linePositions: linePositions.subarray(0, retainedCount * HULL_SEGMENTS * 6),
    lineColors: lineColors.subarray(0, retainedCount * HULL_SEGMENTS * 6),
    hullCount: retainedCount,
    omittedHullCount: Math.max(0, validCount - limit),
  };
}

export function summarizeTimeline(
  response: MapTimelineResponse | undefined,
  bucket: TimelineBucket,
  limit: number = PRODUCTION_PARITY_LIMITS.timelinePoints,
): ProductionTimelineSummary | null {
  if (!response) return null;
  if (!Number.isInteger(limit) || limit < 1) throw new Error('timeline limit must be a positive integer');
  const valid = response.points.filter((point) => point.date == null || typeof point.date === 'string');
  const retained = valid.slice(-limit);
  return {
    bucket,
    total: finite(response.total) ? response.total : 0,
    pointCount: retained.length,
    latestDate: retained.at(-1)?.date ?? null,
    omittedPointCount: Math.max(0, valid.length - retained.length),
  };
}

export function resolveProductionSurfaceState(systemCount: number, error?: string | null): ProductionSurfaceState {
  if (error) return { kind: 'error', message: error };
  if (systemCount === 0) {
    return { kind: 'empty', message: 'Run a Finder search to plot systems on the map.' };
  }
  return { kind: 'ready', systemCount };
}

export function estimateOverlayBufferBytes(overlays: ProductionMapOverlays): number {
  return (overlays.heatmap?.positions.byteLength ?? 0)
    + (overlays.heatmap?.colors.byteLength ?? 0)
    + (overlays.aggregateHulls?.linePositions.byteLength ?? 0)
    + (overlays.aggregateHulls?.lineColors.byteLength ?? 0);
}

export function composeProductionParity(input: {
  systemCount: number;
  error?: string | null;
  heatmap?: MapHeatmapResponse;
  hulls?: MapClusterHull[];
  timeline?: MapTimelineResponse;
  timelineBucket?: TimelineBucket;
}): ProductionParityComposition {
  const overlays = {
    heatmap: adaptHeatmap(input.heatmap),
    aggregateHulls: adaptAggregateHulls(input.hulls),
  };
  const estimatedOverlayBufferBytes = estimateOverlayBufferBytes(overlays);
  return {
    overlays,
    timeline: summarizeTimeline(input.timeline, input.timelineBucket ?? 'month'),
    surface: resolveProductionSurfaceState(input.systemCount, input.error),
    estimatedOverlayBufferBytes,
    withinOverlayBufferBudget: estimatedOverlayBufferBytes <= PRODUCTION_PARITY_LIMITS.overlayBufferBytes,
  };
}

function zoomForRadius(radius: number, viewport: ViewportSize): number {
  const usableHalfExtent = Math.max(1, Math.min(viewport.width, viewport.height) / 2 - 40);
  return Math.max(2, radius / usableHalfExtent);
}

export function cameraForViewPreset(
  preset: MapViewPreset,
  systems: SystemRecord[],
  reference: { x: number; z: number },
  viewport: ViewportSize,
): CameraState {
  if (preset === 'galaxy') {
    return { center: { x: 0, z: 0 }, zoom: zoomForRadius(50_000, viewport), pitchDeg: 0, bearingDeg: 0 };
  }
  if (preset === 'reference') {
    return { center: { ...reference }, zoom: zoomForRadius(50, viewport), pitchDeg: 0, bearingDeg: 0 };
  }
  let radius = 50;
  if (systems.length > 0) {
    let furthest = 20;
    for (const system of systems) {
      furthest = Math.max(furthest, Math.hypot(
        system.coords.x - reference.x,
        system.coords.z - reference.z,
      ));
    }
    radius = furthest * 1.1;
  }
  return { center: { ...reference }, zoom: zoomForRadius(radius, viewport), pitchDeg: 0, bearingDeg: 0 };
}

export function applyViewPreset(
  scene: MapSceneState,
  preset: MapViewPreset,
  reference: { x: number; z: number },
  viewport: ViewportSize,
): MapSceneState {
  const camera = cameraForViewPreset(preset, scene.systems, reference, viewport);
  const armed = reduceScene(scene, { type: 'enableOneTimeFit', center: camera.center, zoom: camera.zoom });
  const fitted = reduceScene(armed, { type: 'advanceSceneRevision', revision: scene.sceneRevision + 1 });
  return { ...fitted, camera: { ...fitted.camera, pitchDeg: camera.pitchDeg, bearingDeg: camera.bearingDeg } };
}
