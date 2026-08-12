import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { RouteDetail } from '@/types/api';
import { RouteDetailPanel } from './RouteDetailPanel';

const detail: RouteDetail = {
  route_id: '12345678-1234-5678-1234-567812345678',
  name: 'Distant Worlds Test', source: 'expedition', type: 'expedition',
  created_at: '2026-08-01T00:00:00Z', updated_at: '2026-08-12T00:00:00Z',
  waypoint_count: 2, visited_count: 1, completion_percent: 50,
  remaining_distance: 1234.5, current_waypoint_index: 1,
  metadata: { organizer: 'Pilots Federation', description: 'A long expedition.' },
  waypoints: [], events: [],
  planned_actual_alignment: [
    { planned_order: 0, waypoint: { order: 0, system_name: 'Sol', bookmarked: true }, visited: true, visited_at: '2026-08-01T12:00:00Z' },
    { planned_order: 1, waypoint: { order: 1, system_name: 'Beagle Point', bookmarked: true }, visited: false },
  ],
};

describe('route detail panel', () => {
  it('shows comparison, completion, remaining distance, and expedition metadata', () => {
    render(<RouteDetailPanel routes={[detail]} selectedRouteId={detail.route_id} detail={detail} loading={false} error={null} onSelect={vi.fn()} />);
    expect(screen.getByText('50.0%')).toBeTruthy();
    expect(screen.getByText(/1,234.5 LY/)).toBeTruthy();
    expect(screen.getByText(/Pilots Federation/)).toBeTruthy();
    expect(screen.getByTestId('route-alignment-list').textContent).toContain('Beagle Point');
  });

  it('reports route selection changes', () => {
    const onSelect = vi.fn();
    render(<RouteDetailPanel routes={[detail]} selectedRouteId={detail.route_id} detail={detail} loading={false} error={null} onSelect={onSelect} />);
    fireEvent.change(screen.getByTestId('route-selector'), { target: { value: '' } });
    expect(onSelect).toHaveBeenCalledWith(null);
  });
});
