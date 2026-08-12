import { beforeEach, describe, expect, it } from 'vitest';
import { useSelectedRouteStore } from './selectedRouteStore';

beforeEach(() => {
  localStorage.clear();
  useSelectedRouteStore.setState({ selectedRouteId: null });
});

describe('selected route persistence', () => {
  it('stores the selected route for the next map session', () => {
    useSelectedRouteStore.getState().selectRoute('12345678-1234-5678-1234-567812345678');
    expect(useSelectedRouteStore.getState().selectedRouteId).toBe('12345678-1234-5678-1234-567812345678');
    expect(localStorage.getItem('ed_selected_route')).toContain('12345678-1234-5678-1234-567812345678');
  });

  it('can turn the route layer off without discarding the store', () => {
    useSelectedRouteStore.getState().selectRoute('12345678-1234-5678-1234-567812345678');
    useSelectedRouteStore.getState().selectRoute(null);
    expect(useSelectedRouteStore.getState().selectedRouteId).toBeNull();
  });
});
