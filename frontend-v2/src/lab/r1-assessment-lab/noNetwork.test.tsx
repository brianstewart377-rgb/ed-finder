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

describe('R1 assessment lab entry has no network or persistence writes', () => {
  it('does not call named network or persistence channels during DEV lab entry', async () => {
    window.location.hash = '#r1-assessment-lab';

    const fetchSpy = vi.fn();
    const xhrOpenSpy = vi.fn();
    const webSocketSpy = vi.fn();
    const eventSourceSpy = vi.fn();
    const sendBeaconSpy = vi.fn();
    const localStorageSetSpy = vi.spyOn(Object.getPrototypeOf(window.localStorage), 'setItem');
    const sessionStorageSetSpy = vi.spyOn(Object.getPrototypeOf(window.sessionStorage), 'setItem');
    const indexedDbOpenSpy = vi.fn();

    vi.stubGlobal('fetch', fetchSpy);
    vi.stubGlobal('XMLHttpRequest', class {
      open = xhrOpenSpy;
      send = vi.fn();
    });
    vi.stubGlobal('WebSocket', webSocketSpy);
    vi.stubGlobal('EventSource', eventSourceSpy);
    Object.defineProperty(window.navigator, 'sendBeacon', {
      configurable: true,
      value: sendBeaconSpy,
    });
    Object.defineProperty(window, 'indexedDB', {
      configurable: true,
      value: { open: indexedDbOpenSpy },
    });

    const App = await loadAppForEnv(true);
    render(<App />);

    expect(await screen.findByText('R1 Assessment Laboratory')).toBeTruthy();
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(xhrOpenSpy).not.toHaveBeenCalled();
    expect(webSocketSpy).not.toHaveBeenCalled();
    expect(eventSourceSpy).not.toHaveBeenCalled();
    expect(sendBeaconSpy).not.toHaveBeenCalled();
    expect(localStorageSetSpy).not.toHaveBeenCalled();
    expect(sessionStorageSetSpy).not.toHaveBeenCalled();
    expect(indexedDbOpenSpy).not.toHaveBeenCalled();
  });
});
