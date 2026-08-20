import { useEffect, useRef } from 'react';
import * as BABYLON from 'babylonjs';
import type { MapViewportSystem } from '@/lib/api';
import type { BabylonMapSceneHandle, GameWorldPosition, MapSceneConfig } from './types';
import { setupMapCamera, updateCameraPosition } from './mapCamera';
import { createStarsLayer, updateStarsLayer } from './starsLayer';

export interface BabylonMapSceneProps {
  sceneRef: React.MutableRefObject<BabylonMapSceneHandle | null>;
  config: MapSceneConfig;
  onSceneReady?: (scene: BABYLON.Scene) => void;
}

/**
 * React wrapper for the Babylon.js scene lifecycle: owns the canvas, engine,
 * scene, and render loop, and exposes an imperative handle (`sceneRef`) for
 * the map feature to drive camera position and star data without
 * re-rendering React on every frame.
 *
 * Real stars (`updateStars`/`updateZoom`, backed by `starsLayer.ts`) are
 * wired up as of Task 2. Galaxy background particles are still Task 3.
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

      // Owned by this effect's closure, not React state: the render loop and
      // imperative handle methods below run outside React's render cycle, so
      // stars/layer state lives here rather than in a ref that would need a
      // re-render to update. `lastSystems` lets `updateZoom` re-weight the
      // existing star batch (density/LOD) without the caller having to
      // re-supply the systems array on every zoom change.
      let starsLayerMesh: BABYLON.Mesh | null = null;
      let lastSystems: MapViewportSystem[] = [];

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
        updateStars: (systems: MapViewportSystem[]) => {
          // Guard against the Task 1 -> Task 2 handoff race: callers must not
          // touch the scene before Babylon reports it ready.
          if (!scene || !scene.isReady()) return;

          lastSystems = systems;
          const options = { densityWeighting: true, zoomLy: currentZoomRef.current };

          if (starsLayerMesh) {
            updateStarsLayer(starsLayerMesh, systems, config.worldScale, options);
          } else {
            starsLayerMesh = createStarsLayer(scene, systems, config.worldScale, options);
          }
        },
        updateZoom: (zoomLy: number) => {
          currentZoomRef.current = zoomLy;

          // Re-apply density/LOD weighting to the existing star batch. Do
          // NOT call updateStars([]) here -- that would wipe the layer,
          // since [] is indistinguishable from "no stars in viewport".
          if (!scene || !scene.isReady() || !starsLayerMesh) return;
          updateStarsLayer(starsLayerMesh, lastSystems, config.worldScale, {
            densityWeighting: true,
            zoomLy,
          });
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
