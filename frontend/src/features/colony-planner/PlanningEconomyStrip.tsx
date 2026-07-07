import type { PlanningEconomyLedger } from './planningEconomy';
import { compactEconomyLabel, PLANNING_ECONOMY_NOTE } from './planningEconomy';
import { economyColor } from './economyVisuals';

export function PlanningEconomyStrip({
  ledger,
  compact = false,
  testId,
}: {
  ledger: PlanningEconomyLedger;
  compact?: boolean;
  testId?: string;
}) {
  const hasEntries = ledger.entries.length > 0;
  const topEntries = compact ? ledger.entries.slice(0, 4) : ledger.entries;

  return (
    <section
      data-testid={testId}
      className={[
        'rounded border border-border/55 bg-bg3/35',
        compact ? 'px-2 py-1' : 'px-3 py-2',
      ].join(' ')}
      title={PLANNING_ECONOMY_NOTE}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-silver-dk">Eco</span>
        {!compact && (
          <span className="font-mono text-[9px] text-silver-dk">{PLANNING_ECONOMY_NOTE}</span>
        )}
      </div>
      {hasEntries ? (
        <>
          <div
            className="mt-1 flex h-2 overflow-hidden rounded bg-bg2/80"
            aria-hidden="true"
            data-testid={testId ? `${testId}-bar` : undefined}
          >
            {topEntries.map((entry) => {
              const plannedWidth = ledger.total > 0 ? (entry.planned / ledger.total) * 100 : 0;
              const projectedWidth = ledger.total > 0 ? (entry.projected / ledger.total) * 100 : 0;
              const color = economyColor(entry.economy);
              return (
                <span key={entry.economy} className="contents">
                  {entry.planned > 0 && (
                    <span
                      data-economy={entry.economy}
                      data-economy-color={color}
                      className="block h-full"
                      style={{ width: `${plannedWidth}%`, backgroundColor: color }}
                    />
                  )}
                  {entry.projected > 0 && (
                    <span
                      data-economy={entry.economy}
                      data-economy-color={color}
                      className="block h-full opacity-35"
                      style={{ width: `${projectedWidth}%`, backgroundColor: color }}
                    />
                  )}
                </span>
              );
            })}
          </div>
          <div className="mt-1 flex flex-wrap gap-1">
            {topEntries.map((entry) => (
              <span
                key={entry.economy}
                className="rounded border border-border/55 bg-bg2/55 px-1 font-mono text-[8px] uppercase tracking-[0.1em] text-silver-dk"
                title={`${entry.economy}: ${entry.planned} planned, ${entry.projected} projected`}
              >
                {compactEconomyLabel(entry.economy)}
                <span className="text-orange"> {entry.planned}</span>
                {entry.projected > 0 && <span className="text-cyan">+{entry.projected}</span>}
              </span>
            ))}
          </div>
        </>
      ) : (
        <div className="mt-1 font-mono text-[9px] text-silver-dk">No economy contribution yet</div>
      )}
      {!compact && ledger.unknownCount > 0 && (
        <div className="mt-1 font-mono text-[9px] text-gold">
          {ledger.unknownCount} structure{ledger.unknownCount === 1 ? '' : 's'} have no economy metadata.
        </div>
      )}
    </section>
  );
}
