import { formatArchetypeLabel } from '@/lib/archetypes';
import type { SystemDetail } from '@/types/api';
import { SemanticStatusBadge, type SemanticStatusTone } from '@/components/SemanticStatusBadge';

export function SelectedSystemReviewContext({
  system,
  modeLabel,
  tone,
  summary,
  targetArchetype = null,
}: {
  system: SystemDetail;
  modeLabel: string;
  tone: SemanticStatusTone;
  summary: string;
  targetArchetype?: string | null;
}) {
  const planningLens = targetArchetype
    ? formatArchetypeLabel(targetArchetype)
    : system.primary_archetype
      ? formatArchetypeLabel(system.primary_archetype)
      : (system.primary_economy ?? 'Unknown');

  return (
    <section
      data-testid="selected-system-review-context"
      className="rounded-chunk-lg border border-cyan/25 bg-cyan/5 p-3"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-display text-xs tracking-[0.14em] text-cyan">
          Selected-system context
        </span>
        <SemanticStatusBadge label={modeLabel} tone={tone} />
        <span className="rounded border border-border/70 bg-bg1/45 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-silver-dk">
          Review only
        </span>
      </div>
      <p
        data-testid="selected-system-review-summary"
        className="mt-2 text-sm leading-relaxed text-silver"
      >
        {summary}
      </p>
      <div className="mt-3 flex flex-wrap gap-2 text-[11px] font-mono">
        <span className="premium-subpanel inline-flex items-center gap-1.5 px-2.5 py-1.5 text-silver">
          <span className="uppercase tracking-[0.14em] text-silver-dk">System</span>
          <span>{system.name ?? `ID64 ${system.id64}`}</span>
        </span>
        <span className="premium-subpanel inline-flex items-center gap-1.5 px-2.5 py-1.5 text-orange">
          <span className="uppercase tracking-[0.14em] text-silver-dk">Planning lens</span>
          <span>{planningLens}</span>
        </span>
      </div>
    </section>
  );
}
