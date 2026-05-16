import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from './App';

vi.mock('@/lib/api', () => ({
  api: {
    health: vi.fn().mockResolvedValue({ status: 'ok', database: 'connected', version: 'test' }),
  },
}));

vi.mock('@/features/search/useSearch', () => ({
  useSearch: () => ({
    run: vi.fn().mockResolvedValue(undefined),
    results: [],
    filters: {
      refName: 'Sol',
      refCoords: { x: 0, y: 0, z: 0 },
    },
    setFilters: vi.fn(),
    reset: vi.fn(),
    state: { kind: 'idle' },
  }),
}));

vi.mock('@/features/search/SearchForm', () => ({
  SearchForm: () => <div>Search form</div>,
}));

vi.mock('@/features/watchlist/useWatchlist', () => ({
  useWatchlist: () => ({
    entries: [],
    loading: false,
    error: null,
    refresh: vi.fn(),
    add: vi.fn(),
    remove: vi.fn(),
    has: vi.fn(() => false),
  }),
}));

vi.mock('@/features/pinned/usePinned', () => ({
  usePinned: () => ({
    entries: [],
    has: vi.fn(() => false),
    toggle: vi.fn(),
  }),
}));

vi.mock('@/features/compare/useCompare', () => ({
  useCompare: () => ({
    entries: [],
    has: vi.fn(() => false),
    toggle: vi.fn(),
  }),
}));

vi.mock('@/features/search-tuning/useSearchTuning', () => ({
  ECONOMIES: ['Agriculture', 'Refinery', 'Industrial', 'HighTech', 'Military', 'Tourism', 'Extraction'],
  useSearchTuning: () => ({
    weights: {
      economy: 0.3,
      slots: 0.2,
      strategic: 0.15,
      safety: 0.15,
      terraforming: 0.1,
      diversity: 0.1,
    },
    setWeight: vi.fn(),
    resetWeights: vi.fn(),
    weightSum: 1,
    economy: null,
    setEconomy: vi.fn(),
    state: { kind: 'idle' },
    run: vi.fn().mockResolvedValue(undefined),
    resetState: vi.fn(),
  }),
}));

vi.mock('@/features/colony/useColony', () => ({
  useColony: () => ({ counts: { total: 0 } }),
}));

vi.mock('@/features/fc-planner/useFcPlanner', () => ({
  useFcPlanner: () => ({ waypoints: [] }),
}));

vi.mock('@/features/admin/useAdmin', () => ({
  useAdmin: () => ({}),
}));

vi.mock('@/features/eddn/EddnTicker', () => ({
  EddnTicker: () => null,
}));

vi.mock('@/features/system-detail/SystemDetailModal', () => ({
  SystemDetailModal: ({ id64 }: { id64: number }) => (
    <div data-testid="system-detail-modal">System detail {id64}</div>
  ),
}));

vi.mock('@/features/colony-planner/ColonyPlannerWorkspace', () => ({
  ColonyPlannerWorkspace: ({
    id64,
    onBackToFinder,
    onOpenSystemDetail,
  }: {
    id64: number | null;
    onBackToFinder: () => void;
    onOpenSystemDetail: (id64: number) => void;
  }) => (
    <div data-testid="colony-planner-workspace">
      Colony Planner workspace {id64 ?? 'none'}
      <button type="button" onClick={onBackToFinder}>Back to Finder</button>
      <button type="button" onClick={() => id64 != null && onOpenSystemDetail(id64)}>Open full system detail</button>
    </div>
  ),
}));

afterEach(() => {
  window.location.hash = '';
});

describe('App Advanced Search Tuning route', () => {
  it.each(['#search-tuning', '#optimizer'])('renders Advanced Search Tuning for %s', async (hash) => {
    window.location.hash = hash;

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Advanced Search Tuning' })).toBeTruthy();
    });
  });
});

describe('App Colony Planner workspace route', () => {
  it('renders the dedicated workspace without opening the System Detail modal', async () => {
    window.location.hash = '#colony-planner/system/123';

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('colony-planner-workspace').textContent).toContain('123');
    });
    expect(screen.queryByTestId('system-detail-modal')).toBeNull();
  });

  it('renders the workspace no-system state for #colony-planner', async () => {
    window.location.hash = '#colony-planner';

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('colony-planner-workspace').textContent).toContain('none');
    });
    expect(screen.queryByTestId('system-detail-modal')).toBeNull();
  });

  it('opens full System Detail from the workspace through the existing modal route', async () => {
    window.location.hash = '#colony-planner/system/123';

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('colony-planner-workspace')).toBeTruthy();
    });

    fireEvent.click(screen.getByRole('button', { name: /Open full system detail/i }));

    await waitFor(() => {
      expect(window.location.hash).toBe('#finder/system/123');
    });
    expect(screen.getByTestId('system-detail-modal').textContent).toContain('123');
  });
});
