import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MyWorkWorkspace } from './MyWorkWorkspace';
import { useColonyProjectStore } from '@/features/colony-planner/colonyProjectStore';
import { useMyWorkStore } from './myWorkStore';
import type { UseWatchlist } from '@/features/watchlist/useWatchlist';
import type { UsePinned } from '@/features/pinned/usePinned';

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

afterEach(() => {
  localStorage.clear();
  useColonyProjectStore.setState({ projects: {} });
  useMyWorkStore.setState({ systems: {} });
});

describe('MyWorkWorkspace', () => {
  it('merges existing Watchlist, Pins, and local ready-to-plan labels into Saved Systems', async () => {
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
        rating: 77,
        economy: 'Refinery',
        pinned_at: '2026-06-22T11:00:00.000Z',
      }],
      has: vi.fn((id64: number) => id64 === 101),
    });
    useMyWorkStore.getState().setLabel({
      id64: 101,
      name: 'Wregoe',
      x: 1,
      y: 2,
      z: 3,
      population: 0,
      is_colonised: false,
    }, 'ready_to_plan', true);

    render(
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
  });

  it('removes saved systems safely across Watchlist, Pins, and local saved labels', async () => {
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
        rating: null,
        economy: null,
        pinned_at: '2026-06-22T11:00:00.000Z',
      }],
      remove: pinnedRemove,
      has: vi.fn((id64: number) => id64 === 101),
    });
    useMyWorkStore.getState().setLabel({
      id64: 101,
      name: 'Wregoe',
      x: 1,
      y: 2,
      z: 3,
      population: 0,
      is_colonised: false,
    }, 'ready_to_plan', true);

    render(
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
    const onOpenPlanner = vi.fn();
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
    const projectB = useColonyProjectStore.getState().saveProject(null, {
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

    render(
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
    expect(screen.getByTestId(`plan-card-${projectB.id}`).textContent).toContain('ED-Finder recommendation');
    expect(screen.getByTestId('my-work-plans').textContent).toContain('Objective not set');

    fireEvent.click(withinPlan(projectB.id, /Rename/i));
    fireEvent.change(screen.getByDisplayValue('HIP 200 - Materials coverage'), { target: { value: 'HIP 200 - Final draft' } });
    fireEvent.click(screen.getByRole('button', { name: /Save name/i }));
    expect(useColonyProjectStore.getState().projects[projectB.id]?.project_name).toBe('HIP 200 - Final draft');

    fireEvent.change(screen.getByTestId(`plan-status-${projectB.id}`), { target: { value: 'building' } });
    expect(useColonyProjectStore.getState().projects[projectB.id]?.status).toBe('building');

    fireEvent.click(withinPlan(projectB.id, /Duplicate/i));
    expect(Object.values(useColonyProjectStore.getState().projects).some((project) => project.project_name === 'HIP 200 - Final draft - Copy')).toBe(true);

    fireEvent.click(withinPlan(projectB.id, /Continue plan/i));
    expect(onOpenPlanner).toHaveBeenCalledWith(200, { projectId: projectB.id });
  });

  it('shows established plans in My Colonies and updates safely when status changes', async () => {
    const project = useColonyProjectStore.getState().saveProject(null, {
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

    render(
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
    fireEvent.change(screen.getByTestId(`plan-status-${project.id}`), { target: { value: 'building' } });
    fireEvent.click(screen.getByTestId('my-work-section-my-colonies'));

    await waitFor(() => {
      expect(screen.getByTestId('my-work-colonies').textContent).toContain('No colonies marked yet');
    });
  });

  it('prefers the most recently updated active plan for continuation and falls back to a recent saved system', () => {
    const activePlan = useColonyProjectStore.getState().saveProject(null, {
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
        [activePlan.id]: {
          ...state.projects[activePlan.id],
          updated_at: '2026-06-23T15:00:00.000Z',
        },
      },
    }));

    const { rerender } = render(
      <MyWorkWorkspace
        watchlist={makeWatchlist()}
        pinned={makePinned()}
        onOpenDetail={vi.fn()}
        onOpenPlanner={vi.fn()}
      />,
    );

    expect(screen.getByTestId('my-work-continuation').textContent).toContain('Continue planning');
    expect(screen.getByTestId('my-work-continuation').textContent).toContain('Recent Plan - Recent Plan - New plan');

    useColonyProjectStore.setState({ projects: {} });
    rerender(
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
      />,
    );

    expect(screen.getByTestId('my-work-continuation').textContent).toContain('Ready to revisit');
    expect(screen.getByTestId('my-work-continuation').textContent).toContain('Saved System');
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
