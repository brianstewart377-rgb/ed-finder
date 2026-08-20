import { useEffect, useRef } from 'react';
import type { BabylonMapSceneHandle, MapSceneConfig } from './babylon-map/types';
import { BabylonMapScene } from './babylon-map/BabylonMapScene';
import type { FoundationRendererProps } from './types';

export interface BabylonMapFoundationProps extends Omit<FoundationRendererProps, 'visible'> {
  visible?: boolean;
}

/**
 * Babylon.js-based map renderer (Stage 26 redesign).
 *
 * Wraps BabylonMapScene to provide the same interface as R3FMapFoundation.
 * Real-star viewport systems are passed through to the babylon stars layer.
 *
 * Coordinate system: Elite Dangerous galactic (x, y, z) → Babylon world space (x, z, y)
 */
export function BabylonMapFoundation({
  scene,
  regions: _regions,
  productionOverlays,
  viewport: _viewport,
  viewPreset: _viewPreset,
  reference: _reference,
  galaxyBounds: _galaxyBounds,
  labelSafeArea: _labelSafeArea,
  maxBackgroundPoints: _maxBackgroundPoints,
  onInteraction: _onInteraction,
  onZoomIntent: _onZoomIntent,
  onViewportSystemSelect: _onViewportSystemSelect,
  visible = true,
}: BabylonMapFoundationProps) {
  const sceneRef = useRef<BabylonMapSceneHandle | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Initialize Babylon scene
  const sceneConfig: MapSceneConfig = {
    worldScale: 1, // Match existing map scale
    canvasContainer: containerRef.current,
    cameraPosition: {
      x: scene.camera.center.x,
      y: 0, // Galactic plane (no vertical offset)
      z: scene.camera.center.z,
    },
    cameraZoomLy: scene.camera.zoom,
  };

  // Update camera when scene state changes
  useEffect(() => {
    if (!sceneRef.current) return;
    sceneRef.current.setCameraPosition(
      { x: scene.camera.center.x, y: 0, z: scene.camera.center.z },
      scene.camera.zoom,
    );
  }, [scene.camera.center.x, scene.camera.center.z, scene.camera.zoom]);

  // Update real-star systems when viewport systems change
  useEffect(() => {
    if (!sceneRef.current) return;
    const realStars = productionOverlays?.realStars ?? [];
    if (realStars.length > 0) {
      sceneRef.current.updateStars(realStars);
    }
    // Zoom update for density weighting
    sceneRef.current.updateZoom(scene.camera.zoom);
  }, [productionOverlays?.realStars, scene.camera.zoom]);

  return (
    <div
      ref={containerRef}
      className="babylon-map-foundation-renderer"
      style={{
        width: '100%',
        height: '100%',
        opacity: visible ? 1 : 0,
      }}
    >
      <BabylonMapScene
        sceneRef={sceneRef}
        config={sceneConfig}
        onSceneReady={() => {
          // Scene is ready, can start interactions
          if (sceneRef.current?.scene) {
            console.log('[BabylonMapFoundation] Scene ready');
          }
        }}
      />
    </div>
  );
}
