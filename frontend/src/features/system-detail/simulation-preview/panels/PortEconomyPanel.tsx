import type { SimulateBuildResponse } from '@/types/api';
import { Chip } from '../components';
import { titleCase } from '../utils/formatters';

export function PortEconomyPanel({
  states,
  ledger,
}: {
  states: SimulateBuildResponse['port_economy_states'];
  ledger: SimulateBuildResponse['influence_ledger'];
}) {
  if ((!states || states.length === 0) && (!ledger || ledger.length === 0)) return null;
  return (
    <div className="rounded-chunk-lg border border-cyan/25 bg-cyan/5 p-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-cyan">
        Port Economy Breakdown
      </div>
      {states && states.length > 0 ? (
        <div className="space-y-3">
          {states.map((state) => {
            const topInfluences = [...(state.influences ?? [])]
              .sort((a, b) => b.value - a.value)
              .slice(0, 4);
            return (
              <div key={`${state.local_body_id ?? 'system'}-${state.port_id}`} className="rounded border border-border/60 bg-bg3/45 px-2 py-2">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="font-mono text-[11px] text-silver">{state.port_name}</div>
                    <div className="mt-0.5 font-mono text-[10px] text-silver-dk">
                      {state.body_name || (state.local_body_id ? `Body ${state.local_body_id}` : 'System-wide')} · {titleCase(state.location_type)} · {titleCase(state.effective_role)}
                    </div>
                  </div>
                  <div className="flex flex-wrap justify-end gap-1.5 font-mono text-[10px]">
                    {state.top_two.map((economy) => <Chip key={economy} tone="good">{economy}</Chip>)}
                    {state.tertiary_economies.map((economy) => <Chip key={economy} tone="warn">{economy} tertiary</Chip>)}
                    <Chip>{Math.round(state.purity_score)} purity</Chip>
                    <Chip tone={state.contamination_risk === 'low' ? 'good' : 'warn'}>{titleCase(state.contamination_risk)} risk</Chip>
                  </div>
                </div>
                {topInfluences.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {topInfluences.map((influence) => (
                      <div key={`${influence.source_id}-${influence.influence_type}-${influence.economy}-${influence.value}`} className="grid grid-cols-[minmax(0,1fr)_70px_42px] gap-2 font-mono text-[10px] text-silver-dk">
                        <span className="truncate">{influence.source_name} · {titleCase(influence.influence_type)}</span>
                        <span className="truncate text-silver">{influence.economy}</span>
                        <span className="text-right text-cyan tabular-nums">{influence.value.toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                )}
                {[...(state.warnings ?? []), ...(state.recommendations ?? [])].slice(0, 2).map((item) => (
                  <div key={item} className="mt-2 rounded border border-gold/30 bg-gold/5 px-2 py-1 font-mono text-[10px] leading-snug text-gold">
                    {item}
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="rounded border border-border/60 bg-bg3/45 px-2 py-2 font-mono text-[10px] text-silver-dk">
          No Main Ports are present yet, so there are no per-port economy states.
        </div>
      )}
      {ledger && ledger.length > 0 && (
        <details className="mt-3 rounded border border-border/60 bg-bg2/55 px-2 py-2">
          <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-[0.14em] text-silver">
            Influence Ledger
          </summary>
          <div className="mt-2 space-y-1.5">
            {ledger.slice(0, 12).map((influence) => (
              <div key={`${influence.source_id}-${influence.target_port_id}-${influence.influence_type}-${influence.economy}-${influence.value}`} className="rounded border border-border/50 bg-bg3/45 px-2 py-1.5">
                <div className="grid gap-1 font-mono text-[10px] text-silver-dk sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_92px_70px_42px]">
                  <span className="truncate"><span className="text-silver">Source:</span> {influence.source_name}</span>
                  <span className="truncate"><span className="text-silver">Target:</span> {influence.target_port_name}</span>
                  <span>{titleCase(influence.influence_type)}</span>
                  <span>{influence.economy}</span>
                  <span className="text-right text-cyan tabular-nums">{influence.value.toFixed(2)}</span>
                </div>
                <div className="mt-1 font-mono text-[10px] leading-snug text-silver-dk">
                  <span className="text-silver">{titleCase(influence.confidence)}:</span> {influence.reason}
                </div>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
