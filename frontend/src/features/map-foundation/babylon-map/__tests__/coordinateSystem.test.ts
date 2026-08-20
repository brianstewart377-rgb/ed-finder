import { describe, it, expect } from 'vitest';
import { coordinateSystem } from '../coordinateSystem';

describe('coordinateSystem', () => {
  it('transforms Sol [0,0,0] to Babylon origin', () => {
    const sol = { x: 0, y: 0, z: 0 };
    const babylon = coordinateSystem.gameTobabylon(sol, 1);
    expect(babylon.x).toBe(0);
    expect(babylon.y).toBe(0);
    expect(babylon.z).toBe(0);
  });

  it('transforms Elite coords (x,y,z) to Babylon (x,z,y)', () => {
    const star = { x: 1000, y: 500, z: 2000 };
    const babylon = coordinateSystem.gameTobabylon(star, 1);
    // ED (x,y,z) → Babylon (x,z,y)
    expect(babylon.x).toBe(1000);
    expect(babylon.y).toBe(2000);
    expect(babylon.z).toBe(500);
  });

  it('applies worldScale correctly', () => {
    const star = { x: 1000, y: 500, z: 2000 };
    const babylon = coordinateSystem.gameTobabylon(star, 0.001); // 1 unit = 1000 LY
    expect(babylon.x).toBe(1); // 1000 * 0.001
    expect(babylon.y).toBe(2);
    expect(babylon.z).toBe(0.5);
  });

  it('round-trips gameTobabylon and babylonToGame', () => {
    const original = { x: 12345, y: 6789, z: 54321 };
    const scale = 0.01;
    const babylon = coordinateSystem.gameTobabylon(original, scale);
    const recovered = coordinateSystem.babylonToGame(babylon, scale);
    expect(recovered.x).toBeCloseTo(original.x, 5);
    expect(recovered.y).toBeCloseTo(original.y, 5);
    expect(recovered.z).toBeCloseTo(original.z, 5);
  });

  it('handles negative coordinates (galactic center)', () => {
    const galacticCenter = { x: -25000, y: 0, z: 0 };
    const babylon = coordinateSystem.gameTobabylon(galacticCenter, 1);
    expect(babylon.x).toBe(-25000);
    expect(babylon.y).toBe(0);
    expect(babylon.z).toBe(0);
  });

  it('babylonToGame with scale 0 falls back to identity instead of dividing by zero', () => {
    const vec = { x: 3, y: 5, z: 7 } as unknown as import('babylonjs').Vector3;
    const recovered = coordinateSystem.babylonToGame(vec, 0);
    expect(recovered.x).toBe(3);
    expect(recovered.y).toBe(7);
    expect(recovered.z).toBe(5);
  });
});
