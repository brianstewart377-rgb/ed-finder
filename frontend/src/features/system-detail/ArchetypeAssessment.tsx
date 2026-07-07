import type { SystemArchetypeResponse } from '@/types/api';

export function ArchetypeAssessment({
  archetype,
  loading,
  error,
  warning,
  onRetry,
}: {
  archetype: SystemArchetypeResponse | null;
  loading: boolean;
  error: string | null;
  warning?: string | null;
  onRetry: () => void;
}) {
  if (loading) {
    return (
      <div
        data-testid="archetype-assessment-loading"
        className="rounded-chunk-lg border border-border/70 bg-bg3/30 p-4 animate-pulse"
      >
        <div className="h-4 w-48 rounded bg-bg4/70" />
        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          <div className="h-16 rounded bg-bg4/50" />
          <div className="h-16 rounded bg-bg4/40" />
          <div className="h-16 rounded bg-bg4/30" />
        </div>
      </div>
    );
  }

  if (error && !archetype) {
    return (
      <div
        data-testid="archetype-assessment-error"
        className="rounded-chunk-lg border border-gold/40 bg-gold/10 p-4"
      >
        <div className="flex flex-wrap items-center gap-3">
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-gold">
            Archetype assessment unavailable
          </div>
          <button
            type="button"
            onClick={onRetry}
            className="rounded-chunk-sm border border-gold/40 bg-gold/10 px-3 py-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.12em] text-gold hover:bg-gold/15"
          >
            Retry
          </button>
        </div>
        <p className="mt-2 text-sm text-silver">
          The archetype service did not return a result. Retry to refresh the development assessment.
        </p>
      </div>
    );
  }

  if (!archetype) return null;

  const primaryKey = archetype.primary_archetype;
  const primary = primaryKey ? archetype.archetypes?.[primaryKey] : null;
  const secondaryKey = archetype.secondary_archetype;
  const secondary = secondaryKey ? archetype.archetypes?.[secondaryKey] : null;
  const positives = primary?.rationale?.positives?.filter(Boolean) ?? [];
  const risks = primary?.rationale?.risks?.filter(Boolean) ?? [];
  const tags = (primary?.rationale?.tags?.filter(Boolean) ?? archetype.tags ?? []).slice(0, 4);
  const metrics = [
    ['Development potential', formatScore(archetype.overall_development_potential)],
    ['Buildability', formatScore(archetype.buildability_score)],
    ['Purity', formatScore(archetype.purity_score)],
    ['Confidence', formatPercent(archetype.confidence ?? archetype.archetype_confidence)],
  ];

  return (
    <div data-testid="archetype-assessment" className="space-y-4">
      {warning ? (
        <div
          data-testid="archetype-assessment-warning"
          className="rounded-chunk-lg border border-gold/40 bg-gold/10 p-4"
        >
          <div className="flex flex-wrap items-center gap-3">
            <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-gold">
              Live archetype refresh unavailable
            </div>
            <button
              type="button"
              onClick={onRetry}
              className="rounded-chunk-sm border border-gold/40 bg-gold/10 px-3 py-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.12em] text-gold hover:bg-gold/15"
            >
              Retry
            </button>
          </div>
          <p className="mt-2 text-sm text-silver">{warning}</p>
        </div>
      ) : null}
      <div className="rounded-chunk-lg border border-cyan/30 bg-cyan/5 p-4">
        <div className="flex flex-wrap items-start gap-3">
          <div className="min-w-0 flex-1">
            <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">
              Primary archetype
            </div>
            <div className="mt-1 text-lg font-mono font-bold text-white" data-testid="archetype-primary">
              {primary?.label ?? formatArchetypeLabel(primaryKey)}
            </div>
            {primary?.rationale?.headline && (
              <p className="mt-2 text-sm leading-snug text-silver">
                {primary.rationale.headline}
              </p>
            )}
            {!primary?.rationale?.headline && primary?.rationale?.summary && (
              <p className="mt-2 text-sm leading-snug text-silver">
                {primary.rationale.summary}
              </p>
            )}
          </div>
          <Badge label={`Tier ${primary?.tier ?? '?'}`} tone={tierTone(primary?.tier)} />
          {secondaryKey && (
            <Badge label={`Secondary ${formatArchetypeLabel(secondaryKey)}`} tone="silver" />
          )}
        </div>

        <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {metrics.map(([label, value]) => (
            <div key={label} className="rounded border border-border/70 bg-bg2/70 px-3 py-2">
              <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-silver-dk">{label}</div>
              <div className="mt-1 font-mono text-sm font-bold text-orange-lt">{value}</div>
            </div>
          ))}
        </div>
      </div>

      {(positives.length > 0 || risks.length > 0) && (
        <div className="grid gap-3 md:grid-cols-2">
          <Callout
            title="Strengths"
            items={positives.length ? positives.slice(0, 3) : ['No explicit strengths were returned for this archetype.']}
            tone="good"
          />
          <Callout
            title="Risks"
            items={risks.length ? risks.slice(0, 3) : ['No explicit risks were returned for this archetype.']}
            tone="warn"
          />
        </div>
      )}

      {(secondary || tags.length > 0) && (
        <div className="flex flex-wrap gap-2">
          {secondary && (
            <span className="rounded-chunk-sm border border-border/60 bg-bg3/50 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-silver">
              Secondary fit: <span className="text-white">{secondary.label}</span>
            </span>
          )}
          {tags.map((tag) => (
            <span
              key={tag}
              className="rounded-chunk-sm border border-cyan/25 bg-cyan/10 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-cyan"
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      <p className="font-mono text-[10px] leading-snug text-silver-dk">
        This archetype assessment drives the current Finder development view and planning handoff.
      </p>
    </div>
  );
}

function Callout({
  title,
  items,
  tone,
}: {
  title: string;
  items: string[];
  tone: 'good' | 'warn';
}) {
  const cls = tone === 'good'
    ? 'border-green/35 bg-green/5 text-green'
    : 'border-gold/35 bg-gold/5 text-gold';

  return (
    <div className={`rounded-chunk-lg border px-3 py-2 font-mono text-[11px] ${cls}`}>
      <div className="mb-1 text-[10px] uppercase tracking-[0.16em] opacity-80">{title}</div>
      <ul className="space-y-1">
        {items.map((item) => (
          <li key={item} className="leading-snug">{item}</li>
        ))}
      </ul>
    </div>
  );
}

function Badge({
  label,
  tone,
}: {
  label: string;
  tone: 'cyan' | 'green' | 'gold' | 'orange' | 'silver';
}) {
  const colour = {
    cyan: '#22d3ee',
    green: '#4ade80',
    gold: '#fbbf24',
    orange: '#f97316',
    silver: '#9ca3af',
  }[tone];

  return (
    <span
      className="rounded-chunk-sm border px-2.5 py-1 font-mono text-[10px] font-bold uppercase tracking-[0.12em]"
      style={{ borderColor: `${colour}70`, color: colour, backgroundColor: `${colour}18` }}
    >
      {label}
    </span>
  );
}

function formatArchetypeLabel(value?: string | null): string {
  if (!value) return 'Unknown archetype';
  return value.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatScore(value?: number | null): string {
  if (value == null || !Number.isFinite(value)) return 'Unknown';
  return `${Math.round(value)}`;
}

function formatPercent(value?: number | null): string {
  if (value == null || !Number.isFinite(value)) return 'Unknown';
  return `${Math.round(value * 100)}%`;
}

function tierTone(value?: string | null): 'cyan' | 'green' | 'gold' | 'orange' | 'silver' {
  if (value === 'S') return 'cyan';
  if (value === 'A') return 'green';
  if (value === 'B') return 'gold';
  if (value === 'C') return 'orange';
  return 'silver';
}
