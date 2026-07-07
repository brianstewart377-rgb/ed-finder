import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useCompare, COMPARE_MAX } from './useCompare';
import type { SystemResult } from '@/types/api';

const mk = (id64: number, name: string): SystemResult => ({
  id64, name, population: 0,
  coords: { x: 0, y: 0, z: 0 },
});

beforeEach(() => { localStorage.clear(); });

describe('useCompare', () => {
  it('starts empty and toggles add/remove', () => {
    const { result } = renderHook(() => useCompare());
    expect(result.current.entries).toHaveLength(0);

    let addedOk = false;
    act(() => { addedOk = result.current.toggle(mk(1, 'A')); });
    expect(addedOk).toBe(true);
    expect(result.current.has(1)).toBe(true);

    let removed = false;
    act(() => { removed = result.current.toggle(mk(1, 'A')); });
    expect(removed).toBe(false);
    expect(result.current.has(1)).toBe(false);
  });

  it(`enforces the ${COMPARE_MAX}-system cap with a transient error`, () => {
    const { result } = renderHook(() => useCompare());
    for (let i = 1; i <= COMPARE_MAX; i++) {
      act(() => { result.current.toggle(mk(i, `S${i}`)); });
    }
    expect(result.current.entries).toHaveLength(COMPARE_MAX);

    let resp = true;
    act(() => { resp = result.current.toggle(mk(99, 'Overflow')); });
    expect(resp).toBe(false);                         // refused
    expect(result.current.entries).toHaveLength(COMPARE_MAX);
    expect(result.current.lastError).toMatch(/full/i);

    act(() => { result.current.clearError(); });
    expect(result.current.lastError).toBeNull();
  });

  it('persists across hook re-mounts via localStorage', () => {
    const { result, unmount } = renderHook(() => useCompare());
    act(() => { result.current.toggle(mk(42, 'Persisted')); });
    unmount();

    const { result: again } = renderHook(() => useCompare());
    expect(again.current.entries).toHaveLength(1);
    expect(again.current.entries[0].id64).toBe(42);
  });

  it('clear() empties the list and resets error', () => {
    const { result } = renderHook(() => useCompare());
    act(() => { result.current.toggle(mk(1, 'A')); });
    act(() => { result.current.toggle(mk(2, 'B')); });
    expect(result.current.entries).toHaveLength(2);

    act(() => { result.current.clear(); });
    expect(result.current.entries).toHaveLength(0);
    expect(result.current.lastError).toBeNull();
  });
});
