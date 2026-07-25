import { useEffect, useMemo, useRef } from 'react';
import type {
  CameraState,
  MapInteractionEvent,
  SystemRecord,
} from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';
import type { ProductionMapOverlays, ViewportSize } from './types';

const REGION_MAP_ORIGIN = { x: -49_985, z: -24_105 } as const;
const REGION_MAP_PIXELS = 2_048;
const REGION_MAP_LY_PER_PIXEL = 4_096 / 83;
const REGION_MAP_SPAN_LY = REGION_MAP_PIXELS * REGION_MAP_LY_PER_PIXEL;
const MIN_ZOOM_LY_PER_PIXEL = 35;
const MAX_ZOOM_LY_PER_PIXEL = 500;

type AuthoritativeRegionMapProps = {
  camera: CameraState;
  systems: SystemRecord[];
  selectedSystemId64: number | null;
  viewport: ViewportSize;
  viewPreset: 'results' | 'galaxy' | 'reference';
  showRegions: boolean;
  productionOverlays?: ProductionMapOverlays;
  onInteraction: (event: MapInteractionEvent) => void;
  onReady?: () => void;
};

export function AuthoritativeRegionMap({
  camera,
  systems,
  selectedSystemId64,
  viewport,
  viewPreset,
  showRegions,
  productionOverlays,
  onInteraction,
  onReady,
}: AuthoritativeRegionMapProps) {
  useEffect(() => onReady?.(), [onReady]);
  const heatmapCanvasRef = useRef<HTMLCanvasElement>(null);
  const clusterCanvasRef = useRef<HTMLCanvasElement>(null);
  const pointer = useRef<{ x: number; y: number; camera: CameraState } | null>(null);

  const displaySize = REGION_MAP_SPAN_LY / camera.zoom;
  const sheetLeft = viewport.width / 2
    - ((camera.center.x - REGION_MAP_ORIGIN.x) / REGION_MAP_SPAN_LY) * displaySize;
  const sheetTop = viewport.height / 2
    - (1 - ((camera.center.z - REGION_MAP_ORIGIN.z) / REGION_MAP_SPAN_LY)) * displaySize;
  const markers = useMemo(() => systems.flatMap((system, index) => {
    const x = (system.coords.x - REGION_MAP_ORIGIN.x) / REGION_MAP_SPAN_LY;
    // RegionMap's lookup rows run from minimum Z at the bottom to maximum Z at
    // the top, while SVG/CSS Y increases downward.
    const y = 1 - ((system.coords.z - REGION_MAP_ORIGIN.z) / REGION_MAP_SPAN_LY);
    if (x < 0 || x > 1 || y < 0 || y > 1) return [];
    const overlapIndex = systems
      .slice(0, index)
      .filter((candidate) => (
        candidate.coords.x === system.coords.x
        && candidate.coords.z === system.coords.z
      )).length;
    return [{
      system,
      x,
      y,
      overlapIndex,
      overlapIds: systems
        .filter((candidate) => (
          candidate.coords.x === system.coords.x
          && candidate.coords.z === system.coords.z
        ))
        .map((candidate) => candidate.id64),
    }];
  }), [systems]);

  useEffect(() => {
    const canvas = heatmapCanvasRef.current;
    const heatmap = productionOverlays?.heatmap;
    if (!canvas || !heatmap) return;
    const context = prepareOverlayCanvas(canvas, viewport);
    if (!context) return;
    context.globalCompositeOperation = 'lighter';
    for (let index = 0; index < heatmap.cellCount; index += 1) {
      const offset = index * 3;
      const x = projectX(heatmap.positions[offset]!, camera, viewport);
      const y = projectY(heatmap.positions[offset + 1]!, camera, viewport);
      const radius = Math.max(3, Math.min(36, heatmap.voxelSize / camera.zoom / 2));
      if (x + radius < 0 || x - radius > viewport.width || y + radius < 0 || y - radius > viewport.height) {
        continue;
      }
      const red = Math.round(heatmap.colors[offset]! * 255);
      const green = Math.round(heatmap.colors[offset + 1]! * 255);
      const blue = Math.round(heatmap.colors[offset + 2]! * 255);
      const gradient = context.createRadialGradient(x, y, 0, x, y, radius);
      gradient.addColorStop(0, `rgba(${red}, ${green}, ${blue}, 0.72)`);
      gradient.addColorStop(1, `rgba(${red}, ${green}, ${blue}, 0)`);
      context.fillStyle = gradient;
      context.beginPath();
      context.arc(x, y, radius, 0, Math.PI * 2);
      context.fill();
    }
  }, [camera, productionOverlays?.heatmap, viewport]);

  useEffect(() => {
    const canvas = clusterCanvasRef.current;
    const hulls = productionOverlays?.aggregateHulls;
    if (!canvas || !hulls) return;
    const context = prepareOverlayCanvas(canvas, viewport);
    if (!context) return;
    context.strokeStyle = 'rgba(255, 179, 93, 0.72)';
    context.lineWidth = 1.5;
    context.shadowColor = 'rgba(255, 119, 22, 0.7)';
    context.shadowBlur = 7;
    context.beginPath();
    for (let offset = 0; offset < hulls.linePositions.length; offset += 6) {
      const x1 = projectX(hulls.linePositions[offset]!, camera, viewport);
      const y1 = projectY(hulls.linePositions[offset + 1]!, camera, viewport);
      const x2 = projectX(hulls.linePositions[offset + 3]!, camera, viewport);
      const y2 = projectY(hulls.linePositions[offset + 4]!, camera, viewport);
      if (
        Math.max(x1, x2) < 0
        || Math.min(x1, x2) > viewport.width
        || Math.max(y1, y2) < 0
        || Math.min(y1, y2) > viewport.height
      ) {
        continue;
      }
      context.moveTo(x1, y1);
      context.lineTo(x2, y2);
    }
    context.stroke();
  }, [camera, productionOverlays?.aggregateHulls, viewport]);

  return (
    <div
      className="map-foundation-renderer authoritative-region-map"
      data-projection="2d"
      data-view-preset={viewPreset}
      aria-label="Authoritative Elite Dangerous region map"
      onPointerDown={(event) => {
        if (viewPreset === 'galaxy' || event.button !== 0 || event.target instanceof HTMLButtonElement) return;
        pointer.current = { x: event.clientX, y: event.clientY, camera };
        event.currentTarget.setPointerCapture(event.pointerId);
      }}
      onPointerMove={(event) => {
        if (!pointer.current || event.buttons !== 1) return;
        onInteraction({
          type: 'cameraChanged',
          camera: {
            ...pointer.current.camera,
            center: {
              x: pointer.current.camera.center.x - (event.clientX - pointer.current.x) * pointer.current.camera.zoom,
              z: pointer.current.camera.center.z + (event.clientY - pointer.current.y) * pointer.current.camera.zoom,
            },
          },
        });
      }}
      onPointerUp={() => { pointer.current = null; }}
      onPointerCancel={() => { pointer.current = null; }}
      onWheel={(event) => {
        event.preventDefault();
        const zoom = Math.max(
          MIN_ZOOM_LY_PER_PIXEL,
          Math.min(MAX_ZOOM_LY_PER_PIXEL, camera.zoom * Math.exp(event.deltaY * 0.001)),
        );
        onInteraction({ type: 'cameraChanged', camera: { ...camera, zoom } });
      }}
    >
      <div
        className="authoritative-region-map__sheet"
        style={{
          width: displaySize,
          height: displaySize,
          left: sheetLeft,
          top: sheetTop,
        }}
      >
        {showRegions && (
          <img
            src="/assets/elite-dangerous-region-map.svg"
            alt="The 42 named Elite Dangerous galactic regions"
            draggable={false}
          />
        )}
        <div className="authoritative-region-map__markers" aria-label="Finder systems on galaxy map">
          {markers.map(({ system, x, y, overlapIndex, overlapIds }) => (
            <button
              key={system.id64}
              type="button"
              className={system.id64 === selectedSystemId64 ? 'is-selected' : undefined}
              style={{
                left: `${x * 100}%`,
                top: `${y * 100}%`,
                transform: `translate(-50%, -50%) translate(${overlapIndex * 7}px, ${-overlapIndex * 7}px)`,
              }}
              title={system.name}
              aria-label={`Select ${system.name}`}
              onClick={() => onInteraction(overlapIds.length > 1
                ? { type: 'overlapChoiceRequired', candidateSystemIds: overlapIds }
                : {
                    type: 'selectSystem',
                    systemId64: system.id64,
                    clusterAnchorId64: null,
                  })}
            />
          ))}
        </div>
      </div>
      {productionOverlays?.heatmap && productionOverlays.heatmap.cellCount > 0 && (
        <canvas
          ref={heatmapCanvasRef}
          data-testid="authoritative-map-heatmap"
          data-cell-count={productionOverlays.heatmap.cellCount}
          className="authoritative-region-map__overlay"
          aria-label={`${productionOverlays.heatmap.cellCount.toLocaleString()} heatmap cells`}
        />
      )}
      {productionOverlays?.aggregateHulls && productionOverlays.aggregateHulls.hullCount > 0 && (
        <canvas
          ref={clusterCanvasRef}
          data-testid="authoritative-map-clusters"
          data-hull-count={productionOverlays.aggregateHulls.hullCount}
          className="authoritative-region-map__overlay"
          aria-label={`${productionOverlays.aggregateHulls.hullCount.toLocaleString()} cluster hulls`}
        />
      )}
      <div className="map-foundation-map-readout" aria-hidden="true">
        <strong>{viewPreset === 'galaxy' ? 'Whole galaxy' : viewPreset === 'reference' ? 'Origin system' : 'Finder results'}</strong>
        <span>42 authoritative named regions</span>
        <span>{viewPreset === 'galaxy' ? 'Scroll to zoom · centre locked' : 'Drag to pan · scroll to zoom'}</span>
      </div>
      <div className="authoritative-region-map__credit">
        Region map © 2020 Ben Peddell · MIT
      </div>
      <output className="map-foundation-render-stats" aria-label="Renderer draw summary">
        {systems.length.toLocaleString()} Finder systems · {viewport.width}×{viewport.height}
      </output>
    </div>
  );
}

function prepareOverlayCanvas(
  canvas: HTMLCanvasElement,
  viewport: ViewportSize,
): CanvasRenderingContext2D | null {
  const scale = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
  canvas.width = Math.max(1, Math.round(viewport.width * scale));
  canvas.height = Math.max(1, Math.round(viewport.height * scale));
  const context = canvas.getContext('2d');
  if (!context) return null;
  context.setTransform(scale, 0, 0, scale, 0, 0);
  context.clearRect(0, 0, viewport.width, viewport.height);
  return context;
}

function projectX(value: number, camera: CameraState, viewport: ViewportSize): number {
  return viewport.width / 2 + (value - camera.center.x) / camera.zoom;
}

function projectY(value: number, camera: CameraState, viewport: ViewportSize): number {
  return viewport.height / 2 - (value - camera.center.z) / camera.zoom;
}
