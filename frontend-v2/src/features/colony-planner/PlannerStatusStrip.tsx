import type { TopologySelection } from './ColonyTopologyRail';
import { PlanningEconomyStrip } from './PlanningEconomyStrip';
import type { PlanningEconomyLedger } from './planningEconomy';

export function PlannerStatusStrip({
  selection,
  planningFocusLabel,
  placementCount,
  projectedCount,
  existingCount = 0,
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
  emptySlotCount?: number;
  unresolvedExistingCount?: number;
  unsavedChanges: boolean;
  economyLedger: PlanningEconomyLedger;
  prerequisiteIssueCount?: number;
}) {
  const title = selection.type === 'body' || selection.type === 'placement' || selection.type === 'projected-placement'
    ? 'Body Planner'
    : 'Whole-System Planner';
  return (
    <div className="mb-3 rounded border border-border/60 bg-bg3/25 px-3 py-2" data-testid="planner-status-strip">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-mono text-[12px] uppercase tracking-[0.18em] text-orange">
            {title}
          </h2>
          <p className="mt-0.5 max-w-2xl text-[11px] font-mono leading-snug text-silver-dk">
            {planningFocusLabel
              ? `Planning focus: ${planningFocusLabel}`
              : 'Whole-system slot map is active. Select a body to edit local slots.'}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5" aria-label="Planner status">
          <StatusChip label={`${existingCount} existing`} tone={existingCount > 0 ? 'green' : 'silver'} />
          <StatusChip label={`${placementCount} planned`} tone={placementCount > 0 ? 'orange' : 'silver'} />
          <StatusChip label={`${projectedCount} projected`} tone={projectedCount > 0 ? 'cyan' : 'silver'} />
          <StatusChip label={`${emptySlotCount} empty slots`} tone="silver" />
          {unresolvedExistingCount > 0 && <StatusChip label={`${unresolvedExistingCount} unresolved existing`} tone="gold" />}
          {prerequisiteIssueCount > 0 && <StatusChip label={`${prerequisiteIssueCount} prerequisite warning${prerequisiteIssueCount === 1 ? '' : 's'}`} tone="gold" />}
          <StatusChip label={unsavedChanges ? 'Unsaved changes' : 'Saved locally'} tone={unsavedChanges ? 'gold' : 'silver'} />
        </div>
      </div>
      <div className="mt-2">
        <PlanningEconomyStrip ledger={economyLedger} testId="workspace-economy-ledger" />
      </div>
    </div>
  );
}

function StatusChip({ label, tone = 'silver' }: { label: string; tone?: 'silver' | 'orange' | 'gold' | 'cyan' | 'green' }) {
  return (
    <span
      className={[
        'rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-[0.12em]',
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
      {label}
    </span>
  );
}
