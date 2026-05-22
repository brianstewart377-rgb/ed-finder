import type { TopologySelection } from './ColonyTopologyRail';
import { PlanningEconomyStrip } from './PlanningEconomyStrip';
import type { PlanningEconomyLedger } from './planningEconomy';

export function PlannerStatusStrip({
  selection,
  planningFocusLabel,
  placementCount,
  projectedCount,
  unsavedChanges,
  economyLedger,
}: {
  selection: TopologySelection;
  planningFocusLabel: string | null;
  placementCount: number;
  projectedCount: number;
  unsavedChanges: boolean;
  economyLedger: PlanningEconomyLedger;
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
          <StatusChip label={`${placementCount} planned`} tone={placementCount > 0 ? 'orange' : 'silver'} />
          {projectedCount > 0 && <StatusChip label={`${projectedCount} projected`} tone="cyan" />}
          <StatusChip label={unsavedChanges ? 'Unsaved changes' : 'Saved locally'} tone={unsavedChanges ? 'gold' : 'silver'} />
        </div>
      </div>
      <div className="mt-2">
        <PlanningEconomyStrip ledger={economyLedger} testId="workspace-economy-ledger" />
      </div>
    </div>
  );
}

function StatusChip({ label, tone = 'silver' }: { label: string; tone?: 'silver' | 'orange' | 'gold' | 'cyan' }) {
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
              : 'border-border/60 bg-bg3/45 text-silver-dk',
      ].join(' ')}
    >
      {label}
    </span>
  );
}
