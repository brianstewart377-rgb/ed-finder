import { describe, it, expect } from 'vitest';
import { useFcPlanner } from './useFcPlanner';
import { renderHook, act } from '@testing-library/react';

// Lightweight tests of the pure FC route maths, plus the hook's basic
// state-machine semantics. No DOM/network — just verify our arithmetic.
//
// We import the hook (not the unexported `computeRoute`) so the tests
// also exercise the persistence + mutation API, which is what every
// real call site uses.

const SOL    = { name: 'Sol',    x: 0,    y: 0,     z: 0,    id64: null };
const SIRIUS = { name: 'Sirius', x: 6.25, y: -1.28, z: -5.75, id64: null };
const COLONIA = { name: 'Colonia', x: -9530, y: -910, z: 19808, id64: null };

describe('useFcPlanner.route', () => {
  it('returns zeros for an empty plan', () => {
    localStorage.clear();
    const { result } = renderHook(() => useFcPlanner());
    expect(result.current.waypoints).toHaveLength(0);
    expect(result.current.route.legs).toHaveLength(0);
    expect(result.current.route.total_distance_ly).toBe(0);
    expect(result.current.route.total_hops).toBe(0);
  });

  it('computes a single short leg correctly (Sol → Sirius, ~8.6 LY)', () => {
    localStorage.clear();
    const { result } = renderHook(() => useFcPlanner());
    act(() => { result.current.add(SOL); });
    act(() => { result.current.add(SIRIUS); });

    const r = result.current.route;
    expect(r.legs).toHaveLength(1);
    expect(r.legs[0].distance_ly).toBeCloseTo(8.6, 1);
    expect(r.legs[0].hops).toBe(1);                      // ceil(8.6/500) = 1
    expect(r.legs[0].tritium_t).toBe(50);                // 1 hop × 50 t/hop
    expect(r.total_cost_cr).toBe(50 * 50_000);           // 50 t × 50k cr/t
    expect(r.cargo_trips).toBe(1);                       // ceil(50 / 25_000) = 1
    expect(r.missing_coord_names).toEqual([]);
  });

  it('computes a long leg requiring multiple hops (Sol → Colonia, ~22 kLY)', () => {
    localStorage.clear();
    const { result } = renderHook(() => useFcPlanner());
    act(() => { result.current.add(SOL); });
    act(() => { result.current.add(COLONIA); });

    const r = result.current.route;
    // Real distance is ~22,000 LY; with 500 LY range that's 44 hops.
    expect(r.legs[0].hops).toBeGreaterThanOrEqual(44);
    expect(r.legs[0].tritium_t).toBeGreaterThan(2000);
    expect(r.cargo_trips).toBeGreaterThanOrEqual(1);
  });

  it('flags waypoints with missing coords and excludes them from totals', () => {
    localStorage.clear();
    const { result } = renderHook(() => useFcPlanner());
    act(() => { result.current.add(SOL); });
    act(() => { result.current.add({ name: 'Beagle Point', x: null, y: null, z: null, id64: null }); });

    const r = result.current.route;
    expect(r.legs).toHaveLength(1);
    expect(r.legs[0].distance_ly).toBeNull();
    expect(r.legs[0].hops).toBeNull();
    expect(r.total_distance_ly).toBe(0);
    expect(r.missing_coord_names).toContain('Beagle Point');
  });

  it('honours config changes — halving jump-range roughly doubles hops', () => {
    localStorage.clear();
    const { result } = renderHook(() => useFcPlanner());
    act(() => { result.current.add(SOL); });
    act(() => { result.current.add(COLONIA); });

    const hopsAt500 = result.current.route.total_hops;
    act(() => { result.current.setConfig({ jump_range_ly: 250 }); });
    const hopsAt250 = result.current.route.total_hops;

    // Not exactly 2× because of ceiling boundaries on the per-leg integer
    // hop count, but it should be within ±5% of double.
    expect(hopsAt250).toBeGreaterThan(hopsAt500 * 1.95);
    expect(hopsAt250).toBeLessThan(hopsAt500 * 2.05);
  });

  it('move() reorders waypoints in place', () => {
    localStorage.clear();
    const { result } = renderHook(() => useFcPlanner());
    act(() => { result.current.add(SOL); });
    act(() => { result.current.add(SIRIUS); });
    act(() => { result.current.add(COLONIA); });

    const idMid = result.current.waypoints[1].id;
    act(() => { result.current.move(idMid, -1); });
    expect(result.current.waypoints.map((w) => w.name))
      .toEqual(['Sirius', 'Sol', 'Colonia']);
  });
});
