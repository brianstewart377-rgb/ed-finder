import type { WatchlistEntry } from '@/lib/api';
import type { PinnedEntry } from '@/features/pinned/usePinned';
import type { ColonyProject, ColonyProjectStatus } from '@/features/colony-planner/colonyProjectStore';
import { objectiveSummaryLabel } from '@/features/colony-planner/plannerDraftContext';
import type { MyWorkSystemRecord, SavedSystemLabel, SavedSystemSnapshot } from './myWorkStore';

export interface SavedSystemViewModel extends SavedSystemSnapshot {
  labels: SavedSystemLabel[];
  planCount: number;
  latestPlanActivity: string | null;
  latestSavedAt: string | null;
  activeProject: ColonyProject | null;
  establishedProject: ColonyProject | null;
  explicitColonisedAt: string | null;
  isColonised: boolean;
  watchlistEntry: WatchlistEntry | null;
  pinnedEntry: PinnedEntry | null;
  localRecord: MyWorkSystemRecord | null;
}

export interface ColonyViewModel {
  id64: number;
  systemName: string;
  plan: ColonyProject | null;
  objective: string;
  colonisedAt: string | null;
}

export type MyWorkContinuation =
  | { kind: 'plan'; project: ColonyProject }
  | { kind: 'saved-system'; system: SavedSystemViewModel }
  | null;

export function buildSavedSystems({
  watchlistEntries,
  pinnedEntries,
  localSystems,
  projects,
}: {
  watchlistEntries: WatchlistEntry[];
  pinnedEntries: PinnedEntry[];
  localSystems: Record<string, MyWorkSystemRecord>;
  projects: ColonyProject[];
}): SavedSystemViewModel[] {
  const bySystem = new Map<number, SavedSystemViewModel>();
  const projectsBySystem = new Map<number, ColonyProject[]>();
  for (const project of projects) {
    const existing = projectsBySystem.get(project.system_id64) ?? [];
    existing.push(project);
    projectsBySystem.set(project.system_id64, existing);
  }

  const register = (snapshot: SavedSystemSnapshot, partial: Partial<SavedSystemViewModel>) => {
    const existing = bySystem.get(snapshot.id64);
    const localRecord = partial.localRecord ?? existing?.localRecord ?? localSystems[String(snapshot.id64)] ?? null;
    const watchlistEntry = partial.watchlistEntry ?? existing?.watchlistEntry ?? null;
    const pinnedEntry = partial.pinnedEntry ?? existing?.pinnedEntry ?? null;
    const systemProjects = (projectsBySystem.get(snapshot.id64) ?? []).slice().sort((a, b) => b.updated_at.localeCompare(a.updated_at));
    const activeProject = systemProjects.find((project) => project.status != 'established') ?? null;
    const establishedProject = systemProjects.find((project) => project.status == 'established') ?? null;
    const labels = new Set<SavedSystemLabel>([
      ...(localRecord?.labels ?? []),
      ...(watchlistEntry ? ['considering'] as const : []),
      ...(pinnedEntry ? ['favourite'] as const : []),
    ]);
    bySystem.set(snapshot.id64, {
      ...existing,
      id64: snapshot.id64,
      name: snapshot.name,
      x: snapshot.x,
      y: snapshot.y,
      z: snapshot.z,
      population: snapshot.population,
      is_colonised: snapshot.is_colonised,
      labels: Array.from(labels),
      planCount: systemProjects.length,
      latestPlanActivity: systemProjects[0]?.updated_at ?? null,
      latestSavedAt: latestTimestamp([
        watchlistEntry?.added_at ?? null,
        pinnedEntry?.pinned_at ?? null,
        localRecord?.updated_at ?? null,
      ]),
      activeProject,
      establishedProject,
      explicitColonisedAt: localRecord?.explicit_colonised_at ?? null,
      isColonised: Boolean(establishedProject || localRecord?.explicit_colonised_at),
      watchlistEntry,
      pinnedEntry,
      localRecord,
      ...partial,
    });
  };

  for (const entry of watchlistEntries) {
    register({
      id64: entry.system_id64,
      name: entry.name,
      x: entry.x,
      y: entry.y,
      z: entry.z,
      population: entry.population,
      is_colonised: entry.is_colonised,
    }, {
      watchlistEntry: entry,
    });
  }

  for (const entry of pinnedEntries) {
    register({
      id64: entry.id64,
      name: entry.name,
      x: entry.x,
      y: entry.y,
      z: entry.z,
      population: entry.population,
      is_colonised: entry.is_colonised,
    }, {
      pinnedEntry: entry,
    });
  }

  for (const record of Object.values(localSystems)) {
    register(record, {
      localRecord: record,
    });
  }

  return Array.from(bySystem.values())
    .filter((system) => system.labels.length > 0)
    .sort((a, b) => (b.latestSavedAt ?? '').localeCompare(a.latestSavedAt ?? ''));
}

export function groupPlansBySystem(projects: ColonyProject[]) {
  const groups = new Map<number, { systemId64: number; systemName: string; plans: ColonyProject[]; latestUpdatedAt: string }>();
  for (const project of projects) {
    const existing = groups.get(project.system_id64);
    if (existing) {
      existing.plans.push(project);
      if (project.updated_at > existing.latestUpdatedAt) existing.latestUpdatedAt = project.updated_at;
      continue;
    }
    groups.set(project.system_id64, {
      systemId64: project.system_id64,
      systemName: project.system_name,
      plans: [project],
      latestUpdatedAt: project.updated_at,
    });
  }
  return Array.from(groups.values())
    .map((group) => ({
      ...group,
      plans: group.plans.slice().sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
    }))
    .sort((a, b) => b.latestUpdatedAt.localeCompare(a.latestUpdatedAt));
}

export function buildColonies({
  savedSystems,
  localSystems,
  projects,
}: {
  savedSystems: SavedSystemViewModel[];
  localSystems: Record<string, MyWorkSystemRecord>;
  projects: ColonyProject[];
}): ColonyViewModel[] {
  const establishedBySystem = new Map<number, ColonyProject>();
  for (const project of projects) {
    if (project.status !== 'established') continue;
    const current = establishedBySystem.get(project.system_id64);
    if (!current || project.updated_at > current.updated_at) {
      establishedBySystem.set(project.system_id64, project);
    }
  }

  const colonies = new Map<number, ColonyViewModel>();
  for (const system of savedSystems) {
    const establishedProject = establishedBySystem.get(system.id64) ?? system.establishedProject ?? null;
    if (!establishedProject && !system.explicitColonisedAt) continue;
    colonies.set(system.id64, {
      id64: system.id64,
      systemName: system.name,
      plan: establishedProject,
      objective: objectiveSummaryLabel(establishedProject?.objective ?? null),
      colonisedAt: latestTimestamp([establishedProject?.updated_at ?? null, system.explicitColonisedAt]),
    });
  }

  for (const record of Object.values(localSystems)) {
    if (!record.explicit_colonised_at || colonies.has(record.id64)) continue;
    colonies.set(record.id64, {
      id64: record.id64,
      systemName: record.name,
      plan: establishedBySystem.get(record.id64) ?? null,
      objective: objectiveSummaryLabel(establishedBySystem.get(record.id64)?.objective ?? null),
      colonisedAt: latestTimestamp([record.explicit_colonised_at, establishedBySystem.get(record.id64)?.updated_at ?? null]),
    });
  }

  for (const project of projects) {
    if (project.status !== 'established' || colonies.has(project.system_id64)) continue;
    colonies.set(project.system_id64, {
      id64: project.system_id64,
      systemName: project.system_name,
      plan: project,
      objective: objectiveSummaryLabel(project.objective),
      colonisedAt: project.updated_at,
    });
  }

  return Array.from(colonies.values()).sort((a, b) => (b.colonisedAt ?? '').localeCompare(a.colonisedAt ?? ''));
}

export function selectContinuation({
  savedSystems,
  projects,
}: {
  savedSystems: SavedSystemViewModel[];
  projects: ColonyProject[];
}): MyWorkContinuation {
  const latestActivePlan = projects
    .filter((project) => project.status !== 'established')
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))[0] ?? null;
  if (latestActivePlan) {
    return { kind: 'plan', project: latestActivePlan };
  }
  const recentSavedSystem = savedSystems
    .filter((system) => system.planCount === 0)
    .sort((a, b) => (b.latestSavedAt ?? '').localeCompare(a.latestSavedAt ?? ''))[0] ?? null;
  if (recentSavedSystem) {
    return { kind: 'saved-system', system: recentSavedSystem };
  }
  return null;
}

export function projectStatusLabel(status: ColonyProjectStatus) {
  if (status === 'ready_to_build') return 'Ready to build';
  if (status === 'building') return 'Building';
  if (status === 'established') return 'Established';
  return 'Draft';
}

export function labelText(label: SavedSystemLabel) {
  if (label === 'considering') return 'Considering';
  if (label === 'favourite') return 'Favourite';
  return 'Ready to plan';
}

export function latestTimestamp(values: Array<string | null | undefined>) {
  return values.filter((value): value is string => Boolean(value)).sort().slice(-1)[0] ?? null;
}

export function formatTimestamp(value: string) {
  return new Date(value).toLocaleString();
}

export function formatRecentActivity(value: string) {
  const deltaMs = Date.now() - new Date(value).getTime();
  if (deltaMs < 60_000) return 'just now';
  if (deltaMs < 60 * 60_000) return `${Math.max(1, Math.floor(deltaMs / 60_000))}m ago`;
  if (deltaMs < 24 * 60 * 60_000) return `${Math.max(1, Math.floor(deltaMs / (60 * 60_000)))}h ago`;
  return formatTimestamp(value);
}
