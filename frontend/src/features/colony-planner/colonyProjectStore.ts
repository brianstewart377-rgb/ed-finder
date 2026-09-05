import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import {
  buildColonyProject,
  createColonyProjectId,
  duplicateColonyProject,
  normaliseColonyProjectRecord,
  normaliseColonyProjectStatus,
  type ColonyProject,
  type ColonyProjectInput,
  type ColonyProjectStatus,
} from '@ed-finder/planner-core/colonyProjectTypes';

export type {
  ColonyProject,
  ColonyProjectInput,
  ColonyProjectStatus,
} from '@ed-finder/planner-core/colonyProjectTypes';

export {
  activeProjectsForSystem,
  projectMatchesSnapshot,
} from '@ed-finder/planner-core/colonyProjectTypes';

interface ColonyProjectState {
  projects: Record<string, ColonyProject>;
  saveProject: (projectId: string | null, input: ColonyProjectInput) => ColonyProject;
  renameProject: (projectId: string, name: string) => void;
  updateProjectStatus: (projectId: string, status: ColonyProjectStatus) => void;
  duplicateProject: (projectId: string) => ColonyProject | null;
  archiveProject: (projectId: string) => void;
  deleteProject: (projectId: string) => void;
}

const STORAGE_KEY = 'ed_colony_projects_v1';
const SKIP_PERSIST_HYDRATION = import.meta.env.MODE === 'test';

export const useColonyProjectStore = create<ColonyProjectState>()(
  persist(
    (set, get) => ({
      projects: {},
      saveProject: (projectId, input) => {
        const now = new Date().toISOString();
        const existing = projectId ? get().projects[projectId] ?? null : null;
        const project = buildColonyProject(
          input,
          existing,
          now,
          existing?.id ?? createColonyProjectId(input.system_id64),
        );
        set((state) => ({ projects: { ...state.projects, [project.id]: project } }));
        return project;
      },
      renameProject: (projectId, name) => {
        const trimmed = name.trim();
        if (!trimmed) return;
        const project = get().projects[projectId];
        if (!project) return;
        const now = new Date().toISOString();
        set((state) => ({
          projects: {
            ...state.projects,
            [projectId]: { ...project, project_name: trimmed, updated_at: now },
          },
        }));
      },
      updateProjectStatus: (projectId, status) => {
        const project = get().projects[projectId];
        if (!project) return;
        const nextStatus = normaliseColonyProjectStatus(status);
        const now = new Date().toISOString();
        set((state) => ({
          projects: {
            ...state.projects,
            [projectId]: { ...project, status: nextStatus, updated_at: now },
          },
        }));
      },
      duplicateProject: (projectId) => {
        const source = get().projects[projectId];
        if (!source) return null;
        const now = new Date().toISOString();
        const duplicate = duplicateColonyProject(
          source,
          now,
          createColonyProjectId(source.system_id64),
        );
        set((state) => ({ projects: { ...state.projects, [duplicate.id]: duplicate } }));
        return duplicate;
      },
      archiveProject: (projectId) => {
        const project = get().projects[projectId];
        if (!project) return;
        const now = new Date().toISOString();
        set((state) => ({
          projects: {
            ...state.projects,
            [projectId]: { ...project, archived_at: now, updated_at: now },
          },
        }));
      },
      deleteProject: (projectId) => {
        set((state) => {
          const projects = { ...state.projects };
          delete projects[projectId];
          return { projects };
        });
      },
    }),
    {
      name: STORAGE_KEY,
      storage: createJSONStorage(() => localStorage),
      skipHydration: SKIP_PERSIST_HYDRATION,
      version: 3,
      migrate: (persistedState) => ({
        ...(persistedState as Partial<ColonyProjectState> | undefined),
        projects: normaliseColonyProjectRecord((persistedState as { projects?: unknown } | undefined)?.projects),
      }),
      merge: (persistedState, currentState) => ({
        ...currentState,
        ...(persistedState as Partial<ColonyProjectState> | undefined),
        projects: normaliseColonyProjectRecord((persistedState as { projects?: unknown } | undefined)?.projects),
      }),
    },
  ),
);

export function rehydrateColonyProjectStore(): Promise<void> {
  return Promise.resolve(useColonyProjectStore.persist.rehydrate());
}
