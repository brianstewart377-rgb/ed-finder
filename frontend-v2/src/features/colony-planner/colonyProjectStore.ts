import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { SimulateBuildPlacement } from '@/types/api';
import { normaliseDeclaredRoles, type DeclaredColonyRole } from './colonyRoles';
import type {
  ColonyProjectCreatedFrom,
  ColonyProjectObjective,
  ColonyProjectStartApproach,
} from './plannerDraftContext';

export type ColonyProjectStatus = 'draft' | 'ready_to_build' | 'building' | 'established';

export interface ColonyProject {
  id: string;
  system_id64: number;
  system_name: string;
  project_name: string;
  build_plan_placements: SimulateBuildPlacement[];
  selected_body_assignments: Record<number, string | null>;
  declared_roles: DeclaredColonyRole[];
  target_archetype: string;
  notes: string;
  status: ColonyProjectStatus;
  objective?: ColonyProjectObjective | null;
  start_approach?: ColonyProjectStartApproach | null;
  created_from?: ColonyProjectCreatedFrom | null;
  created_at: string;
  updated_at: string;
  archived_at?: string | null;
}

export interface ColonyProjectInput {
  system_id64: number;
  system_name: string;
  project_name: string;
  build_plan_placements: SimulateBuildPlacement[];
  declared_roles?: DeclaredColonyRole[];
  target_archetype: string;
  notes: string;
  status?: ColonyProjectStatus;
  objective?: ColonyProjectObjective | null;
  start_approach?: ColonyProjectStartApproach | null;
  created_from?: ColonyProjectCreatedFrom | null;
}

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

export const useColonyProjectStore = create<ColonyProjectState>()(
  persist(
    (set, get) => ({
      projects: {},
      saveProject: (projectId, input) => {
        const now = new Date().toISOString();
        const existing = projectId ? get().projects[projectId] ?? null : null;
        const project: ColonyProject = {
          id: existing?.id ?? createProjectId(input.system_id64),
          system_id64: input.system_id64,
          system_name: input.system_name,
          project_name: input.project_name.trim() || `${input.system_name || 'Colony'} project`,
          build_plan_placements: clonePlacements(input.build_plan_placements),
          selected_body_assignments: bodyAssignments(input.build_plan_placements),
          declared_roles: normaliseDeclaredRoles(input.declared_roles ?? existing?.declared_roles ?? []),
          target_archetype: input.target_archetype,
          notes: input.notes,
          status: input.status ?? existing?.status ?? 'draft',
          objective: input.objective ?? existing?.objective ?? null,
          start_approach: input.start_approach ?? existing?.start_approach ?? null,
          created_from: input.created_from ?? existing?.created_from ?? null,
          created_at: existing?.created_at ?? now,
          updated_at: now,
          archived_at: null,
        };
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
        const nextStatus = normaliseProjectStatus(status);
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
        const duplicate: ColonyProject = {
          ...source,
          id: createProjectId(source.system_id64),
          project_name: `${source.project_name} - Copy`,
          build_plan_placements: clonePlacements(source.build_plan_placements),
          selected_body_assignments: { ...source.selected_body_assignments },
          declared_roles: normaliseDeclaredRoles(source.declared_roles),
          status: 'draft',
          created_at: now,
          updated_at: now,
          archived_at: null,
        };
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
      version: 3,
      migrate: (persistedState) => ({
        ...(persistedState as Partial<ColonyProjectState> | undefined),
        projects: normaliseProjectRecord((persistedState as { projects?: unknown } | undefined)?.projects),
      }),
      merge: (persistedState, currentState) => ({
        ...currentState,
        ...(persistedState as Partial<ColonyProjectState> | undefined),
        projects: normaliseProjectRecord((persistedState as { projects?: unknown } | undefined)?.projects),
      }),
    },
  ),
);

export function activeProjectsForSystem(projects: ColonyProject[], systemId64: number) {
  return projects
    .filter((project) => project.system_id64 === systemId64 && !project.archived_at)
    .map((project) => ({
      ...project,
      build_plan_placements: clonePlacements(project.build_plan_placements),
      selected_body_assignments: project.selected_body_assignments && typeof project.selected_body_assignments === 'object'
        ? project.selected_body_assignments
        : {},
      declared_roles: normaliseDeclaredRoles(project.declared_roles),
      objective: project.objective ?? null,
      start_approach: project.start_approach ?? null,
      created_from: project.created_from ?? null,
      status: normaliseProjectStatus(project.status),
    }))
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
}

export function projectMatchesSnapshot(
  project: ColonyProject | null,
  placements: SimulateBuildPlacement[],
  targetArchetype: string,
  notes: string,
  name: string,
  declaredRoles: DeclaredColonyRole[] = [],
) {
  if (!project) return placements.length === 0 && notes.trim() === '' && declaredRoles.length === 0;
  return project.project_name === name
    && project.target_archetype === targetArchetype
    && project.notes === notes
    && JSON.stringify(project.build_plan_placements) === JSON.stringify(clonePlacements(placements))
    && JSON.stringify(normaliseDeclaredRoles(project.declared_roles)) === JSON.stringify(normaliseDeclaredRoles(declaredRoles));
}

function clonePlacements(placements: SimulateBuildPlacement[]) {
  if (!Array.isArray(placements)) return [];
  return placements
    .map<SimulateBuildPlacement | null>((placement, index) => {
      if (!placement || typeof placement !== 'object') return null;
      const candidate = placement as Partial<SimulateBuildPlacement>;
      if (typeof candidate.facility_template_id !== 'string' || !candidate.facility_template_id.trim()) return null;
      const buildOrder = typeof candidate.build_order === 'number' && Number.isFinite(candidate.build_order)
        ? candidate.build_order
        : index + 1;
      const normalised: SimulateBuildPlacement = {
        facility_template_id: candidate.facility_template_id,
        local_body_id: candidate.local_body_id == null ? null : String(candidate.local_body_id),
        is_primary_port: Boolean(candidate.is_primary_port),
        build_order: buildOrder,
      };
      return normalised;
    })
    .filter((placement): placement is SimulateBuildPlacement => Boolean(placement));
}

function bodyAssignments(placements: SimulateBuildPlacement[]) {
  return placements.reduce<Record<number, string | null>>((assignments, placement, index) => {
    assignments[index] = placement.local_body_id ?? null;
    return assignments;
  }, {});
}

function normaliseProjectRecord(projects: unknown): Record<string, ColonyProject> {
  const entries = Array.isArray(projects)
    ? projects
    : projects && typeof projects === 'object'
      ? Object.values(projects)
      : [];

  return entries.reduce<Record<string, ColonyProject>>((record, project) => {
    if (!project || typeof project !== 'object') return record;
    const candidate = project as ColonyProject;
    if (!candidate.id) return record;
    record[candidate.id] = {
      ...candidate,
      build_plan_placements: clonePlacements(candidate.build_plan_placements),
      selected_body_assignments: candidate.selected_body_assignments && typeof candidate.selected_body_assignments === 'object'
        ? candidate.selected_body_assignments
        : {},
      declared_roles: normaliseDeclaredRoles(candidate.declared_roles),
      objective: candidate.objective ?? null,
      start_approach: candidate.start_approach ?? null,
      created_from: candidate.created_from ?? null,
      status: normaliseProjectStatus(candidate.status),
      archived_at: candidate.archived_at ?? null,
    };
    return record;
  }, {});
}

function normaliseProjectStatus(status: unknown): ColonyProjectStatus {
  if (status === 'ready_to_build' || status === 'building' || status === 'established') {
    return status;
  }
  return 'draft';
}

function createProjectId(systemId64: number) {
  const random = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `colony-${systemId64}-${random}`;
}
