import { Network } from 'lucide-react';
import { Chip } from './components';
import type { LayoutTopologyReadout as LayoutTopologyReadoutModel } from './layoutTopologyUtils';

export function LayoutTopologyReadout({
  readout,
  compact = false,
}: {
  readout: LayoutTopologyReadoutModel;
  compact?: boolean;
}) {
  const visibleChips = compact ? readout.chips.slice(0, 6) : readout.chips;

  return (
    <section
      aria-label={`Topology readout for ${readout.bodyLabel}`}
      data-testid="layout-topology-readout"
      className={[
        'rounded border border-cyan/25 bg-cyan/5 px-2 py-2',
        compact ? 'mt-2' : '',
      ].join(' ')}
    >
      <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em] text-cyan">
        <Network size={12} />
        Topology readout
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5 font-mono text-[10px]">
        {visibleChips.map((chip) => (
          <Chip key={chip.key} tone={chip.tone === 'good' ? 'good' : chip.tone === 'warn' ? 'warn' : 'default'}>
            {chip.label}
          </Chip>
        ))}
      </div>
      {!compact && (
        <p className="mt-2 font-mono text-[10px] leading-snug text-silver-dk">
          Slot counts stay unknown until Architect Mode observations are recorded; this readout only groups the current plan.
        </p>
      )}
    </section>
  );
}
