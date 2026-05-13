import { Play } from 'lucide-react';
import type { RecommendedBuildPlan } from '@/types/api';
import { BuildOrderTimeline } from './BuildOrderTimeline';

export function BuildPlanCard({
  plan,
  onPreview,
}: {
  plan: RecommendedBuildPlan;
  onPreview: (plan: RecommendedBuildPlan) => void;
}) {
  const economyRows = Object.entries(plan.economy_result).slice(0, 3);
  const keyReason = plan.decision_explanation?.why_this_plan_won?.[0] ?? plan.strengths[0] ?? plan.summary;
  const keyRisk = plan.warnings[0] ?? plan.tradeoffs[0] ?? plan.economy_caveats[0];
  const rankBreakdownEntries = Object.entries(plan.rank_breakdown ?? {}).filter(
    ([key, value]) => !(key === 'service_score' && value === 0),
  );
  const serviceScoringReserved = plan.rank_breakdown?.service_score === 0;
  const regionalAdjustment = plan.rank_breakdown?.regional_fit_score ?? 0;
  return (
    <article
      className={[
        'rounded-chunk-lg border bg-bg2/80 p-3 shadow-metal',
        plan.is_default ? 'border-orange/55' : 'border-border/70',
      ].join(' ')}
    >
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="font-mono text-sm font-bold text-orange">{plan.label}</h4>
            {plan.is_default && <Badge label="Default" tone="orange" />}
            <Badge label={titleCase(plan.complexity)} tone={complexityTone(plan.complexity)} />
            <Badge label={confidenceLabel(plan.confidence)} tone={confidenceTone(plan.confidence)} />
          </div>
          <p className="mt-2 text-xs leading-snug text-silver-dk">{plan.summary}</p>
          <p className="mt-2 text-[11px] leading-snug text-silver">
            <span className="font-mono text-green">Why this plan:</span> {keyReason}
          </p>
          {keyRisk && (
            <p className="mt-1 text-[11px] leading-snug text-gold">
              <span className="font-mono">Key risk:</span> {keyRisk}
            </p>
          )}
        </div>
        <div className="text-right font-mono">
          <div className="text-[9px] uppercase tracking-[0.14em] text-silver-dk">Score</div>
          <div className="text-lg font-bold text-orange tabular-nums">{Math.round(plan.final_score)}</div>
        </div>
      </div>

      {economyRows.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {economyRows.map(([economy, value]) => (
            <div key={economy} className="grid grid-cols-[88px_minmax(0,1fr)_42px] items-center gap-2">
              <span className="truncate font-mono text-[10px] text-silver">{economy}</span>
              <div className="h-2 overflow-hidden rounded-full border border-border bg-bg4">
                <div className="h-full rounded-full bg-orange-grad" style={{ width: `${Math.max(3, Math.min(100, value))}%` }} />
              </div>
              <span className="text-right font-mono text-[10px] text-orange tabular-nums">{value.toFixed(0)}%</span>
            </div>
          ))}
        </div>
      )}

      <div className="mt-3 rounded border border-cyan/25 bg-cyan/5 px-2 py-2">
        <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-cyan">Selected body</div>
        <div className="mt-1 font-mono text-[11px] text-silver">
          {plan.selected_body_name || (plan.selected_body_id ? `Body ${plan.selected_body_id}` : 'Estimated body candidate')}
        </div>
        {plan.body_selection_reason && (
          <p className="mt-1 text-[11px] leading-snug text-silver-dk">{plan.body_selection_reason}</p>
        )}
      </div>

      {(plan.regional_role || plan.nearest_colony_distance != null || plan.archetype_regional_fit != null) && (
        <div className="mt-3 rounded border border-orange/25 bg-orange/5 px-2 py-2">
          <div className="flex flex-wrap items-center gap-1.5">
            {plan.regional_role && <Badge label={`Region: ${titleCase(plan.regional_role)}`} tone="orange" />}
            {plan.nearest_colony_distance != null && (
              <Badge label={`${plan.nearest_colony_distance.toFixed(0)} LY nearest`} tone="gold" />
            )}
            {plan.archetype_regional_fit != null && (
              <Badge label={`${Math.round(plan.archetype_regional_fit)} regional fit`} tone={plan.archetype_regional_fit >= 70 ? 'green' : 'gold'} />
            )}
          </div>
          {regionalSummary(plan.regional_rationale) && (
            <p className="mt-2 text-[11px] leading-snug text-silver-dk">{regionalSummary(plan.regional_rationale)}</p>
          )}
        </div>
      )}

      <div className="mt-3 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(150px,0.85fr)]">
        <BuildOrderTimeline steps={plan.build_order.slice(0, 5)} />
        <div className="space-y-2">
          <MiniList title="Mechanics basis" items={plan.mechanics_basis} tone="info" />
          <MiniList title="Caveats" items={plan.economy_caveats} tone="warn" />
          <MiniList title="Assumptions" items={plan.assumptions} tone="warn" />
          <MiniList title="Strengths" items={plan.strengths} tone="good" />
          <MiniList title="Tradeoffs" items={plan.tradeoffs.length ? plan.tradeoffs : plan.warnings} tone="warn" />
        </div>
      </div>

      <details className="mt-3 rounded border border-border/60 bg-bg3/35 px-2 py-2">
        <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-[0.14em] text-silver">
          Why this plan won
        </summary>
        <div className="mt-2 grid gap-2 md:grid-cols-2">
          <MiniList title="Decision" items={plan.decision_explanation?.why_this_plan_won ?? []} tone="good" />
          <MiniList title="Sensitive assumptions" items={plan.decision_explanation?.sensitive_assumptions ?? []} tone="warn" />
          <MiniList title="Why not simpler" items={plan.decision_explanation?.why_not_simpler ?? []} tone="info" />
          <MiniList title="Why not advanced" items={plan.decision_explanation?.why_not_more_advanced ?? []} tone="warn" />
        </div>
        {plan.decision_explanation?.confidence_summary && (
          <p className="mt-2 font-mono text-[10px] leading-snug text-silver-dk">{plan.decision_explanation.confidence_summary}</p>
        )}
      </details>

      {rankBreakdownEntries.length > 0 && (
        <details className="mt-2 rounded border border-border/60 bg-bg3/35 px-2 py-2">
          <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-[0.14em] text-silver">
            Score breakdown
          </summary>
          <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
            {rankBreakdownEntries.map(([key, value]) => (
              <div key={key} className="flex justify-between gap-2 rounded border border-border/50 bg-bg2/60 px-2 py-1 font-mono text-[10px]">
                <span className="text-silver-dk">{titleCase(key)}</span>
                <span className={value < 0 || key.includes('penalty') ? 'text-gold' : 'text-orange'}>{value.toFixed(1)}</span>
              </div>
            ))}
          </div>
          {regionalAdjustment > 0 && (
            <p className="mt-2 font-mono text-[10px] leading-snug text-silver-dk">
              Regional fit is a light adjustment and does not override local build quality.
            </p>
          )}
          {serviceScoringReserved && (
            <p className="mt-1 font-mono text-[10px] leading-snug text-silver-dk">
              Service scoring is not yet included in recommendation ranking.
            </p>
          )}
        </details>
      )}

      <button
        type="button"
        onClick={() => onPreview(plan)}
        className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-chunk-sm border border-orange/50 bg-orange/15 px-3 py-2 font-mono text-xs font-bold text-orange hover:bg-orange/25"
      >
        <Play size={14} />
        Preview & edit this build
      </button>
    </article>
  );
}

function MiniList({ title, items, tone }: { title: string; items: string[]; tone: 'good' | 'warn' | 'info' }) {
  if (items.length === 0) return null;
  const colour = tone === 'good' ? 'text-green' : tone === 'info' ? 'text-cyan' : 'text-gold';
  return (
    <div className="rounded border border-border/60 bg-bg3/45 px-2 py-1.5">
      <div className={`font-mono text-[9px] uppercase tracking-[0.14em] ${colour}`}>{title}</div>
      <ul className="mt-1 space-y-1 font-mono text-[10px] text-silver-dk">
        {items.slice(0, 2).map((item) => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}

function Badge({ label, tone }: { label: string; tone: 'green' | 'gold' | 'red' | 'orange' }) {
  const colour = {
    green: '#4ade80',
    gold: '#fbbf24',
    red: '#ef5350',
    orange: '#f97316',
  }[tone];
  return (
    <span className="rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.1em]" style={{ borderColor: `${colour}60`, color: colour, backgroundColor: `${colour}14` }}>
      {label}
    </span>
  );
}

function titleCase(value: string): string {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
}

function confidenceLabel(value: number): string {
  if (value >= 0.75) return 'High';
  if (value >= 0.55) return 'Medium';
  return 'Low';
}

function confidenceTone(value: number): 'green' | 'gold' | 'red' {
  if (value >= 0.75) return 'green';
  if (value >= 0.55) return 'gold';
  return 'red';
}

function complexityTone(value: RecommendedBuildPlan['complexity']): 'green' | 'gold' | 'orange' | 'red' {
  if (value === 'simple') return 'green';
  if (value === 'moderate') return 'gold';
  if (value === 'advanced') return 'orange';
  return 'red';
}

function regionalSummary(value: Record<string, unknown> | undefined): string | null {
  const summary = value?.summary;
  return typeof summary === 'string' && summary.length > 0 ? summary : null;
}
