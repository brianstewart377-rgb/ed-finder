import { useMemo, useState } from 'react';
import type { UseWatchlist } from '@/features/watchlist/useWatchlist';
import type { UsePinned } from '@/features/pinned/usePinned';
import {
  useColonyProjectStore,
  type ColonyProject,
} from '@/features/colony-planner/colonyProjectStore';
import {
  useMyWorkStore,
  type SavedSystemLabel,
} from './myWorkStore';
import {
  buildColonies,
  buildSavedSystems,
  formatTimestamp,
  groupPlansBySystem,
  selectContinuation,
  type SavedSystemViewModel,
} from './myWorkWorkspaceUtils';
import { JournalImportPanel } from '@/features/journal-import/JournalImportPanel';
import { useJournalTelemetrySummary } from './useJournalTelemetrySummary';
import { useSyncKeyStore } from '@/store/syncKeyStore';
import {
  useExpansionPlanStore,
  type ExpansionPlan,
} from '@/features/expansion-plans/expansionPlanStore';
import { computeExpansionPlanStatus } from './expansionPlanStatus';
import { economyColor } from '@ed-finder/planner-core/economyVisuals';
import type { JournalTelemetryRecentSystem } from '@/types/api';
import { ContinueWhereLeftOff } from './components/ContinueWhereLeftOff';
import { SavedSystemCard } from './components/SavedSystemCard';
import { PlanCard } from './components/PlanCard';
import { EmptyPanel } from './components/EmptyPanel';
import { TelemetrySection } from './components/TelemetrySection';

type MyWorkSection = 'saved-systems' | 'plans' | 'expansion-plans' | 'my-colonies' | 'telemetry';

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
  { id: 'expansion-plans', label: 'Expansion Plans' },
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

  // Expansion plans
  const expansionPlansRecord = useExpansionPlanStore((state) => state.plans);
  const renameExpansionPlan = useExpansionPlanStore((state) => state.renamePlan);
  const archiveExpansionPlan = useExpansionPlanStore((state) => state.archivePlan);
  const [editingExpansionPlanId, setEditingExpansionPlanId] = useState<string | null>(null);
  const [editingExpansionPlanName, setEditingExpansionPlanName] = useState('');

  const activeExpansionPlans = useMemo(
    () => Object.values(expansionPlansRecord).filter((p) => !p.archived_at)
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
    [expansionPlansRecord],
  );

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

  const beginExpansionRename = (plan: ExpansionPlan) => {
    setEditingExpansionPlanId(plan.id);
    setEditingExpansionPlanName(plan.plan_name);
  };

  const saveExpansionRename = () => {
    if (!editingExpansionPlanId) return;
    renameExpansionPlan(editingExpansionPlanId, editingExpansionPlanName);
    setEditingExpansionPlanId(null);
    setEditingExpansionPlanName('');
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
            <span className="premium-toolbar rounded-full px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-orange-lt">
              Stored on this device
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
              body="Start a plan from a system’s details and it will appear here with its objective, starting approach, and saved progress."
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

      {activeSection === 'expansion-plans' ? (
        <section className="space-y-4" data-testid="my-work-expansion-plans">
          {activeExpansionPlans.length === 0 ? (
            <EmptyPanel
              title="No expansion plans yet"
              body="Create one from a Region Search result in Finder."
            />
          ) : (
            <div className="space-y-4">
              {activeExpansionPlans.map((plan) => {
                const planStatus = computeExpansionPlanStatus(plan, projectsRecord);
                return (
                  <section key={plan.id} className="premium-subpanel space-y-3 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        {editingExpansionPlanId === plan.id ? (
                          <div className="flex items-center gap-2">
                            <input
                              type="text"
                              value={editingExpansionPlanName}
                              onChange={(e) => setEditingExpansionPlanName(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') saveExpansionRename();
                                if (e.key === 'Escape') setEditingExpansionPlanId(null);
                              }}
                              className="px-2 py-1 rounded bg-bg3 border border-border font-display text-base text-text"
                              autoFocus
                            />
                            <button type="button" onClick={saveExpansionRename} className="btn-primary text-[10px] px-2 py-1">Save</button>
                            <button type="button" onClick={() => setEditingExpansionPlanId(null)} className="btn-metal text-[10px] px-2 py-1">Cancel</button>
                          </div>
                        ) : (
                          <h2
                            className="font-display text-base tracking-[0.12em] text-text cursor-pointer hover:text-orange transition-colors"
                            onClick={() => beginExpansionRename(plan)}
                            title="Click to rename"
                          >
                            {plan.plan_name}
                          </h2>
                        )}
                        <div className="flex items-center gap-2 mt-1">
                          <span className="font-mono text-[11px] text-silver-dk">
                            {plan.anchor_system_name}
                          </span>
                          {plan.galaxy_region && (
                            <>
                              <span className="text-text-dim text-[10px]">·</span>
                              <span className="font-mono text-[10px] text-text-dim">
                                {plan.galaxy_region}
                              </span>
                            </>
                          )}
                          <span className="text-text-dim text-[10px]">·</span>
                          <span
                            className={[
                              'rounded-full px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide border',
                              planStatus === 'Established'
                                ? 'border-green/40 bg-green/10 text-green'
                                : planStatus === 'In Progress'
                                  ? 'border-gold/40 bg-gold/10 text-gold'
                                  : 'border-text-dim/40 bg-bg3/50 text-text-dim',
                            ].join(' ')}
                          >
                            {planStatus}
                          </span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => handleInspectSystem(plan.anchor_system_id64)}
                          className="btn-metal text-[11px] font-mono"
                        >
                          Inspect anchor
                        </button>
                        <button
                          type="button"
                          onClick={() => archiveExpansionPlan(plan.id)}
                          className="btn-metal text-[11px] font-mono text-red hover:text-red"
                        >
                          Archive
                        </button>
                      </div>
                    </div>

                    {/* Slots */}
                    <div className="space-y-2 pl-2 border-l-2 border-border/50">
                      {plan.slots.map((slot) => {
                        const slotColor = economyColor(slot.economies[0]);
                        const linkedProject = slot.colony_project_id
                          ? projectsRecord[slot.colony_project_id] ?? null
                          : null;
                        return (
                          <div key={slot.slot_index} className="flex flex-wrap items-start justify-between gap-2 py-1.5">
                            <div className="min-w-0 flex-1">
                              <div
                                className="font-mono text-[10px] uppercase tracking-[0.12em] mb-0.5"
                                style={{ color: slotColor }}
                              >
                                {slot.label}
                              </div>
                              <button
                                type="button"
                                className="font-mono text-xs text-text hover:text-orange transition-colors text-left truncate block"
                                onClick={() => handleInspectSystem(slot.system_id64)}
                              >
                                {slot.system_name}
                              </button>
                              <div className="flex items-center gap-1.5 flex-wrap mt-0.5">
                                {Object.entries(slot.scores).map(([econ, score]) => (
                                  <span
                                    key={econ}
                                    className="font-mono text-[10px] px-1.5 py-0.5 rounded border"
                                    style={{
                                      color: economyColor(econ),
                                      borderColor: `${economyColor(econ)}40`,
                                      backgroundColor: `${economyColor(econ)}10`,
                                    }}
                                  >
                                    {econ.slice(0, 4)} {score}
                                  </span>
                                ))}
                                {slot.distance_from_anchor_ly != null && (
                                  <span className="font-mono text-[10px] text-text-dim">
                                    {slot.distance_from_anchor_ly} LY from anchor
                                  </span>
                                )}
                              </div>
                            </div>
                            <button
                              type="button"
                              onClick={() => onOpenPlanner(slot.system_id64, { projectId: slot.colony_project_id })}
                              className="btn-metal text-[11px] font-mono shrink-0"
                            >
                              {linkedProject ? 'Continue in Planner' : 'Open in Planner'}
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  </section>
                );
              })}
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
