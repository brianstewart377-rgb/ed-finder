import { useEffect, useMemo, useState } from 'react';
import { Bookmark, Compass, Rocket, X } from 'lucide-react';
import type { SystemArchetypeResponse, SystemDetail, SystemBody, SystemStation } from '@/types/api';
import { distanceFromSol, formatCoords, formatPopulationForSystem, systemStatusLabel } from '@/lib/format';
import { compareBodiesByHierarchy } from '@/lib/bodyHierarchySort';
import { transientStationPlanningReason } from '@/features/colony-planner/existingInfrastructure';
import {
  defaultDraftProjectName,
  objectiveLabel,
  PLANNER_OBJECTIVE_OPTIONS,
  type ColonyProjectObjective,
  type ColonyProjectStartApproach,
} from '@/features/colony-planner/plannerDraftContext';
import { SemanticStatusBadge } from '@/components/SemanticStatusBadge';
import { WorkspaceContextHeader } from '@/components/WorkspaceContextHeader';
import { archetypeTierFromScore, formatArchetypeLabel } from '@/lib/archetypes';
import { archetypeFromEconomy } from '@/features/system-detail/simulation-preview/utils/placementHelpers';
import { useSystemDetail } from './useSystemDetail';
import { useSystemArchetype } from './useSystemArchetype';
import { ArchetypeAssessment } from './ArchetypeAssessment';

export interface SystemDetailModalProps {
  id64:    number;
  onClose: () => void;
  focusIntent?: 'colony-planner' | null;
  savedForLater?: boolean;
  saveForLaterState?: 'idle' | 'saving' | 'removing';
  onToggleSaveForLater?: (context: {
    system: SystemDetail;
    archetype: SystemArchetypeResponse | null;
  }) => void;
  onStartPlan?: (
    system: SystemDetail,
    planStart: {
      objective: ColonyProjectObjective;
      startApproach: ColonyProjectStartApproach;
    },
  ) => void;
  /** Renders alongside Spansh / Inara / EDSM so callers can wire up
   *  Watchlist / Pin / Compare / Show-on-map without this component knowing
   *  about those features. Receives the loaded SystemDetail or null while
   *  the fetch is in flight. */
  renderActions?: (context: {
    system: SystemDetail | null;
    archetype: SystemArchetypeResponse | null;
  }) => React.ReactNode;
}

/**
 * Full system-detail modal. Renders on top of the current tab via a
 * fixed-position overlay; closes on:
 *   • Escape key
 *   • click on the dim backdrop (not the content)
 *   • the X button in the header
 *
 * Body scroll is locked while the modal is open so the page underneath
 * doesn't scroll when you wheel the modal content.
 */
export function SystemDetailModal({
  id64,
  onClose,
  focusIntent = null,
  savedForLater = false,
  saveForLaterState = 'idle',
  onToggleSaveForLater,
  onStartPlan,
  renderActions,
}: SystemDetailModalProps) {
  const { data, loading, error, refetch } = useSystemDetail(id64);
  const {
    data: archetypeData,
    loading: archetypeLoading,
    error: archetypeError,
    refetch: refetchArchetype,
  } = useSystemArchetype(id64);
  const [planStartOpen, setPlanStartOpen] = useState(false);
  const [selectedObjective, setSelectedObjective] = useState<ColonyProjectObjective | null>(null);
  const [selectedStartApproach, setSelectedStartApproach] = useState<ColonyProjectStartApproach | null>(null);
  const loadedSystemId = data?.id64 ?? null;
  const fallbackArchetype = useMemo(() => buildFallbackArchetype(data), [data]);
  const effectiveArchetype = archetypeData ?? fallbackArchetype;
  const archetypeWarning = archetypeError && effectiveArchetype
    ? 'Using the development snapshot already loaded with system detail while the live archetype service is unavailable.'
    : null;
  const showArchetypeLoading = archetypeLoading && !effectiveArchetype;

  // Esc closes the modal. Body scroll lock only fires if we're actually
  // mounted (id64 changes between mounts so this is per-open).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose]);

  useEffect(() => {
    if (loadedSystemId == null) return;
    setPlanStartOpen(focusIntent === 'colony-planner' && Boolean(onStartPlan));
    setSelectedObjective(null);
    setSelectedStartApproach(null);
  }, [focusIntent, loadedSystemId, onStartPlan]);

  return (
    <div
      data-testid="system-detail-modal"
      className="fixed inset-0 z-40 flex items-start justify-center bg-bg1/85 backdrop-blur-md overflow-y-auto px-4 py-8 sm:py-12"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="system-detail-title"
    >
      <article
        className="panel relative w-full max-w-6xl animate-fade-up"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          data-testid="system-detail-close"
          aria-label="Close system details"
          className="absolute right-4 top-4 z-50 grid h-10 w-10 place-items-center rounded-full border border-white/20 bg-bg1/95 text-white shadow-[0_10px_30px_rgba(0,0,0,0.45)] transition-colors hover:border-orange/70 hover:bg-orange hover:text-bg1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/80"
        >
          <X size={19} strokeWidth={3} />
        </button>
        <ModalHeader
          system={data}
          id64={id64}
          loading={loading}
          hasError={Boolean(error)}
        />

        <div className="px-5 sm:px-6 py-5 space-y-5 text-sm">
          {loading && (
            <div className="rounded-chunk-lg border border-border bg-bg3/30 px-4 py-8 text-center">
              <div className="flex justify-center">
                <SemanticStatusBadge label="Loading" tone="loading" />
              </div>
              <p className="mt-3 text-sm text-silver">
                Loading system detail for inspection.
              </p>
              <p className="mt-1 text-xs text-silver-dk">
                Review the selected system here, then move into Colony Planner when the context is ready.
              </p>
            </div>
          )}

          {error && (
            <div className="rounded-chunk-lg border border-red/50 bg-red/10 p-4 text-sm text-red">
              <div className="flex flex-wrap items-center gap-2">
                <SemanticStatusBadge label="Unavailable" tone="unavailable" />
                <span className="font-semibold">System detail is unavailable right now.</span>
              </div>
              <p className="mt-2 text-silver">
                Retry the request, or return to Explore and inspect another system.
              </p>
              <button
                type="button"
                onClick={refetch}
                className="mt-3 rounded-chunk-sm border border-border bg-bg4 px-3 py-2 text-xs font-mono font-bold text-text-dim hover:text-orange focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/80"
              >
                ↺ Retry
              </button>
            </div>
          )}

          {data && (
            <>
              <ColonyPlannerEntryPoint
                system={data}
                archetype={effectiveArchetype}
                savedForLater={savedForLater}
                saveForLaterState={saveForLaterState}
                planningOpen={planStartOpen}
                selectedObjective={selectedObjective}
                selectedStartApproach={selectedStartApproach}
                onToggleSaveForLater={onToggleSaveForLater}
                onTogglePlanStart={() => setPlanStartOpen((open) => !open)}
                onSelectObjective={setSelectedObjective}
                onSelectStartApproach={setSelectedStartApproach}
                onStartPlan={onStartPlan}
              />
              <Section title="Archetype assessment">
                <ArchetypeAssessment
                  archetype={effectiveArchetype}
                  loading={showArchetypeLoading}
                  error={archetypeError}
                  warning={archetypeWarning}
                  onRetry={refetchArchetype}
                />
              </Section>
              <SystemInfoGrid sys={data} />
              <BodiesSection bodies={data.bodies} systemName={data.name} />
              <StationsSection stations={data.stations} />
              <ExplorationValue value={data.exploration_value} />


              <ExternalLinks sys={data} />
            </>
          )}

          <div className="flex flex-wrap gap-2 pt-2 border-t border-border">
            {renderActions?.({ system: data, archetype: effectiveArchetype })}
          </div>
        </div>
      </article>
    </div>
  );
}

function ColonyPlannerEntryPoint({
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

function buildFallbackArchetype(system: SystemDetail | null): SystemArchetypeResponse | null {
  if (!system) return null;

  const primaryKey = system.primary_archetype
    ?? archetypeFromEconomy(system.primary_economy ?? null)
    ?? archetypeFromEconomy(system.secondary_economy ?? null);
  if (!primaryKey) return null;

  const developmentScore = firstFinite(
    system.overall_development_potential,
    system.buildability_score,
    system.purity_score,
    system.score,
  );
  if (developmentScore == null) return null;

  const positives: string[] = [];
  if ((system.buildability_score ?? 0) >= 70) positives.push('Strong buildability snapshot already present in system detail.');
  if ((system.purity_score ?? 0) >= 70) positives.push('High purity signal suggests a cleaner economy mix.');
  if ((system.est_total_slots ?? 0) > 0) positives.push(`Estimated slot capacity: ${system.est_total_slots}.`);

  const risks: string[] = [];
  if ((system.contamination_risk ?? 0) >= 40) risks.push('Contamination risk is elevated in the current snapshot.');
  if (system.build_complexity) risks.push(`Build complexity is currently marked ${system.build_complexity}.`);

  const summary = [
    `Development score snapshot ${Math.round(developmentScore)}.`,
    system.overall_development_potential == null && system.score != null
      ? 'Using the score already present on system detail until archetype rows refresh.'
      : null,
    system.buildability_score != null ? `Buildability ${Math.round(system.buildability_score)}.` : null,
    system.purity_score != null ? `Purity ${Math.round(system.purity_score)}.` : null,
  ].filter(Boolean).join(' ');

  return {
    id64: system.id64,
    name: system.name ?? `System ${system.id64}`,
    coords: system.coords ?? null,
    main_star_type: system.main_star_type ?? null,
    archetypes: {
      [primaryKey]: {
        score: developmentScore,
        tier: archetypeTierFromScore(developmentScore) ?? 'D',
        label: formatArchetypeLabel(primaryKey),
        rationale: {
          summary,
          positives,
          risks,
          tags: [],
        },
      },
    },
    primary_archetype: primaryKey,
    secondary_archetype: system.secondary_archetype ?? null,
    archetype_confidence: system.archetype_confidence ?? null,
    overall_development_potential: system.overall_development_potential ?? developmentScore,
    buildability_score: system.buildability_score ?? null,
    build_complexity: system.build_complexity ?? null,
    purity_score: system.purity_score ?? null,
    contamination_risk: system.contamination_risk ?? null,
    confidence: system.archetype_confidence ?? null,
    tags: [],
  };
}

function firstFinite(...values: Array<number | null | undefined>): number | null {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
  }
  return null;
}

// ─── Header ────────────────────────────────────────────────────────────────

function ModalHeader({
  system,
  id64,
  loading,
  hasError,
}: {
  system?: SystemDetail | null;
  id64: number;
  loading: boolean;
  hasError: boolean;
}) {
  const statusLabel = loading
    ? 'Loading'
    : hasError
      ? 'Unavailable'
      : system
        ? systemStatusLabel(system)
        : 'Unknown';
  const statusTone = loading
    ? 'loading'
    : hasError
      ? 'unavailable'
      : statusLabel === 'Colonised'
        ? 'canonical'
        : statusLabel === 'Colonising'
          ? 'caution'
          : 'available';

  return (
    <header className="sticky top-0 z-10 border-b border-border bg-bg2/90 px-5 py-4 pr-16 backdrop-blur-md rounded-t-chunk-lg sm:px-7 sm:pr-20">
      <WorkspaceContextHeader
        journeyLabel="Journey stage: Inspect"
        title="System Detail"
        headingLevel={2}
        supportingText="Review the selected system, understand its current context, and move into planning when you are ready."
        selectedSystemName={loading ? 'Loading system...' : system?.name || 'Unknown system'}
        selectedSystemMeta={<span className="tabular-nums">ID64 {id64}</span>}
        status={<SemanticStatusBadge label={statusLabel} tone={statusTone} />}
        testId="system-detail-context-header"
      />
      <h2 id="system-detail-title" className="sr-only">
        {loading ? 'Loading system detail' : system?.name || 'Unknown system'}
      </h2>
    </header>
  );
}

// ─── Sections ──────────────────────────────────────────────────────────────

function SystemInfoGrid({ sys }: { sys: SystemDetail }) {
  const dSol = distanceFromSol(sys, sys.id64);
  const fields: Array<{ label: string; value: React.ReactNode } | null> = [
    {
      label: 'Coordinates',
      value: (
        <span className="tabular-nums text-cyan">
          {formatCoords(sys, sys.id64)}
          {dSol != null && (
            <span className="text-text-dim text-[10px] ml-2">
              ({dSol.toFixed(1)} LY from Sol)
            </span>
          )}
        </span>
      ),
    },
    sys.primary_economy
      ? { label: 'Primary economy', value: <span className="text-gold">{sys.primary_economy}</span> }
      : null,
    sys.secondary_economy
      ? { label: 'Secondary economy', value: sys.secondary_economy }
      : null,
    {
      label: 'Population',
      value: formatPopulationForSystem(sys),
    },
    sys.security    ? { label: 'Security',    value: sys.security } : null,
    sys.allegiance  ? { label: 'Allegiance',  value: sys.allegiance } : null,
    sys.government  ? { label: 'Government',  value: sys.government } : null,
    sys.main_star_subtype || sys.main_star_type
      ? { label: 'Main star', value: <span className="text-cyan">{sys.main_star_subtype || sys.main_star_type}</span> }
      : null,
  ];

  const visible = fields.filter(
    (f): f is { label: string; value: React.ReactNode } => f !== null,
  );

  return (
    <Section title="System info">
      <dl className="grid sm:grid-cols-2 gap-x-6 gap-y-2 text-xs">
        {visible.map((f) => (
          <div key={f.label} className="flex justify-between gap-3 border-b border-border/50 pb-1">
            <dt className="text-text-dim font-mono uppercase tracking-wider text-[10px]">{f.label}</dt>
            <dd className="text-right text-text font-mono">{f.value}</dd>
          </div>
        ))}
      </dl>
    </Section>
  );
}

function BodiesSection({ bodies, systemName }: { bodies?: SystemBody[]; systemName?: string | null }) {
  if (!bodies || bodies.length === 0) return null;

  // Stars first, then planets/moons by natural Elite hierarchy.
  const sorted = [...bodies].sort((a, b) => {
    const rank = (v: SystemBody) =>
      v.body_type === 'Star' ? 0 :
      v.body_type === 'Planet' ? 1 : 2;
    if (rank(a) !== rank(b)) return rank(a) - rank(b);
    return compareBodiesByHierarchy(a, b, systemName);
  });

  return (
    <Section title={`Bodies (${bodies.length})`}>
      <div className="overflow-x-auto rounded-chunk-lg border border-border" style={{
        background: 'linear-gradient(180deg, rgba(20,22,26,0.85), rgba(14,16,20,0.85))',
        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04), 0 8px 24px -16px rgba(0,0,0,0.6)',
      }}>
        <table className="w-full text-xs font-mono">
          <thead className="text-silver-dk uppercase tracking-[0.16em] text-[10px]" style={{
            background: 'linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01))',
            borderBottom: '1px solid hsl(216 10% 24%)',
          }}>
            <tr>
              <th className="px-3 py-2.5 text-left">Name</th>
              <th className="px-3 py-2.5 text-left">Type</th>
              <th className="px-3 py-2.5 text-left">Tags</th>
              <th className="px-3 py-2.5 text-right">Dist (ls)</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((b) => (
              <tr key={b.id} className="border-t border-border/50 hover:bg-orange/5 transition-colors">
                <td className="px-3 py-2 text-orange-lt font-semibold">{b.name}</td>
                <td className="px-3 py-2 text-silver">{b.subtype || b.body_type || '—'}</td>
                <td className="px-3 py-2 text-silver-dk text-[10px]">
                  <BodyTags body={b} />
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-silver">
                  {b.distance_from_star != null ? b.distance_from_star.toFixed(0) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function BodyTags({ body }: { body: SystemBody }) {
  const tags: string[] = [];
  if (body.is_earth_like)         tags.push('🌍 ELW');
  if (body.is_water_world)        tags.push('🌊 WW');
  if (body.is_ammonia_world)      tags.push('🟣 AW');
  if (body.is_landable)           tags.push('⬇ Land');
  if (body.is_terraformable)      tags.push('♻ Terr');
  if ((body.bio_signal_count ?? 0) > 0) tags.push(`🧬 ×${body.bio_signal_count}`);
  if ((body.geo_signal_count ?? 0) > 0) tags.push(`🌋 ×${body.geo_signal_count}`);
  if (body.spectral_class)        tags.push(`${body.spectral_class}${body.is_scoopable ? ' ⛽' : ''}`);
  if (tags.length === 0) return <span className="text-text-dim">—</span>;
  return <>{tags.join(' · ')}</>;
}

function StationsSection({ stations }: { stations?: SystemStation[] }) {
  if (!stations || stations.length === 0) return null;
  return (
    <Section title={`Stations (${stations.length})`}>
      <div className="overflow-x-auto rounded-chunk-lg border border-border" style={{
        background: 'linear-gradient(180deg, rgba(20,22,26,0.85), rgba(14,16,20,0.85))',
        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04), 0 8px 24px -16px rgba(0,0,0,0.6)',
      }}>
        <table data-testid="system-detail-stations-table" className="w-full text-xs font-mono">
          <thead className="text-silver-dk uppercase tracking-[0.16em] text-[10px]" style={{
            background: 'linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01))',
            borderBottom: '1px solid hsl(216 10% 24%)',
          }}>
            <tr>
              <th className="px-3 py-2.5 text-left">Name</th>
              <th className="px-3 py-2.5 text-left">Body</th>
              <th className="px-3 py-2.5 text-left">Type</th>
              <th className="px-3 py-2.5 text-left">Lane</th>
              <th className="px-3 py-2.5 text-left">Status</th>
              <th className="px-3 py-2.5 text-left">Pad</th>
              <th className="px-3 py-2.5 text-left">Services</th>
              <th className="px-3 py-2.5 text-right">Dist (ls)</th>
            </tr>
          </thead>
          <tbody>
            {stations.map((s) => (
              <tr key={s.id} className="border-t border-border/50 hover:bg-orange/5 transition-colors">
                <td className="px-3 py-2 text-orange-lt font-semibold">{s.name}</td>
                <td className="px-3 py-2 text-silver">{stationBodyLabel(s)}</td>
                <td className="px-3 py-2 text-silver">{s.station_type || '—'}</td>
                <td className="px-3 py-2">
                  <StationLaneBadge station={s} />
                </td>
                <td className="px-3 py-2">
                  <StationAssociationBadge station={s} />
                </td>
                <td className="px-3 py-2">
                  <span className={[
                    'inline-grid place-items-center min-w-[26px] h-6 rounded-md text-[10px] font-bold border',
                    s.landing_pad_size === 'L' ? 'border-green/50 text-green bg-green/10'
                      : s.landing_pad_size === 'M' ? 'border-gold/50 text-gold bg-gold/10'
                      : s.landing_pad_size === 'S' ? 'border-silver-dk/50 text-silver bg-bg4'
                      : 'border-border text-silver-dk',
                  ].join(' ')}>
                    {s.landing_pad_size || '?'}
                  </span>
                </td>
                <td className="px-3 py-2 text-silver-dk text-[10px] space-x-1">
                  {s.has_market     && <span className="chip">Market</span>}
                  {s.has_shipyard   && <span className="chip">Shipyard</span>}
                  {s.has_outfitting && <span className="chip">Outfitting</span>}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-silver">
                  {s.distance_from_star != null ? s.distance_from_star.toFixed(0) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function StationLaneBadge({ station }: { station: SystemStation }) {
  const transientReason = transientStationPlanningReason(station as SystemStation & Record<string, unknown>);
  const label = transientReason
    ? 'Transient / non-slot'
    : station.lane === 'orbital'
      ? 'Orbital'
      : station.lane === 'surface'
        ? 'Surface'
        : 'Unknown';
  const tone = transientReason
    ? 'border-cyan/35 bg-cyan/10 text-cyan'
    : station.lane === 'orbital' || station.lane === 'surface'
      ? 'border-green/35 bg-green/10 text-green'
      : 'border-gold/35 bg-gold/10 text-gold';

  return (
    <span
      title={transientReason ?? `Lane: ${label}`}
      className={['inline-flex rounded border px-2 py-1 text-[10px]', tone].join(' ')}
    >
      {label}
    </span>
  );
}

function StationAssociationBadge({ station }: { station: SystemStation }) {
  const transientReason = transientStationPlanningReason(station as SystemStation & Record<string, unknown>);
  if (transientReason) {
    return (
      <span
        title={transientReason}
        className="inline-flex rounded border border-cyan/35 bg-cyan/10 px-2 py-1 text-[10px] text-cyan"
      >
        Fleet Carrier / transient / ignored for colony planning
      </span>
    );
  }

  const status = formatAssociationStatus(station.association_status);
  const confidence = formatAssociationConfidence(station.association_confidence);
  const source = formatAssociationSource(station.association_source);
  const label = [status, confidence, source].filter(Boolean).join(' / ') || 'Unknown';
  const tone = station.association_status === 'confirmed'
    ? 'border-green/35 bg-green/10 text-green'
    : station.association_status === 'inferred'
      ? 'border-gold/35 bg-gold/10 text-gold'
      : 'border-border text-silver-dk bg-bg4';

  return (
    <span
      title={station.resolver_notes ?? label}
      className={['inline-flex rounded border px-2 py-1 text-[10px]', tone].join(' ')}
    >
      {label}
    </span>
  );
}

function stationBodyLabel(station: SystemStation): string {
  return station.body_name || station.station_body_name || (station.body_id != null ? `Body ${station.body_id}` : '—');
}

function formatAssociationStatus(value?: string | null): string | null {
  if (value === 'confirmed') return 'Confirmed';
  if (value === 'inferred') return 'Inferred';
  if (value === 'unresolved') return 'Unresolved';
  return null;
}

function formatAssociationConfidence(value?: string | null): string | null {
  if (value === 'exact') return 'exact';
  if (value === 'strong_inference') return 'strong inference';
  if (value === 'weak_inference') return 'weak inference';
  if (value === 'unresolved') return 'unresolved';
  return null;
}

function formatAssociationSource(value?: string | null): string | null {
  const source = value?.trim();
  if (!source) return null;
  if (source.toLowerCase().startsWith('edsm')) return 'EDSM';
  if (source === 'transient_non_slot') return 'transient';
  return source.replace(/_/g, ' ');
}

function ExplorationValue({ value }: { value?: SystemDetail['exploration_value'] }) {
  if (!value || value.combined_value <= 0) return null;
  return (
    <Section title="Estimated exploration value">
      <div className="grid grid-cols-3 gap-3 text-xs font-mono">
        <ValueCell label="Scan"     value={value.total_scan_value} />
        <ValueCell label="Mapping"  value={value.total_mapping_value} />
        <ValueCell label="Combined" value={value.combined_value} highlight />
      </div>
    </Section>
  );
}

function ValueCell({ label, value, highlight }: { label: string; value: number; highlight?: boolean }) {
  return (
    <div className={[
      'rounded border p-2',
      highlight ? 'border-orange/50 bg-orange/10' : 'border-border bg-bg3/40',
    ].join(' ')}>
      <div className="text-text-dim uppercase tracking-wider text-[10px]">{label}</div>
      <div className={['tabular-nums font-bold', highlight ? 'text-orange' : 'text-text'].join(' ')}>
        {value.toLocaleString()} cr
      </div>
    </div>
  );
}

function ExternalLinks({ sys }: { sys: SystemDetail }) {
  const links: Array<[string, string]> = [
    ['Spansh', `https://spansh.co.uk/system/${sys.id64}`],
    ['Inara',  `https://inara.cz/elite/starsystem/?search=${encodeURIComponent(sys.name || '')}`],
    ['EDSM',   `https://www.edsm.net/en/system/id/${sys.id64}/name/${encodeURIComponent(sys.name || '')}`],
  ];
  return (
    <Section title="External">
      <div className="flex flex-wrap gap-2 text-xs font-mono">
        {links.map(([label, href]) => (
          <a
            key={label}
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="px-2 py-1 rounded bg-bg4 border border-border text-text-dim hover:text-orange hover:border-orange-dk"
          >
            {label} ↗
          </a>
        ))}
      </div>
    </Section>
  );
}

// ─── Layout helpers ────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h3 className="font-mono text-silver-dk uppercase tracking-[0.22em] text-[10px] flex items-center gap-3">
        <span className="block h-px flex-1 bg-gradient-to-r from-transparent via-border-bright to-transparent" />
        <span className="text-orange">{title}</span>
        <span className="block h-px flex-1 bg-gradient-to-r from-border-bright via-border-bright to-transparent" />
      </h3>
      {children}
    </section>
  );
}
