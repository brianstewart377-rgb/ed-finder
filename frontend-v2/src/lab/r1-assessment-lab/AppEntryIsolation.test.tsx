import type React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

type LoadAppResult = {
  App: React.ComponentType;
  healthSpy: ReturnType<typeof vi.fn>;
  searchRunSpy: ReturnType<typeof vi.fn>;
  providerSpy: ReturnType<typeof vi.fn>;
  devtoolsSpy: ReturnType<typeof vi.fn>;
};

function installAppMocks() {
  const healthSpy = vi.fn().mockResolvedValue({ ok: true });
  const searchRunSpy = vi.fn().mockResolvedValue(undefined);
  const providerSpy = vi.fn(({ children }: { children: React.ReactNode }) => (
    <div data-testid="query-client-provider">{children}</div>
  ));
  const devtoolsSpy = vi.fn(() => <div data-testid="react-query-devtools">devtools</div>);

  vi.doMock('@tanstack/react-query', () => ({
    QueryClientProvider: providerSpy,
  }));
  vi.doMock('@tanstack/react-query-devtools', () => ({
    ReactQueryDevtools: devtoolsSpy,
  }));
  vi.doMock('@/lib/queryClient', () => ({
    queryClient: {},
  }));
  vi.doMock('@/lib/api', () => ({
    api: {
      health: healthSpy,
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
      run: searchRunSpy,
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

  return { healthSpy, searchRunSpy, providerSpy, devtoolsSpy };
}

async function loadAppForEnv(dev: boolean): Promise<LoadAppResult> {
  vi.resetModules();
  vi.unstubAllEnvs();
  vi.stubEnv('DEV', dev);
  vi.stubEnv('PROD', !dev);
  const { healthSpy, searchRunSpy, providerSpy, devtoolsSpy } = installAppMocks();
  const mod = await import('@/App');
  return { App: mod.default, healthSpy, searchRunSpy, providerSpy, devtoolsSpy };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
  window.location.hash = '';
});

describe('App entry isolation', () => {
  it('renders the DEV-only lab shell through the real App entry', async () => {
    window.location.hash = '#r1-assessment-lab';
    const { App } = await loadAppForEnv(true);

    render(<App />);

    expect(await screen.findByText('R1 Assessment Laboratory')).toBeTruthy();
    expect(screen.getByText('DEV only — reconstruction shell')).toBeTruthy();
  });

  it('does not mount the normal provider/bootstrap tree at the exact DEV lab hash', async () => {
    window.location.hash = '#r1-assessment-lab';
    const { App, healthSpy, searchRunSpy, providerSpy, devtoolsSpy } = await loadAppForEnv(true);

    render(<App />);
    expect(await screen.findByText('R1 Assessment Laboratory')).toBeTruthy();

    expect(providerSpy).not.toHaveBeenCalled();
    expect(devtoolsSpy).not.toHaveBeenCalled();
    expect(screen.queryByTestId('query-client-provider')).toBeNull();
    expect(screen.queryByTestId('react-query-devtools')).toBeNull();
    expect(screen.queryByTestId('normal-nav')).toBeNull();
    expect(screen.queryByTestId('finder-root')).toBeNull();
    expect(healthSpy).not.toHaveBeenCalled();
    expect(searchRunSpy).not.toHaveBeenCalled();
  });
});
