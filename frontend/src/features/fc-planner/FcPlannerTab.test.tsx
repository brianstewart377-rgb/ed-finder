import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FcPlannerTab } from './FcPlannerTab';
import type { UseFcPlanner } from './useFcPlanner';
import type { ReviewSelectedSystem } from '@/components/ReviewWorkspaceHeader';

vi.mock('@/features/search/useAutocomplete', () => ({
  useAutocomplete: () => ({ hits: [] }),
}));

function makeFc(overrides: Partial<UseFcPlanner> = {}): UseFcPlanner {
  return {
    waypoints: [],
    config: {
      jump_range_ly: 500,
      cargo_t: 25_000,
      tritium_per_jump: 50,
      tritium_price_cr: 50_000,
    },
    add: vi.fn(),
    remove: vi.fn(),
    move: vi.fn(),
    clear: vi.fn(),
    setConfig: vi.fn(),
    route: {
      legs: [],
      total_distance_ly: 0,
      total_hops: 0,
      total_tritium_t: 0,
      total_cost_cr: 0,
      cargo_trips: 0,
      missing_coord_names: [],
    },
    exportCsv: vi.fn(),
    ...overrides,
  };
}

describe('FcPlannerTab', () => {
  it('shows selected-system review context in the workspace header', () => {
    const selectedSystem: ReviewSelectedSystem = {
      id64: 12866676218109,
      name: 'Shinrarta Dezhra',
      loading: false,
      evidenceLabel: 'Observed colony state',
      evidenceTone: 'observed',
      evidenceSummary: 'This system remains selected across Explore, Inspect, Plan, and Review until you choose another one.',
    };

    render(<FcPlannerTab fc={makeFc()} selectedSystem={selectedSystem} />);

    expect(screen.getByTestId('fc-workspace-header')).toBeTruthy();
    expect(screen.getByText('Shinrarta Dezhra')).toBeTruthy();
    expect(screen.getByText('Observed colony state')).toBeTruthy();
    expect(screen.getByText(/player-journey reference/i)).toBeTruthy();
  });

  it('shows an explicit empty selected-system state before anything is pinned', () => {
    render(<FcPlannerTab fc={makeFc()} />);

    expect(screen.getByTestId('fc-workspace-header')).toBeTruthy();
    expect(screen.getByText('No selected system')).toBeTruthy();
    expect(screen.getByText('Waiting for selection')).toBeTruthy();
    expect(screen.getByText(/Choose a system in Explore, Inspect, or Plan/i)).toBeTruthy();
  });

  it('associates the waypoint label with its input', () => {
    render(<FcPlannerTab fc={makeFc()} />);

    expect(screen.getByLabelText('Add waypoint').getAttribute('data-testid')).toBe('fc-input');
  });
});
