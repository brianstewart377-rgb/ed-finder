import type { SimulateBuildResponse } from '@/types/api';
import { Chip } from '../components';
import { asNumber, asString, asStringArray, titleCase } from '../utils/formatters';

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
