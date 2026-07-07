import type { SimulationSummary } from '@/types/api';
import { Chip } from '../components';
import { titleCase } from '../utils/formatters';

export function RegionalContextMini({
  regional,
  loading,
}: {
  regional: SimulationSummary['regional_context'];
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="rounded-chunk-lg border border-border/50 bg-bg3/25 p-3">
        <div className="h-3 w-40 rounded bg-bg4/60" />
        <div className="mt-3 h-3 w-2/3 rounded bg-bg4/40" />
      </div>
    );
  }
  if (!regional || regional.regional_role === 'unknown') {
    return (
      <div className="rounded-chunk-lg border border-border/60 bg-bg3/25 p-3 font-mono text-[11px] text-silver-dk">
        <div className="text-[10px] uppercase tracking-[0.18em] text-silver-dk">Regional context</div>
        <div className="mt-1">Regional positioning is not computed yet; local simulation remains deterministic.</div>
      </div>
    );
  }
  const bestFit = Object.entries(regional.archetype_regional_fit)
    .sort((a, b) => b[1] - a[1])[0];
  return (
    <div className="rounded-chunk-lg border border-orange/25 bg-orange/5 p-3 font-mono text-[11px] text-silver">
      <div className="text-[10px] uppercase tracking-[0.18em] text-orange">Regional context</div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <Chip tone="warn">{titleCase(regional.regional_role)}</Chip>
        {regional.nearest_colonised_system?.distance_ly != null && (
          <Chip>{regional.nearest_colonised_system.distance_ly.toFixed(0)} LY nearest colony</Chip>
        )}
        {bestFit && <Chip tone="good">{titleCase(bestFit[0])}: {Math.round(bestFit[1])}</Chip>}
      </div>
      {regional.rationale?.summary && (
        <p className="mt-2 leading-snug text-silver-dk">{regional.rationale.summary}</p>
      )}
    </div>
  );
}
