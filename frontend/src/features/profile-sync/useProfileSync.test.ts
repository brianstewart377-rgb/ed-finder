import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useColonyProjectStore } from '@/features/colony-planner/colonyProjectStore';
import { useMyWorkStore } from '@/features/my-work/myWorkStore';
import { api } from '@/lib/api';
import { usePinnedStore } from '@/store/pinnedStore';
import { useProfileSync } from './useProfileSync';

vi.mock('@/lib/api', () => ({
  api: {
    profileSyncPull: vi.fn(),
    profileSyncPush: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    constructor(
      public readonly status: number,
      public readonly path: string,
      public readonly body: string,
    ) {
      super(`API ${status} on ${path}: ${body}`);
      this.name = 'ApiError';
    }
  },
}));

describe('useProfileSync', () => {
  beforeEach(() => {
    localStorage.clear();
    usePinnedStore.setState({ entries: [] });
    useMyWorkStore.setState({ systems: {} });
    useColonyProjectStore.setState({ projects: {} });
    vi.mocked(api.profileSyncPull).mockReset();
    vi.mocked(api.profileSyncPush).mockReset();
  });

  it('pull() restores pinned, My Work, and planner drafts into current-tab state', async () => {
    vi.mocked(api.profileSyncPull).mockResolvedValue({
      blob: {
        version: 1,
        exported_at: '2026-07-07T00:00:00Z',
        ed_pinned: [{
          id64: 42,
          name: 'Pinned System',
          x: 1,
          y: 2,
          z: 3,
          population: 0,
          is_colonised: false,
          economy: 'Refinery',
          pinned_at: '2026-07-07T00:00:00Z',
        }],
        ed_my_work_v1: {
          state: {
            systems: {
              '42': {
                id64: 42,
                name: 'Pinned System',
                x: 1,
                y: 2,
                z: 3,
                population: 0,
                is_colonised: false,
                labels: ['ready_to_plan'],
                explicit_colonised_at: null,
                updated_at: '2026-07-07T00:00:00Z',
              },
            },
          },
          version: 1,
        },
        ed_colony_projects_v1: {
          state: {
            projects: {
              'draft-42': {
                id: 'draft-42',
                system_id64: 42,
                system_name: 'Pinned System',
                project_name: 'Pinned System - Materials coverage',
                build_plan_placements: [],
                selected_body_assignments: {},
                declared_roles: [],
                target_archetype: 'refinery_industrial',
                notes: '',
                status: 'draft',
                objective: 'materials_coverage',
                start_approach: 'manual',
                created_from: 'system_detail',
                created_at: '2026-07-07T00:00:00Z',
                updated_at: '2026-07-07T00:00:00Z',
                archived_at: null,
              },
            },
          },
          version: 3,
        },
      },
      blob_bytes: 512,
      updated_at: '2026-07-07T00:00:00Z',
    } as never);

    const { result } = renderHook(() => useProfileSync());

    act(() => {
      result.current.setSyncKey('sync-key-1234567890');
    });

    await act(async () => {
      await result.current.pull();
    });

    await waitFor(() => {
      expect(usePinnedStore.getState().entries).toHaveLength(1);
      expect(useMyWorkStore.getState().systems['42']?.labels).toEqual(['ready_to_plan']);
      expect(useColonyProjectStore.getState().projects['draft-42']?.system_id64).toBe(42);
    });
  });

  it('push() includes current My Work and planner draft payloads', async () => {
    localStorage.setItem('ed_pinned', JSON.stringify([{
      id64: 99,
      name: 'Sync System',
      x: 0,
      y: 0,
      z: 0,
      population: 0,
      is_colonised: false,
      economy: 'Tourism',
      pinned_at: '2026-07-07T00:00:00Z',
    }]));
    localStorage.setItem('ed_my_work_v1', JSON.stringify({
      state: {
        systems: {
          '99': {
            id64: 99,
            name: 'Sync System',
            x: 0,
            y: 0,
            z: 0,
            population: 0,
            is_colonised: false,
            labels: ['considering'],
            explicit_colonised_at: null,
            updated_at: '2026-07-07T00:00:00Z',
          },
        },
      },
      version: 1,
    }));
    localStorage.setItem('ed_colony_projects_v1', JSON.stringify({
      state: {
        projects: {
          'draft-99': {
            id: 'draft-99',
            system_id64: 99,
            system_name: 'Sync System',
            project_name: 'Sync draft',
            build_plan_placements: [],
            selected_body_assignments: {},
            declared_roles: [],
            target_archetype: 'trade_logistics',
            notes: 'sync me',
            status: 'draft',
            objective: 'balanced',
            start_approach: 'manual',
            created_from: 'system_detail',
            created_at: '2026-07-07T00:00:00Z',
            updated_at: '2026-07-07T00:00:00Z',
            archived_at: null,
          },
        },
      },
      version: 3,
    }));
    vi.mocked(api.profileSyncPush).mockResolvedValue({
      updated_at: '2026-07-07T00:00:00Z',
      blob_bytes: 1024,
    } as never);

    const { result } = renderHook(() => useProfileSync());

    act(() => {
      result.current.setSyncKey('sync-key-1234567890');
    });

    await act(async () => {
      await result.current.push();
    });

    expect(api.profileSyncPush).toHaveBeenCalledWith(
      'sync-key-1234567890',
      expect.objectContaining({
        ed_my_work_v1: expect.objectContaining({
          state: expect.objectContaining({
            systems: expect.objectContaining({
              '99': expect.objectContaining({ name: 'Sync System' }),
            }),
          }),
        }),
        ed_colony_projects_v1: expect.objectContaining({
          state: expect.objectContaining({
            projects: expect.objectContaining({
              'draft-99': expect.objectContaining({ project_name: 'Sync draft' }),
            }),
          }),
        }),
      }),
    );
  });
});
