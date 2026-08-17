import * as BABYLON from 'babylonjs';
import type { MapViewportSystem } from '@/lib/api';

/**
 * A position in Elite Dangerous game-world coordinates.
 * Cartesian [X, Y, Z] light-years, Sol at origin.
 */
export interface GameWorldPosition {
  x: number; // light-years
  y: number; // light-years
  z: number; // light-years
}

/**
 * A position in Babylon.js world-space (post coordinate-transform, pre worldScale
 * inverse). Distinct from BABYLON.Vector3 to keep the transform boundary explicit
 * and testable without pulling the Babylon runtime into plain data shapes.
 */
export interface BabylonWorldPosition {
  x: number;
  y: number;
  z: number;
}

export interface MapSceneConfig {
  worldScale: number; // light-years per Babylon world unit
  canvasContainer: HTMLElement | null;
  cameraPosition: GameWorldPosition;
  cameraZoomLy: number; // light-years per pixel on screen
}

export interface BabylonMapSceneHandle {
  scene: BABYLON.Scene | null;
  engine: BABYLON.Engine | null;
  dispose: () => void;
  setCameraPosition: (pos: GameWorldPosition, zoomLy: number) => void;
  setWorldScale: (scale: number) => void;
  updateStars: (systems: MapViewportSystem[]) => void;
  updateZoom: (zoomLy: number) => void; // Re-apply LOD weighting on zoom change
}

export interface CoordinateTransform {
  gameTobabylon: (pos: GameWorldPosition, scale: number) => BABYLON.Vector3;
  babylonToGame: (vec: BABYLON.Vector3, scale: number) => GameWorldPosition;
}
