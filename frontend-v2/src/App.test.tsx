import { render, screen, waitFor } from '@testing-library/react';
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
  }),
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
