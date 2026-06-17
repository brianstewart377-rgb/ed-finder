import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { WarehouseEvidenceCard } from '@/features/colony-planner/WarehouseEvidenceCard';
import { toWarehouseEvidenceFromProvenance } from '@/features/colony-planner/warehouseEvidenceBridge';
import { ApiError, getProvenanceCockpit, listObservedFacts } from '@/lib/api';
import type {
  ProvenanceCockpitResponse,
  ProvenanceCockpitState,
} from '@/types/api';


export function ProvenanceCockpitPanel({
  systemId64,
  targetArchetype,
}: {
  systemId64: number;
  targetArchetype?: string;
}) {
  const query = useQuery({
    queryKey: ['provenance-cockpit', systemId64],
    queryFn: () => getProvenanceCockpit(systemId64),
    retry: 1,
    staleTime: 60_000,
  });
  const observedFactsQuery = useQuery({
    queryKey: ['provenance-cockpit-observed-facts', systemId64, targetArchetype ?? null],
    queryFn: () => listObservedFacts({ system_id64: systemId64, target_archetype: targetArchetype, limit: 1 }),
    retry: 1,
    staleTime: 60_000,
  });

  const effectiveResponse = useMemo(
    () => mergeLiveObservedFactCount(query.data, observedFactsQuery.data?.summary?.total_count),
    [query.data, observedFactsQuery.data?.summary?.total_count],
  );

  const warehouseEvidence = useMemo(
    () => toWarehouseEvidenceFromProvenance(effectiveResponse),
    [effectiveResponse],
  );

  return (
    <section
      aria-label="Provenance cockpit"
      data-testid="provenance-cockpit-panel"
      className="rounded-chunk-lg border border-cyan/30 bg-bg1/50 p-3 font-mono text-[11px] text-silver-dk space-y-3"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-display tracking-[0.14em] text-cyan text-xs">Provenance cockpit</h3>
        <StateBadge state={effectiveResponse?.provenance_summary.state ?? 'unknown'} />
        <span className="px-1.5 py-0.5 rounded border border-border bg-bg4 text-[9px] uppercase tracking-wider text-text-dim">
          Read-only
        </span>
      </div>

      <p className="leading-snug text-text-dim">
        Source-run, warehouse, and planner evidence are surfaced here for review only. This panel does not run imports,
        staging, canonical apply, rebaseline, scheduler work, or DB writes.
      </p>

      {query.isLoading && (
        <div className="rounded border border-border bg-bg2/70 px-3 py-2 text-text-dim">
          Loading provenance cockpit…
        </div>
      )}

      {query.isError && (
        <div role="alert" className="rounded border border-red-400/50 bg-red-950/30 px-3 py-2 text-red-100">
          Provenance cockpit failed to load.
          <span className="block text-[10px] text-red-200/80">
            {query.error instanceof ApiError ? query.error.message : 'Unknown error'}
          </span>
        </div>
      )}

      {effectiveResponse && (
        <>
          <SummaryGrid response={effectiveResponse} liveObservedFactsLoaded={observedFactsQuery.isSuccess} />
          <WarehouseEvidenceCard evidence={warehouseEvidence} />
          <GuardrailsSummaryCard response={effectiveResponse} />
        </>
      )}
    </section>
  );
}

function SummaryGrid({
  response,
  liveObservedFactsLoaded,
}: {
  response: ProvenanceCockpitResponse;
  liveObservedFactsLoaded: boolean;
}) {
  const { system, provenance_summary: summary, evidence_panels: panels, warnings } = response;

  return (
    <div className="grid gap-3 lg:grid-cols-3">
      <article className="rounded border border-border bg-bg2/70 p-3 space-y-2">
        <header className="flex items-center justify-between gap-2">
          <span className="font-display tracking-[0.14em] text-[10px] text-cyan">Source run</span>
          <StateBadge state={panels.source_run.state} />
        </header>
        <dl className="space-y-1 leading-snug">
          <Metric label="System" value={system.name ?? `ID64 ${system.id64}`} />
          <Metric label="Latest run key" value={summary.latest_source_run_key ?? 'Unknown'} />
          <Metric label="Source" value={panels.source_run.source_name ?? 'Unknown'} />
          <Metric label="Artifact" value={panels.source_run.artifact_name ?? 'Unknown'} />
          <Metric label="Rows read" value={formatCount(panels.source_run.rows_read)} />
          <Metric label="Rows staged" value={formatCount(panels.source_run.rows_staged)} />
        </dl>
      </article>

      <article className="rounded border border-border bg-bg2/70 p-3 space-y-2">
        <header className="flex items-center justify-between gap-2">
          <span className="font-display tracking-[0.14em] text-[10px] text-cyan">Planner evidence</span>
          <StateBadge state={summary.planner_evidence_state} />
        </header>
        <dl className="space-y-1 leading-snug">
          <Metric label="Primary archetype" value={system.primary_archetype ?? 'Unknown'} />
          <Metric label="Observed facts" value={String(panels.planner.observed_facts_count)} />
          <Metric label="Observed fact source" value={liveObservedFactsLoaded ? 'Live observations API' : 'Provenance snapshot'} />
          <Metric label="Projected builds" value={String(panels.planner.projected_build_count)} />
          <Metric
            label="Manual review"
            value={panels.planner.manual_review_required ? 'Required' : 'Not required'}
          />
        </dl>
      </article>

      <article className="rounded border border-border bg-bg2/70 p-3 space-y-2">
        <header className="flex items-center justify-between gap-2">
          <span className="font-display tracking-[0.14em] text-[10px] text-cyan">Warnings</span>
          <StateBadge state={summary.warehouse_state} />
        </header>
        {warnings.length > 0 ? (
          <ul className="space-y-1 leading-snug text-orange-lt" aria-label="Provenance warnings">
            {warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        ) : (
          <p className="leading-snug text-text-dim">
            No active provenance warnings. Evidence remains review-only and does not authorize production work.
          </p>
        )}
      </article>
    </div>
  );
}

function GuardrailsSummaryCard({ response }: { response: ProvenanceCockpitResponse }) {
  const guardrails = [
    ['Stage 19 paused', response.guardrails.stage19_paused],
    ['Production activation complete', response.guardrails.stage19_production_activation_complete],
    ['Next write lane authorized', response.guardrails.next_stage19_write_lane_authorized],
    ['Canonical apply complete', response.guardrails.canonical_apply_complete],
    ['Rebaseline complete', response.guardrails.rebaseline_complete],
    ['Scheduler enabled', response.guardrails.scheduler_enabled],
    ['DB writes authorized', response.guardrails.db_writes_authorized],
    ['Stage 19 operator commands authorized', response.guardrails.stage19_operator_commands_authorized],
  ] as const;

  return (
    <article className="rounded border border-border bg-bg2/70 p-3 space-y-2">
      <header className="flex items-center gap-2">
        <span className="font-display tracking-[0.14em] text-[10px] text-cyan">Guardrails</span>
        <span className="text-text-dim">Deferred production lanes remain explicit.</span>
      </header>
      <ul className="grid gap-1 md:grid-cols-2" aria-label="Provenance guardrails">
        {guardrails.map(([label, enabled]) => (
          <li
            key={label}
            className="flex items-center justify-between gap-2 rounded border border-border/80 bg-bg1/70 px-2 py-1"
          >
            <span>{label}</span>
            <span className={enabled ? 'text-cyan' : 'text-orange-lt'}>
              {enabled ? 'True' : 'False'}
            </span>
          </li>
        ))}
      </ul>
    </article>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-text-dim">{label}</dt>
      <dd className="text-right text-text">{value}</dd>
    </div>
  );
}

function StateBadge({ state }: { state: ProvenanceCockpitState }) {
  const tone =
    state === 'available'
      ? 'border-cyan/40 bg-cyan/10 text-cyan'
      : state === 'stale'
        ? 'border-orange-lt/40 bg-orange-lt/10 text-orange-lt'
        : 'border-border bg-bg4 text-text-dim';

  return (
    <span className={`px-1.5 py-0.5 rounded border text-[9px] uppercase tracking-wider ${tone}`}>
      {state}
    </span>
  );
}

function formatCount(value: number | null | undefined): string {
  return typeof value === 'number' ? String(value) : 'Unknown';
}

function mergeLiveObservedFactCount(
  response: ProvenanceCockpitResponse | undefined,
  liveObservedFactCount: number | undefined,
): ProvenanceCockpitResponse | undefined {
  if (!response || typeof liveObservedFactCount !== 'number') return response;

  const plannerState =
    response.provenance_summary.planner_evidence_state === 'unknown' && liveObservedFactCount > 0
      ? 'available'
      : response.provenance_summary.planner_evidence_state;

  return {
    ...response,
    provenance_summary: {
      ...response.provenance_summary,
      planner_evidence_state: plannerState,
    },
    evidence_panels: {
      ...response.evidence_panels,
      planner: {
        ...response.evidence_panels.planner,
        state: plannerState,
        observed_facts_count: liveObservedFactCount,
      },
    },
  };
}
