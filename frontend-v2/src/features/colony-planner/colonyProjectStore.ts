import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { SimulateBuildPlacement } from '@/types/api';

export type ColonyProjectStatus = 'draft' | 'previewed' | 'validated';

export interface ColonyProject {
  id: string;
  system_id64: number;
  system_name: string;
  project_name: string;
  build_plan_placements: SimulateBuildPlacement[];
  selected_body_assignments: Record<number, string | null>;
  target_archetype: string;
  notes: string;
  status: ColonyProjectStatus;
  created_at: string;
  updated_at: string;
  archived_at?: string | null;
}

export interface ColonyProjectInput {
  system_id64: number;
  system_name: string;
  project_name: string;
  build_plan_placements: SimulateBuildPlacement[];
  target_archetype: string;
  notes: string;
  status?: ColonyProjectStatus;
}

interface ColonyProjectState {
  projects: ColonyProject[];
  saveProject: (projectId: string | null, input: ColonyProjectInput) => ColonyProject;
  renameProject: (projectId: string, name: string) => void;
  duplicateProject: (projectId: string) => ColonyProject | null;
  archiveProject: (projectId: string) => void;
}

const STORAGE_KEY = 'ed_colony_projects_v1';

export const useColonyProjectStore = create<ColonyProjectState>()(
  persist(
    (set, get) => ({
      projects: [],
      saveProject: (projectId, input) => {
        const now = new Date().toISOString();
        const existing = projectId ? get().projects.find((project) => project.id === projectId) ?? null : null;
        const project: ColonyProject = {
          id: existing?.id ?? createProjectId(input.system_id64),
          system_id64: input.system_id64,
          system_name: input.system_name,
          project_name: input.project_name.trim() || `${input.system_name || 'Colony'} project`,
          build_plan_placements: clonePlacements(input.build_plan_placements),
          selected_body_assignments: bodyAssignments(input.build_plan_placements),
          target_archetype: input.target_archetype,
          notes: input.notes,
          status: input.status ?? existing?.status ?? 'draft',
          created_at: existing?.created_at ?? now,
          updated_at: now,
          archived_at: null,
        };
        set({
          projects: [
            project,
            ...get().projects.filter((item) => item.id !== project.id),
          ],
        });
        return project;
      },
      renameProject: (projectId, name) => {
        const trimmed = name.trim();
        if (!trimmed) return;
        const now = new Date().toISOString();
        set({
          projects: get().projects.map((project) => (
            project.id === projectId ? { ...project, project_name: trimmed, updated_at: now } : project
          )),
        });
      },
      duplicateProject: (projectId) => {
        const source = get().projects.find((project) => project.id === projectId);
        if (!source) return null;
        const now = new Date().toISOString();
        const duplicate: ColonyProject = {
          ...source,
          id: createProjectId(source.system_id64),
          project_name: `${source.project_name} copy`,
          build_plan_placements: clonePlacements(source.build_plan_placements),
          selected_body_assignments: { ...source.selected_body_assignments },
          status: 'draft',
          created_at: now,
          updated_at: now,
          archived_at: null,
        };
        set({ projects: [duplicate, ...get().projects] });
        return duplicate;
      },
      archiveProject: (projectId) => {
        const now = new Date().toISOString();
        set({
          projects: get().projects.map((project) => (
            project.id === projectId ? { ...project, archived_at: now, updated_at: now } : project
          )),
        });
      },
    }),
    {
      name: STORAGE_KEY,
      storage: createJSONStorage(() => localStorage),
    },
  ),
);

export function activeProjectsForSystem(projects: ColonyProject[], systemId64: number) {
  return projects
    .filter((project) => project.system_id64 === systemId64 && !project.archived_at)
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
}

export function projectMatchesSnapshot(
  project: ColonyProject | null,
  placements: SimulateBuildPlacement[],
  targetArchetype: string,
  notes: string,
  name: string,
) {
  if (!project) return placements.length === 0 && notes.trim() === '';
  return project.project_name === name
    && project.target_archetype === targetArchetype
    && project.notes === notes
    && JSON.stringify(project.build_plan_placements) === JSON.stringify(clonePlacements(placements));
}

function clonePlacements(placements: SimulateBuildPlacement[]) {
  return placements.map((placement) => ({ ...placement }));
}

function bodyAssignments(placements: SimulateBuildPlacement[]) {
  return placements.reduce<Record<number, string | null>>((assignments, placement, index) => {
    assignments[index] = placement.local_body_id ?? null;
    return assignments;
  }, {});
}

function createProjectId(systemId64: number) {
  const random = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `colony-${systemId64}-${random}`;
}
