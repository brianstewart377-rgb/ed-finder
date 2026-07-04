import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { useHashRoute } from './useHashRoute';

afterEach(() => {
  window.location.hash = '';
});

describe('useHashRoute selected-system context', () => {
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
  ] as const)('parses %s as %s without selected context', (hash, route) => {
    window.location.hash = hash;

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe(route);
    expect(result.current.selectedSystemId).toBeNull();
    expect(result.current.contextSystemId).toBeNull();
    expect(result.current.selectedSystemRouteStatus).toBe('none');
    expect(result.current.plannerSystemId).toBeNull();
  });

  it('normalizes #optimizer as the legacy Advanced Search Tuning alias', () => {
    window.location.hash = '#optimizer';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('search-tuning');
    expect(result.current.contextSystemId).toBeNull();
  });

  it('keeps modal inspection separate from selected context', () => {
    window.location.hash = '#compare/system/123456';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('compare');
    expect(result.current.selectedSystemId).toBe(123456);
    expect(result.current.contextSystemId).toBe(123456);
    expect(result.current.selectedSystemRouteStatus).toBe('pending');
    expect(result.current.plannerSystemId).toBeNull();
  });

  it('parses external #system links as Finder Inspect routes', () => {
    window.location.hash = '#system/123456';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('finder');
    expect(result.current.selectedSystemId).toBe(123456);
    expect(result.current.contextSystemId).toBe(123456);
    expect(result.current.selectedSystemRouteStatus).toBe('pending');
  });

  it('parses a non-modal Finder selected-context route', () => {
    window.location.hash = '#finder/context/123456';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('finder');
    expect(result.current.selectedSystemId).toBeNull();
    expect(result.current.contextSystemId).toBe(123456);
    expect(result.current.selectedSystemRouteStatus).toBe('pending');
    expect(result.current.plannerSystemId).toBeNull();
  });

  it('keeps #finder/system as the modal Inspect route', () => {
    window.location.hash = '#finder/system/123456';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('finder');
    expect(result.current.selectedSystemId).toBe(123456);
    expect(result.current.contextSystemId).toBe(123456);
  });

  it('parses dedicated Colony Planner workspace routes as selected context without a modal', () => {
    window.location.hash = '#colony-planner/system/123456';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('colony-planner');
    expect(result.current.selectedSystemId).toBeNull();
    expect(result.current.contextSystemId).toBe(123456);
    expect(result.current.plannerSystemId).toBe(123456);
    expect(result.current.plannerProjectId).toBeNull();
  });

  it('parses a Planner project route without changing the selected system', () => {
    window.location.hash = '#colony-planner/system/123456/project/draft%20one';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.contextSystemId).toBe(123456);
    expect(result.current.plannerSystemId).toBe(123456);
    expect(result.current.plannerProjectId).toBe('draft one');
  });

  it.each([
    '#finder/context/not-a-number',
    '#finder/context/0',
    '#finder/context/12.5',
    '#finder/system/not-a-number',
    '#system/-1',
    '#colony-planner/system/not-a-number',
    '#colony-planner/system/0',
    '#colony-planner/system/123/project',
  ])('marks malformed selected-system destinations invalid without retaining a prior system for %s', (hash) => {
    window.location.hash = hash;

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.contextSystemId).toBeNull();
    expect(result.current.selectedSystemId).toBeNull();
    expect(result.current.selectedSystemRouteStatus).toBe('invalid');
    expect(result.current.plannerSystemId).toBeNull();
    expect(result.current.plannerProjectId).toBeNull();
  });

  it('opens the dedicated Colony Planner workspace without setting modal state', () => {
    window.location.hash = '#finder/context/123456';
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      result.current.openColonyPlanner(123456);
    });

    expect(window.location.hash).toBe('#colony-planner/system/123456');
  });

  it('enters Plan from non-modal Finder context with the exact selected system', () => {
    window.location.hash = '#finder/context/123456';
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      result.current.navigate('colony-planner');
    });

    expect(window.location.hash).toBe('#colony-planner/system/123456');
  });

  it('returns from Plan to non-modal Finder context without reopening Inspect', () => {
    window.location.hash = '#colony-planner/system/123456';
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      result.current.navigate('finder');
    });

    expect(window.location.hash).toBe('#finder/context/123456');
  });

  it('closing Finder Inspect preserves selected context through the non-modal route', () => {
    window.location.hash = '#finder/system/123456';
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      result.current.closeSystem();
    });

    expect(window.location.hash).toBe('#finder/context/123456');
  });

  it('still closes a non-Finder modal back to its current tab route', () => {
    window.location.hash = '#map/system/123456';
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      result.current.closeSystem();
    });

    expect(window.location.hash).toBe('#map');
  });

  it('preserves an explicitly open modal when changing a non-Planner tab', () => {
    window.location.hash = '#finder/system/123456';
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      result.current.navigate('map');
    });

    expect(window.location.hash).toBe('#map/system/123456');
  });

  it('does not invent selected context for invalid navigation', () => {
    window.location.hash = '#finder/context/not-a-number';
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      result.current.navigate('colony-planner');
    });

    expect(window.location.hash).toBe('#colony-planner');
  });

  it('falls back to Finder for unknown routes without selected context', () => {
    window.location.hash = '#does-not-exist';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('finder');
    expect(result.current.contextSystemId).toBeNull();
    expect(result.current.selectedSystemRouteStatus).toBe('none');
  });
});
