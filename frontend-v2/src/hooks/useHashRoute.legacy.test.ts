import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { useHashRoute } from './useHashRoute';

afterEach(() => {
  window.location.hash = '';
});

describe('useHashRoute legacy compatibility', () => {
  it('parses legacy optimizer system links as Advanced Search Tuning Inspect routes', () => {
    window.location.hash = '#optimizer/system/123456';
    const { result } = renderHook(() => useHashRoute());
    expect(result.current.route).toBe('search-tuning');
    expect(result.current.selectedSystemId).toBe(123456);
    expect(result.current.contextSystemId).toBe(123456);
  });

  it('navigates to an empty Planner workspace without inventing selected context', () => {
    window.location.hash = '#finder';
    const { result } = renderHook(() => useHashRoute());
    act(() => result.current.navigate('colony-planner'));
    expect(window.location.hash).toBe('#colony-planner');
  });

  it('preserves a Planner route when navigating to Planner again', () => {
    window.location.hash = '#colony-planner/system/123456';
    const { result } = renderHook(() => useHashRoute());
    act(() => result.current.navigate('colony-planner'));
    expect(window.location.hash).toBe('#colony-planner/system/123456');
  });

  it('opens Inspect from Planner through the Finder modal route', () => {
    window.location.hash = '#colony-planner/system/123456';
    const { result } = renderHook(() => useHashRoute());
    act(() => result.current.openSystem(123456));
    expect(window.location.hash).toBe('#finder/system/123456');
  });

  it('does not mutate a Planner route when closing a non-existent modal', () => {
    window.location.hash = '#colony-planner/system/123456';
    const { result } = renderHook(() => useHashRoute());
    act(() => result.current.closeSystem());
    expect(window.location.hash).toBe('#colony-planner/system/123456');
  });

  it('navigates to the preferred search tuning hash', () => {
    window.location.hash = '#finder';
    const { result } = renderHook(() => useHashRoute());
    act(() => result.current.navigate('search-tuning'));
    expect(window.location.hash).toBe('#search-tuning');
  });
});
