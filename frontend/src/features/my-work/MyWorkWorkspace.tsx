import { useMemo, useState } from 'react';
import type { UseWatchlist } from '@/features/watchlist/useWatchlist';
import type { UsePinned } from '@/features/pinned/usePinned';
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
  type SavedSystemLabel,
} from './myWorkStore';
import {
  buildColonies,
  buildSavedSystems,
  formatRecentActivity,
  formatTimestamp,
  groupPlansBySystem,
  labelText,
  projectStatusLabel,
  selectContinuation,
  type SavedSystemViewModel,
} from './myWorkWorkspaceUtils';
import { JournalImportPanel } from '@/features/journal-import/JournalImportPanel';
import { useJournalTelemetrySummary } from './useJournalTelemetrySummary';
import { useSyncKeyStore } from '@/store/syncKeyStore';
import type { JournalTelemetryRecentSystem } from '@/types/api';

type MyWorkSection = 'saved-systems' | 'plans' | 'my-colonies' | 'telemetry';

interface MyWorkWorkspaceProps {
  initialSection?: MyWorkSection;
  routeSource?: 'my-work' | 'watchlist' | 'pinned' | 'colony';
  watchlist: UseWatchlist;
  pinned: UsePinned;
  onOpenDetail: (id64: number, options?: { focus?: 'colony-planner' }) => void;
  onOpenPlanner: (id64: number, options?: { projectId?: string | null }) => void;
}

const SECTION_OPTIONS: Array<{ id: MyWorkSection; label: string }> = [
  { id: 'saved-systems', label: 'Saved Systems' },
  { id: 'plans', label: 'Plans' },
  { id: 'my-colonies', label: 'My Colonies' },
  { id: 'telemetry', label: 'Telemetry' },
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
  const syncKey = useSyncKeyStore((state) => state.syncKey);
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
  const telemetryQuery = useJournalTelemetrySummary(syncKey) ?? {
    data: null,
    isLoading: false,
    error: null,
  };
  const telemetryData = telemetryQuery.data ?? null;
  const telemetryBySystem = useMemo(() => {
    const entries = telemetryData?.recent_systems ?? [];
    return entries.reduce<Record<number, JournalTelemetryRecentSystem>>((record, system) => {
      record[system.system_id64] = system;
      return record;
    }, {});
  }, [telemetryData?.recent_systems]);
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
      <header className="premium-subpanel space-y-4 p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="font-display text-xl tracking-[0.14em] text-text">
              My Work
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-relaxed text-silver">
              Saved systems, plans, and colonies in one place.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="premium-toolbar rounded-2xl px-3 py-2 font-mono text-[11px] text-silver-dk">
              Saved systems {savedSystems.length} · Plans {activeProjects.length} · Colonies {myColonies.length}
            </div>
            <span className="premium-toolbar rounded-full px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-cyan">
              Local workspace
            </span>
          </div>
        </div>
        {aliasNotice ? (
          <div className="premium-subpanel border-cyan/30 bg-cyan/8 px-3 py-2 text-sm text-cyan">
            {aliasNotice}
          </div>
        ) : null}
        <JournalImportPanel />
        {continuation ? (
          <ContinueWhereLeftOff
            continuation={continuation}
            onInspectSystem={handleInspectSystem}
            onContinuePlan={handleContinuePlan}
          />
        ) : null}
        <div
          className="premium-toolbar flex flex-wrap gap-2 rounded-2xl p-1"
          data-testid="my-work-section-tabs"
        >
          {SECTION_OPTIONS.map((option) => (
            <button
              key={option.id}
              type="button"
              data-testid={`my-work-section-${option.id}`}
              onClick={() => setActiveSection(option.id)}
              className={[
                'rounded-chunk-sm border px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.14em] transition-all',
                activeSection === option.id
                  ? 'border-orange/55 bg-orange/15 text-orange shadow-brand-glow'
                  : 'border-transparent bg-transparent text-silver hover:border-orange/25 hover:bg-orange/5 hover:text-orange-lt',
              ].join(' ')}
            >
              {option.label}
            </button>
          ))}
        </div>
      </header>

      {activeSection === 'saved-systems' ? (
        <section className="space-y-4" data-testid="my-work-saved-systems">
          <div className="premium-toolbar flex flex-wrap items-center gap-2 rounded-2xl px-3 py-2">
            {SAVED_LABEL_FILTERS.map((filter) => (
              <button
                key={filter.id}
                type="button"
                data-testid={`saved-systems-filter-${filter.id}`}
                onClick={() => setSavedFilter(filter.id)}
                className={[
                  'rounded border px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] transition-all',
                  savedFilter === filter.id
                    ? 'border-orange/50 bg-orange/12 text-orange shadow-brand-glow'
                    : 'border-border/50 bg-bg3/35 text-silver-dk hover:border-orange/35 hover:text-orange-lt',
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
                  telemetry={telemetryBySystem[system.id64] ?? null}
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
                <section key={group.systemId64} className="premium-subpanel space-y-3 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <h2 className="font-display text-base tracking-[0.12em] text-text">
                        {group.systemName}
                      </h2>
                      <p className="mt-1 font-mono text-[11px] text-silver-dk">
                        {group.plans.length} plan{group.plans.length === 1 ? '' : 's'}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleInspectSystem(group.systemId64)}
                      className="btn-metal text-[11px] font-mono"
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
          <div className="premium-subpanel border-violet/30 bg-violet/8 px-3 py-2 text-sm text-silver">
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
                <li key={`${colony.id64}-${colony.plan?.id ?? 'explicit'}`} className="premium-subpanel flex flex-wrap items-start justify-between gap-3 p-4">
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded border border-violet/35 bg-violet/10 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-violet">
                        Player-managed colony
                      </span>
                      <span className="font-mono text-[11px] text-silver-dk">
                        {colony.colonisedAt ? `Established ${formatTimestamp(colony.colonisedAt)}` : 'Colonised date unavailable'}
                      </span>
                    </div>
                      <h2 className="font-display text-base tracking-[0.1em] text-text">
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
                        className="btn-primary text-[11px] font-mono"
                      >
                        Open plan
                      </button>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => handleInspectSystem(colony.id64)}
                      className="btn-metal text-[11px] font-mono"
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

      {activeSection === 'telemetry' ? (
        <TelemetrySection
          syncKey={syncKey}
          isLoading={Boolean(telemetryQuery.isLoading)}
          error={telemetryQuery.error instanceof Error ? telemetryQuery.error.message : null}
          telemetry={telemetryData}
          onInspectSystem={(id64) => handleInspectSystem(id64)}
        />
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
      <section data-testid="my-work-continuation" className="premium-subpanel border-orange/35 bg-orange/8 p-4">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-orange">Continue planning</p>
        <h2 className="mt-2 font-display text-lg tracking-[0.1em] text-text">
          {continuation.project.system_name} - {continuation.project.project_name}
        </h2>
        <p className="mt-1 text-sm text-silver">
          {projectStatusLabel(continuation.project.status)} · Updated {formatRecentActivity(continuation.project.updated_at)}
        </p>
        <button
          type="button"
          onClick={() => onContinuePlan(continuation.project)}
          className="btn-primary mt-3 text-[11px] font-mono"
        >
          Continue plan
        </button>
      </section>
    );
  }

  return (
    <section data-testid="my-work-continuation" className="premium-subpanel border-cyan/35 bg-cyan/8 p-4">
      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-cyan">Ready to revisit</p>
      <h2 className="mt-2 font-display text-lg tracking-[0.1em] text-text">
        {continuation.system.name}
      </h2>
      <p className="mt-1 text-sm text-silver">
        Saved as {continuation.system.labels.map(labelText).join(' · ')} · No plan yet
      </p>
      <button
        type="button"
        onClick={() => onInspectSystem(continuation.system.id64)}
        className="mt-3 rounded-chunk-sm border border-cyan/45 bg-cyan/10 px-3 py-1.5 font-mono text-[11px] font-bold text-cyan shadow-[0_14px_24px_-20px_rgba(34,211,238,0.8)] transition-colors hover:bg-cyan/20"
      >
        Inspect system
      </button>
    </section>
  );
}

function SavedSystemCard({
  system,
  telemetry,
  onInspect,
  onStartPlan,
  onContinuePlan,
  onToggleConsidering,
  onToggleFavourite,
  onToggleReadyToPlan,
  onRemove,
}: {
  system: SavedSystemViewModel;
  telemetry: JournalTelemetryRecentSystem | null;
  onInspect: () => void;
  onStartPlan: () => void;
  onContinuePlan: () => void;
  onToggleConsidering: (enabled: boolean) => void;
  onToggleFavourite: (enabled: boolean) => void;
  onToggleReadyToPlan: (enabled: boolean) => void;
  onRemove: () => void;
}) {
  return (
    <li data-testid={`saved-system-${system.id64}`} className="premium-subpanel flex flex-wrap items-start justify-between gap-4 p-4">
      <div className="min-w-0 flex-1 space-y-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-display text-base tracking-[0.1em] text-text">
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
            {telemetry ? (
              <span className="rounded border border-cyan/35 bg-cyan/10 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-cyan">
                Personal telemetry imported
              </span>
            ) : null}
          </div>
          <p className="mt-1 font-mono text-[11px] text-silver-dk">
            {system.planCount} associated plan{system.planCount === 1 ? '' : 's'}
            {system.latestPlanActivity ? ` · latest plan update ${formatTimestamp(system.latestPlanActivity)}` : ''}
          </p>
          {telemetry ? (
            <p className="mt-1 text-sm text-silver">
              Last observed {formatTimestamp(telemetry.last_observed_at)} Â· {telemetry.event_count} telemetry event{telemetry.event_count === 1 ? '' : 's'} Â· {telemetry.event_types.join(', ')}
            </p>
          ) : null}
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
          className="btn-metal text-[11px] font-mono"
        >
          Inspect
        </button>
        {system.activeProject ? (
          <button
            type="button"
            onClick={onContinuePlan}
            className="btn-primary text-[11px] font-mono"
          >
            Continue plan
          </button>
        ) : (
          <button
            type="button"
            onClick={onStartPlan}
            className="btn-primary text-[11px] font-mono"
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
    <article data-testid={`plan-card-${project.id}`} className="premium-subpanel p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-2">
          {isEditing ? (
            <div className="flex flex-wrap gap-2">
              <input
                value={editingName}
                onChange={(event) => onEditNameChange(event.target.value)}
                className="min-w-[18rem] flex-1 rounded border border-border/70 bg-bg2/80 px-2 py-1.5 font-mono text-xs text-silver"
              />
              <button
                type="button"
                onClick={onSaveRename}
                className="btn-primary text-[11px] font-mono"
              >
                Save name
              </button>
              <button
                type="button"
                onClick={onCancelRename}
                className="btn-metal text-[11px] font-mono"
              >
                Cancel
              </button>
            </div>
          ) : (
            <h3 className="truncate font-display text-sm tracking-[0.1em] text-text">
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
            <div className="premium-toolbar rounded-xl px-2 py-1.5">
              Plan health: {project.build_plan_placements.length} placements · {humanizeArchetype(project.target_archetype)}
            </div>
            <div className="premium-toolbar rounded-xl px-2 py-1.5">
              Status: {projectStatusLabel(project.status)}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onContinue}
            className="btn-primary text-[11px] font-mono"
          >
            Continue plan
          </button>
          <button
            type="button"
            onClick={onInspectSystem}
            className="btn-metal text-[11px] font-mono"
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
          className="rounded border border-border/70 bg-bg2/80 px-2 py-1.5 font-mono text-[11px] text-silver"
        >
          <option value="draft">Draft</option>
          <option value="ready_to_build">Ready to build</option>
          <option value="building">Building</option>
          <option value="established">Established</option>
        </select>
        <button
          type="button"
          onClick={onBeginRename}
          className="btn-metal text-[11px] font-mono"
        >
          Rename
        </button>
        <button
          type="button"
          onClick={onDuplicate}
          className="btn-metal text-[11px] font-mono"
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
        <div className="premium-subpanel mt-3 border-violet/30 bg-violet/8 px-3 py-2 text-sm text-silver">
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
      aria-pressed={active}
      className={[
        'rounded border px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] transition-colors',
        active
          ? 'border-orange/50 bg-orange/12 text-orange'
          : 'border-border bg-bg3/35 text-silver-dk hover:border-orange/35 hover:text-orange-lt',
      ].join(' ')}
    >
      {label}
      <span className="sr-only">{active ? ' enabled' : ' disabled'}</span>
    </button>
  );
}

function EmptyPanel({ title, body }: { title: string; body: string }) {
  return (
    <div className="premium-subpanel px-4 py-12 text-center">
      <h2 className="font-display text-sm tracking-[0.12em] text-text">{title}</h2>
      <p className="mx-auto mt-2 max-w-lg text-sm leading-relaxed text-silver-dk">{body}</p>
    </div>
  );
}

function TelemetrySection({
  syncKey,
  isLoading,
  error,
  telemetry,
  onInspectSystem,
}: {
  syncKey: string;
  isLoading: boolean;
  error: string | null;
  telemetry: ReturnType<typeof useJournalTelemetrySummary>['data'] | null;
  onInspectSystem: (id64: number) => void;
}) {
  return (
    <section className="space-y-4" data-testid="my-work-telemetry">
      <div className="premium-subpanel border-cyan/30 bg-cyan/8 px-3 py-2 text-sm text-silver">
        My Work telemetry is sync-key scoped and read-only. It shows what your imported journal data observed; it does not claim canonical truth or live commander identity.
      </div>
      <div className="rounded border border-border/60 bg-bg2/35 px-3 py-2 font-mono text-[11px] text-silver-dk">
        Telemetry scope: <span className="text-cyan">{syncKey}</span>
      </div>
      {isLoading ? (
        <div className="premium-subpanel px-4 py-8 text-sm text-silver-dk">
          Loading telemetry summary...
        </div>
      ) : null}
      {error ? (
        <div className="rounded-chunk-sm border border-red/40 bg-red/10 px-3 py-2 text-sm text-red">
          {error}
        </div>
      ) : null}
      {!isLoading && !error && telemetry ? (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Imports" value={telemetry.runs_count} detail={telemetry.last_imported_at ? `Last import ${formatTimestamp(telemetry.last_imported_at)}` : 'No imports yet'} />
            <MetricCard label="Observed systems" value={telemetry.systems_observed} detail="Distinct systems seen in your staged journal telemetry" />
            <MetricCard label="Body observations" value={telemetry.body_observation_count} detail="Scan and signal events captured from your journal imports" />
            <MetricCard label="Docked events" value={telemetry.docked_observation_count} detail="Station visit observations captured from your journal imports" />
          </div>
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
            <div className="premium-subpanel space-y-3 p-4">
              <div>
                <h2 className="font-display text-base tracking-[0.1em] text-text">Recently observed systems</h2>
                <p className="mt-1 text-sm text-silver-dk">
                  Recent systems seen in your imported telemetry. Use these as personal context, not shared canonical truth.
                </p>
              </div>
              {telemetry.recent_systems.length === 0 ? (
                <p className="text-sm text-silver-dk">No telemetry-backed systems yet. Import journal files above to start building your personal observed context.</p>
              ) : (
                <ul className="space-y-2">
                  {telemetry.recent_systems.map((system) => (
                    <li key={system.system_id64} className="premium-toolbar flex flex-wrap items-center justify-between gap-3 rounded-2xl px-3 py-2">
                      <div className="min-w-0 flex-1">
                        <div className="font-display text-sm tracking-[0.08em] text-text">{system.system_name}</div>
                        <div className="mt-1 text-sm text-silver-dk">
                          {system.event_count} event{system.event_count === 1 ? '' : 's'} Â· {system.event_types.join(', ')} Â· Last observed {formatTimestamp(system.last_observed_at)}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => onInspectSystem(system.system_id64)}
                        className="btn-metal text-[11px] font-mono"
                      >
                        Inspect system
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="space-y-4">
              <div className="premium-subpanel space-y-3 p-4">
                <div>
                  <h2 className="font-display text-base tracking-[0.1em] text-text">Recent import runs</h2>
                  <p className="mt-1 text-sm text-silver-dk">
                    Bounded receipts for your recent sync-key journal imports.
                  </p>
                </div>
                {telemetry.recent_runs.length === 0 ? (
                  <p className="text-sm text-silver-dk">No recent runs yet.</p>
                ) : (
                  <ul className="space-y-2">
                    {telemetry.recent_runs.map((run) => (
                      <li key={run.run_key} className="rounded border border-border/40 bg-bg1/35 px-3 py-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-cyan">{run.status}</span>
                          <span className="font-mono text-[11px] text-silver-dk">{run.run_key}</span>
                        </div>
                        <p className="mt-2 text-sm text-silver">
                          Staged {run.observations_staged} Â· Duplicates {run.duplicates_skipped}
                        </p>
                        <p className="mt-1 text-sm text-silver-dk">
                          {formatCompactEventCounts(run.event_counts)}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="premium-subpanel space-y-3 p-4">
                <h2 className="font-display text-base tracking-[0.1em] text-text">Event mix</h2>
                <p className="text-sm text-silver-dk">
                  {formatCompactEventCounts(telemetry.event_counts)}
                </p>
              </div>
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}

function MetricCard({ label, value, detail }: { label: string; value: number; detail: string }) {
  return (
    <div className="premium-subpanel p-4">
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">{label}</div>
      <div className="mt-1 text-2xl text-text">{value.toLocaleString()}</div>
      <div className="mt-2 text-sm text-silver-dk">{detail}</div>
    </div>
  );
}

function formatCompactEventCounts(eventCounts: Record<string, number>): string {
  const entries = Object.entries(eventCounts).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return 'No observed events recorded yet.';
  return entries.map(([eventType, count]) => `${eventType} ${count}`).join(' Â· ');
}
