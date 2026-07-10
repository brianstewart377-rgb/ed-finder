import { Compass, Route } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { getRegionalAnalysis } from '@/lib/api';
import type { RegionalAnalysisResponse } from '@/types/api';

const COLONISATION_CLAIM_RANGE_LY = 16;

export function RegionalPositionPanel({ id64 }: { id64: number }) {
  const { data, isLoading, isError, error, refetch } = useQuery<RegionalAnalysisResponse, Error>({
    queryKey: ['regional-analysis', id64],
    queryFn: () => getRegionalAnalysis(id64),
    staleTime: 10 * 60 * 1000,
    retry: 1,
  });

  if (isLoading) {
    return (
      <div data-testid="regional-position-loading" className="rounded-chunk-lg border border-border/60 bg-bg3/30 p-4 animate-pulse">
        <div className="h-4 w-52 rounded bg-bg4/70" />
        <div className="mt-4 grid gap-2 sm:grid-cols-3">
          <div className="h-16 rounded bg-bg4/50" />
          <div className="h-16 rounded bg-bg4/40" />
          <div className="h-16 rounded bg-bg4/30" />
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div data-testid="regional-position-error" className="rounded-chunk-lg border border-gold/40 bg-gold/10 p-3 font-mono text-xs text-gold">
        Regional positioning unavailable: {error?.message}
        <button type="button" onClick={() => void refetch()} className="ml-2 underline hover:text-orange">
          retry
        </button>
      </div>
    );
  }

  if (!data || data.regional_role === 'unknown') {
    return (
      <section data-testid="regional-position-unknown" className="rounded-chunk-lg border border-border/70 bg-bg1/60 p-4">
        <Header />
        <div className="rounded border border-border/60 bg-bg3/35 px-3 py-3 font-mono text-[11px] text-silver-dk">
          {data?.rationale?.summary || 'Regional analysis has not been computed for this system yet.'}
        </div>
      </section>
    );
  }

  const fitRows = Object.entries(data.archetype_regional_fit)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4);
  const nearestDistance = data.nearest_colonised_system?.distance_ly ?? null;
  const inClaimRange = nearestDistance != null && nearestDistance <= COLONISATION_CLAIM_RANGE_LY;
  const proximityLabel = inClaimRange ? 'Within claim range' : 'Out of claim range';
  const proximityTone = inClaimRange ? 'cyan' : 'orange';

  return (
    <section data-testid="regional-position-success" className="rounded-chunk-lg border border-orange/25 bg-bg1/60 p-4 shadow-metal">
      <Header />
      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(180px,0.55fr)]">
        <div className="rounded-chunk-lg border border-orange/35 bg-orange/10 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge label={formatRole(data.regional_role)} tone="orange" />
            <Badge label={proximityLabel} tone={proximityTone} />
            {data.nearest_colonised_system?.distance_ly != null && (
              <Badge label={`${data.nearest_colonised_system.distance_ly.toFixed(1)} LY nearest`} tone="cyan" />
            )}
            {data.data_quality?.regional_position && (
              <Badge label={standardLabel(data.data_quality.regional_position)} tone="cyan" />
            )}
          </div>
          {data.nearest_colonised_system?.name && nearestDistance != null && (
            <div
              data-testid="regional-position-verdict"
              className="mt-3 rounded border border-border/60 bg-bg3/45 px-3 py-3"
            >
              <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-silver-dk">
                Colonisation proximity
              </div>
              <p className="mt-2 text-sm leading-snug text-silver">
                {inClaimRange
                  ? `Within claim range of ${data.nearest_colonised_system.name} at ${nearestDistance.toFixed(1)} ly.`
                  : `Out of claim range. Nearest observed colonised anchor is ${data.nearest_colonised_system.name} at ${nearestDistance.toFixed(1)} ly.`}
              </p>
              <p className="mt-1 font-mono text-[10px] text-silver-dk">
                Measured star-to-star against the current {COLONISATION_CLAIM_RANGE_LY} ly claim-range setting.
              </p>
            </div>
          )}
          <p className="mt-3 text-sm leading-snug text-silver">
            {data.rationale?.summary}
          </p>
          {data.nearest_colonised_system?.name && (
            <div className="mt-2 flex items-center gap-2 font-mono text-[11px] text-silver-dk">
              <Route size={13} />
              Nearest colony: <span className="text-cyan">{data.nearest_colonised_system.name}</span>
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 gap-2">
          <Metric label="50 LY" value={data.counts.within_50ly} />
          <Metric label="100 LY" value={data.counts.within_100ly} />
          <Metric label="250 LY" value={data.counts.within_250ly} />
          <Metric label="Competition" value={Math.round(data.scores.competition)} />
        </div>
      </div>

      {fitRows.length > 0 && (
        <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {fitRows.map(([archetype, score]) => (
            <div key={archetype} className="rounded border border-border/60 bg-bg3/45 px-2 py-2">
              <div className="font-mono text-[9px] uppercase tracking-[0.12em] text-silver-dk">{formatRole(archetype)}</div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-bg4">
                <div className="h-full rounded-full bg-orange-grad" style={{ width: `${Math.max(4, Math.min(100, score))}%` }} />
              </div>
              <div className="mt-1 font-mono text-[10px] text-orange tabular-nums">{score.toFixed(0)} regional fit</div>
            </div>
          ))}
        </div>
      )}

      {data.rationale?.warnings && data.rationale.warnings.length > 0 && (
        <div className="mt-3 rounded border border-gold/35 bg-gold/5 px-3 py-2 font-mono text-[11px] text-gold">
          {data.rationale.warnings[0]}
        </div>
      )}

      {data.confidence_signals.length > 0 && (
        <div className="mt-3 rounded border border-border/60 bg-bg3/35 px-3 py-2 font-mono text-[10px] text-silver-dk">
          <span className="text-cyan">{standardLabel(data.confidence_signals[0].level)}:</span> {data.confidence_signals[0].reason}
        </div>
      )}
    </section>
  );
}

function Header() {
  return (
    <div className="mb-3 flex items-center gap-2">
      <Compass size={16} className="text-orange" />
      <div>
        <h3 className="text-orange text-sm font-bold tracking-[0.18em] uppercase">Colonisation Proximity</h3>
        <p className="mt-1 text-[11px] text-silver-dk font-mono">
          Nearest colonised-anchor context for Inspect, measured star-to-star.
        </p>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded border border-border/60 bg-bg3/60 p-2 text-center">
      <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-silver-dk">{label}</div>
      <div className="mt-1 font-mono text-sm font-bold text-orange tabular-nums">{value}</div>
    </div>
  );
}

function Badge({ label, tone }: { label: string; tone: 'orange' | 'cyan' }) {
  const colour = tone === 'orange' ? '#f97316' : '#22d3ee';
  return (
    <span className="rounded border px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em]" style={{ borderColor: `${colour}66`, color: colour, backgroundColor: `${colour}14` }}>
      {label}
    </span>
  );
}

function formatRole(value: string): string {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
}

function standardLabel(value: string): string {
  const labels: Record<string, string> = {
    observed: 'Observed',
    verified: 'Verified',
    community_observed: 'Community observed',
    inferred: 'Inferred',
    estimated: 'Estimated',
    speculative: 'Speculative',
    unknown: 'Unknown',
  };
  return labels[value] ?? formatRole(value);
}
