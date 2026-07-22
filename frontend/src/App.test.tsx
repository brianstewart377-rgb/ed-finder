import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { useColonyProjectStore } from '@/features/colony-planner/colonyProjectStore';
import { useMyWorkStore } from '@/features/my-work/myWorkStore';

const {
  mockImportJournal,
  mockWatchlistAdd,
  mockWatchlistRemove,
  mockWatchlistHas,
  mockWatchlistEntries,
  mockSearchRun,
  mockSearchResults,
  mockSearchState,
} = vi.hoisted(() => ({
  mockImportJournal: vi.fn().mockResolvedValue({
    import_id: 'test-import',
    systems_processed: 0,
    bodies_processed: 0,
    journal_entries_processed: 0,
    warnings: [],
  }),
  mockWatchlistAdd: vi.fn(),
  mockWatchlistRemove: vi.fn(),
  mockWatchlistHas: vi.fn((_id64: number) => false),
  mockWatchlistEntries: [] as Array<Record<string, unknown>>,
  mockSearchRun: vi.fn().mockResolvedValue(undefined),
  mockSearchResults: [] as Array<Record<string, unknown>>,
  mockSearchState: {
    current: { kind: 'idle' } as Record<string, unknown>,
  },
}));

vi.mock('@/lib/api', () => {
  class ApiError extends Error {
    constructor(
      public readonly status: number,
      public readonly path: string,
      public readonly body: string,
    ) {
      super(`API ${status} on ${path}: ${body}`);
      this.name = 'ApiError';
    }
  }

  return {
    ApiError,
    api: {
      health: vi.fn().mockResolvedValue({ status: 'ok', database: 'connected', version: 'test' }),
    },
    importJournal: mockImportJournal,
  };
});

vi.mock('@/features/search/useSearch', () => ({
  useSearch: () => ({
    run: mockSearchRun,
    results: mockSearchResults,
    filters: {
      refName: 'Sol',
      refCoords: { x: 0, y: 0, z: 0 },
    },
    setFilters: vi.fn(),
    reset: vi.fn(),
    state: mockSearchState.current,
  }),
}));

vi.mock('@/features/search/SearchForm', () => ({
  SearchForm: () => <div>Search form</div>,
}));

vi.mock('@/features/watchlist/useWatchlist', () => ({
  useWatchlist: () => ({
    entries: mockWatchlistEntries,
    loading: false,
    error: null,
    refresh: vi.fn(),
    add: mockWatchlistAdd,
    remove: mockWatchlistRemove,
    has: mockWatchlistHas,
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
  COMPARE_MAX: 4,
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
      purity: 0.3,
      buildability: 0.25,
      slots: 0.2,
      expansion: 0.15,
      logistics: 0.1,
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

vi.mock('@/features/fc-planner/useFcPlanner', () => ({
  useFcPlanner: () => ({ waypoints: [] }),
}));

vi.mock('@/features/admin/useAdmin', () => ({
  useAdmin: () => ({}),
}));

vi.mock('@/features/admin/AdminTab', () => ({
  AdminTab: () => <div data-testid="admin-tab">Admin tab</div>,
}));

vi.mock('@/features/operator/OperatorCockpitTab', () => ({
  OperatorCockpitTab: () => <div data-testid="operator-tab">Operator tab</div>,
}));

vi.mock('@/features/news/EliteNewsBar', () => ({
  EliteNewsBar: () => null,
}));

vi.mock('@/features/system-detail/SystemDetailModal', () => ({
  SystemDetailModal: ({
    id64,
    savedForLater,
    saveForLaterState = 'idle',
    onToggleSaveForLater,
    onStartPlan,
  }: {
    id64: number;
    savedForLater?: boolean;
    saveForLaterState?: 'idle' | 'saving' | 'removing';
    onToggleSaveForLater?: (context: {
      system: {
        id64: number;
        name: string;
        x: number;
        y: number;
        z: number;
        population: number | null;
        is_colonised: boolean;
        score: number | null;
        primary_economy: string | null;
        economy_suggestion: string | null;
      };
      archetype: {
        overall_development_potential: number | null;
        primary_archetype: string | null;
        secondary_archetype: string | null;
        buildability_score: number | null;
        purity_score: number | null;
      } | null;
    }) => void;
    onStartPlan?: (system: {
      id64: number;
      name: string;
      x: number;
      y: number;
      z: number;
      population: number | null;
      is_colonised: boolean;
      score: number | null;
      primary_economy: string | null;
      economy_suggestion: string | null;
    }, planStart: {
      objective: 'materials_coverage';
      startApproach: 'manual';
    }) => void;
  }) => (
    <div data-testid="system-detail-modal">
      System detail {id64}
      <button
        type="button"
        disabled={saveForLaterState === 'saving' || saveForLaterState === 'removing'}
        onClick={() => onToggleSaveForLater?.({
          system: {
            id64,
            name: `System ${id64}`,
            x: 1,
            y: 2,
            z: 3,
            population: 0,
            is_colonised: false,
            score: 77,
            primary_economy: 'Agriculture',
            economy_suggestion: 'Refinery',
          },
          archetype: {
            overall_development_potential: 88,
            primary_archetype: 'refinery_industrial',
            secondary_archetype: 'trade_logistics',
            buildability_score: 80,
            purity_score: 70,
          },
        })}
      >
        {saveForLaterState === 'saving'
          ? 'Saving…'
          : saveForLaterState === 'removing'
            ? 'Removing…'
            : savedForLater ? 'Remove from saved' : 'Save for later'}
      </button>
      <button
        type="button"
        onClick={() => onStartPlan?.({
          id64,
          name: `System ${id64}`,
          x: 1,
          y: 2,
          z: 3,
          population: 0,
          is_colonised: false,
          score: 77,
          primary_economy: 'Agriculture',
          economy_suggestion: 'Refinery',
        }, {
          objective: 'materials_coverage',
          startApproach: 'manual',
        })}
      >
        Create manual draft
      </button>
    </div>
  ),
}));

vi.mock('@/features/system-detail/useSystemDetail', () => ({
  useSystemDetail: (id64: number | null) => ({
    data: id64 != null ? { id64, name: `System ${id64}` } : null,
    loading: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

vi.mock('@/features/colony-planner/ColonyPlannerWorkspace', () => ({
  ColonyPlannerWorkspace: ({
    id64,
    projectId,
    initialCockpitMode,
    onBackToFinder,
    onOpenSystemDetail,
    onCockpitModeChange,
  }: {
    id64: number | null;
    projectId?: string | null;
    initialCockpitMode?: string | null;
    onBackToFinder: () => void;
    onOpenSystemDetail: (id64: number) => void;
    onCockpitModeChange?: (mode: string) => void;
  }) => (
    <div data-testid="colony-planner-workspace">
      Colony Planner workspace {id64 ?? 'none'} / {projectId ?? 'no-project'} / {initialCockpitMode ?? 'build-plan'}
      <button type="button" onClick={onBackToFinder}>Back to Finder</button>
      <button type="button" onClick={() => id64 != null && onOpenSystemDetail(id64)}>Open full system detail</button>
      <button type="button" onClick={() => onCockpitModeChange?.('validation')}>Open validation mode</button>
    </div>
  ),
}));

vi.mock('@/features/map/MapTab', () => ({
  MapTab: ({
    systems,
    reference,
    initialSelectedSystemId,
  }: {
    systems: Array<{ name?: string; id64: number }>;
    reference: { name: string };
    initialSelectedSystemId?: number | null;
  }) => (
    <div data-testid="map-tab">
      <span>Map for {reference.name}</span>
      <span data-testid="map-tab-system-count">{systems.length}</span>
      <span data-testid="map-tab-selected-id">{initialSelectedSystemId ?? 'none'}</span>
    </div>
  ),
}));

afterEach(() => {
  window.location.hash = '';
  localStorage.clear();
  useColonyProjectStore.setState({ projects: {} });
  useMyWorkStore.setState({ systems: {} });
  document.documentElement.style.removeProperty('--coalsack-bg-2560');
  document.documentElement.style.removeProperty('--coalsack-bg-1600');
  mockWatchlistAdd.mockReset();
  mockWatchlistRemove.mockReset();
  mockWatchlistHas.mockReset();
  mockWatchlistHas.mockReturnValue(false);
  mockImportJournal.mockClear();
  mockWatchlistEntries.length = 0;
  mockSearchRun.mockClear();
  mockSearchResults.length = 0;
  mockSearchState.current = { kind: 'idle' };
  vi.unstubAllGlobals();
});

async function renderApp() {
  let rendered: ReturnType<typeof render> | null = null;
  await act(async () => {
    rendered = render(<App />);
    await Promise.resolve();
    await Promise.resolve();
  });
  return rendered!;
}

function seedFinderResult(overrides: Record<string, unknown> = {}) {
  const result = {
    id64: 777,
    name: 'Finder Candidate',
    coords: { x: 10, y: 20, z: 30 },
    distance: 45.6,
    population: 0,
    is_colonised: false,
    primaryEconomy: 'Refinery',
    archetype_score: 91,
    primary_archetype: 'refinery_industrial',
    secondary_archetype: 'trade_logistics',
    buildability_score: 84,
    purity_score: 73,
    economy_suggestion: 'Refinery',
    ...overrides,
  };
  mockSearchResults.push(result);
  mockSearchState.current = {
    kind: 'ok',
    data: {
      count: mockSearchResults.length,
      total: mockSearchResults.length,
    },
    queriedAt: Date.now(),
  };
  return result;
}

describe('App Development Tuning route', () => {
  it('shows the owner-approved non-commercial Frontier disclaimer site-wide', async () => {
    window.location.hash = '#finder';

    await renderApp();

    expect(screen.getByTestId('frontier-fan-disclaimer').textContent).toBe(
      'This site/app was created using assets and imagery from Elite: Dangerous for non-commercial purposes. It is not endorsed by nor reflects the views or opinions of Frontier Developments and no employee of Frontier Developments was involved in the making of it.',
    );
  });

  it('renders Development Tuning for the direct route', async () => {
    const hash = '#search-tuning';
    window.location.hash = hash;

    await renderApp();

    await waitFor(() => {
      expect(screen.getAllByRole('heading', { name: 'Development Tuning' }).length).toBeGreaterThan(0);
    });
  });
});

describe('App Colony Planner workspace route', () => {
  it('sets local-root Coalsack background image URLs without probing image paths in dev', async () => {
    const fetchMock = vi.fn(async (url: string | URL | Request) => ({
      ok: String(url).startsWith('/bg/'),
      headers: {
        get: (name: string) => {
          if (name.toLowerCase() !== 'content-type') return null;
          return String(url).startsWith('/bg/') ? 'image/jpeg' : 'text/html';
        },
      },
    }));
    vi.stubGlobal('fetch', fetchMock);
    window.location.hash = '#finder';

    await renderApp();

    await waitFor(() => {
      expect(screen.getByText('Search form')).toBeTruthy();
    });

    await waitFor(() => {
      expect(document.documentElement.style.getPropertyValue('--coalsack-bg-2560')).toContain('/bg/coalsack-2560.jpg');
      expect(document.documentElement.style.getPropertyValue('--coalsack-bg-1600')).toContain('/bg/coalsack-1600.jpg');
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('renders the dedicated workspace with the shared selected-system shell context and no System Detail modal', async () => {
    window.location.hash = '#colony-planner/system/123';

    await renderApp();

    await waitFor(() => {
      expect(screen.getByTestId('colony-planner-workspace').textContent).toContain('123');
    });
    expect(screen.getByTestId('navbar')).toBeTruthy();
    expect(screen.getByTestId('product-shell-context').textContent).toContain('System 123');
    expect(screen.getByTestId('selected-system-evidence-badge').textContent).toContain('Available candidate');
    expect(screen.queryByTestId('system-detail-modal')).toBeNull();
  });

  it('passes planner cockpit mode from the route into the dedicated planner workspace', async () => {
    window.location.hash = '#colony-planner/system/123/mode/sequence';

    await renderApp();

    await waitFor(() => {
      expect(screen.getByTestId('colony-planner-workspace').textContent).toContain('/ sequence');
    });
    expect(screen.getByTestId('product-shell-context').textContent).toContain('System 123');
  });

  it('updates the planner route when the cockpit mode changes inside Plan', async () => {
    window.location.hash = '#colony-planner/system/123/project/draft-1/mode/preview';

    await renderApp();

    await waitFor(() => {
      expect(screen.getByTestId('colony-planner-workspace').textContent).toContain('/ preview');
    });

    fireEvent.click(screen.getByRole('button', { name: 'Open validation mode' }));

    await waitFor(() => {
      expect(window.location.hash).toBe('#colony-planner/system/123/project/draft-1/mode/validation');
    });
  });

  it('uses full-width main layout on the dedicated planner route only', async () => {
    window.location.hash = '#colony-planner/system/123';
    const { container, unmount } = await renderApp();
    await waitFor(() => {
      expect(screen.getByTestId('colony-planner-workspace')).toBeTruthy();
    });
    const plannerMain = container.querySelector('main');
    expect(plannerMain?.className).toContain('max-w-none');
    expect(plannerMain?.className).not.toContain('max-w-[1840px]');
    unmount();

    window.location.hash = '#finder';
    const { container: finderContainer } = await renderApp();
    await waitFor(() => {
      expect(screen.getByText('Search form')).toBeTruthy();
    });
    const finderMain = finderContainer.querySelector('main');
    expect(finderMain?.className).toContain('max-w-[1840px]');
  });

  it('renders the workspace no-system state for #colony-planner without duplicate shell context', async () => {
    window.location.hash = '#colony-planner';

    await renderApp();

    await waitFor(() => {
      expect(screen.getByTestId('colony-planner-workspace').textContent).toContain('none');
    });
    expect(screen.queryByTestId('product-shell-context')).toBeNull();
    expect(screen.queryByTestId('product-shell-context-mobile')).toBeNull();
    expect(screen.queryByTestId('system-detail-modal')).toBeNull();
  });

  it('opens full System Detail from the workspace through a planning-owned modal route', async () => {
    window.location.hash = '#colony-planner/system/123';

    await renderApp();

    await waitFor(() => {
      expect(screen.getByTestId('colony-planner-workspace')).toBeTruthy();
    });

    fireEvent.click(screen.getByRole('button', { name: /Open full system detail/i }));

    await waitFor(() => {
      expect(window.location.hash).toBe('#colony-planner/system/123/detail/123');
    });
    expect((await screen.findByTestId('system-detail-modal')).textContent).toContain('123');
  });

  it('creates exactly one selected-system Draft from System Detail and opens its planner project', async () => {
    window.location.hash = '#finder/system/123';

    await renderApp();

    await waitFor(async () => {
      expect((await screen.findByTestId('system-detail-modal')).textContent).toContain('123');
    });

    fireEvent.click(screen.getByRole('button', { name: /Create manual draft/i }));

    await waitFor(() => {
      expect(window.location.hash).toMatch(/^#colony-planner\/system\/123\/project\//);
    });
    expect(screen.getByTestId('colony-planner-workspace').textContent).toContain('123');
    const projects = Object.values(useColonyProjectStore.getState().projects);
    expect(projects).toHaveLength(1);
    expect(projects.filter((project) => project.system_id64 === 123 && project.status === 'draft')).toHaveLength(1);
    expect(projects[0]).toEqual(expect.objectContaining({
      system_id64: 123,
      project_name: 'System 123 - Materials coverage',
      objective: 'materials_coverage',
      start_approach: 'manual',
      created_from: 'system_detail',
      status: 'draft',
    }));
    expect(screen.getByTestId('colony-planner-workspace').textContent).toContain(projects[0].id);
  });

  it.each([
    ['#my-work', null],
    ['#watchlist', 'Watchlist now opens the Saved Systems view inside My Work'],
    ['#pinned', 'Pins now open the Saved Systems view inside My Work'],
    ['#colony', 'Colony Tracker remains available by route, while My Work now holds the player-facing colonies overview.'],
  ])('renders My Work with one local header and no shell context before a system is selected for %s', async (hash, aliasNotice) => {
    window.location.hash = hash;

    await renderApp();

    await waitFor(() => {
      expect(screen.getByTestId('my-work-workspace')).toBeTruthy();
    });

    expect(screen.queryByTestId('product-shell-context')).toBeNull();
    expect(screen.queryByTestId('product-shell-context-mobile')).toBeNull();
    expect(screen.getByTestId('nav-my-work').getAttribute('aria-current')).toBe('page');
    expect(screen.getAllByRole('heading', { name: 'My Work' })).toHaveLength(1);
    expect(screen.getByTestId('my-work-workspace').textContent).toContain('Saved systems, plans, and colonies in one place.');
    expect(screen.getByTestId('my-work-section-tabs').textContent).toContain('Saved Systems');
    expect(screen.getByTestId('my-work-section-tabs').textContent).toContain('Plans');
    expect(screen.getByTestId('my-work-section-tabs').textContent).toContain('My Colonies');
    expect(screen.getByTestId('my-work-saved-systems')).toBeTruthy();

    if (aliasNotice) {
      expect(screen.getByTestId('my-work-workspace').textContent).toContain(aliasNotice);
    } else {
      expect(screen.getByTestId('my-work-workspace').textContent).not.toContain('now opens the Saved Systems view inside My Work');
    }
  });

  it('renders a skip link to main content for keyboard navigation', async () => {
    window.location.hash = '#finder';

    const { container } = await renderApp();

    const skipLink = screen.getByRole('link', { name: 'Skip to main content' });
    expect(skipLink.getAttribute('href')).toBe('#app-content');
    const main = container.querySelector('main');
    expect(main?.id).toBe('app-content');
  });

  it('restores selected-system shell context from browser storage on direct My Work entry', async () => {
    localStorage.setItem('ed-finder:selected-system-context', '456');
    window.location.hash = '#my-work';

    await renderApp();

    await waitFor(() => {
      expect(screen.getByTestId('my-work-workspace')).toBeTruthy();
    });
    expect(screen.getByTestId('product-shell-context').textContent).toContain('System 456');
    expect(screen.getByTestId('product-shell-context').textContent).toContain('ID64 456');
    expect(screen.getByTestId('selected-system-evidence-badge').textContent).toContain('Available candidate');
  });

  it('uses the shell context hand-off to open the selected system in Plan', async () => {
    localStorage.setItem('ed-finder:selected-system-context', '456');
    window.location.hash = '#my-work';

    await renderApp();

    await waitFor(() => {
      expect(screen.getByTestId('product-shell-context').textContent).toContain('System 456');
    });

    fireEvent.click(screen.getByTestId('nav-open-selected-system-plan'));

    await waitFor(() => {
      expect(window.location.hash).toBe('#colony-planner/system/456/mode/build-plan');
    });
    expect(screen.getByTestId('colony-planner-workspace').textContent).toContain('456 / no-project / build-plan');
  });

  it('shows existing Watchlist saved systems in My Work from the current saved-system hook state', async () => {
    mockWatchlistEntries.push({
      system_id64: 909,
      name: 'Existing Saved System',
      x: 12,
      y: 34,
      z: 56,
      population: 0,
      is_colonised: false,
      added_at: '2026-06-24T00:00:00.000Z',
      score: 82,
    });
    window.location.hash = '#watchlist';

    await renderApp();

    await waitFor(() => {
      expect(screen.getByTestId('saved-system-909')).toBeTruthy();
    });
    expect(screen.getByTestId('saved-system-909').textContent).toContain('Existing Saved System');
    expect(screen.getByTestId('saved-system-909').textContent).toContain('Considering');
  });

  it('saves a system for later without creating a draft', async () => {
    window.location.hash = '#finder/system/123';

    await renderApp();

    await waitFor(() => {
      expect(screen.getByTestId('system-detail-modal')).toBeTruthy();
    });

    fireEvent.click(screen.getByRole('button', { name: /Save for later/i }));

    await waitFor(() => {
      expect(mockWatchlistAdd).toHaveBeenCalledTimes(1);
    });
    expect(mockWatchlistAdd).toHaveBeenCalledWith(123, expect.objectContaining({
      name: 'System 123',
      x: 1,
      y: 2,
      z: 3,
      population: 0,
      is_colonised: false,
      economy_suggestion: 'Refinery',
      archetype_score: 88,
      primary_archetype: 'refinery_industrial',
      secondary_archetype: 'trade_logistics',
      buildability_score: 80,
      purity_score: 70,
    }));
    await waitFor(() => {
      expect(screen.getByTestId('saved-system-notice').textContent).toContain('Saved to My Work');
    });
    expect(Object.values(useColonyProjectStore.getState().projects)).toHaveLength(0);
  });

  it('removes a saved system from System Detail without creating a draft', async () => {
    mockWatchlistHas.mockImplementation((id64: number) => id64 === 123);
    window.location.hash = '#finder/system/123';

    await renderApp();

    await waitFor(() => {
      expect(screen.getByTestId('system-detail-modal')).toBeTruthy();
    });

    fireEvent.click(screen.getByRole('button', { name: /Remove from saved/i }));

    await waitFor(() => {
      expect(mockWatchlistRemove).toHaveBeenCalledWith(123);
    });
    await waitFor(() => {
      expect(screen.getByTestId('saved-system-notice').textContent).toContain('Removed from saved');
    });
    expect(Object.values(useColonyProjectStore.getState().projects)).toHaveLength(0);
  });

  it('shows Finder save progress, confirmed saved state, and a My Work shortcut', async () => {
    seedFinderResult();
    let resolveSave: (() => void) | null = null;
    mockWatchlistAdd.mockImplementationOnce(() => new Promise<void>((resolve) => {
      resolveSave = () => {
        mockWatchlistHas.mockImplementation((id64: number) => id64 === 777);
        resolve();
      };
    }));
    window.location.hash = '#finder';

    await renderApp();

    await waitFor(() => {
      expect(screen.getByTestId('result-card-777')).toBeTruthy();
    });

    fireEvent.click(screen.getByText('Finder Candidate'));
    fireEvent.click(screen.getByRole('button', { name: /Save for later/i }));

    await waitFor(() => {
      expect(screen.getByText('Saving…')).toBeTruthy();
    });
    await act(async () => {
      resolveSave?.();
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(screen.getByText('Saved')).toBeTruthy();
    });
    expect(screen.getByRole('button', { name: /Remove from saved/i })).toBeTruthy();
    expect(screen.getByTestId('saved-system-notice').textContent).toContain('Saved to My Work');
    expect(Object.values(useColonyProjectStore.getState().projects)).toHaveLength(0);

    fireEvent.click(screen.getByRole('button', { name: /Open My Work/i }));

    await waitFor(() => {
      expect(window.location.hash).toBe('#my-work');
    });
  });

  it('reports Finder save failures without claiming success or creating a draft', async () => {
    seedFinderResult();
    mockWatchlistAdd.mockRejectedValueOnce(new Error('Watchlist unavailable'));
    window.location.hash = '#finder';

    await renderApp();

    await waitFor(() => {
      expect(screen.getByTestId('result-card-777')).toBeTruthy();
    });

    fireEvent.click(screen.getByText('Finder Candidate'));
    fireEvent.click(screen.getByRole('button', { name: /Save for later/i }));

    await waitFor(() => {
      expect(screen.getByTestId('saved-system-notice').textContent).toContain('Could not save system');
    });
    expect(screen.getByTestId('saved-system-notice').textContent).toContain('Watchlist unavailable');
    expect(screen.getByRole('button', { name: /Save for later/i })).toBeTruthy();
    expect(screen.queryByText('Saved to My Work')).toBeNull();
    expect(Object.values(useColonyProjectStore.getState().projects)).toHaveLength(0);
  });

  it('lets Finder save and inspect the selected system without entering a generic Planner route', async () => {
    seedFinderResult();
    window.location.hash = '#finder';

    await renderApp();

    await waitFor(() => {
      expect(screen.getByTestId('result-card-777')).toBeTruthy();
    });

    fireEvent.click(screen.getByText('Finder Candidate'));
    fireEvent.click(screen.getByRole('button', { name: /Save for later/i }));

    expect(mockWatchlistAdd).toHaveBeenCalledWith(777, expect.objectContaining({
      name: 'Finder Candidate',
      x: 10,
      y: 20,
      z: 30,
      population: 0,
      is_colonised: false,
      economy_suggestion: 'Refinery',
      archetype_score: 91,
      primary_archetype: 'refinery_industrial',
      secondary_archetype: 'trade_logistics',
      buildability_score: 84,
      purity_score: 73,
    }));
    expect(Object.values(useColonyProjectStore.getState().projects)).toHaveLength(0);
    expect(window.location.hash).toBe('#finder');

    fireEvent.click(screen.getByRole('button', { name: /Inspect system/i }));

    await waitFor(() => {
      expect(window.location.hash).toBe('#finder/system/777');
    });
    expect(screen.getByTestId('system-detail-modal').textContent).toContain('777');
    expect(screen.queryByTestId('colony-planner-workspace')).toBeNull();
    expect(Object.values(useColonyProjectStore.getState().projects)).toHaveLength(0);
  });

  it('carries the chosen Finder result into the Map route and preselects it there', async () => {
    seedFinderResult();
    window.location.hash = '#finder';

    await renderApp();

    await waitFor(() => {
      expect(screen.getByTestId('result-card-777')).toBeTruthy();
    });

    const resultCard = screen.getByTestId('result-card-777');
    fireEvent.click(screen.getByText('Finder Candidate'));
    fireEvent.click(within(resultCard).getByRole('button', { name: /^Map$/i }));

    await waitFor(() => {
      expect(window.location.hash).toBe('#map/system/777');
    });
    await waitFor(() => {
      expect(screen.getByTestId('map-tab-selected-id').textContent).toBe('777');
    });
    expect(screen.getByTestId('product-shell-context').textContent).toContain('System 777');
  });

  it('lets Finder remove an already saved system through the same Watchlist path', async () => {
    seedFinderResult();
    mockWatchlistHas.mockImplementation((id64: number) => id64 === 777);
    window.location.hash = '#finder';

    await renderApp();

    await waitFor(() => {
      expect(screen.getByTestId('result-card-777')).toBeTruthy();
    });

    fireEvent.click(screen.getByText('Finder Candidate'));
    fireEvent.click(screen.getByRole('button', { name: /Remove from saved/i }));

    expect(mockWatchlistRemove).toHaveBeenCalledWith(777);
    expect(Object.values(useColonyProjectStore.getState().projects)).toHaveLength(0);
    expect(window.location.hash).toBe('#finder');
  });

  it('updates Finder and System Detail together after removing a saved system', async () => {
    seedFinderResult();
    const savedIds = new Set([777]);
    mockWatchlistHas.mockImplementation((id64: number) => savedIds.has(id64));
    mockWatchlistRemove.mockImplementation(async (id64: number) => {
      savedIds.delete(id64);
    });
    window.location.hash = '#finder';

    await renderApp();

    await waitFor(() => {
      expect(screen.getByTestId('result-card-777')).toBeTruthy();
    });

    fireEvent.click(screen.getByText('Finder Candidate'));
    expect(screen.getByRole('button', { name: /Remove from saved/i })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Inspect system/i }));

    await waitFor(() => {
      expect(screen.getByTestId('system-detail-modal').textContent).toContain('777');
    });
    expect(screen.getAllByRole('button', { name: /Remove from saved/i }).length).toBeGreaterThanOrEqual(2);

    fireEvent.click(within(screen.getByTestId('system-detail-modal')).getByRole('button', { name: /Remove from saved/i }));

    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: /Save for later/i }).length).toBeGreaterThanOrEqual(2);
    });
    expect(mockWatchlistRemove).toHaveBeenCalledWith(777);
    expect(screen.getByTestId('saved-system-notice').textContent).toContain('Removed from saved');
  });

  it('renders the compact player-facing Finder intro without internal shell labels', async () => {
    window.location.hash = '#finder';

    await renderApp();

    await waitFor(() => {
      expect(screen.getByTestId('nav-finder')).toBeTruthy();
    });

    expect(screen.getByTestId('nav-player-routes').textContent).toContain('Finder');
    expect(screen.getByTestId('nav-player-routes').textContent).toContain('My Work');
    expect(screen.getByTestId('nav-player-routes').textContent).toContain('Compare');
    expect(screen.getByTestId('nav-finder').textContent).toContain('Finder');
    expect(screen.getByTestId('nav-my-work').textContent).toContain('My Work');
    expect(screen.getByTestId('finder-page-heading').textContent).toContain('Finder');
    expect(screen.getByTestId('finder-page-heading').textContent).toContain(
      'Find promising systems. Save them for later or inspect them before starting a plan.',
    );
    expect(screen.queryByTestId('product-shell-context')).toBeNull();
    expect(screen.queryByText('Primary workspace')).toBeNull();
    expect(screen.queryByText('Discovery workspace')).toBeNull();
    expect(screen.queryByText('Next action')).toBeNull();
    expect(screen.queryByText(/hand off into Plan/i)).toBeNull();
    expect(screen.queryByText('Operator tools')).toBeNull();
    expect(screen.queryByTestId('nav-admin')).toBeNull();
    expect(screen.queryByTestId('nav-operator')).toBeNull();
  });

  it('opens Finder empty and does not auto-run a search on load', async () => {
    window.location.hash = '#finder';

    await renderApp();

    await waitFor(() => {
      expect(screen.getByText('Ready to search')).toBeTruthy();
    });
    expect(screen.getByText('Adjust the filters on the left, then run a search.')).toBeTruthy();
    expect(mockSearchRun).not.toHaveBeenCalled();
  });

  it('keeps admin and operator out of the normal mobile player menu', async () => {
    window.location.hash = '#finder';

    await renderApp();

    await waitFor(() => {
      expect(screen.getByTestId('nav-menu-toggle')).toBeTruthy();
    });

    fireEvent.click(screen.getByTestId('nav-menu-toggle'));

    expect(screen.getByTestId('nav-menu-panel')).toBeTruthy();
    expect(screen.queryByTestId('nav-admin-menu')).toBeNull();
    expect(screen.queryByTestId('nav-operator-menu')).toBeNull();
    expect(screen.queryByTestId('operator-mode-menu')).toBeNull();
  });

  it('renders Compare with the full existing shared-header supporting text', async () => {
    window.location.hash = '#compare';

    await renderApp();

    await waitFor(() => {
      expect(screen.getByTestId('product-shell-context')).toBeTruthy();
    });

    const context = screen.getByTestId('product-shell-context');
    const supportingText = within(context).getByText('Review candidate systems side by side before committing to a plan. This remains a decision-support surface, not a planning workspace.');
    expect(context.textContent).toContain('Decision review');
    expect(context.textContent).toContain('Compare');
    expect(within(context).queryByText(/^Review$/i)).toBeNull();
    expect(supportingText.className).toContain('max-w-none');
    expect(supportingText.className).not.toContain('max-w-3xl');
  });
  it('keeps Finder content compact while preserving selected-system context into My Work after inspect', async () => {
    window.location.hash = '#finder/system/123';

    await renderApp();

    await waitFor(() => {
      expect(screen.getByTestId('system-detail-modal').textContent).toContain('123');
    });
    expect(screen.getByTestId('finder-page-heading').textContent).toContain(
      'Find promising systems. Save them for later or inspect them before starting a plan.',
    );
    expect(screen.getByTestId('product-shell-context').textContent).toContain('System 123');
    expect(screen.getByTestId('selected-system-evidence-badge').textContent).toContain('Available candidate');

    window.location.hash = '#my-work';
    fireEvent(window, new HashChangeEvent('hashchange'));

    await waitFor(() => {
      expect(screen.getByTestId('my-work-workspace')).toBeTruthy();
    });
    expect(screen.getByTestId('product-shell-context').textContent).toContain('System 123');
    expect(screen.getByTestId('product-shell-context').textContent).toContain('ID64 123');
  });

  it.each([
    ['#admin', 'admin-tab'],
    ['#operator', 'operator-tab'],
  ])('keeps direct %s route entries working with separate operator-mode framing', async (hash, tabTestId) => {
    window.location.hash = hash;

    await renderApp();

    await waitFor(() => {
      expect(screen.getByTestId(tabTestId)).toBeTruthy();
    });

    expect(screen.getByTestId('operator-mode-context-desktop').textContent).toContain('Separate mode: Operator');
    expect(screen.getByTestId('operator-mode-context-desktop').textContent).toContain('outside the normal Explore, Plan, and Review player journey');

    fireEvent.click(screen.getByTestId('nav-return-to-player-desktop'));

    await waitFor(() => {
      expect(window.location.hash).toBe('#finder');
    });
  });
});
