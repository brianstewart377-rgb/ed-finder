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
