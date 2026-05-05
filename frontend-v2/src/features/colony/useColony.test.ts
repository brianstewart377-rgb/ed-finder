import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { renderHook as rh } from '@testing-library/react';
import { useColony, PHASES } from './useColony';

const baseEntry = {
  name:               'Test Outpost',
  phase:              'planning' as const,
  target_population:  100_000,
  current_population: null,
  notes:              '',
  id64:               null,
  x: null, y: null, z: null,
};

beforeEach(() => { localStorage.clear(); });

describe('useColony', () => {
  it('counts.total + per-phase reflect current entries', () => {
    const { result } = renderHook(() => useColony());
    expect(result.current.counts.total).toBe(0);

    let firstId = '';
    act(() => { firstId = result.current.add(baseEntry).id; });
    act(() => { result.current.add({ ...baseEntry, name: 'B', phase: 'building' }); });
    act(() => { result.current.add({ ...baseEntry, name: 'C', phase: 'active' }); });

    expect(result.current.counts.total).toBe(3);
    expect(result.current.counts.planning).toBe(1);
    expect(result.current.counts.building).toBe(1);
    expect(result.current.counts.active).toBe(1);
    expect(result.current.counts.complete).toBe(0);
    expect(firstId).toMatch(/^col-/);
  });

  it('update() patches fields and bumps updated_at', async () => {
    const { result } = renderHook(() => useColony());
    let id = '';
    act(() => { id = result.current.add(baseEntry).id; });
    const original = result.current.entries[0].updated_at;

    // Sleep a tick so the timestamp can actually advance.
    await new Promise((r) => setTimeout(r, 5));
    act(() => { result.current.update(id, { phase: 'complete', notes: 'shipped' }); });

    const e = result.current.entries[0];
    expect(e.phase).toBe('complete');
    expect(e.notes).toBe('shipped');
    expect(e.updated_at).not.toBe(original);
    expect(e.claimed_at).toBe(result.current.entries[0].claimed_at); // unchanged
  });

  it('PHASES const exposes all 4 phases in order', () => {
    expect(PHASES).toEqual(['planning', 'building', 'active', 'complete']);
  });

  it('persists across remounts', () => {
    const { result, unmount } = renderHook(() => useColony());
    act(() => { result.current.add(baseEntry); });
    unmount();
    const { result: again } = rh(() => useColony());
    expect(again.current.counts.total).toBe(1);
    expect(again.current.entries[0].name).toBe('Test Outpost');
  });
});
