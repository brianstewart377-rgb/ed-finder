import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { useColonyProjectStore } from '@/features/colony-planner/colonyProjectStore';
import { useMyWorkStore } from '@/features/my-work/myWorkStore';

const {
  mockWatchlistAdd,
  mockWatchlistRemove,
  mockWatchlistHas,
  mockWatchlistEntries,
  mockSearchRun,
  mockSearchResults,
  mockSearchState,
  mockUseSystemDetail,
} = vi.hoisted(() => ({
  mockWatchlistAdd: vi.fn(),
  mockWatchlistRemove: vi.fn(),
  mockWatchlistHas: vi.fn((_id64: number) => false),
  mockWatchlistEntries: [] as Array<Record<string, unknown>>,
  mockSearchRun: vi.fn().mockResolvedValue(undefined),
  mockSearchResults: [] as Array<Record<string, unknown>>,
  mockSearchState: {
    current: { kind: 'idle' } as Record<string, unknown>,
  },
  mockUseSystemDetail: vi.fn((id64: number | null) => ({
    data: id64 != null ? { id64, name: `System ${id64}` } : null,
    loading: false,
    error: null as string | null,
    refetch: vi.fn(),
  })),
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
    onClose,
    savedForLater,
    saveForLaterState = 'idle',
    onToggleSaveForLater,
    onStartPlan,
  }: {
    id64: number;
    onClose?: () => void;
    savedForLater?: boolean;
    saveForLaterState?: 'idle' | 'saving' | 'removing';
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
      <button type="button" onClick={onClose}>Close system details</button>
      <button
        type="button"
        disabled={saveForLaterState === 'saving' || saveForLaterState === 'removing'}
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
  useSystemDetail: mockUseSystemDetail,
}));

vi.mock('@/features/colony-planner/ColonyPlannerWorkspace', () => ({
  ColonyPlannerWorkspace: ({
    id64,
    projectId,
    invalidSystemRoute,
    invalidProjectRoute,
    system,
    onBackToFinder,
    onOpenSystemDetail,
    onCreateDraft,
  }: {
    id64: number | null;
    projectId?: string | null;
    invalidSystemRoute?: boolean;
    invalidProjectRoute?: boolean;
    system?: { id64: number; name: string } | null;
    onBackToFinder: () => void;
    onOpenSystemDetail: (id64: number) => void;
    onCreateDraft: (system: { id64: number; name: string }) => void;
  }) => (
    <div data-testid="colony-planner-workspace">
      Colony Planner workspace {id64 ?? 'none'} / {projectId ?? 'no-project'} / {system?.name ?? 'no-system'}
      {invalidSystemRoute ? <span>invalid-system-route</span> : null}
      {invalidProjectRoute ? <span>invalid-project-route</span> : null}
      <button type="button" onClick={onBackToFinder}>Back to Finder</button>
      <button type="button" onClick={() => id64 != null && onOpenSystemDetail(id64)}>Open full system detail</button>
      {system ? <button type="button" onClick={() => onCreateDraft(system)}>Create draft</button> : null}
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
  mockWatchlistEntries.length = 0;
  mockSearchRun.mockClear();
  mockSearchResults.length = 0;
  mockSearchState.current = { kind: 'idle' };
  mockUseSystemDetail.mockReset();
  mockUseSystemDetail.mockImplementation((id64: number | null) => ({
    data: id64 != null ? { id64, name: `System ${id64}` } : null,
    loading: false,
    error: null,
    refetch: vi.fn(),
  }));
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

  it('renders the dedicated workspace with selected-system shell context and without the System Detail modal', async () => {
    window.location.hash = '#colony-planner/system/123';

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('colony-planner-workspace').textContent).toContain('123');
    });
    expect(screen.getByTestId('navbar')).toBeTruthy();
    expect(screen.getByTestId('product-shell-context').textContent).toContain('System 123');
    expect(screen.getByTestId('product-shell-context').textContent).toContain('Evidence posture unavailable');
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

  it('renders the workspace no-system state for #colony-planner without selected-system shell context', async () => {
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

  it('renders non-modal Finder context without opening Inspect', async () => {
    window.location.hash = '#finder/context/123';

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Search form')).toBeTruthy();
    });
    expect(screen.getByTestId('product-shell-context').textContent).toContain('System 123');
    expect(screen.getByTestId('product-shell-context').textContent).toContain('Evidence posture unavailable');
    expect(screen.queryByTestId('system-detail-modal')).toBeNull();
  });

  it('returns Inspect close to Finder context', async () => {
    window.location.hash = '#finder/system/123';

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('system-detail-modal')).toBeTruthy();
    });

    fireEvent.click(screen.getByRole('button', { name: /Close system details/i }));

    await waitFor(() => {
      expect(window.location.hash).toBe('#finder/context/123');
    });
    expect(screen.queryByTestId('system-detail-modal')).toBeNull();
    expect(screen.getByTestId('product-shell-context').textContent).toContain('System 123');
  });

  it('returns Planner to Finder context without reopening Inspect', async () => {
    window.location.hash = '#colony-planner/system/123';

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('colony-planner-workspace')).toBeTruthy();
    });

    fireEvent.click(screen.getByRole('button', { name: /^Back to Finder$/i }));

    await waitFor(() => {
      expect(window.location.hash).toBe('#finder/context/123');
    });
    expect(screen.queryByTestId('system-detail-modal')).toBeNull();
  });

  it('clears stale selected-system shell context after a malformed Finder route replaces a valid one', async () => {
    window.location.hash = '#finder/context/123';

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('product-shell-context').textContent).toContain('System 123');
    });

    act(() => {
      window.location.hash = '#finder/system';
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    });

    await waitFor(() => {
      expect(screen.getByTestId('product-shell-context').textContent).toContain('Selected system route invalid');
    });
    expect(screen.getByTestId('product-shell-context').textContent).not.toContain('System 123');
    expect(screen.getByTestId('product-shell-context').textContent).not.toContain('Evidence posture unavailable');
    expect(screen.getByTestId('product-shell-context').textContent).not.toContain('ID64 123');
    expect(screen.queryByTestId('system-detail-modal')).toBeNull();
  });

  it('clears stale evidence posture and prior identity when a selected-system route becomes unavailable', async () => {
    window.location.hash = '#finder/context/123';

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('product-shell-context').textContent).toContain('System 123');
      expect(screen.getByTestId('product-shell-context').textContent).toContain('Evidence posture unavailable');
    });

    mockUseSystemDetail.mockImplementation((id64: number | null) => ({
      data: null,
      loading: false,
      error: id64 != null ? 'Not found' : null,
      refetch: vi.fn(),
    }));

    act(() => {
      window.location.hash = '#finder/context/999';
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    });

    await waitFor(() => {
      expect(screen.getByTestId('product-shell-context').textContent).toContain('Selected system unavailable');
    });
    expect(screen.getByTestId('product-shell-context').textContent).not.toContain('System 123');
    expect(screen.getByTestId('product-shell-context').textContent).not.toContain('Evidence posture unavailable');
    expect(screen.getByTestId('product-shell-context').textContent).not.toContain('ID64 123');
  });

  it('creates exactly one selected-system Draft from System Detail and opens its planner project', async () => {
    window.location.hash = '#finder/system/123';

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('system-detail-modal').textContent).toContain('123');
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

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('saved-system-909')).toBeTruthy();
    });
    expect(screen.getByTestId('saved-system-909').textContent).toContain('Existing Saved System');
    expect(screen.getByTestId('saved-system-909').textContent).toContain('Considering');
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
    await waitFor(() => {
      expect(screen.getByTestId('saved-system-notice').textContent).toContain('Saved to My Work');
    });
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

    render(<App />);

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

    render(<App />);

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

    render(<App />);

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
      score: 88,
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

  it('lets Finder remove an already saved system through the same Watchlist path', async () => {
    seedFinderResult();
    mockWatchlistHas.mockImplementation((id64: number) => id64 === 777);
    window.location.hash = '#finder';

    render(<App />);

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

    render(<App />);

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
    expect(screen.getByTestId('product-shell-context').textContent).toContain('System 123');
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
