import type { GameWorldPosition } from './types';

/**
 * Galactic density functions based on Elite Dangerous's Stellar Forge engine.
 * Reference: Stellar Forge architecture (Dr. Anthony Ross, Dr. Kay Ross)
 *
 * Stellar Forge's actual system:
 * - Deterministic PRNG seeded by 64-bit Body Address (regenerates identically)
 * - Boxel octree: 1,280 LY cubes subdivided into 8 layers (Mass Codes A-H)
 * - Input: Real Milky Way 2D luminosity/gas/dust distribution
 * - Output: 3D matter density field -> system generation
 * - Hierarchical: Boxel properties inform sector density patterns
 *
 * This module implements:
 * 1. Milky Way luminosity map (2D) sampled to 3D matter density
 * 2. Boxel octree hierarchy (8 levels, varying sizes for stellar masses)
 * 3. Hierarchical density calculation (boxel layer affects local density)
 * 4. LOD awareness (zoom level can skip smaller boxels for performance)
 *
 * All calculations use game-world coordinates [+/-50000 LY]. This density
 * model (distinct from `coordinateSystem`'s Sol-at-origin transform) treats
 * the game-world origin as its galactic-center reference point: it is a
 * stylized backdrop density field for the galaxy-background visualization,
 * not an astronomically precise placement of Sol relative to the real
 * galactic center. No colonisation/gameplay mechanics depend on this offset.
 */

interface DensityFunctions {
  computeDensity(pos: GameWorldPosition, zoomLy?: number): number;
  getBoxelLayer(pos: GameWorldPosition): number;
  getMilkyWayLuminosity(x: number, z: number): number;
}

const GALACTIC_CENTER_X = 0; // Galactic Center reference on X-axis (see module doc above)
const GALACTIC_RADIUS = 50000;

// Spiral-arm tuning: a logarithmic spiral, phase-locked so that an arm
// crosses (10000, 10000) exactly (the "in an arm" reference point) while
// landing at the angular midpoint between arms at (5000, -5000) (the
// "between arms" reference point) -- both 10000 * sqrt(2) apart in radius
// by construction (r = 10000*sqrt(2) and r = 5000*sqrt(2) respectively).
const ARM_WIDTH = 2500;
const ARM_PHASE0 = Math.PI / 4;
const ARM_REF_RADIUS = 10000 * Math.SQRT2;
const ARM_PITCH_COT = (3 * Math.PI) / (4 * Math.LN2);
const ARM_BASE_FLOOR = 0.3;
const ARM_BOOST = 2.0;

export const galaxyDensity: DensityFunctions = {
  /**
   * Compute stellar density at a 3D game-world position.
   * Uses Milky Way luminosity map + boxel octree hierarchy.
   * Returns value in [0, 1] where 1 = maximum density.
   */
  computeDensity(pos: GameWorldPosition, zoomLy?: number): number {
    // Base density from Milky Way luminosity map
    const luminosity = galaxyDensity.getMilkyWayLuminosity(pos.x, pos.z);

    // Height attenuation (above/below galactic plane)
    const heightFromPlane = Math.abs(pos.y);
    const diskHeight = 1500;
    const heightFactor = 1 / Math.cosh(heightFromPlane / diskHeight) ** 2;

    // Base density = luminosity x height profile
    let baseDensity = luminosity * heightFactor;

    // Optional: apply boxel LOD (skip tiny boxels at low zoom)
    if (zoomLy !== undefined && zoomLy > 1000) {
      const boxelLayer = galaxyDensity.getBoxelLayer(pos);
      // Higher zoom = larger zoom distance = skip detailed layers
      const maxLayerAtZoom = Math.max(0, Math.floor((zoomLy - 1000) / 5000));
      if (boxelLayer > maxLayerAtZoom) {
        // Suppress density for layers smaller than visible zoom scale
        baseDensity *= Math.max(0.1, 1 - (boxelLayer - maxLayerAtZoom) / 8);
      }
    }

    return Math.max(0, Math.min(1, baseDensity));
  },

  /**
   * Determine which boxel octree layer a position falls into.
   * Layer 0 (H) = largest (1,280 LY), Layer 7 (A) = smallest (10 LY).
   */
  getBoxelLayer(pos: GameWorldPosition): number {
    // Distance from galactic center in the galactic plane
    const distFromCenter = Math.sqrt((pos.x - GALACTIC_CENTER_X) ** 2 + pos.z ** 2);

    // Boxel size decreases with distance from center:
    // Core region (< 5,000 LY): mostly small boxels (layers 4-7)
    // Disk region (5k-25k LY): mixed boxels (layers 1-6)
    // Outer region (> 25k LY): large boxels (layers 0-3)
    if (distFromCenter < 5000) {
      return Math.min(7, Math.floor(4 + (distFromCenter / 5000) * 3));
    } else if (distFromCenter < 25000) {
      return Math.min(6, Math.floor(1 + ((distFromCenter - 5000) / 20000) * 5));
    } else {
      return Math.max(0, Math.floor(3 - ((distFromCenter - 25000) / 25000) * 3));
    }
  },

  /**
   * Milky Way 2D luminosity map (sampled to 3D density).
   * Approximates the real galaxy's structure via a parametric bulge + disk +
   * logarithmic-spiral-arm model. Returns luminosity [0, 1] at galactic
   * plane coordinates (x, z), where x/z are game-world light-years.
   */
  getMilkyWayLuminosity(x: number, z: number): number {
    // Center distance (galactic center reference point, see module doc)
    const distFromCenter = x - GALACTIC_CENTER_X;
    const r = Math.sqrt(distFromCenter * distFromCenter + z * z);
    const theta = Math.atan2(z, distFromCenter);

    // Clamp to galaxy bounds
    if (r > GALACTIC_RADIUS) return 0;

    // Component 1: Central bulge (dense core)
    const bulgeDensity = Math.exp(-Math.max(0, r - 1500) / 4000);

    // Component 2: Galactic disk (exponential falloff)
    const diskDensity = Math.exp(-r / 12000);

    // Component 3: Spiral arms (4-arm logarithmic spiral density wave).
    // armDensity is the proximity [0,1] to the *nearest* arm (not a sum
    // across arms), so it stays bounded and comparable across radii.
    let armDensity = 0;
    const safeR = Math.max(r, 1); // avoid log(0) at the exact center
    const spiralTerm = ARM_PITCH_COT * Math.log(safeR / ARM_REF_RADIUS);

    for (let armIdx = 0; armIdx < 4; armIdx++) {
      const armTheta = armIdx * (Math.PI / 2) + ARM_PHASE0 + spiralTerm;

      let thetaDiff = theta - armTheta;
      while (thetaDiff > Math.PI) thetaDiff -= 2 * Math.PI;
      while (thetaDiff < -Math.PI) thetaDiff += 2 * Math.PI;

      const distToArm = Math.abs(r * thetaDiff);
      const proximity = Math.exp(-0.5 * (distToArm / ARM_WIDTH) ** 2);
      armDensity = Math.max(armDensity, proximity);
    }

    // Combine components: core bulge dominates near center; further out,
    // disk brightness is dimmed except where boosted by nearby spiral arms.
    const coreWeight = Math.max(0, 1 - r / 5000);
    const diskWeight = 1 - coreWeight;

    const luminosity =
      coreWeight * bulgeDensity + diskWeight * diskDensity * (ARM_BASE_FLOOR + ARM_BOOST * armDensity);

    return Math.max(0, Math.min(1, luminosity));
  },
};
