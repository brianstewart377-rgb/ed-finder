import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { useHashRoute } from './useHashRoute';

afterEach(() => {
  window.location.hash = '';
});

describe('useHashRoute route parsing', () => {
  it.each([
    ['#finder', 'finder', null],
    ['#watchlist', 'my-work', 'watchlist'],
    ['#pinned', 'my-work', 'pinned'],
    ['#compare', 'compare', null],
    ['#map', 'map', null],
    ['#search-tuning', 'search-tuning', null],
    ['#fc', 'fc', null],
    ['#colony', 'my-work', 'colony'],
    ['#admin', 'admin', null],
    ['#operator', 'operator', null],
    ['#colony-planner', 'colony-planner', null],
  ] as const)('parses %s as %s', (hash, route, routeAlias) => {
    window.location.hash = hash;

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe(route);
    expect(result.current.routeAlias).toBe(routeAlias);
    expect(result.current.selectedSystemId).toBeNull();
    expect(result.current.plannerSystemId).toBeNull();
  });

  it('parses #search-tuning as the preferred Development Tuning route', () => {
    window.location.hash = '#search-tuning';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('search-tuning');
    expect(result.current.routeAlias).toBeNull();
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

  it('parses planner-owned detail routes without losing workspace context', () => {
    window.location.hash = '#colony-planner/system/123456/project/draft-1/mode/sequence/detail/654321';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('colony-planner');
    expect(result.current.plannerSystemId).toBe(123456);
    expect(result.current.plannerProjectId).toBe('draft-1');
    expect(result.current.plannerMode).toBe('sequence');
    expect(result.current.selectedSystemId).toBe(654321);
  });

  it('parses planner cockpit mode routes for direct Colony Planner deep links', () => {
    window.location.hash = '#colony-planner/system/123456/mode/export';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('colony-planner');
    expect(result.current.plannerSystemId).toBe(123456);
    expect(result.current.plannerMode).toBe('export');
    expect(result.current.selectedSystemId).toBeNull();
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

  it('opens the dedicated Colony Planner workspace with an explicit cockpit mode', () => {
    window.location.hash = '#finder';
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      result.current.openColonyPlanner(123456, { mode: 'validation' });
    });

    expect(window.location.hash).toBe('#colony-planner/system/123456/mode/validation');
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
    window.location.hash = '#colony-planner/system/123456/project/draft-1/mode/evidence';
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      result.current.navigate('colony-planner');
    });

    expect(window.location.hash).toBe('#colony-planner/system/123456/project/draft-1/mode/evidence');
    expect(result.current.selectedSystemId).toBeNull();
  });

  it('falls back to Finder for unknown routes', () => {
    window.location.hash = '#does-not-exist';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('finder');
    expect(result.current.selectedSystemId).toBeNull();
    expect(result.current.plannerSystemId).toBeNull();
  });

  it('treats legacy #optimizer links as unknown routes after alias retirement', () => {
    window.location.hash = '#optimizer';

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

  it('keeps openSystem as a planner-owned detail route from the Colony Planner workspace', () => {
    window.location.hash = '#colony-planner/system/123456/mode/sequence';
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      result.current.openSystem(123456);
    });

    expect(window.location.hash).toBe('#colony-planner/system/123456/mode/sequence/detail/123456');
  });

  it('allows planner flows to open system detail under an explicit planning host route', () => {
    window.location.hash = '#colony-planner/system/123456/mode/evidence';
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      result.current.openSystem(123456, { hostRoute: 'colony-planner' });
    });

    expect(window.location.hash).toBe('#colony-planner/system/123456/mode/evidence/detail/123456');
  });

  it('closes planner-owned detail back to the planner workspace route', () => {
    window.location.hash = '#colony-planner/system/123456/project/draft-1/mode/validation/detail/987654';
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      result.current.closeSystem();
    });

    expect(window.location.hash).toBe('#colony-planner/system/123456/project/draft-1/mode/validation');
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
