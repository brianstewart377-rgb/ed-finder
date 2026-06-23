import { useEffect, useMemo, useState } from 'react';
import type { WatchlistEntry } from '@/lib/api';
import type { UseWatchlist } from '@/features/watchlist/useWatchlist';
import type { UsePinned, PinnedEntry } from '@/features/pinned/usePinned';
import {
  useColonyProjectStore,
  type ColonyProject,
  type ColonyProjectStatus,
} from '@/features/colony-planner/colonyProjectStore';
import {
  objectiveSummaryLabel,
  startApproachLabel,
} from '@/features/colony-planner/plannerDraftContext';
import { humanizeArchetype } from '@/features/colony-planner/workspaceUtils';
import {
  useMyWorkStore,
  type MyWorkSystemRecord,
  type SavedSystemLabel,
  type SavedSystemSnapshot,
} from './myWorkStore';

type MyWorkSection = 'saved-systems' | 'plans' | 'my-colonies';

interface MyWorkWorkspaceProps {
  initialSection?: MyWorkSection;
  routeSource?: 'my-work' | 'watchlist' | 'pinned' | 'colony';
  watchlist: UseWatchlist;
  pinned: UsePinned;
  onOpenDetail: (id64: number, options?: { focus?: 'colony-planner' }) => void;
  onOpenPlanner: (id64: number, options?: { projectId?: string | null }) => void;
}

interface SavedSystemViewModel extends SavedSystemSnapshot {
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

interface ColonyViewModel {
  id64: number;
  systemName: string;
  plan: ColonyProject | null;
  objective: string;
  colonisedAt: string | null;
}

const SECTION_OPTIONS: Array<{ id: MyWorkSection; label: string }> = [
  { id: 'saved-systems', label: 'Saved Systems' },
  { id: 'plans', label: 'Plans' },
  { id: 'my-colonies', label: 'My Colonies' },
];

const SAVED_LABEL_FILTERS: Array<{ id: 'all' | SavedSystemLabel; label: string }> = [
  { id: 'all', label: 'All saved' },
  { id: 'considering', label: 'Considering' },
  { id: 'favourite', label: 'Favourite' },
  { id: 'ready_to_plan', label: 'Ready to plan' },
];

export function MyWorkWorkspace({
  initialSection = 'saved-systems',
  routeSource = 'my-work',
  watchlist,
  pinned,
  onOpenDetail,
  onOpenPlanner,
}: MyWorkWorkspaceProps) {
  const [activeSection, setActiveSection] = useState<MyWorkSection>(initialSection);
  const [savedFilter, setSavedFilter] = useState<'all' | SavedSystemLabel>('all');
  const [editingPlanId, setEditingPlanId] = useState<string | null>(null);
  const [editingPlanName, setEditingPlanName] = useState('');
  const projectsRecord = useColonyProjectStore((state) => state.projects);
  const renameProject = useColonyProjectStore((state) => state.renameProject);
  const duplicateProject = useColonyProjectStore((state) => state.duplicateProject);
  const archiveProject = useColonyProjectStore((state) => state.archiveProject);
  const updateProjectStatus = useColonyProjectStore((state) => state.updateProjectStatus);
  const localSystems = useMyWorkStore((state) => state.systems);
  const rememberSystem = useMyWorkStore((state) => state.rememberSystem);
  const setLabel = useMyWorkStore((state) => state.setLabel);
  const setExplicitColonised = useMyWorkStore((state) => state.setExplicitColonised);
  const clearSystemMetadata = useMyWorkStore((state) => state.clearSystemMetadata);

  const activeProjects = useMemo(
    () => Object.values(projectsRecord).filter((project) => !project.archived_at),
    [projectsRecord],
  );

  useEffect(() => {
    setActiveSection((current) => (current === initialSection ? current : initialSection));
  }, [initialSection]);

  const savedSystems = useMemo(
    () => buildSavedSystems({ watchlistEntries: watchlist.entries, pinnedEntries: pinned.entries, localSystems, projects: activeProjects }),
    [watchlist.entries, pinned.entries, localSystems, activeProjects],
  );
  const filteredSavedSystems = useMemo(
    () => savedSystems.filter((system) => savedFilter === 'all' || system.labels.includes(savedFilter)),
    [savedFilter, savedSystems],
  );
  const groupedPlans = useMemo(() => groupPlansBySystem(activeProjects), [activeProjects]);
  const myColonies = useMemo(
    () => buildColonies({ savedSystems, localSystems, projects: activeProjects }),
    [activeProjects, localSystems, savedSystems],
  );
  const continuation = useMemo(
    () => selectContinuation({ savedSystems, projects: activeProjects }),
    [savedSystems, activeProjects],
  );

  const aliasNotice = routeSource !== 'my-work'
    ? routeSource === 'watchlist'
      ? 'Watchlist now opens the Saved Systems view inside My Work.'
      : routeSource === 'pinned'
        ? 'Pins now open the Saved Systems view inside My Work.'
        : 'Colony Tracker remains available by route, while My Work now holds the player-facing colonies overview.'
    : null;

  const handleInspectSystem = (id64: number, options?: { focus?: 'colony-planner' }) => {
    onOpenDetail(id64, options);
  };

  const handleContinuePlan = (project: ColonyProject) => {
    onOpenPlanner(project.system_id64, { projectId: project.id });
  };

  const handleToggleConsidering = async (system: SavedSystemViewModel, enabled: boolean) => {
    if (enabled && !system.watchlistEntry) {
      await watchlist.add(system.id64, system);
      return;
    }
    if (!enabled && system.watchlistEntry) {
      await watchlist.remove(system.id64);
    }
  };

  const handleToggleFavourite = (system: SavedSystemViewModel, enabled: boolean) => {
    if (enabled && system.pinnedEntry) return;
    if (!enabled && system.pinnedEntry) {
      pinned.remove(system.id64);
      return;
    }
    if (!enabled) return;
    pinned.toggle({
      id64: system.id64,
      name: system.name,
      x: system.x,
      y: system.y,
      z: system.z,
      population: system.population,
      is_colonised: system.is_colonised,
      distance: null,
      rating: null,
      economy: null,
      pinned_at: new Date().toISOString(),
    });
  };

  const handleToggleReadyToPlan = (system: SavedSystemViewModel, enabled: boolean) => {
    rememberSystem(system);
    setLabel(system, 'ready_to_plan', enabled);
    if (!enabled && !system.watchlistEntry && !system.pinnedEntry && !system.explicitColonisedAt) {
      clearSystemMetadata(system.id64);
    }
  };

  const handleRemoveFromSaved = async (system: SavedSystemViewModel) => {
    if (system.watchlistEntry) {
      await watchlist.remove(system.id64);
    }
    if (system.pinnedEntry) {
      pinned.remove(system.id64);
    }
    if (system.localRecord?.labels.includes('ready_to_plan')) {
      setLabel(system, 'ready_to_plan', false);
    }
    if (!system.explicitColonisedAt) {
      clearSystemMetadata(system.id64);
    }
  };

  const beginRename = (project: ColonyProject) => {
    setEditingPlanId(project.id);
    setEditingPlanName(project.project_name);
  };

  const saveRename = () => {
    if (!editingPlanId) return;
    renameProject(editingPlanId, editingPlanName);
    setEditingPlanId(null);
    setEditingPlanName('');
  };

  return (
    <section data-testid="my-work-workspace" className="space-y-5">
      <header className="panel space-y-4 p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
              Player workspace
            </p>
            <h1 className="font-display text-xl tracking-[0.14em] text-orange">
              My Work
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-relaxed text-silver">
              One calm place to return to saved systems, active plans, and established colony work without guessing which tool last held the context.
            </p>
          </div>
          <div className="rounded border border-border/60 bg-bg3/35 px-3 py-2 font-mono text-[11px] text-silver-dk">
            Saved systems {savedSystems.length} · Plans {activeProjects.length} · Colonies {myColonies.length}
          </div>
        </div>
        {aliasNotice ? (
          <div className="rounded border border-cyan/30 bg-cyan/8 px-3 py-2 text-sm text-cyan">
            {aliasNotice}
          </div>
        ) : null}
        {continuation ? (
          <ContinueWhereLeftOff
            continuation={continuation}
            onInspectSystem={handleInspectSystem}
            onContinuePlan={handleContinuePlan}
          />
        ) : null}
        <div
          className="flex flex-wrap gap-2"
          data-testid="my-work-section-tabs"
        >
          {SECTION_OPTIONS.map((option) => (
            <button
              key={option.id}
              type="button"
              data-testid={`my-work-section-${option.id}`}
              onClick={() => setActiveSection(option.id)}
              className={[
                'rounded-chunk-sm border px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.14em] transition-colors',
                activeSection === option.id
                  ? 'border-orange/55 bg-orange/15 text-orange'
                  : 'border-border bg-bg3/35 text-silver hover:border-orange/40 hover:text-orange-lt',
              ].join(' ')}
            >
              {option.label}
            </button>
          ))}
        </div>
      </header>

      {activeSection === 'saved-systems' ? (
        <section className="space-y-4" data-testid="my-work-saved-systems">
          <div className="flex flex-wrap items-center gap-2">
            {SAVED_LABEL_FILTERS.map((filter) => (
              <button
                key={filter.id}
                type="button"
                data-testid={`saved-systems-filter-${filter.id}`}
                onClick={() => setSavedFilter(filter.id)}
                className={[
                  'rounded border px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] transition-colors',
                  savedFilter === filter.id
                    ? 'border-orange/50 bg-orange/12 text-orange'
                    : 'border-border bg-bg3/35 text-silver-dk hover:border-orange/35 hover:text-orange-lt',
                ].join(' ')}
              >
                {filter.label}
              </button>
            ))}
          </div>
          {filteredSavedSystems.length === 0 ? (
            <EmptyPanel
              title="No saved systems yet"
              body="Saved systems from Watchlist, Pins, and Ready to plan labels appear here automatically."
            />
          ) : (
            <ul className="space-y-3">
              {filteredSavedSystems.map((system) => (
                <SavedSystemCard
                  key={system.id64}
                  system={system}
                  onInspect={() => handleInspectSystem(system.id64)}
                  onStartPlan={() => handleInspectSystem(system.id64, { focus: 'colony-planner' })}
                  onContinuePlan={() => system.activeProject && handleContinuePlan(system.activeProject)}
                  onToggleConsidering={(enabled) => void handleToggleConsidering(system, enabled)}
                  onToggleFavourite={(enabled) => handleToggleFavourite(system, enabled)}
                  onToggleReadyToPlan={(enabled) => handleToggleReadyToPlan(system, enabled)}
                  onRemove={() => void handleRemoveFromSaved(system)}
                />
              ))}
            </ul>
          )}
        </section>
      ) : null}

      {activeSection === 'plans' ? (
        <section className="space-y-4" data-testid="my-work-plans">
          {groupedPlans.length === 0 ? (
            <EmptyPanel
              title="No plans yet"
              body="Start a plan from System Detail and it will appear here with its objective, start approach, and local draft context."
            />
          ) : (
            <div className="space-y-4">
              {groupedPlans.map((group) => (
                <section key={group.systemId64} className="panel space-y-3 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <h2 className="font-display text-base tracking-[0.12em] text-orange-lt">
                        {group.systemName}
                      </h2>
                      <p className="mt-1 font-mono text-[11px] text-silver-dk">
                        {group.plans.length} plan{group.plans.length === 1 ? '' : 's'}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleInspectSystem(group.systemId64)}
                      className="rounded border border-border bg-bg3/35 px-3 py-1.5 font-mono text-[11px] text-silver hover:border-orange/35 hover:text-orange-lt"
                    >
                      Inspect system
                    </button>
                  </div>
                  <div className="space-y-3">
                    {group.plans.map((project) => (
                      <PlanCard
                        key={project.id}
                        project={project}
                        isEditing={editingPlanId === project.id}
                        editingName={editingPlanName}
                        onEditNameChange={setEditingPlanName}
                        onBeginRename={() => beginRename(project)}
                        onSaveRename={saveRename}
                        onCancelRename={() => {
                          setEditingPlanId(null);
                          setEditingPlanName('');
                        }}
                        onDuplicate={() => duplicateProject(project.id)}
                        onArchive={() => archiveProject(project.id)}
                        onStatusChange={(status) => updateProjectStatus(project.id, status)}
                        onContinue={() => handleContinuePlan(project)}
                        onInspectSystem={() => handleInspectSystem(project.system_id64)}
                        onToggleColonised={(enabled) => {
                          const snapshot = {
                            id64: project.system_id64,
                            name: project.system_name,
                            x: null,
                            y: null,
                            z: null,
                            population: null,
                            is_colonised: project.status === 'established',
                          };
                          rememberSystem(snapshot);
                          setExplicitColonised(snapshot, enabled);
                          if (!enabled) {
                            const local = localSystems[String(project.system_id64)];
                            if (local && local.labels.length === 0) {
                              clearSystemMetadata(project.system_id64);
                            }
                          }
                        }}
                        isExplicitlyColonised={Boolean(localSystems[String(project.system_id64)]?.explicit_colonised_at)}
                      />
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}
        </section>
      ) : null}

      {activeSection === 'my-colonies' ? (
        <section className="space-y-4" data-testid="my-work-colonies">
          <div className="rounded border border-violet/30 bg-violet/8 px-3 py-2 text-sm text-silver">
            My Colonies is player-managed planning state. It does not claim live Architect, journal, EDMC, or in-game verification.
          </div>
          {myColonies.length === 0 ? (
            <EmptyPanel
              title="No colonies marked yet"
              body="Plans marked Established, or systems you explicitly mark as colonised, appear here."
            />
          ) : (
            <ul className="space-y-3">
              {myColonies.map((colony) => (
                <li key={`${colony.id64}-${colony.plan?.id ?? 'explicit'}`} className="panel flex flex-wrap items-start justify-between gap-3 p-4">
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded border border-violet/35 bg-violet/10 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-violet">
                        Player-managed colony
                      </span>
                      <span className="font-mono text-[11px] text-silver-dk">
                        {colony.colonisedAt ? `Established ${formatTimestamp(colony.colonisedAt)}` : 'Colonised date unavailable'}
                      </span>
                    </div>
                    <h2 className="font-display text-base tracking-[0.1em] text-orange-lt">
                      {colony.systemName}
                    </h2>
                    <p className="text-sm text-silver">
                      {colony.plan ? colony.plan.project_name : 'No linked plan'}
                    </p>
                    <p className="font-mono text-[11px] text-silver-dk">
                      Objective: {colony.objective}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {colony.plan ? (
                      <button
                        type="button"
                        onClick={() => handleContinuePlan(colony.plan!)}
                        className="rounded border border-orange/45 bg-orange/10 px-3 py-1.5 font-mono text-[11px] font-bold text-orange hover:bg-orange/20"
                      >
                        Open plan
                      </button>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => handleInspectSystem(colony.id64)}
                      className="rounded border border-border bg-bg3/35 px-3 py-1.5 font-mono text-[11px] text-silver hover:border-orange/35 hover:text-orange-lt"
                    >
                      Inspect system
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}
    </section>
  );
}

function ContinueWhereLeftOff({
  continuation,
  onInspectSystem,
  onContinuePlan,
}: {
  continuation: ReturnType<typeof selectContinuation>;
  onInspectSystem: (id64: number) => void;
  onContinuePlan: (project: ColonyProject) => void;
}) {
  if (!continuation) return null;
  if (continuation.kind === 'plan') {
    return (
      <section data-testid="my-work-continuation" className="rounded-chunk-lg border border-orange/35 bg-orange/8 p-4">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-orange">Continue planning</p>
        <h2 className="mt-2 font-display text-lg tracking-[0.1em] text-orange-lt">
          {continuation.project.system_name} - {continuation.project.project_name}
        </h2>
        <p className="mt-1 text-sm text-silver">
          {projectStatusLabel(continuation.project.status)} · Updated {formatRecentActivity(continuation.project.updated_at)}
        </p>
        <button
          type="button"
          onClick={() => onContinuePlan(continuation.project)}
          className="mt-3 rounded border border-orange/45 bg-orange/10 px-3 py-1.5 font-mono text-[11px] font-bold text-orange hover:bg-orange/20"
        >
          Continue plan
        </button>
      </section>
    );
  }

  return (
    <section data-testid="my-work-continuation" className="rounded-chunk-lg border border-cyan/35 bg-cyan/8 p-4">
      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-cyan">Ready to revisit</p>
      <h2 className="mt-2 font-display text-lg tracking-[0.1em] text-orange-lt">
        {continuation.system.name}
      </h2>
      <p className="mt-1 text-sm text-silver">
        Saved as {continuation.system.labels.map(labelText).join(' · ')} · No plan yet
      </p>
      <button
        type="button"
        onClick={() => onInspectSystem(continuation.system.id64)}
        className="mt-3 rounded border border-cyan/45 bg-cyan/10 px-3 py-1.5 font-mono text-[11px] font-bold text-cyan hover:bg-cyan/20"
      >
        Inspect system
      </button>
    </section>
  );
}

function SavedSystemCard({
  system,
  onInspect,
  onStartPlan,
  onContinuePlan,
  onToggleConsidering,
  onToggleFavourite,
  onToggleReadyToPlan,
  onRemove,
}: {
  system: SavedSystemViewModel;
  onInspect: () => void;
  onStartPlan: () => void;
  onContinuePlan: () => void;
  onToggleConsidering: (enabled: boolean) => void;
  onToggleFavourite: (enabled: boolean) => void;
  onToggleReadyToPlan: (enabled: boolean) => void;
  onRemove: () => void;
}) {
  return (
    <li data-testid={`saved-system-${system.id64}`} className="panel flex flex-wrap items-start justify-between gap-4 p-4">
      <div className="min-w-0 flex-1 space-y-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-display text-base tracking-[0.1em] text-orange-lt">
              {system.name}
            </h2>
            {system.activeProject ? (
              <span className="rounded border border-orange/35 bg-orange/10 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-orange">
                Has active plan
              </span>
            ) : null}
            {system.isColonised ? (
              <span className="rounded border border-violet/35 bg-violet/10 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-violet">
                Colonised
              </span>
            ) : null}
          </div>
          <p className="mt-1 font-mono text-[11px] text-silver-dk">
            {system.planCount} associated plan{system.planCount === 1 ? '' : 's'}
            {system.latestPlanActivity ? ` · latest plan update ${formatTimestamp(system.latestPlanActivity)}` : ''}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <LabelToggle
            active={system.labels.includes('considering')}
            label="Considering"
            onClick={() => onToggleConsidering(!system.labels.includes('considering'))}
          />
          <LabelToggle
            active={system.labels.includes('favourite')}
            label="Favourite"
            onClick={() => onToggleFavourite(!system.labels.includes('favourite'))}
          />
          <LabelToggle
            active={system.labels.includes('ready_to_plan')}
            label="Ready to plan"
            onClick={() => onToggleReadyToPlan(!system.labels.includes('ready_to_plan'))}
          />
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onInspect}
          className="rounded border border-border bg-bg3/35 px-3 py-1.5 font-mono text-[11px] text-silver hover:border-orange/35 hover:text-orange-lt"
        >
          Inspect
        </button>
        {system.activeProject ? (
          <button
            type="button"
            onClick={onContinuePlan}
            className="rounded border border-orange/45 bg-orange/10 px-3 py-1.5 font-mono text-[11px] font-bold text-orange hover:bg-orange/20"
          >
            Continue plan
          </button>
        ) : (
          <button
            type="button"
            onClick={onStartPlan}
            className="rounded border border-orange/45 bg-orange/10 px-3 py-1.5 font-mono text-[11px] font-bold text-orange hover:bg-orange/20"
          >
            Start plan
          </button>
        )}
        <button
          type="button"
          onClick={onRemove}
          className="rounded border border-red/40 bg-red/10 px-3 py-1.5 font-mono text-[11px] text-red hover:bg-red/20"
        >
          Remove from saved
        </button>
      </div>
    </li>
  );
}

function PlanCard({
  project,
  isEditing,
  editingName,
  onEditNameChange,
  onBeginRename,
  onSaveRename,
  onCancelRename,
  onDuplicate,
  onArchive,
  onStatusChange,
  onContinue,
  onInspectSystem,
  onToggleColonised,
  isExplicitlyColonised,
}: {
  project: ColonyProject;
  isEditing: boolean;
  editingName: string;
  onEditNameChange: (value: string) => void;
  onBeginRename: () => void;
  onSaveRename: () => void;
  onCancelRename: () => void;
  onDuplicate: () => void;
  onArchive: () => void;
  onStatusChange: (status: ColonyProjectStatus) => void;
  onContinue: () => void;
  onInspectSystem: () => void;
  onToggleColonised: (enabled: boolean) => void;
  isExplicitlyColonised: boolean;
}) {
  return (
    <article data-testid={`plan-card-${project.id}`} className="rounded border border-border/70 bg-bg3/30 p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-2">
          {isEditing ? (
            <div className="flex flex-wrap gap-2">
              <input
                value={editingName}
                onChange={(event) => onEditNameChange(event.target.value)}
                className="min-w-[18rem] flex-1 rounded border border-border/70 bg-bg2 px-2 py-1.5 font-mono text-xs text-silver"
              />
              <button
                type="button"
                onClick={onSaveRename}
                className="rounded border border-orange/45 bg-orange/10 px-3 py-1.5 font-mono text-[11px] text-orange"
              >
                Save name
              </button>
              <button
                type="button"
                onClick={onCancelRename}
                className="rounded border border-border bg-bg3/35 px-3 py-1.5 font-mono text-[11px] text-silver"
              >
                Cancel
              </button>
            </div>
          ) : (
            <h3 className="truncate font-display text-sm tracking-[0.1em] text-orange-lt">
              {project.project_name}
            </h3>
          )}
          <div className="flex flex-wrap gap-2 font-mono text-[11px] text-silver-dk">
            <span>Objective: {objectiveSummaryLabel(project.objective)}</span>
            <span>Start: {startApproachLabel(project.start_approach)}</span>
            <span>Saved locally</span>
            <span>Updated {formatTimestamp(project.updated_at)}</span>
          </div>
          <div className="grid gap-2 text-[11px] font-mono text-silver sm:grid-cols-2">
            <div className="rounded border border-border/60 bg-bg2/40 px-2 py-1.5">
              Plan health: {project.build_plan_placements.length} placements · {humanizeArchetype(project.target_archetype)}
            </div>
            <div className="rounded border border-border/60 bg-bg2/40 px-2 py-1.5">
              Status: {projectStatusLabel(project.status)}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onContinue}
            className="rounded border border-orange/45 bg-orange/10 px-3 py-1.5 font-mono text-[11px] font-bold text-orange hover:bg-orange/20"
          >
            Continue plan
          </button>
          <button
            type="button"
            onClick={onInspectSystem}
            className="rounded border border-border bg-bg3/35 px-3 py-1.5 font-mono text-[11px] text-silver hover:border-orange/35 hover:text-orange-lt"
          >
            Inspect system
          </button>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <label className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">
          Status
        </label>
        <select
          data-testid={`plan-status-${project.id}`}
          value={project.status}
          onChange={(event) => onStatusChange(event.target.value as ColonyProjectStatus)}
          className="rounded border border-border/70 bg-bg2 px-2 py-1.5 font-mono text-[11px] text-silver"
        >
          <option value="draft">Draft</option>
          <option value="ready_to_build">Ready to build</option>
          <option value="building">Building</option>
          <option value="established">Established</option>
        </select>
        <button
          type="button"
          onClick={onBeginRename}
          className="rounded border border-border bg-bg3/35 px-3 py-1.5 font-mono text-[11px] text-silver hover:border-cyan/35 hover:text-cyan"
        >
          Rename
        </button>
        <button
          type="button"
          onClick={onDuplicate}
          className="rounded border border-border bg-bg3/35 px-3 py-1.5 font-mono text-[11px] text-silver hover:border-cyan/35 hover:text-cyan"
        >
          Duplicate
        </button>
        <button
          type="button"
          onClick={onArchive}
          className="rounded border border-gold/35 bg-gold/10 px-3 py-1.5 font-mono text-[11px] text-gold hover:bg-gold/20"
        >
          Archive
        </button>
      </div>
      {project.status === 'established' ? (
        <div className="mt-3 rounded border border-violet/30 bg-violet/8 px-3 py-2 text-sm text-silver">
          <p>
            Established is still player-managed planning state. Use the action below if you also want this system to appear in My Colonies as explicitly colonised.
          </p>
          <button
            type="button"
            onClick={() => onToggleColonised(!isExplicitlyColonised)}
            className="mt-2 rounded border border-violet/35 bg-violet/12 px-3 py-1.5 font-mono text-[11px] text-violet hover:bg-violet/20"
          >
            {isExplicitlyColonised ? 'Remove colonised mark' : 'Mark system colonised'}
          </button>
        </div>
      ) : null}
    </article>
  );
}

function LabelToggle({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        'rounded border px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] transition-colors',
        active
          ? 'border-orange/50 bg-orange/12 text-orange'
          : 'border-border bg-bg3/35 text-silver-dk hover:border-orange/35 hover:text-orange-lt',
      ].join(' ')}
    >
      {label}
    </button>
  );
}

function EmptyPanel({ title, body }: { title: string; body: string }) {
  return (
    <div className="panel px-4 py-12 text-center">
      <h2 className="font-display text-sm tracking-[0.12em] text-orange">{title}</h2>
      <p className="mx-auto mt-2 max-w-lg text-sm leading-relaxed text-silver-dk">{body}</p>
    </div>
  );
}

function buildSavedSystems({
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
    const activeProject = systemProjects.find((project) => project.status !== 'established') ?? null;
    const establishedProject = systemProjects.find((project) => project.status === 'established') ?? null;
    const labels = new Set<SavedSystemLabel>([
      ...(localRecord?.labels ?? []),
      ...(watchlistEntry ? ['considering'] as const : []),
      ...(pinnedEntry ? ['favourite'] as const : []),
    ]);
    bySystem.set(snapshot.id64, {
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
      ...existing,
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

function groupPlansBySystem(projects: ColonyProject[]) {
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

function buildColonies({
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

function selectContinuation({
  savedSystems,
  projects,
}: {
  savedSystems: SavedSystemViewModel[];
  projects: ColonyProject[];
}) {
  const latestActivePlan = projects
    .filter((project) => project.status !== 'established')
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))[0] ?? null;
  if (latestActivePlan) {
    return { kind: 'plan' as const, project: latestActivePlan };
  }
  const recentSavedSystem = savedSystems
    .filter((system) => system.planCount === 0)
    .sort((a, b) => (b.latestSavedAt ?? '').localeCompare(a.latestSavedAt ?? ''))[0] ?? null;
  if (recentSavedSystem) {
    return { kind: 'saved-system' as const, system: recentSavedSystem };
  }
  return null;
}

function latestTimestamp(values: Array<string | null | undefined>) {
  return values.filter((value): value is string => Boolean(value)).sort().slice(-1)[0] ?? null;
}

function formatTimestamp(value: string) {
  return new Date(value).toLocaleString();
}

function formatRecentActivity(value: string) {
  const deltaMs = Date.now() - new Date(value).getTime();
  if (deltaMs < 60_000) return 'just now';
  if (deltaMs < 60 * 60_000) return `${Math.max(1, Math.floor(deltaMs / 60_000))}m ago`;
  if (deltaMs < 24 * 60 * 60_000) return `${Math.max(1, Math.floor(deltaMs / (60 * 60_000)))}h ago`;
  return formatTimestamp(value);
}

function projectStatusLabel(status: ColonyProjectStatus) {
  if (status === 'ready_to_build') return 'Ready to build';
  if (status === 'building') return 'Building';
  if (status === 'established') return 'Established';
  return 'Draft';
}

function labelText(label: SavedSystemLabel) {
  if (label === 'considering') return 'Considering';
  if (label === 'favourite') return 'Favourite';
  return 'Ready to plan';
}
