import { useMemo } from 'react';
import { Bookmark, Compass, Rocket } from 'lucide-react';
import type { SystemArchetypeResponse, SystemDetail } from '@/types/api';
import {
  defaultDraftProjectName,
  objectiveLabel,
  PLANNER_OBJECTIVE_OPTIONS,
  type ColonyProjectObjective,
  type ColonyProjectStartApproach,
} from '@/features/colony-planner/plannerDraftContext';
import { SemanticStatusBadge } from '@/components/SemanticStatusBadge';
import { WorkspaceContextHeader } from '@/components/WorkspaceContextHeader';

export function ColonyPlannerEntryPoint({
  system,
  archetype,
  savedForLater,
  saveForLaterState,
  planningOpen,
  selectedObjective,
  selectedStartApproach,
  onToggleSaveForLater,
  onTogglePlanStart,
  onSelectObjective,
  onSelectStartApproach,
  onStartPlan,
}: {
  system: SystemDetail;
  archetype: SystemArchetypeResponse | null;
  savedForLater: boolean;
  saveForLaterState: 'idle' | 'saving' | 'removing';
  planningOpen: boolean;
  selectedObjective: ColonyProjectObjective | null;
  selectedStartApproach: ColonyProjectStartApproach | null;
  onToggleSaveForLater?: (context: {
    system: SystemDetail;
    archetype: SystemArchetypeResponse | null;
  }) => void;
  onTogglePlanStart: () => void;
  onSelectObjective: (value: ColonyProjectObjective) => void;
  onSelectStartApproach: (value: ColonyProjectStartApproach) => void;
  onStartPlan?: (
    system: SystemDetail,
    planStart: {
      objective: ColonyProjectObjective;
      startApproach: ColonyProjectStartApproach;
    },
  ) => void;
}) {
  const canStartPlan = Number.isFinite(system.id64) && system.id64 > 0 && !!onStartPlan;
  const saveActionBusy = saveForLaterState === 'saving' || saveForLaterState === 'removing';
  const saveActionLabel = saveForLaterState === 'saving'
    ? 'Saving…'
    : saveForLaterState === 'removing'
      ? 'Removing…'
      : savedForLater
        ? 'Saved'
        : 'Save for later';
  const defaultDraftName = useMemo(
    () => defaultDraftProjectName(system.name || 'Unknown system', selectedObjective ?? 'decide_later'),
    [selectedObjective, system.name],
  );

  return (
    <section
      data-testid="colony-planner-entry-card"
      className="rounded-chunk-lg border border-orange/35 bg-orange/10 p-4"
    >
      <WorkspaceContextHeader
        journeyLabel="Next step: Plan"
        title="Start a plan"
        headingLevel={3}
        supportingText={canStartPlan
          ? 'Assess this system, save it for later if needed, then create an intentional draft when you are ready to enter the canonical planner.'
          : 'Planner routing is unavailable for this system record, so continue reviewing system detail here or return to Explore.'}
        selectedSystemName={system.name || 'Unknown system'}
        selectedSystemMeta={<span className="tabular-nums">ID64 {Number.isFinite(system.id64) ? system.id64 : 'unknown'}</span>}
        status={(
          <SemanticStatusBadge
            label={canStartPlan ? 'Planning available' : 'Planner unavailable'}
            tone={canStartPlan ? 'available' : 'unavailable'}
          />
        )}
        actions={(
          <>
            <button
              type="button"
              onClick={() => onToggleSaveForLater?.({ system, archetype })}
              disabled={saveActionBusy}
              data-testid="system-detail-save-for-later"
              aria-pressed={savedForLater}
              aria-label={savedForLater ? 'Remove from saved' : 'Save for later'}
              aria-busy={saveActionBusy || undefined}
              className={[
                'inline-flex items-center gap-2 rounded-chunk-sm border px-3 py-2 text-xs font-mono font-bold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/80',
                savedForLater
                  ? 'border-orange/50 bg-orange/15 text-orange hover:bg-orange/25'
                  : 'border-border bg-bg4 text-silver hover:border-orange/45 hover:text-orange',
                saveActionBusy ? 'cursor-not-allowed opacity-80' : '',
              ].join(' ')}
            >
              <Bookmark size={14} />
              {saveActionLabel}
            </button>
            <button
              type="button"
              onClick={onTogglePlanStart}
              disabled={!canStartPlan}
              data-testid="open-plan-start"
              className="inline-flex items-center gap-2 rounded-chunk-sm border border-orange/50 bg-orange/15 px-3 py-2 text-xs font-mono font-bold text-orange hover:bg-orange/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/80 disabled:cursor-not-allowed disabled:border-border disabled:bg-bg3/60 disabled:text-silver-dk"
            >
              <Rocket size={14} />
              {planningOpen ? 'Hide plan start' : 'Start a plan'}
            </button>
          </>
        )}
      />
      {planningOpen ? (
        <PlanStartPanel
          systemName={system.name || 'Unknown system'}
          selectedObjective={selectedObjective}
          selectedStartApproach={selectedStartApproach}
          draftName={defaultDraftName}
          onSelectObjective={onSelectObjective}
          onSelectStartApproach={onSelectStartApproach}
          onConfirm={() => {
            if (!selectedObjective || !selectedStartApproach) return;
            onStartPlan?.(system, {
              objective: selectedObjective,
              startApproach: selectedStartApproach,
            });
          }}
        />
      ) : null}
    </section>
  );
}

function PlanStartPanel({
  systemName,
  selectedObjective,
  selectedStartApproach,
  draftName,
  onSelectObjective,
  onSelectStartApproach,
  onConfirm,
}: {
  systemName: string;
  selectedObjective: ColonyProjectObjective | null;
  selectedStartApproach: ColonyProjectStartApproach | null;
  draftName: string;
  onSelectObjective: (value: ColonyProjectObjective) => void;
  onSelectStartApproach: (value: ColonyProjectStartApproach) => void;
  onConfirm: () => void;
}) {
  const readyToCreate = selectedObjective != null && selectedStartApproach != null;

  return (
    <div
      data-testid="plan-start-panel"
      className="mt-4 rounded-chunk-lg border border-orange/30 bg-bg2/85 p-4 space-y-4"
    >
      <div className="space-y-1">
        <h4 className="font-display text-base tracking-[0.1em] text-orange-lt">
          Start a real local draft
        </h4>
        <p className="text-sm leading-relaxed text-silver">
          Choose an objective, choose how you want to begin, then enter the canonical planner for {systemName}.
        </p>
      </div>

      <section className="space-y-2">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-orange">Step 1</span>
          <h5 className="font-mono text-[11px] uppercase tracking-[0.14em] text-silver">Objective</h5>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          {PLANNER_OBJECTIVE_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => onSelectObjective(option.value)}
              data-testid={`plan-objective-${option.value}`}
              aria-pressed={selectedObjective === option.value}
              className={[
                'rounded border px-3 py-3 text-left transition-colors',
                selectedObjective === option.value
                  ? 'border-orange/50 bg-orange/10'
                  : 'border-border bg-bg3/35 hover:border-orange/35',
              ].join(' ')}
            >
              <div className="font-semibold text-text">{option.label}</div>
              <p className="mt-1 text-xs leading-relaxed text-silver-dk">{option.description}</p>
            </button>
          ))}
        </div>
      </section>

      <section className="space-y-2">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-orange">Step 2</span>
          <h5 className="font-mono text-[11px] uppercase tracking-[0.14em] text-silver">Starting approach</h5>
        </div>
        <div className="grid gap-2 lg:grid-cols-2">
          <button
            type="button"
            onClick={() => onSelectStartApproach('recommendation_assisted')}
            data-testid="plan-approach-recommendation"
            aria-pressed={selectedStartApproach === 'recommendation_assisted'}
            className={[
              'rounded border px-3 py-3 text-left transition-colors',
              selectedStartApproach === 'recommendation_assisted'
                ? 'border-cyan/45 bg-cyan/10'
                : 'border-border bg-bg3/35 hover:border-cyan/35',
            ].join(' ')}
          >
            <div className="flex items-center gap-2 font-semibold text-text">
              <Compass size={15} className="text-cyan" />
              Start with ED-Finder recommendation
            </div>
            <p className="mt-1 text-xs leading-relaxed text-silver-dk">
              ED-Finder will help compare suitable approaches in the planner. No recommendation is generated yet.
            </p>
          </button>
          <button
            type="button"
            onClick={() => onSelectStartApproach('manual')}
            data-testid="plan-approach-manual"
            aria-pressed={selectedStartApproach === 'manual'}
            className={[
              'rounded border px-3 py-3 text-left transition-colors',
              selectedStartApproach === 'manual'
                ? 'border-orange/45 bg-orange/10'
                : 'border-border bg-bg3/35 hover:border-orange/35',
            ].join(' ')}
          >
            <div className="flex items-center gap-2 font-semibold text-text">
              <Rocket size={15} className="text-orange" />
              Build my own plan
            </div>
            <p className="mt-1 text-xs leading-relaxed text-silver-dk">
              Start with an empty editable draft and shape the plan manually in the planner.
            </p>
          </button>
        </div>
      </section>

      <div className="rounded border border-border/60 bg-bg3/35 px-3 py-2">
        <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">Draft preview</div>
        <div className="mt-1 text-sm text-text">{draftName}</div>
        <div className="mt-1 text-xs text-silver-dk">
          {selectedObjective ? objectiveLabel(selectedObjective) : 'Choose an objective'} / Draft
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={onConfirm}
          disabled={!readyToCreate}
          data-testid="confirm-start-plan"
          className="inline-flex items-center gap-2 rounded-chunk-sm border border-orange/50 bg-orange/15 px-3 py-2 text-xs font-mono font-bold text-orange hover:bg-orange/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/80 disabled:cursor-not-allowed disabled:border-border disabled:bg-bg3/60 disabled:text-silver-dk"
        >
          <Rocket size={14} />
          Create draft and open planner
        </button>
        {!readyToCreate ? (
          <p className="text-xs text-silver-dk">
            Choose one objective and one starting approach to continue.
          </p>
        ) : null}
      </div>
    </div>
  );
}
