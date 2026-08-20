import * as BABYLON from 'babylonjs';
import type { GameWorldPosition, CoordinateTransform } from './types';

/**
 * Explicit game-world <-> Babylon.js coordinate transforms.
 *
 * Elite Dangerous uses a Cartesian [X, Y, Z] light-year coordinate system with
 * Sol at the origin. Babylon.js uses a left-handed Y-up coordinate system by
 * default. We map ED's Y (galactic "up") onto Babylon's Z axis, and ED's Z
 * (galactic "forward") onto Babylon's Y axis, so that Babylon's Y stays "up"
 * on screen while X/Z remain the horizontal galactic plane.
 *
 * ED (x, y, z) -> Babylon (x, z, y)
 *
 * `scale` is light-years per Babylon world unit's inverse, i.e. it converts
 * game-world light-years into Babylon world units (Babylon units = LY * scale).
 * No implicit matrix magic: every transform is explicit and unit-tested.
 */
export const coordinateSystem: CoordinateTransform = {
  gameTobabylon: (pos: GameWorldPosition, scale: number): BABYLON.Vector3 => {
    // Elite Dangerous (x, y, z) -> Babylon (x, z, y)
    // Apply worldScale: game-world light-years -> Babylon units
    return new BABYLON.Vector3(pos.x * scale, pos.z * scale, pos.y * scale);
  },

  babylonToGame: (vec: BABYLON.Vector3, scale: number): GameWorldPosition => {
    // Babylon (x, z, y) -> Elite Dangerous (x, y, z)
    // Guard against divide-by-zero: an unset/zero scale is treated as identity
    // rather than producing Infinity/NaN positions.
    const invScale = scale === 0 ? 1 : 1 / scale;
    return {
      x: vec.x * invScale,
      y: vec.z * invScale,
      z: vec.y * invScale,
    };
  },
};
