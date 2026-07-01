import type React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

function installAppMocks() {
  vi.doMock('@tanstack/react-query', () => ({
    QueryClientProvider: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="query-client-provider">{children}</div>
    ),
  }));
  vi.doMock('@tanstack/react-query-devtools', () => ({
    ReactQueryDevtools: () => <div data-testid="react-query-devtools">devtools</div>,
  }));
  vi.doMock('@/lib/queryClient', () => ({
    queryClient: {},
  }));
  vi.doMock('@/lib/api', () => ({
    api: {
      health: vi.fn().mockResolvedValue({ ok: true }),
    },
    ApiError: class ApiError extends Error {},
  }));
  vi.doMock('@/components/ResultCard', () => ({
    ResultCard: () => <div data-testid="result-card" />,
  }));
  vi.doMock('@/components/NavBar', () => ({
    NavBar: ({ current }: { current: string }) => <div data-testid="normal-nav">route:{current}</div>,
  }));
  vi.doMock('@/features/search/SearchForm', () => ({
    SearchForm: () => <div data-testid="finder-root">Finder fallback</div>,
  }));
  vi.doMock('@/features/search/useSearch', () => ({
    useSearch: () => ({
      run: vi.fn().mockResolvedValue(undefined),
      results: [],
      filters: { refName: '', refCoords: { x: 0, z: 0 } },
      setFilters: vi.fn(),
      reset: vi.fn(),
      state: { kind: 'idle' as const },
      loading: false,
      error: null,
    }),
  }));
  vi.doMock('@/features/watchlist/useWatchlist', () => ({
    useWatchlist: () => ({
      entries: [],
      has: () => false,
      add: vi.fn(),
      remove: vi.fn(),
    }),
  }));
  vi.doMock('@/features/pinned/usePinned', () => ({
    usePinned: () => ({
      entries: [],
      has: () => false,
      toggle: vi.fn(),
    }),
  }));
  vi.doMock('@/features/pinned/pinnedEntry', () => ({
    toPinnedEntry: vi.fn(),
  }));
  vi.doMock('@/features/compare/useCompare', () => ({
    useCompare: () => ({
      entries: [],
      has: () => false,
      toggle: vi.fn(),
    }),
  }));
  vi.doMock('@/features/compare/CompareTab', () => ({
    CompareTab: () => <div data-testid="compare-tab" />,
  }));
  vi.doMock('@/features/search-tuning/useSearchTuning', () => ({
    useSearchTuning: () => ({}),
  }));
  vi.doMock('@/features/search-tuning/AdvancedSearchTuningTab', () => ({
    AdvancedSearchTuningTab: () => <div data-testid="search-tuning-tab" />,
  }));
  vi.doMock('@/features/colony/useColony', () => ({
    useColony: () => ({ counts: { total: 0 } }),
  }));
  vi.doMock('@/features/colony/ColonyTab', () => ({
    ColonyTab: () => <div data-testid="colony-tab" />,
  }));
  vi.doMock('@/features/fc-planner/useFcPlanner', () => ({
    useFcPlanner: () => ({ waypoints: [] }),
  }));
  vi.doMock('@/features/fc-planner/FcPlannerTab', () => ({
    FcPlannerTab: () => <div data-testid="fc-tab" />,
  }));
  vi.doMock('@/features/admin/useAdmin', () => ({
    useAdmin: () => ({}),
  }));
  vi.doMock('@/features/admin/AdminTab', () => ({
    AdminTab: () => <div data-testid="admin-tab" />,
  }));
  vi.doMock('@/features/operator/OperatorCockpitTab', () => ({
    OperatorCockpitTab: () => <div data-testid="operator-tab" />,
  }));
  vi.doMock('@/features/map/MapTab', () => ({
    MapTab: () => <div data-testid="map-tab" />,
  }));
  vi.doMock('@/features/system-detail/SystemDetailModal', () => ({
    SystemDetailModal: () => null,
  }));
  vi.doMock('@/features/system-detail/useSystemDetail', () => ({
    useSystemDetail: () => ({ data: null, loading: false }),
  }));
  vi.doMock('@/features/colony-planner/ColonyPlannerWorkspace', () => ({
    ColonyPlannerWorkspace: () => <div data-testid="planner-workspace" />,
  }));
  vi.doMock('@/features/colony-planner/prototype/RavenStylePlannerPrototype', () => ({
    RavenStylePlannerPrototype: () => <div data-testid="planner-prototype" />,
  }));
  vi.doMock('@/features/colony-planner/colonyProjectStore', () => ({
    useColonyProjectStore: () => vi.fn(() => ({ id: 'draft-project' })),
  }));
  vi.doMock('@/features/colony-planner/plannerDraftContext', () => ({
    defaultDraftProjectName: () => 'Draft project',
  }));
  vi.doMock('@/features/system-detail/simulation-preview/utils/placementHelpers', () => ({
    archetypeFromEconomy: () => 'refinery_industrial',
  }));
  vi.doMock('@/features/my-work/MyWorkWorkspace', () => ({
    MyWorkWorkspace: () => <div data-testid="my-work" />,
  }));
  vi.doMock('@/features/eddn/EddnTicker', () => ({
    EddnTicker: () => null,
  }));
}

async function loadAppForEnv(dev: boolean) {
  vi.resetModules();
  vi.unstubAllEnvs();
  vi.stubEnv('DEV', dev);
  vi.stubEnv('PROD', !dev);
  installAppMocks();
  const mod = await import('@/App');
  return mod.default;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
  window.location.hash = '';
});

describe('R1 assessment lab route boundary', () => {
  it('renders the shell for the exact DEV hash', async () => {
    window.location.hash = '#r1-assessment-lab';
    const App = await loadAppForEnv(true);

    render(<App />);

    expect(await screen.findByText('R1 Assessment Laboratory')).toBeTruthy();
    expect(screen.queryByTestId('finder-root')).toBeNull();
  });

  it('mounts the normal application path for a non-lab DEV hash', async () => {
    window.location.hash = '';
    const App = await loadAppForEnv(true);

    render(<App />);

    expect(await screen.findByTestId('query-client-provider')).toBeTruthy();
    expect(screen.getByTestId('normal-nav').textContent).toContain('route:finder');
    expect(screen.getByTestId('finder-root')).toBeTruthy();
    expect(screen.queryByText('R1 Assessment Laboratory')).toBeNull();
  });

  it('treats the lab hash as an ordinary unknown hash in production and falls back to Finder', async () => {
    window.location.hash = '#r1-assessment-lab';
    const App = await loadAppForEnv(false);

    render(<App />);

    expect(await screen.findByTestId('finder-root')).toBeTruthy();
    expect(screen.getByTestId('normal-nav').textContent).toContain('route:finder');
    expect(screen.queryByText('R1 Assessment Laboratory')).toBeNull();
  });
});
