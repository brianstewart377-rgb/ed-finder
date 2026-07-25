import { useEffect, useMemo } from 'react';
import type {
  CameraState,
  MapInteractionEvent,
  SystemRecord,
} from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';
import type { ViewportSize } from './types';

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
  showRegions: boolean;
  onInteraction: (event: MapInteractionEvent) => void;
  onReady?: () => void;
};

export function AuthoritativeRegionMap({
  camera,
  systems,
  selectedSystemId64,
  viewport,
  showRegions,
  onInteraction,
  onReady,
}: AuthoritativeRegionMapProps) {
  useEffect(() => onReady?.(), [onReady]);

  const displaySize = REGION_MAP_SPAN_LY / camera.zoom;
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

  return (
    <div
      className="map-foundation-renderer authoritative-region-map"
      data-projection="2d"
      data-view-preset="galaxy"
      aria-label="Authoritative Elite Dangerous region map"
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
        style={{ width: displaySize, height: displaySize }}
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
      <div className="map-foundation-map-readout" aria-hidden="true">
        <strong>Whole galaxy</strong>
        <span>42 authoritative named regions</span>
        <span>Scroll to zoom · centre locked</span>
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
