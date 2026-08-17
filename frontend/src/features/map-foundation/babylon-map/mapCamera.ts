import * as BABYLON from 'babylonjs';
import type { GameWorldPosition } from './types';
import { coordinateSystem } from './coordinateSystem';

/**
 * STUB for Task 4 (camera positioning, zoom, panning).
 *
 * This is a deliberately minimal placeholder so `BabylonMapScene` (Task 1)
 * has a working camera to render with. It does not implement Task 4's real
 * zoom/pan behavior -- do not build on top of this without re-reading Task 4
 * of docs/superpowers/plans/2026-08-16-babylon-js-map-redesign.md, which
 * replaces this file.
 */

const STUB_CAMERA_DISTANCE = 100;

export function setupMapCamera(
  scene: BABYLON.Scene,
  position: GameWorldPosition,
  worldScale: number,
): BABYLON.ArcRotateCamera {
  const target = coordinateSystem.gameTobabylon(position, worldScale);
  const camera = new BABYLON.ArcRotateCamera(
    'mapCamera',
    -Math.PI / 2,
    Math.PI / 2.5,
    STUB_CAMERA_DISTANCE,
    target,
    scene,
  );
  camera.attachControl(scene.getEngine().getRenderingCanvas(), true);
  return camera;
}

export function updateCameraPosition(
  camera: BABYLON.ArcRotateCamera,
  position: GameWorldPosition,
  worldScale: number,
  _zoomLy: number,
): void {
  // _zoomLy is unused by this stub; Task 4 will translate it into camera
  // radius/FOV. For now we only re-target the camera at the requested
  // game-world position so setCameraPosition() is at least functional.
  camera.target = coordinateSystem.gameTobabylon(position, worldScale);
}
