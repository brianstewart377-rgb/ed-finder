import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MyWorkWorkspace } from './MyWorkWorkspace';
import { useColonyProjectStore, type ColonyProject } from '@/features/colony-planner/colonyProjectStore';
import { useMyWorkStore } from './myWorkStore';
import type { UseWatchlist } from '@/features/watchlist/useWatchlist';
import type { UsePinned } from '@/features/pinned/usePinned';
import { useJournalTelemetrySummary } from './useJournalTelemetrySummary';
import type { JournalTelemetrySummaryResponse } from '@/types/api';

vi.mock('./useJournalTelemetrySummary', () => ({
  useJournalTelemetrySummary: vi.fn(),
}));

const mockUseJournalTelemetrySummary = vi.mocked(useJournalTelemetrySummary);

function makeJournalTelemetryQueryResult(
  data?: JournalTelemetrySummaryResponse,
): ReturnType<typeof useJournalTelemetrySummary> {
  return {
    data,
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useJournalTelemetrySummary>;
}

function makeWatchlist(overrides: Partial<UseWatchlist> = {}): UseWatchlist {
  return {
    entries: [],
    loading: false,
    error: null,
    refresh: vi.fn(),
    add: vi.fn().mockResolvedValue(undefined),
    remove: vi.fn().mockResolvedValue(undefined),
    has: vi.fn(() => false),
    ...overrides,
  };
}

function makePinned(overrides: Partial<UsePinned> = {}): UsePinned {
  return {
    entries: [],
    has: vi.fn(() => false),
    toggle: vi.fn(() => true),
    remove: vi.fn(),
    clear: vi.fn(),
    exportJson: vi.fn(),
    ...overrides,
  };
}

function renderWorkspace(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      {ui}
    </QueryClientProvider>,
  );
}

function runStoreUpdate(update: () => void) {
  act(() => {
    update();
  });
}

afterEach(() => {
  localStorage.clear();
  runStoreUpdate(() => {
    useColonyProjectStore.setState({ projects: {} });
    useMyWorkStore.setState({ systems: {} });
  });
  mockUseJournalTelemetrySummary.mockReset();
});

describe('MyWorkWorkspace', () => {
  it('shows a telemetry section tab alongside saved systems, plans, and colonies', () => {
    mockUseJournalTelemetrySummary.mockReturnValue(makeJournalTelemetryQueryResult());

    renderWorkspace(
      <MyWorkWorkspace
        watchlist={makeWatchlist()}
        pinned={makePinned()}
        onOpenDetail={vi.fn()}
        onOpenPlanner={vi.fn()}
      />,
    );

    expect(screen.getByTestId('my-work-section-tabs').textContent).toContain('Telemetry');
  });

  it('keeps the local My Work header concise with section tabs intact', () => {
    mockUseJournalTelemetrySummary.mockReturnValue(makeJournalTelemetryQueryResult());

    renderWorkspace(
      <MyWorkWorkspace
        watchlist={makeWatchlist()}
        pinned={makePinned()}
        onOpenDetail={vi.fn()}
        onOpenPlanner={vi.fn()}
      />,
    );

    expect(screen.getByRole('heading', { name: 'My Work' })).toBeTruthy();
    expect(screen.queryByText('Player workspace')).toBeNull();
    expect(screen.getByText('Saved systems, plans, and colonies in one place.')).toBeTruthy();
    expect(screen.getByText('Journal Import')).toBeTruthy();
    expect(screen.getByTestId('my-work-section-tabs').textContent).toContain('Saved Systems');
    expect(screen.getByTestId('my-work-section-tabs').textContent).toContain('Plans');
    expect(screen.getByTestId('my-work-section-tabs').textContent).toContain('My Colonies');
    expect(screen.getByTestId('my-work-section-tabs').textContent).toContain('Telemetry');
  });
  it('merges existing Watchlist, Pins, and local ready-to-plan labels into Saved Systems', async () => {
    mockUseJournalTelemetrySummary.mockReturnValue(makeJournalTelemetryQueryResult({
        sync_key: 'sync-key-1234567890',
        runs_count: 1,
        last_imported_at: '2026-07-11T11:00:00.000Z',
        observations_staged: 3,
        duplicates_skipped: 0,
        systems_observed: 1,
        body_observation_count: 2,
        docked_observation_count: 1,
        event_counts: { Scan: 2, Docked: 1 },
        recent_runs: [],
        recent_systems: [{
          system_id64: 101,
          system_name: 'Wregoe',
          last_observed_at: '2026-07-11T11:05:00.000Z',
          event_count: 3,
          event_types: ['Docked', 'Scan'],
        }],
      }));

    const watchlist = makeWatchlist({
      entries: [{
        system_id64: 101,
        name: 'Wregoe',
        x: 1,
        y: 2,
        z: 3,
        population: 0,
        is_colonised: false,
        added_at: '2026-06-22T10:00:00.000Z',
        score: 77,
        economy_suggestion: 'Refinery',
      }],
      has: vi.fn((id64: number) => id64 === 101),
    });
    const pinned = makePinned({
      entries: [{
        id64: 101,
        name: 'Wregoe',
        x: 1,
        y: 2,
        z: 3,
        population: 0,
        is_colonised: false,
        distance: null,
        economy: 'Refinery',
        pinned_at: '2026-06-22T11:00:00.000Z',
      }],
      has: vi.fn((id64: number) => id64 === 101),
    });
    runStoreUpdate(() => {
      useMyWorkStore.getState().setLabel({
        id64: 101,
        name: 'Wregoe',
        x: 1,
        y: 2,
        z: 3,
        population: 0,
        is_colonised: false,
      }, 'ready_to_plan', true);
    });

    renderWorkspace(
      <MyWorkWorkspace
        watchlist={watchlist}
        pinned={pinned}
        onOpenDetail={vi.fn()}
        onOpenPlanner={vi.fn()}
      />,
    );

    expect(screen.getByTestId('saved-system-101').textContent).toContain('Wregoe');
    expect(screen.getByTestId('saved-system-101').textContent).toContain('Considering');
    expect(screen.getByTestId('saved-system-101').textContent).toContain('Favourite');
    expect(screen.getByTestId('saved-system-101').textContent).toContain('Ready to plan');
    expect(screen.getByTestId('saved-system-101').textContent).toContain('Personal telemetry imported');
    expect(screen.getByTestId('saved-system-101').textContent).toContain('Docked, Scan');
    expect(within(screen.getByTestId('saved-system-101')).getByRole('button', { name: /Favourite enabled/i }).getAttribute('aria-pressed')).toBe('true');
  });

  it('removes saved systems safely across Watchlist, Pins, and local saved labels', async () => {
    mockUseJournalTelemetrySummary.mockReturnValue(makeJournalTelemetryQueryResult());

    const watchlistRemove = vi.fn().mockResolvedValue(undefined);
    const pinnedRemove = vi.fn();
    const watchlist = makeWatchlist({
      entries: [{
        system_id64: 101,
        name: 'Wregoe',
        x: 1,
        y: 2,
        z: 3,
        population: 0,
        is_colonised: false,
        added_at: '2026-06-22T10:00:00.000Z',
      }],
      remove: watchlistRemove,
      has: vi.fn((id64: number) => id64 === 101),
    });
    const pinned = makePinned({
      entries: [{
        id64: 101,
        name: 'Wregoe',
        x: 1,
        y: 2,
        z: 3,
        population: 0,
        is_colonised: false,
        economy: null,
        pinned_at: '2026-06-22T11:00:00.000Z',
      }],
      remove: pinnedRemove,
      has: vi.fn((id64: number) => id64 === 101),
    });
    runStoreUpdate(() => {
      useMyWorkStore.getState().setLabel({
        id64: 101,
        name: 'Wregoe',
        x: 1,
        y: 2,
        z: 3,
        population: 0,
        is_colonised: false,
      }, 'ready_to_plan', true);
    });

    renderWorkspace(
      <MyWorkWorkspace
        watchlist={watchlist}
        pinned={pinned}
        onOpenDetail={vi.fn()}
        onOpenPlanner={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Remove from saved/i }));

    await waitFor(() => {
      expect(watchlistRemove).toHaveBeenCalledWith(101);
    });
    expect(pinnedRemove).toHaveBeenCalledWith(101);
    expect(Object.values(useColonyProjectStore.getState().projects)).toHaveLength(0);
  });

  it('groups plans by system, supports rename, duplication, status changes, and continue-plan routing', async () => {
    mockUseJournalTelemetrySummary.mockReturnValue(makeJournalTelemetryQueryResult());

    const onOpenPlanner = vi.fn();
    let projectB: ColonyProject | undefined;
    runStoreUpdate(() => {
      useColonyProjectStore.getState().saveProject(null, {
        system_id64: 200,
        system_name: 'HIP 200',
        project_name: 'HIP 200 - Balanced plan',
        build_plan_placements: [],
        target_archetype: 'refinery_industrial',
        notes: '',
        status: 'draft',
        objective: 'balanced',
        start_approach: 'manual',
        created_from: 'system_detail',
      });
      projectB = useColonyProjectStore.getState().saveProject(null, {
        system_id64: 200,
        system_name: 'HIP 200',
        project_name: 'HIP 200 - Materials coverage',
        build_plan_placements: [],
        target_archetype: 'refinery_industrial',
        notes: '',
        status: 'draft',
        objective: 'materials_coverage',
        start_approach: 'recommendation_assisted',
        created_from: 'system_detail',
      });
      useColonyProjectStore.getState().saveProject(null, {
        system_id64: 300,
        system_name: 'HIP 300',
        project_name: 'Legacy project',
        build_plan_placements: [],
        target_archetype: 'refinery_industrial',
        notes: '',
      });
    });
    const seededProjectB = projectB!;

    renderWorkspace(
      <MyWorkWorkspace
        initialSection="plans"
        watchlist={makeWatchlist()}
        pinned={makePinned()}
        onOpenDetail={vi.fn()}
        onOpenPlanner={onOpenPlanner}
      />,
    );

    expect(screen.getByTestId('my-work-plans').textContent).toContain('HIP 200');
    expect(screen.getByTestId('my-work-plans').textContent).toContain('2 plans');
    expect(screen.getByTestId(`plan-card-${seededProjectB.id}`).textContent).toContain('ED-Finder recommendation');
    expect(screen.getByTestId('my-work-plans').textContent).toContain('Objective not set');

    fireEvent.click(withinPlan(seededProjectB.id, /Rename/i));
    fireEvent.change(screen.getByDisplayValue('HIP 200 - Materials coverage'), { target: { value: 'HIP 200 - Final draft' } });
    fireEvent.click(screen.getByRole('button', { name: /Save name/i }));
    expect(useColonyProjectStore.getState().projects[seededProjectB.id]?.project_name).toBe('HIP 200 - Final draft');

    fireEvent.change(screen.getByTestId(`plan-status-${seededProjectB.id}`), { target: { value: 'building' } });
    expect(useColonyProjectStore.getState().projects[seededProjectB.id]?.status).toBe('building');

    fireEvent.click(withinPlan(seededProjectB.id, /Duplicate/i));
    expect(Object.values(useColonyProjectStore.getState().projects).some((project) => project.project_name === 'HIP 200 - Final draft - Copy')).toBe(true);

    fireEvent.click(withinPlan(seededProjectB.id, /Continue plan/i));
    expect(onOpenPlanner).toHaveBeenCalledWith(200, { projectId: seededProjectB.id });
  });

  it('shows established plans in My Colonies and updates safely when status changes', async () => {
    mockUseJournalTelemetrySummary.mockReturnValue(makeJournalTelemetryQueryResult());

    let project: ColonyProject | undefined;
    runStoreUpdate(() => {
      project = useColonyProjectStore.getState().saveProject(null, {
        system_id64: 400,
        system_name: 'Established System',
        project_name: 'Established System - New plan',
        build_plan_placements: [],
        target_archetype: 'refinery_industrial',
        notes: '',
        status: 'established',
        objective: 'decide_later',
        start_approach: 'manual',
        created_from: 'system_detail',
      });
    });
    const establishedProject = project!;

    renderWorkspace(
      <MyWorkWorkspace
        initialSection="my-colonies"
        watchlist={makeWatchlist()}
        pinned={makePinned()}
        onOpenDetail={vi.fn()}
        onOpenPlanner={vi.fn()}
      />,
    );

    expect(screen.getByTestId('my-work-colonies').textContent).toContain('player-managed planning state');
    expect(screen.getByTestId('my-work-colonies').textContent).toContain('Established System');

    fireEvent.click(screen.getByTestId('my-work-section-plans'));
    fireEvent.change(screen.getByTestId(`plan-status-${establishedProject.id}`), { target: { value: 'building' } });
    fireEvent.click(screen.getByTestId('my-work-section-my-colonies'));

    await waitFor(() => {
      expect(screen.getByTestId('my-work-colonies').textContent).toContain('No colonies marked yet');
    });
  });

  it('prefers the most recently updated active plan for continuation and falls back to a recent saved system', () => {
    mockUseJournalTelemetrySummary.mockReturnValue(makeJournalTelemetryQueryResult());

    let activePlan: ColonyProject | undefined;
    runStoreUpdate(() => {
      activePlan = useColonyProjectStore.getState().saveProject(null, {
        system_id64: 500,
        system_name: 'Recent Plan',
        project_name: 'Recent Plan - New plan',
        build_plan_placements: [],
        target_archetype: 'refinery_industrial',
        notes: '',
        status: 'draft',
      });
      useColonyProjectStore.setState((state) => ({
        projects: {
          ...state.projects,
          [activePlan!.id]: {
            ...state.projects[activePlan!.id],
            updated_at: '2026-06-23T15:00:00.000Z',
          },
        },
      }));
    });
    const { rerender } = renderWorkspace(
      <MyWorkWorkspace
        watchlist={makeWatchlist()}
        pinned={makePinned()}
        onOpenDetail={vi.fn()}
        onOpenPlanner={vi.fn()}
      />,
    );

    expect(screen.getByTestId('my-work-continuation').textContent).toContain('Continue planning');
    expect(screen.getByTestId('my-work-continuation').textContent).toContain('Recent Plan - Recent Plan - New plan');

    runStoreUpdate(() => {
      useColonyProjectStore.setState({ projects: {} });
    });
    rerender(
      <QueryClientProvider client={new QueryClient({
        defaultOptions: {
          queries: { retry: false },
          mutations: { retry: false },
        },
      })}>
        <MyWorkWorkspace
          watchlist={makeWatchlist({
            entries: [{
              system_id64: 501,
              name: 'Saved System',
              x: null,
              y: null,
              z: null,
              population: null,
              is_colonised: false,
              added_at: '2026-06-23T16:00:00.000Z',
            }],
            has: vi.fn((id64: number) => id64 === 501),
          })}
          pinned={makePinned()}
          onOpenDetail={vi.fn()}
          onOpenPlanner={vi.fn()}
        />
      </QueryClientProvider>,
    );

    expect(screen.getByTestId('my-work-continuation').textContent).toContain('Ready to revisit');
    expect(screen.getByTestId('my-work-continuation').textContent).toContain('Saved System');
  });

  it('renders a telemetry section with recent runs and observed systems', () => {
    const onOpenDetail = vi.fn();
    mockUseJournalTelemetrySummary.mockReturnValue(makeJournalTelemetryQueryResult({
        sync_key: 'sync-key-1234567890',
        runs_count: 2,
        last_imported_at: '2026-07-11T12:00:00.000Z',
        observations_staged: 5,
        duplicates_skipped: 1,
        systems_observed: 2,
        body_observation_count: 3,
        docked_observation_count: 1,
        event_counts: { Scan: 3, Docked: 1, Location: 1 },
        recent_runs: [{
          run_key: 'jrnl-20260711-demo',
          status: 'succeeded',
          started_at: '2026-07-11T11:00:00.000Z',
          finished_at: '2026-07-11T11:00:10.000Z',
          observations_staged: 3,
          duplicates_skipped: 1,
          event_counts: { Scan: 2, Docked: 1 },
        }],
        recent_systems: [{
          system_id64: 777,
          system_name: 'Telemetry System',
          last_observed_at: '2026-07-11T11:59:00.000Z',
          event_count: 3,
          event_types: ['Docked', 'Scan'],
        }],
      }));

    renderWorkspace(
      <MyWorkWorkspace
        initialSection="telemetry"
        watchlist={makeWatchlist()}
        pinned={makePinned()}
        onOpenDetail={onOpenDetail}
        onOpenPlanner={vi.fn()}
      />,
    );

    expect(screen.getByTestId('my-work-telemetry').textContent).toContain('Observed systems');
    expect(screen.getByTestId('my-work-telemetry').textContent).toContain('Telemetry System');
    expect(screen.getByTestId('my-work-telemetry').textContent).toContain('jrnl-20260711-demo');
    fireEvent.click(screen.getByRole('button', { name: /Inspect system/i }));
    expect(onOpenDetail).toHaveBeenCalledWith(777, undefined);
  });
});

function withinPlan(projectId: string, name: RegExp) {
  const card = screen.getByTestId(`plan-card-${projectId}`);
  const buttons = card.querySelectorAll('button');
  const match = Array.from(buttons).find((button) => name.test(button.textContent ?? ''));
  if (!match) {
    throw new Error(`No button matching ${name} for plan ${projectId}`);
  }
  return match as HTMLButtonElement;
}
