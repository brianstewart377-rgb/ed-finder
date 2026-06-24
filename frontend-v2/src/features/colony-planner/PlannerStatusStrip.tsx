import type { TopologySelection } from './ColonyTopologyRail';
import { PlanningEconomyStrip } from './PlanningEconomyStrip';
import type { PlanningEconomyLedger } from './planningEconomy';

export function PlannerStatusStrip({
  selection,
  planningFocusLabel,
  placementCount,
  projectedCount,
  existingCount = 0,
  inferredExistingCount = 0,
  emptySlotCount = 0,
  unresolvedExistingCount = 0,
  unsavedChanges,
  economyLedger,
  prerequisiteIssueCount = 0,
}: {
  selection: TopologySelection;
  planningFocusLabel: string | null;
  placementCount: number;
  projectedCount: number;
  existingCount?: number;
  inferredExistingCount?: number;
  emptySlotCount?: number;
  unresolvedExistingCount?: number;
  unsavedChanges: boolean;
  economyLedger: PlanningEconomyLedger;
  prerequisiteIssueCount?: number;
}) {
  const title = selection.type === 'body' || selection.type === 'placement' || selection.type === 'projected-placement'
    ? 'Body Planner'
    : 'Whole-System Planner';
  const confirmedExistingCount = Math.max(0, existingCount - inferredExistingCount);
  return (
    <div
      className="mb-3 rounded-chunk-lg border border-border/70 bg-bg2/95 px-3 py-3 shadow-[0_14px_36px_-28px_rgba(0,0,0,0.85)]"
      data-testid="planner-status-strip"
      data-readability="solid-graphite"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-mono text-sm uppercase tracking-[0.16em] text-orange">
            {title}
          </h2>
          <p className="mt-1 max-w-2xl text-xs font-mono leading-snug text-silver">
            {planningFocusLabel
              ? `Planning focus: ${planningFocusLabel}`
              : 'Whole-system slot map is active. Select a body to edit local slots.'}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5" aria-label="Planner status">
          <StatusChip label="Existing" value={existingCount} tone={existingCount > 0 ? 'green' : 'silver'} />
          <StatusChip label="Planned" value={placementCount} tone={placementCount > 0 ? 'orange' : 'silver'} />
          <StatusChip label="Preview" value={projectedCount} tone={projectedCount > 0 ? 'cyan' : 'silver'} />
          <StatusChip label="Open slots" value={emptySlotCount} tone="silver" />
          <StatusChip label={unsavedChanges ? 'Unsaved changes' : 'Saved locally'} tone={unsavedChanges ? 'gold' : 'silver'} />
        </div>
      </div>
      {(unresolvedExistingCount > 0 || prerequisiteIssueCount > 0) ? (
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs font-mono">
          {unresolvedExistingCount > 0 ? (
            <details
              data-testid="existing-location-review"
              className="rounded border border-gold/35 bg-gold/10 px-2 py-1 text-gold"
            >
              <summary className="cursor-pointer font-bold">
                Existing locations need review ({unresolvedExistingCount})
              </summary>
              <p className="mt-1 leading-relaxed text-silver">
                Confirmed {confirmedExistingCount} · Inferred {inferredExistingCount} · Need review {unresolvedExistingCount}. Review these existing locations before treating body placement as final.
              </p>
            </details>
          ) : null}
          {prerequisiteIssueCount > 0 ? (
            <span data-testid="planner-prerequisite-summary" className="rounded border border-gold/25 bg-bg3/60 px-2 py-1 text-gold">
              {prerequisiteIssueCount} prerequisite warning{prerequisiteIssueCount === 1 ? '' : 's'}
            </span>
          ) : null}
        </div>
      ) : null}
      <div className="mt-2">
        <PlanningEconomyStrip ledger={economyLedger} testId="workspace-economy-ledger" />
      </div>
    </div>
  );
}

function StatusChip({
  label,
  value,
  tone = 'silver',
}: {
  label: string;
  value?: number;
  tone?: 'silver' | 'orange' | 'gold' | 'cyan' | 'green';
}) {
  return (
    <span
      className={[
        'rounded border px-2 py-1 text-[11px] uppercase tracking-[0.12em]',
        tone === 'orange'
          ? 'border-orange/35 bg-orange/10 text-orange'
          : tone === 'gold'
            ? 'border-gold/35 bg-gold/10 text-gold'
            : tone === 'cyan'
              ? 'border-cyan/35 bg-cyan/10 text-cyan'
              : tone === 'green'
                ? 'border-green/35 bg-green/10 text-green'
              : 'border-border/60 bg-bg3/45 text-silver-dk',
      ].join(' ')}
    >
      {label}{value == null ? null : <span className="ml-1.5 text-sm font-bold tabular-nums">{value}</span>}
    </span>
  );
}
