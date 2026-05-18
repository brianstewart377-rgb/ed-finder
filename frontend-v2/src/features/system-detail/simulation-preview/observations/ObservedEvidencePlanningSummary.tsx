import type { ObservedFact } from '@/types/api';
import { summarizeObservedEvidenceCategories } from './observedEvidencePlanningUtils';

interface ObservedEvidencePlanningSummaryProps {
  facts: readonly ObservedFact[];
  totalCount: number;
  filtered: boolean;
}

export function ObservedEvidencePlanningSummary({
  facts,
  totalCount,
  filtered,
}: ObservedEvidencePlanningSummaryProps) {
  const categories = summarizeObservedEvidenceCategories(facts);
  const visibleCount = facts.length;

  return (
    <div className="mb-4 rounded border border-border/60 bg-bg2/25 p-3 font-mono text-[10px] text-silver-dk">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="uppercase tracking-[0.16em] text-silver">Observed vs planned framing</div>
        <div className="text-cyan">
          {visibleCount} visible / {totalCount} recorded
        </div>
      </div>

      <div className="grid gap-2 md:grid-cols-3">
        <EvidenceState label="Planned" value="Build Plan and Preview Result are planning context." />
        <EvidenceState label="Observed" value="Manual evidence is what was checked in-game." />
        <EvidenceState label="Unknown" value="Missing evidence stays not checked, not contradicted." />
      </div>

      <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3" aria-label="Observed evidence categories">
        {categories.map((category) => (
          <div
            key={category.id}
            className={[
              'rounded border px-2 py-2',
              category.count > 0
                ? 'border-orange/30 bg-orange/10 text-silver'
                : 'border-border/50 bg-bg3/20 text-silver-dk',
            ].join(' ')}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="uppercase tracking-[0.12em]">{category.label}</span>
              <span className={category.count > 0 ? 'text-orange' : 'text-silver-dk'}>
                {category.count}
              </span>
            </div>
            <p className="mt-1 leading-snug">{category.description}</p>
          </div>
        ))}
      </div>

      {filtered && (
        <p className="mt-2 text-cyan">
          Category counts reflect the visible filtered evidence list.
        </p>
      )}
      <p className="mt-2 leading-snug">
        Viewing evidence does not run Preview, Validation, generation, or planner mutation. Use Validation when you want a manual comparison against the current Preview Result.
      </p>
    </div>
  );
}

function EvidenceState({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-border/50 bg-bg3/25 px-2 py-2">
      <div className="uppercase tracking-[0.14em] text-silver">{label}</div>
      <div className="mt-1 leading-snug">{value}</div>
    </div>
  );
}
