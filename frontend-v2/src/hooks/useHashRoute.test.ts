import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { useHashRoute } from './useHashRoute';

afterEach(() => {
  window.location.hash = '';
});

describe('useHashRoute Advanced Search Tuning aliases', () => {
  it.each([
    ['#finder', 'finder'],
    ['#watchlist', 'watchlist'],
    ['#pinned', 'pinned'],
    ['#compare', 'compare'],
    ['#map', 'map'],
    ['#search-tuning', 'search-tuning'],
    ['#fc', 'fc'],
    ['#colony', 'colony'],
    ['#admin', 'admin'],
    ['#colony-planner', 'colony-planner'],
  ] as const)('parses %s as %s', (hash, route) => {
    window.location.hash = hash;

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe(route);
    expect(result.current.selectedSystemId).toBeNull();
    expect(result.current.plannerSystemId).toBeNull();
  });

  it('parses #search-tuning as the preferred Advanced Search Tuning route', () => {
    window.location.hash = '#search-tuning';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('search-tuning');
    expect(result.current.selectedSystemId).toBeNull();
    expect(result.current.plannerSystemId).toBeNull();
  });

  it('normalizes #optimizer as the legacy Advanced Search Tuning alias', () => {
    window.location.hash = '#optimizer';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('search-tuning');
    expect(result.current.selectedSystemId).toBeNull();
    expect(result.current.plannerSystemId).toBeNull();
  });

  it('parses child system modal routes without changing the parent tab', () => {
    window.location.hash = '#compare/system/123456';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('compare');
    expect(result.current.selectedSystemId).toBe(123456);
    expect(result.current.plannerSystemId).toBeNull();
  });

  it('parses legacy #optimizer/system links as Advanced Search Tuning modal routes', () => {
    window.location.hash = '#optimizer/system/123456';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('search-tuning');
    expect(result.current.selectedSystemId).toBe(123456);
    expect(result.current.plannerSystemId).toBeNull();
  });

  it('parses external #system links as Finder modal routes', () => {
    window.location.hash = '#system/123456';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('finder');
    expect(result.current.selectedSystemId).toBe(123456);
    expect(result.current.plannerSystemId).toBeNull();
  });

  it('parses dedicated Colony Planner workspace routes separately from modal routes', () => {
    window.location.hash = '#colony-planner/system/123456';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('colony-planner');
    expect(result.current.selectedSystemId).toBeNull();
    expect(result.current.plannerSystemId).toBe(123456);
  });

  it.each(['#colony-planner', '#colony-planner/system/not-a-number', '#colony-planner/system/0'])(
    'keeps invalid Colony Planner workspace routes on the workspace route for %s',
    (hash) => {
      window.location.hash = hash;

      const { result } = renderHook(() => useHashRoute());

      expect(result.current.route).toBe('colony-planner');
      expect(result.current.selectedSystemId).toBeNull();
      expect(result.current.plannerSystemId).toBeNull();
    },
  );

  it('opens the dedicated Colony Planner workspace without setting modal state', () => {
    window.location.hash = '#finder';
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      result.current.openColonyPlanner(123456);
    });

    expect(window.location.hash).toBe('#colony-planner/system/123456');
  });

  it('navigates to an empty Colony Planner workspace when no planner system is selected', () => {
    window.location.hash = '#finder';
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      result.current.navigate('colony-planner');
    });

    expect(window.location.hash).toBe('#colony-planner');
  });

  it('preserves the active planner system when navigating back to Colony Planner', () => {
    window.location.hash = '#colony-planner/system/123456';
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      result.current.navigate('colony-planner');
    });

    expect(window.location.hash).toBe('#colony-planner/system/123456');
    expect(result.current.selectedSystemId).toBeNull();
  });

  it('falls back to Finder for unknown routes', () => {
    window.location.hash = '#does-not-exist';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('finder');
    expect(result.current.selectedSystemId).toBeNull();
    expect(result.current.plannerSystemId).toBeNull();
  });

  it('closes a modal back to the current tab route', () => {
    window.location.hash = '#map/system/123456';
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      result.current.closeSystem();
    });

    expect(window.location.hash).toBe('#map');
  });

  it('keeps openSystem as a modal route even from the Colony Planner workspace', () => {
    window.location.hash = '#colony-planner/system/123456';
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      result.current.openSystem(123456);
    });

    expect(window.location.hash).toBe('#finder/system/123456');
  });

  it('keeps closeSystem from mutating the Colony Planner workspace route', () => {
    window.location.hash = '#colony-planner/system/123456';
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      result.current.closeSystem();
    });

    expect(window.location.hash).toBe('#colony-planner/system/123456');
  });

  it('navigates to the preferred #search-tuning route', () => {
    window.location.hash = '#finder';
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      result.current.navigate('search-tuning');
    });

    expect(window.location.hash).toBe('#search-tuning');
  });
});
