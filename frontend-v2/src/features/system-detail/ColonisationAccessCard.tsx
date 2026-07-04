import { useEffect, useState } from 'react';
import { Route, Rocket } from 'lucide-react';
import type { RegionalAnalysisResponse, SystemDetail } from '@/types/api';
import { getRegionalAnalysis } from '@/lib/api';
import { calculateColonisationAccess, VERIFIED_CLAIM_HOP_REACH_LY } from './colonisationAccess';

type RegionalState =
  | { status: 'loading'; data: null }
  | { status: 'ready'; data: RegionalAnalysisResponse | null }
  | { status: 'error'; data: null };

export function ColonisationAccessCard({
  system,
  onStartCorridorPlan,
}: {
  system: SystemDetail;
  onStartCorridorPlan?: (system: SystemDetail) => void;
}) {
  const [regional, setRegional] = useState<RegionalState>({ status: 'loading', data: null });

  useEffect(() => {
    let cancelled = false;
    setRegional({ status: 'loading', data: null });
    void getRegionalAnalysis(system.id64)
      .then((data) => {
        if (!cancelled) setRegional({ status: 'ready', data });
      })
      .catch(() => {
        if (!cancelled) setRegional({ status: 'error', data: null });
      });
    return () => {
      cancelled = true;
    };
  }, [system.id64]);

  const nearest = regional.data?.nearest_colonised_system ?? null;
  const access = calculateColonisationAccess(nearest?.distance_ly, VERIFIED_CLAIM_HOP_REACH_LY);
  const canStart = Number.isFinite(system.id64) && system.id64 > 0 && Boolean(onStartCorridorPlan);

  return (
    <section
      data-testid="colonisation-access-card"
      className="rounded-chunk-lg border border-cyan/35 bg-cyan/5 p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Route size={16} className="text-cyan" />
            <h3 className="font-display text-sm tracking-[0.14em] text-cyan uppercase">
              Colonisation Access
            </h3>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-silver-dk">
            Distance is regional context. A route has not yet been searched through intermediate systems.
          </p>
        </div>
        <span className="rounded border border-border bg-bg3/60 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-silver">
          Route search not run
        </span>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <div className="rounded border border-border/60 bg-bg3/35 p-3">
          <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">Nearest known colony</div>
          {regional.status === 'loading' ? (
            <div className="mt-1 text-sm text-silver">Loading regional position…</div>
          ) : nearest?.name && nearest.distance_ly != null ? (
            <>
              <div className="mt-1 text-sm font-semibold text-cyan">{nearest.name}</div>
              <div className="mt-1 font-mono text-xs tabular-nums text-silver">{nearest.distance_ly.toFixed(1)} LY away</div>
            </>
          ) : (
            <div className="mt-1 text-sm text-silver">Nearest known colony is unavailable for this system.</div>
          )}
        </div>

        <div className="rounded border border-border/60 bg-bg3/35 p-3">
          <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">Bridge outlook</div>
          {access.kind === 'direct' ? (
            <>
              <div className="mt-1 text-sm font-semibold text-green">Directly reachable — no intermediate claims required.</div>
              <div className="mt-1 text-xs text-silver-dk">Geometric estimate only; route search has not checked intermediate system availability.</div>
            </>
          ) : access.kind === 'estimate' ? (
            <>
              <div className="mt-1 text-sm font-semibold text-text">{access.intermediateClaims} intermediate claims + target system</div>
              <div className="mt-1 text-xs text-silver-dk">{access.totalNewClaims} total new claims. Geometric estimate only; it does not prove viable or unclaimed systems exist en route.</div>
            </>
          ) : (
            <>
              <div className="mt-1 text-sm font-semibold text-gold">Minimum bridge unavailable</div>
              <div className="mt-1 text-xs leading-relaxed text-silver-dk">A verified claim-hop reach has not been configured. ED-Finder will not guess a numerical bridge count.</div>
            </>
          )}
        </div>
      </div>

      <div className="mt-3 rounded border border-cyan/25 bg-cyan/5 px-3 py-2 text-xs leading-relaxed text-silver">
        <span className="font-mono uppercase tracking-[0.12em] text-cyan">Truth labels:</span>{' '}
        <strong className="text-text">Geometric estimate</strong> means distance plus a verified claim-hop reach only.{' '}
        <strong className="text-text">Route search not run</strong> means no intermediate systems have been checked.
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => onStartCorridorPlan?.(system)}
          disabled={!canStart}
          data-testid="start-corridor-plan"
          className="inline-flex items-center gap-2 rounded-chunk-sm border border-cyan/45 bg-cyan/10 px-3 py-2 text-xs font-mono font-bold text-cyan hover:bg-cyan/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan/80 disabled:cursor-not-allowed disabled:border-border disabled:bg-bg3/60 disabled:text-silver-dk"
        >
          <Rocket size={14} />
          Start corridor plan
        </button>
        <p className="text-xs text-silver-dk">
          Destination locked: optimise the road to {system.name || 'this system'}; do not substitute another target.
        </p>
      </div>
    </section>
  );
}
