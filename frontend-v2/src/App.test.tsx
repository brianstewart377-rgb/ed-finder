import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { useColonyProjectStore } from '@/features/colony-planner/colonyProjectStore';
import { useMyWorkStore } from '@/features/my-work/myWorkStore';

const {
  mockWatchlistAdd,
  mockWatchlistRemove,
  mockWatchlistHas,
  mockSearchRun,
  mockSearchResults,
  mockSearchState,
} = vi.hoisted(() => ({
  mockWatchlistAdd: vi.fn(),
  mockWatchlistRemove: vi.fn(),
  mockWatchlistHas: vi.fn((_id64: number) => false),
  mockSearchRun: vi.fn().mockResolvedValue(undefined),
  mockSearchResults: [] as Array<Record<string, unknown>>,
  mockSearchState: {
    current: { kind: 'idle' } as Record<string, unknown>,
  },
}));

vi.mock('@/lib/api', () => ({
  api: {
    health: vi.fn().mockResolvedValue({ status: 'ok', database: 'connected', version: 'test' }),
  },
}));

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
    entries: [],
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

vi.mock('@/features/admin/AdminTab', () => ({
  AdminTab: () => <div data-testid="admin-tab">Admin tab</div>,
}));

vi.mock('@/features/operator/OperatorCockpitTab', () => ({
  OperatorCockpitTab: () => <div data-testid="operator-tab">Operator tab</div>,
}));

vi.mock('@/features/eddn/EddnTicker', () => ({
  EddnTicker: () => null,
}));

vi.mock('@/features/system-detail/SystemDetailModal', () => ({
  SystemDetailModal: ({
    id64,
    savedForLater,
    onToggleSaveForLater,
  }: {
    id64: number;
    savedForLater?: boolean;
    onToggleSaveForLater?: (system: {
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
    }) => void;
  }) => (
    <div data-testid="system-detail-modal">
      System detail {id64}
      <button
        type="button"
        onClick={() => onToggleSaveForLater?.({
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
        })}
      >
        {savedForLater ? 'Remove from saved' : 'Save for later'}
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
    onBackToFinder,
    onOpenSystemDetail,
  }: {
    id64: number | null;
    projectId?: string | null;
    onBackToFinder: () => void;
    onOpenSystemDetail: (id64: number) => void;
  }) => (
    <div data-testid="colony-planner-workspace">
      Colony Planner workspace {id64 ?? 'none'} / {projectId ?? 'no-project'}
      <button type="button" onClick={onBackToFinder}>Back to Finder</button>
      <button type="button" onClick={() => id64 != null && onOpenSystemDetail(id64)}>Open full system detail</button>
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
  mockSearchRun.mockClear();
  mockSearchResults.length = 0;
  mockSearchState.current = { kind: 'idle' };
  vi.unstubAllGlobals();
});

function seedFinderResult(overrides: Record<string, unknown> = {}) {
  const result = {
    id64: 777,
    name: 'Finder Candidate',
    coords: { x: 10, y: 20, z: 30 },
    distance: 45.6,
    population: 0,
    is_colonised: false,
    primaryEconomy: 'Refinery',
    _rating: {
      score: 88,
      confidence: 0.9,
      rationale: 'Strong candidate',
    },
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
  it('sets base-aware Coalsack background image URLs', async () => {
    const fetchMock = vi.fn(async (url: string | URL | Request) => ({
      ok: String(url).startsWith('/v2/bg/'),
      headers: {
        get: (name: string) => {
          if (name.toLowerCase() !== 'content-type') return null;
          return String(url).startsWith('/v2/bg/') ? 'image/jpeg' : 'text/html';
        },
      },
    }));
    vi.stubGlobal('fetch', fetchMock);
    window.location.hash = '#finder';

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Search form')).toBeTruthy();
    });

    await waitFor(() => {
      expect(document.documentElement.style.getPropertyValue('--coalsack-bg-2560')).toContain('/v2/bg/coalsack-2560.jpg');
      expect(document.documentElement.style.getPropertyValue('--coalsack-bg-1600')).toContain('/v2/bg/coalsack-1600.jpg');
    });
    expect(fetchMock).toHaveBeenCalledWith('/v2/bg/coalsack-2560.jpg?v=2', { method: 'HEAD', cache: 'no-cache' });
    expect(fetchMock).toHaveBeenCalledWith('/v2/bg/coalsack-1600.jpg?v=2', { method: 'HEAD', cache: 'no-cache' });
  });

  it('renders the dedicated workspace without the global product-shell context or System Detail modal', async () => {
    window.location.hash = '#colony-planner/system/123';

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('colony-planner-workspace').textContent).toContain('123');
    });
    expect(screen.getByTestId('navbar')).toBeTruthy();
    expect(screen.queryByTestId('product-shell-context')).toBeNull();
    expect(screen.queryByTestId('product-shell-context-mobile')).toBeNull();
    expect(screen.queryByTestId('system-detail-modal')).toBeNull();
  });

  it('uses full-width main layout on the dedicated planner route only', async () => {
    window.location.hash = '#colony-planner/system/123';
    const { container, unmount } = render(<App />);
    await waitFor(() => {
      expect(screen.getByTestId('colony-planner-workspace')).toBeTruthy();
    });
    const plannerMain = container.querySelector('main');
    expect(plannerMain?.className).toContain('max-w-none');
    expect(plannerMain?.className).not.toContain('max-w-[1840px]');
    unmount();

    window.location.hash = '#finder';
    const { container: finderContainer } = render(<App />);
    await waitFor(() => {
      expect(screen.getByText('Search form')).toBeTruthy();
    });
    const finderMain = finderContainer.querySelector('main');
    expect(finderMain?.className).toContain('max-w-[1840px]');
  });

  it('renders the workspace no-system state for #colony-planner without duplicate shell context', async () => {
    window.location.hash = '#colony-planner';

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('colony-planner-workspace').textContent).toContain('none');
    });
    expect(screen.queryByTestId('product-shell-context')).toBeNull();
    expect(screen.queryByTestId('product-shell-context-mobile')).toBeNull();
    expect(screen.queryByTestId('system-detail-modal')).toBeNull();
  });

  it('renders the static Raven-style planner prototype on its own safe route', async () => {
    window.location.hash = '#colony-planner-prototype';

    const { container } = render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('raven-style-planner-prototype')).toBeTruthy();
    });
    expect(screen.queryByTestId('system-detail-modal')).toBeNull();
    expect(container.querySelector('main')?.className).toContain('max-w-none');
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

  it('keeps System Detail passive without creating a draft or routing into Planner', async () => {
    window.location.hash = '#finder/system/123';

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('system-detail-modal').textContent).toContain('123');
    });

    expect(screen.queryByRole('button', { name: /Create manual draft/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Start a plan/i })).toBeNull();
    expect(window.location.hash).toBe('#finder/system/123');
    const projects = Object.values(useColonyProjectStore.getState().projects);
    expect(projects).toHaveLength(0);
    expect(screen.queryByTestId('colony-planner-workspace')).toBeNull();
  });

  it.each([
    ['#my-work', null],
    ['#watchlist', 'Watchlist now opens the Saved Systems view inside My Work'],
    ['#pinned', 'Pins now open the Saved Systems view inside My Work'],
  ])('renders My Work with one local header and no shell context for %s', async (hash, aliasNotice) => {
    window.location.hash = hash;

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('my-work-workspace')).toBeTruthy();
    });

    expect(screen.queryByTestId('product-shell-context')).toBeNull();
    expect(screen.queryByTestId('product-shell-context-mobile')).toBeNull();
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

  it('saves a system for later without creating a draft', async () => {
    window.location.hash = '#finder/system/123';

    render(<App />);

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
      score: 77,
    }));
    expect(Object.values(useColonyProjectStore.getState().projects)).toHaveLength(0);
  });

  it('removes a saved system from System Detail without creating a draft', async () => {
    mockWatchlistHas.mockImplementation((id64: number) => id64 === 123);
    window.location.hash = '#finder/system/123';

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('system-detail-modal')).toBeTruthy();
    });

    fireEvent.click(screen.getByRole('button', { name: /Remove from saved/i }));

    await waitFor(() => {
      expect(mockWatchlistRemove).toHaveBeenCalledTimes(1);
    });
    expect(mockWatchlistRemove).toHaveBeenCalledWith(123);
    expect(mockWatchlistAdd).not.toHaveBeenCalled();
    expect(Object.values(useColonyProjectStore.getState().projects)).toHaveLength(0);
  });

  it('lets Finder save and inspect the selected system without entering Planner', async () => {
    seedFinderResult();
    window.location.hash = '#finder';

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Finder Candidate')).toBeTruthy();
    });

    fireEvent.click(screen.getByText('Finder Candidate'));
    expect(screen.queryByRole('button', { name: /Evaluate in Colony Planner/i })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /Save for later/i }));

    await waitFor(() => {
      expect(mockWatchlistAdd).toHaveBeenCalledTimes(1);
    });
    expect(mockWatchlistAdd).toHaveBeenCalledWith(777, expect.objectContaining({
      name: 'Finder Candidate',
      x: 10,
      y: 20,
      z: 30,
      population: 0,
      is_colonised: false,
      score: 88,
    }));
    expect(Object.values(useColonyProjectStore.getState().projects)).toHaveLength(0);

    fireEvent.click(screen.getByRole('button', { name: /Inspect system/i }));

    await waitFor(() => {
      expect(window.location.hash).toBe('#finder/system/777');
    });
    expect(screen.getByTestId('system-detail-modal').textContent).toContain('777');
    expect(screen.queryByTestId('colony-planner-workspace')).toBeNull();
  });

  it('lets Finder remove an already saved system through the same Watchlist path', async () => {
    seedFinderResult();
    mockWatchlistHas.mockImplementation((id64: number) => id64 === 777);
    window.location.hash = '#finder';

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Finder Candidate')).toBeTruthy();
    });

    fireEvent.click(screen.getByText('Finder Candidate'));
    fireEvent.click(screen.getByRole('button', { name: /Remove from saved/i }));

    await waitFor(() => {
      expect(mockWatchlistRemove).toHaveBeenCalledTimes(1);
    });
    expect(mockWatchlistRemove).toHaveBeenCalledWith(777);
    expect(mockWatchlistAdd).not.toHaveBeenCalled();
    expect(Object.values(useColonyProjectStore.getState().projects)).toHaveLength(0);
  });

  it('renders the compact player-facing Finder intro without internal shell labels', async () => {
    window.location.hash = '#finder';

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('nav-primary-explore')).toBeTruthy();
    });

    expect(screen.getByTestId('nav-primary-explore').textContent).toContain('Explore');
    expect(screen.getByTestId('nav-primary-plan').textContent).toContain('Plan');
    expect(screen.getByTestId('nav-primary-review').textContent).toContain('Review');
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

  it('keeps admin and operator out of the normal mobile player menu', async () => {
    window.location.hash = '#finder';

    render(<App />);

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

    render(<App />);

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
  it('keeps Finder inspect routes compact and clears selected-system context after leaving inspect/plan', async () => {
    window.location.hash = '#finder/system/123';

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('system-detail-modal').textContent).toContain('123');
    });
    expect(screen.getByTestId('finder-page-heading').textContent).toContain(
      'Find promising systems. Save them for later or inspect them before starting a plan.',
    );
    expect(screen.queryByTestId('product-shell-context')).toBeNull();
    expect(screen.queryByText('Primary workspace')).toBeNull();

    window.location.hash = '#my-work';
    fireEvent(window, new HashChangeEvent('hashchange'));

    await waitFor(() => {
      expect(screen.queryByText('System 123')).toBeNull();
    });
    expect(screen.queryByText(/ID64 123/i)).toBeNull();
  });

  it.each([
    ['#admin', 'admin-tab'],
    ['#operator', 'operator-tab'],
  ])('keeps direct %s route entries working with separate operator-mode framing', async (hash, tabTestId) => {
    window.location.hash = hash;

    render(<App />);

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
