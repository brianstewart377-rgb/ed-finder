import type { SimulateBuildResponse } from '@/types/api';
import { Chip } from '../components/ui';
import { titleCase } from '../utils/formatters';

export function LinkSummary({ result }: { result: SimulateBuildResponse }) {
  const strong = result.links.strong_links.length;
  const weak = result.links.weak_links.length;
  return (
    <div className="rounded-chunk-lg border border-border/70 bg-bg2/70 p-3 font-mono text-[11px] text-silver">
      <div className="mb-1 text-[10px] uppercase tracking-[0.18em] text-silver-dk">Link summary</div>
      <div className="flex flex-wrap gap-2">
        <Chip tone={strong > 0 ? 'good' : 'default'}>{strong} strong same-body links</Chip>
        <Chip>{weak} weak cross-body links</Chip>
        <Chip tone={result.contamination_risk === 'low' ? 'good' : 'warn'}>
          {titleCase(result.contamination_risk)} contamination
        </Chip>
        <Chip>{titleCase(result.top_two_alignment)} alignment</Chip>
      </div>
    </div>
  );
}
