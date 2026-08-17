import { useEffect, useRef } from 'react';
import * as BABYLON from 'babylonjs';
import type { MapViewportSystem } from '@/lib/api';
import type { BabylonMapSceneHandle, GameWorldPosition, MapSceneConfig } from './types';
import { setupMapCamera, updateCameraPosition } from './mapCamera';

export interface BabylonMapSceneProps {
  sceneRef: React.MutableRefObject<BabylonMapSceneHandle | null>;
  config: MapSceneConfig;
  onSceneReady?: (scene: BABYLON.Scene) => void;
}

/**
 * React wrapper for the Babylon.js scene lifecycle: owns the canvas, engine,
 * scene, and render loop, and exposes an imperative handle (`sceneRef`) for
 * the map feature to drive camera position and (in Task 2) star data without
 * re-rendering React on every frame.
 *
 * Real stars (`updateStars`) and galaxy particles are wired up in Tasks 2-3;
 * this task only establishes the scene, camera stub, and the handle surface.
 */
export function BabylonMapScene({ sceneRef, config, onSceneReady }: BabylonMapSceneProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // Initialize scene on mount
  useEffect(() => {
    if (!canvasRef.current) return;

    let engine: BABYLON.Engine | null = null;
    let scene: BABYLON.Scene | null = null;

    try {
      engine = new BABYLON.Engine(canvasRef.current, true, {
        antialias: true,
        preserveDrawingBuffer: false,
        stencil: true,
      });

      scene = new BABYLON.Scene(engine);
      scene.clearColor = new BABYLON.Color4(0, 0, 0, 1);

      const camera = setupMapCamera(scene, config.cameraPosition, config.worldScale);

      const currentZoomRef = { current: config.cameraZoomLy };

      const handle: BabylonMapSceneHandle = {
        scene,
        engine,
        dispose: () => {
          scene?.dispose();
          engine?.dispose();
        },
        setCameraPosition: (pos: GameWorldPosition, zoomLy: number) => {
          updateCameraPosition(camera, pos, config.worldScale, zoomLy);
          currentZoomRef.current = zoomLy;
        },
        setWorldScale: (_scale: number) => {
          // World scale is fixed at scene-init time; changing it would require
          // re-transforming every existing mesh. Not supported yet -- revisit
          // if a future task needs live rescaling.
          console.warn('BabylonMapScene.setWorldScale: not supported after scene initialization');
        },
        updateStars: (_systems: MapViewportSystem[]) => {
          // Implemented in Task 2 (starsLayer.ts) with density/zoom weighting.
          // Guard against the Task 1 -> Task 2 handoff race: callers must not
          // touch the scene before Babylon reports it ready.
          if (!scene || !scene.isReady()) return;
        },
        updateZoom: (zoomLy: number) => {
          // Re-applied to stars/particles once Task 2/3 land; for now this
          // only tracks the current zoom level for future LOD weighting.
          currentZoomRef.current = zoomLy;
        },
      };

      sceneRef.current = handle;
      onSceneReady?.(scene);

      // Render loop
      engine.runRenderLoop(() => {
        scene?.render();
      });
    } catch (error) {
      console.error('Failed to initialize Babylon.js scene:', error);
    }

    // Handle window resize
    const onWindowResize = () => {
      engine?.resize();
    };
    window.addEventListener('resize', onWindowResize);

    return () => {
      window.removeEventListener('resize', onWindowResize);
      sceneRef.current?.dispose();
      sceneRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sceneRef, onSceneReady]);

  return (
    <canvas
      ref={canvasRef}
      style={{
        width: '100%',
        height: '100%',
        display: 'block',
      }}
    />
  );
}
