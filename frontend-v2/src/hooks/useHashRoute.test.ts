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
  ] as const)('parses %s as %s', (hash, route) => {
    window.location.hash = hash;

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe(route);
    expect(result.current.selectedSystemId).toBeNull();
  });

  it('parses #search-tuning as the preferred Advanced Search Tuning route', () => {
    window.location.hash = '#search-tuning';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('search-tuning');
    expect(result.current.selectedSystemId).toBeNull();
  });

  it('normalizes #optimizer as the legacy Advanced Search Tuning alias', () => {
    window.location.hash = '#optimizer';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('search-tuning');
    expect(result.current.selectedSystemId).toBeNull();
  });

  it('parses child system modal routes without changing the parent tab', () => {
    window.location.hash = '#compare/system/123456';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('compare');
    expect(result.current.selectedSystemId).toBe(123456);
  });

  it('parses legacy #optimizer/system links as Advanced Search Tuning modal routes', () => {
    window.location.hash = '#optimizer/system/123456';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('search-tuning');
    expect(result.current.selectedSystemId).toBe(123456);
  });

  it('parses external #system links as Finder modal routes', () => {
    window.location.hash = '#system/123456';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('finder');
    expect(result.current.selectedSystemId).toBe(123456);
  });

  it('falls back to Finder for unknown routes', () => {
    window.location.hash = '#does-not-exist';

    const { result } = renderHook(() => useHashRoute());

    expect(result.current.route).toBe('finder');
    expect(result.current.selectedSystemId).toBeNull();
  });

  it('closes a modal back to the current tab route', () => {
    window.location.hash = '#map/system/123456';
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      result.current.closeSystem();
    });

    expect(window.location.hash).toBe('#map');
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
