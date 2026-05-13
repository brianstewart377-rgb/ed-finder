import type { SimulateBuildResponse } from '@/types/api';
import { Chip, Message } from '../components/ui';
import { asNumber, asString, asStringArray, titleCase } from '../utils/formatters';
import { purityLabel, purityTone } from '../utils/toneHelpers';

export function EconomyStackPanel({ stack }: { stack: SimulateBuildResponse['economy_stack'] }) {
  const topTwo = asStringArray(stack.top_two);
  const tertiary = asStringArray(stack.tertiary);
  const strengths = stack.strengths && typeof stack.strengths === 'object'
    ? Object.entries(stack.strengths as Record<string, unknown>)
      .filter(([, value]) => typeof value === 'number')
      .sort((a, b) => Number(b[1]) - Number(a[1]))
      .slice(0, 5)
    : [];
  const warnings = asStringArray(stack.warnings);
  if (topTwo.length === 0 && strengths.length === 0) return null;
  return (
    <div className="rounded-chunk-lg border border-border/70 bg-bg2/70 p-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
        Economy stack identity
      </div>
      <div className="flex flex-wrap gap-1.5 font-mono text-[10px]">
        {topTwo.map((economy) => <Chip key={economy} tone="good">{economy} top-two</Chip>)}
        {tertiary.map((economy) => <Chip key={economy} tone="warn">{economy} tertiary pressure</Chip>)}
        {asNumber(stack.purity_score) != null && <Chip>{Math.round(asNumber(stack.purity_score) ?? 0)} purity</Chip>}
        {asString(stack.contamination_risk) && <Chip tone={asString(stack.contamination_risk) === 'low' ? 'good' : 'warn'}>{titleCase(asString(stack.contamination_risk) ?? '')} contamination</Chip>}
      </div>
      {strengths.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {strengths.map(([economy, value]) => (
            <div key={economy} className="grid grid-cols-[96px_minmax(0,1fr)_42px] items-center gap-2">
              <span className="truncate font-mono text-[10px] text-silver-dk">{economy}</span>
              <div className="h-2 overflow-hidden rounded-full border border-border bg-bg4">
                <div className="h-full rounded-full bg-orange-grad" style={{ width: `${Math.max(3, Math.min(100, Number(value)))}%` }} />
              </div>
              <span className="text-right font-mono text-[10px] text-orange tabular-nums">{Number(value).toFixed(0)}</span>
            </div>
          ))}
        </div>
      )}
      {warnings.slice(0, 2).map((warning) => (
        <div key={warning} className="mt-2 rounded border border-gold/30 bg-gold/5 px-2 py-1 font-mono text-[10px] leading-snug text-gold">
          {warning}
        </div>
      ))}
    </div>
  );
}

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

export function InheritedEconomyPanel({ profiles }: { profiles: SimulateBuildResponse['inherited_economies'] }) {
  if (!profiles || profiles.length === 0) return null;
  return (
    <div className="rounded-chunk-lg border border-cyan/25 bg-cyan/5 p-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-cyan">
        Mixed inheritance
      </div>
      <div className="space-y-3">
        {profiles.map((profile, index) => {
          const rows = Object.entries(profile.weights).sort((a, b) => b[1] - a[1]);
          return (
            <div key={`${profile.source_body_id ?? 'body'}-${index}`} className="space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2 font-mono text-[11px] text-silver">
                <span>{profile.source_body_name || (profile.source_body_id ? `Body ${profile.source_body_id}` : 'Inherited body')}</span>
                <span className={purityTone(profile.purity)}>{purityLabel(profile.purity)} purity</span>
              </div>
              <div className="space-y-1.5">
                {rows.map(([economy, weight]) => (
                  <div key={economy} className="grid grid-cols-[92px_minmax(0,1fr)_44px] items-center gap-2">
                    <span className="truncate font-mono text-[10px] text-silver-dk">{economy}</span>
                    <div className="h-2 overflow-hidden rounded-full border border-border bg-bg4">
                      <div
                        className="h-full rounded-full bg-cyan"
                        style={{ width: `${Math.max(4, Math.min(100, weight * 100))}%` }}
                      />
                    </div>
                    <span className="text-right font-mono text-[10px] text-cyan tabular-nums">{Math.round(weight * 100)}%</span>
                  </div>
                ))}
              </div>
              {profile.modifier_economies.length > 0 && (
                <div className="flex flex-wrap gap-1.5 font-mono text-[10px]">
                  {profile.modifier_economies.map((economy) => <Chip key={economy} tone="warn">{economy} modifier</Chip>)}
                </div>
              )}
              {profile.caveats.slice(0, 2).map((caveat) => (
                <div key={caveat} className="rounded border border-gold/30 bg-gold/5 px-2 py-1 font-mono text-[10px] leading-snug text-gold">
                  {caveat}
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function EconomyBars({ composition, order }: { composition: Record<string, number>; order: string[] }) {
  const rows = order.map((economy) => [economy, composition[economy] ?? 0] as const);
  if (rows.length === 0) {
    return <Message tone="warn" items={['No economy-producing facilities are present yet.']} />;
  }
  return (
    <div className="rounded-chunk-lg border border-border/70 bg-bg2/70 p-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
        Economy result
      </div>
      <div className="space-y-2">
        {rows.map(([economy, value]) => (
          <div key={economy} className="grid grid-cols-[92px_minmax(0,1fr)_48px] items-center gap-2">
            <span className="truncate font-mono text-[11px] text-silver">{economy}</span>
            <div className="h-2.5 overflow-hidden rounded-full border border-border bg-bg4">
              <div
                className="h-full rounded-full bg-orange-grad shadow-brand-glow"
                style={{ width: `${Math.max(2, Math.min(100, value))}%` }}
              />
            </div>
            <span className="text-right font-mono text-[11px] tabular-nums text-orange">{value.toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
