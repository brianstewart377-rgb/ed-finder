import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { useHashRoute } from './useHashRoute';

afterEach(() => {
  window.location.hash = '';
});

describe('useHashRoute Advanced Search Tuning aliases', () => {
  function dispatchHash(hash: string) {
    window.location.hash = hash;
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  }

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
    ['#operator', 'operator'],
    ['#colony-planner', 'colony-planner'],
    ['#colony-planner-prototype', 'colony-planner-prototype'],
  ] as const)('parses %s as %s', (hash, route) => {
    window.location.hash = hash;

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe(route);
    expect(result.current.contextSystemId).toBeNull();
    expect(result.current.selectedSystemId).toBeNull();
    expect(result.current.plannerSystemId).toBeNull();
  });

  it('parses #search-tuning as the preferred Advanced Search Tuning route', () => {
    window.location.hash = '#search-tuning';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('search-tuning');
    expect(result.current.contextSystemId).toBeNull();
    expect(result.current.selectedSystemId).toBeNull();
    expect(result.current.plannerSystemId).toBeNull();
  });

  it('normalizes #optimizer as the legacy Advanced Search Tuning alias', () => {
    window.location.hash = '#optimizer';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('search-tuning');
    expect(result.current.contextSystemId).toBeNull();
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
    expect(result.current.contextSystemId).toBe(123456);
    expect(result.current.selectedSystemId).toBe(123456);
    expect(result.current.plannerSystemId).toBeNull();
  });

  it('parses non-modal Finder context routes separately from modal inspection', () => {
    window.location.hash = '#finder/context/123456';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('finder');
    expect(result.current.contextSystemId).toBe(123456);
    expect(result.current.selectedSystemId).toBeNull();
    expect(result.current.plannerSystemId).toBeNull();
  });

  it.each([
    ['#finder/context', null, null],
    ['#finder/context/not-a-number', null, null],
    ['#finder/context/123456/extra', 123456, null],
    ['#finder/system', null, null],
    ['#finder/system/not-a-number', null, null],
    ['#finder/system/123456/extra', 123456, 123456],
    ['#system', null, null],
    ['#system/not-a-number', null, null],
    ['#system/123456/extra', 123456, 123456],
  ] as const)('marks malformed Finder selected-system routes invalid for %s', (hash, contextId, selectedId) => {
    window.location.hash = hash;

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('finder');
    expect(result.current.contextSystemId).toBe(contextId);
    expect(result.current.selectedSystemId).toBe(selectedId);
    expect(result.current.invalidSelectedContext).toBe(true);
    expect(result.current.plannerSystemId).toBeNull();
    expect(result.current.plannerProjectId).toBeNull();
  });

  it('parses dedicated Colony Planner workspace routes separately from modal routes', () => {
    window.location.hash = '#colony-planner/system/123456';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('colony-planner');
    expect(result.current.selectedSystemId).toBeNull();
    expect(result.current.plannerSystemId).toBe(123456);
  });

  it.each([
    ['#colony-planner', null, null, false, false],
    ['#colony-planner/system', null, null, true, false],
    ['#colony-planner/system/not-a-number', null, null, true, false],
    ['#colony-planner/system/0', null, null, true, false],
    ['#colony-planner/system/123456/extra', 123456, null, true, false],
    ['#colony-planner/system/123456/project', 123456, null, false, true],
    ['#colony-planner/system/123456/project/foo', 123456, 'foo', false, false],
    ['#colony-planner/system/123456/project/foo/extra', 123456, null, false, true],
  ] as const)('parses exact Colony Planner route shapes for %s', (hash, systemId, projectId, invalidSystem, invalidProject) => {
    window.location.hash = hash;

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('colony-planner');
    expect(result.current.contextSystemId).toBeNull();
    expect(result.current.selectedSystemId).toBeNull();
    expect(result.current.plannerSystemId).toBe(systemId);
    expect(result.current.plannerProjectId).toBe(projectId);
    expect(result.current.invalidPlannerSystem).toBe(invalidSystem);
    expect(result.current.invalidPlannerProject).toBe(invalidProject);
  });

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

  it('preserves Finder selected context when navigating into Colony Planner', () => {
    window.location.hash = '#finder/context/123';
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      result.current.navigate('colony-planner');
    });

    expect(window.location.hash).toBe('#colony-planner/system/123');
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

  it('returns Planner navigation to Finder context instead of reopening Inspect', () => {
    window.location.hash = '#colony-planner/system/123456';
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      result.current.navigate('finder');
    });

    expect(window.location.hash).toBe('#finder/context/123456');
  });

  it('clears stale Finder selected-system state when a malformed Finder route replaces a valid one', () => {
    window.location.hash = '#finder/system/123456';
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      dispatchHash('#finder/system');
    });

    expect(result.current.route).toBe('finder');
    expect(result.current.contextSystemId).toBeNull();
    expect(result.current.selectedSystemId).toBeNull();
    expect(result.current.invalidSelectedContext).toBe(true);
  });

  it('clears stale planner project state when a malformed project route replaces a valid one', () => {
    window.location.hash = '#colony-planner/system/123456/project/project-1';
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      dispatchHash('#colony-planner/system/123456/project');
    });

    expect(result.current.route).toBe('colony-planner');
    expect(result.current.plannerSystemId).toBe(123456);
    expect(result.current.plannerProjectId).toBeNull();
    expect(result.current.invalidPlannerSystem).toBe(false);
    expect(result.current.invalidPlannerProject).toBe(true);
  });

  it('falls back to Finder for unknown routes', () => {
    window.location.hash = '#does-not-exist';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('finder');
    expect(result.current.contextSystemId).toBeNull();
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

  it('closes Finder Inspect back to non-modal Finder context', () => {
    window.location.hash = '#finder/system/123456';
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      result.current.closeSystem();
    });

    expect(window.location.hash).toBe('#finder/context/123456');
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
