import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { useHashRoute } from './useHashRoute';

afterEach(() => {
  window.location.hash = '';
});

describe('useHashRoute Advanced Search Tuning aliases', () => {
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

  it('navigates to the preferred #search-tuning route', () => {
    window.location.hash = '#finder';
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      result.current.navigate('search-tuning');
    });

    expect(window.location.hash).toBe('#search-tuning');
  });
});
