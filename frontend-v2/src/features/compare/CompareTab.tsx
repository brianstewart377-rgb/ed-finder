import type { ReactNode } from 'react';
import type { SystemResult } from '@/types/api';
import type { UseCompare } from './useCompare';
import { COMPARE_MAX } from './useCompare';
import { ratingTier, formatPopulation, formatConfidence } from '@/lib/format';

export interface CompareTabProps {
  compare: UseCompare;
  onOpenDetail?: (id64: number) => void;
}

/**
 * Per-metric matrix view. Columns = systems, rows = metrics.
 *
 * The "winner" per numeric row gets an orange left-border + bold text so
 * you can eyeball the best system per dimension in a few seconds. The
 * vanilla app does the same; we just use CSS classes instead of inline
 * style objects because Tailwind.
 *
 * Non-numeric rows (name, rationale, economy, external links) render plain.
 */
export function CompareTab({ compare, onOpenDetail }: CompareTabProps) {
  const { entries } = compare;

  if (entries.length === 0) {
    return (
      <section data-testid="compare-tab" className="space-y-5">
        <CompareHeader compare={compare} />
        <div className="panel-thin text-center py-16 px-4">
          <div className="text-3xl mb-2" aria-hidden>⚖️</div>
          <h3 className="font-display text-orange text-sm tracking-wider mb-1">No systems selected</h3>
          <p className="text-silver-dk text-xs max-w-sm mx-auto">
            Click ⚖️ on up to {COMPARE_MAX} system cards in the Finder tab to
            line them up side-by-side.
          </p>
        </div>
      </section>
    );
  }

  // Build the metric rows once so the winner-index pass is easy. Keep this
  // in sync with the CSV export in useCompare.ts.
  const rows = buildMetricRows(entries);

  return (
    <section data-testid="compare-tab" className="space-y-5">
      <CompareHeader compare={compare} />

      {compare.lastError && (
        <div className="panel-thin border-red/50 p-2 font-mono text-xs text-red flex items-center gap-2" style={{ background: 'rgba(248,113,113,0.10)' }}>
          <span>{compare.lastError}</span>
          <button
            type="button"
            onClick={compare.clearError}
            className="ml-auto text-red/70 hover:text-red"
            aria-label="Dismiss"
          >
            ✕
          </button>
        </div>
      )}

      <div className="overflow-x-auto rounded-chunk-lg border border-border" style={{
        background: 'linear-gradient(180deg, rgba(20,22,26,0.85), rgba(14,16,20,0.85))',
        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04), 0 8px 24px -16px rgba(0,0,0,0.6)',
      }}>
        <table className="w-full text-sm font-mono">
          <thead className="text-silver-dk text-[10px] uppercase tracking-[0.16em]" style={{
            background: 'linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01))',
            borderBottom: '1px solid hsl(216 10% 24%)',
          }}>
            <tr>
              <th className="px-3 py-2.5 text-left sticky left-0 bg-bg2/95 backdrop-blur z-10">Metric</th>
              {entries.map((sys) => (
                <th key={sys.id64} className="px-3 py-2.5 text-left min-w-[160px]">
                  <div className="flex items-center justify-between gap-2">
                    {onOpenDetail
                      ? (
                        <button
                          type="button"
                          onClick={() => onOpenDetail(sys.id64)}
                          className="text-orange-lt normal-case font-bold tracking-normal truncate hover:underline text-left"
                          title="Open detail"
                        >
                          {sys.name}
                        </button>
                      )
                      : (
                        <span className="text-orange-lt normal-case font-bold tracking-normal truncate" title={sys.name}>
                          {sys.name}
                        </span>
                      )
                    }
                    <button
                      type="button"
                      onClick={() => compare.remove(sys.id64)}
                      data-testid={`compare-remove-${sys.id64}`}
                      title="Remove from comparison"
                      className="text-red/80 hover:text-red text-[10px] shrink-0"
                    >
                      ✕
                    </button>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label} className="border-t border-border/50 hover:bg-orange/5 transition-colors">
                <td className="px-3 py-2 text-silver-dk font-semibold sticky left-0 bg-bg1/85 backdrop-blur">
                  {row.label}
                </td>
                {row.cells.map((cell, i) => (
                  <td
                    key={i}
                    data-testid={`compare-cell-${row.label.replace(/\s+/g, '-').toLowerCase()}-${entries[i].id64}`}
                    className={[
                      'px-3 py-2',
                      cell.winner
                        ? 'bg-orange/15 border-l-2 border-orange font-bold text-orange-lt'
                        : 'text-silver',
                    ].join(' ')}
                  >
                    {cell.display}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-[10px] font-mono text-silver-dk px-2">
        Orange column = best value for that metric.
        Comparison is stored locally in your browser; no server round-trip.
      </p>
    </section>
  );
}

// ─── Header with count + actions ──────────────────────────────────────────

function CompareHeader({ compare }: { compare: UseCompare }) {
  return (
    <header className="panel flex flex-wrap items-center gap-3 px-5 py-3">
      <h2 className="font-display text-orange tracking-[0.14em] text-lg">⚖️ Compare</h2>
      <span className="font-mono text-xs text-silver-dk">
        {compare.entries.length} / {COMPARE_MAX} selected
      </span>
      <span className="flex-1" />
      <button
        type="button"
        onClick={compare.exportCsv}
        disabled={compare.entries.length === 0}
        data-testid="compare-export-csv"
        className="btn-metal text-[11px] py-1.5 px-3 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        ⬇ Export CSV
      </button>
      <button
        type="button"
        onClick={() => {
          if (compare.entries.length === 0) return;
          if (confirm(`Clear all ${compare.entries.length} systems from comparison?`)) {
            compare.clear();
          }
        }}
        disabled={compare.entries.length === 0}
        data-testid="compare-clear"
        className="text-[11px] py-1.5 px-3 rounded-chunk-sm border border-red/40 bg-red/10 text-red hover:bg-red/20 font-mono transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        ✕ Clear all
      </button>
    </header>
  );
}

// ─── Metric-row construction ──────────────────────────────────────────────

interface Cell { display: ReactNode; winner: boolean }
interface MetricRow { label: string; cells: Cell[] }

/**
 * Turn a list of systems into the matrix rows. Keep pure + synchronous so
 * it's trivial to unit-test later.
 *
 * Winner rule: per numeric row, mark the single index with the best value.
 * 'Higher is better' unless explicitly inverted (distance-from-ref). If all
 * values are identical, NOBODY wins — highlighting every column is noise.
 */
function buildMetricRows(entries: SystemResult[]): MetricRow[] {
  const numericRow = (
    label: string,
    extract: (s: SystemResult) => number | null | undefined,
    render: (v: number | null | undefined, winner: boolean) => ReactNode,
    higherIsBetter = true,
  ): MetricRow => {
    const vals = entries.map(extract);
    const numeric = vals.map((v) => (typeof v === 'number' && Number.isFinite(v) ? v : null));
    const finiteVals = numeric.filter((v): v is number => v !== null);
    const allSame = finiteVals.length > 1 && finiteVals.every((v) => v === finiteVals[0]);
    let winnerIdx = -1;
    if (!allSame && finiteVals.length > 0) {
      const target = higherIsBetter ? Math.max(...finiteVals) : Math.min(...finiteVals);
      winnerIdx = numeric.findIndex((v) => v === target);
    }
    return {
      label,
      cells: numeric.map((v, i) => ({
        display: render(v, i === winnerIdx),
        winner: i === winnerIdx,
      })),
    };
  };

  const plainRow = (
    label: string,
    render: (s: SystemResult, i: number) => ReactNode,
  ): MetricRow => ({
    label,
    cells: entries.map((s, i) => ({ display: render(s, i), winner: false })),
  });

  return [
    numericRow(
      'Score',
      (s) => s._rating?.score,
      (v) => {
        const tier = ratingTier(v ?? null);
        return (
          <span
            className={[
              'inline-block px-2 py-0.5 rounded border text-[11px] font-bold',
              tier.label === 'EXCELLENT' && 'bg-green/20 text-green border-green/50',
              tier.label === 'GOOD'      && 'bg-gold/20 text-gold border-gold/50',
              tier.label === 'OK'        && 'bg-orange/20 text-orange border-orange/50',
              tier.label === 'POOR'      && 'bg-red/20 text-red border-red/50',
              tier.label === 'N/A'       && 'bg-bg4 text-text-dim border-border',
            ].filter(Boolean).join(' ')}
          >
            {v ?? '—'}
          </span>
        );
      },
    ),
    plainRow('Confidence', (s) => {
      const c = formatConfidence(s._rating?.confidence);
      if (!c) return <span className="text-text-dim">—</span>;
      const colour =
        c.tier === 'High'   ? 'text-green' :
        c.tier === 'Medium' ? 'text-gold'  : 'text-red';
      return <span className={`${colour} text-xs`}>{c.symbol} {c.pct}%</span>;
    }),
    plainRow('Rationale', (s) => (
      <span className="text-text-dim text-[11px] italic leading-snug block">
        {s._rating?.rationale || '—'}
      </span>
    )),
    plainRow('Primary economy',   (s) => <span className="text-text">{s.primaryEconomy ?? '—'}</span>),
    plainRow('Suggested economy', (s) => <span className="text-orange">{s._rating?.economySuggestion ?? '—'}</span>),
    numericRow(
      'Distance from ref',
      (s) => s.distance,
      (v) => (v == null ? <span className="text-text-dim">—</span> : <span className="tabular-nums">{v.toFixed(2)} LY</span>),
      false, // lower is better
    ),
    numericRow(
      'Population',
      (s) => s.population,
      (v) => (v == null || v === 0
        ? <span className="text-text-dim">—</span>
        : <span>{formatPopulation(v)}</span>),
    ),
    plainRow('Status', (s) => (
      s.is_colonised
        ? <span className="text-red">Colonised</span>
        : <span className="text-green">Available</span>
    )),
    plainRow('Main star', (s) => (
      <span className="text-text-dim text-xs">
        {s.main_star_subtype ?? s.main_star_type ?? '—'}
      </span>
    )),
    plainRow('Security',   (s) => <span className="text-text-dim text-xs">{s.security ?? '—'}</span>),
    plainRow('Allegiance', (s) => <span className="text-text-dim text-xs">{s.allegiance ?? '—'}</span>),
    numericRow('Terraforming potential', (s) => s._rating?.terraformingPotential,
      (v) => v == null ? <span className="text-text-dim">—</span> : <span className="tabular-nums">{v}</span>),
    numericRow('Body diversity', (s) => s._rating?.bodyDiversity,
      (v) => v == null ? <span className="text-text-dim">—</span> : <span className="tabular-nums">{v}</span>),
    numericRow('ELW',           (s) => s.elw_count,          chipOrDash('🌍', 'green')),
    numericRow('Water worlds',  (s) => s.ww_count,           chipOrDash('🌊', 'cyan')),
    numericRow('Ammonia',       (s) => s.ammonia_count,      chipOrDash('🟣', 'text-dim')),
    numericRow('Terraformable', (s) => s.terraformable_count,chipOrDash('🌱', 'gold')),
    numericRow('Landable',      (s) => s.landable_count,     chipOrDash('🪨', 'text-dim')),
    numericRow('Bio signals',   (s) => s.bio_signal_total,   chipOrDash('🧬', 'green')),
    numericRow('Geo signals',   (s) => s.geo_signal_total,   chipOrDash('🌋', 'orange')),
    numericRow('Agriculture',   (s) => s._rating?.scoreAgriculture, scoreChip),
    numericRow('Refinery',      (s) => s._rating?.scoreRefinery,    scoreChip),
    numericRow('Industrial',    (s) => s._rating?.scoreIndustrial,  scoreChip),
    numericRow('High Tech',     (s) => s._rating?.scoreHightech,    scoreChip),
    numericRow('Military',      (s) => s._rating?.scoreMilitary,    scoreChip),
    numericRow('Tourism',       (s) => s._rating?.scoreTourism,     scoreChip),
    numericRow('Extraction',    (s) => s._rating?.scoreExtraction,  scoreChip),
    plainRow('Links', (s) => (
      <span className="space-x-2 whitespace-nowrap text-[11px]">
        <a
          href={`https://spansh.co.uk/system/${s.id64}`}
          target="_blank"
          rel="noopener noreferrer"
          className="text-orange hover:underline"
        >Spansh↗</a>
        <a
          href={`https://inara.cz/starsystem/?search=${encodeURIComponent(s.name)}`}
          target="_blank"
          rel="noopener noreferrer"
          className="text-cyan hover:underline"
        >Inara↗</a>
      </span>
    )),
  ];
}

// ─── Cell renderers ────────────────────────────────────────────────────────

function chipOrDash(icon: string, colourClass: string) {
  return (v: number | null | undefined) => {
    if (v == null || v === 0) return <span className="text-text-dim">—</span>;
    return (
      <span className={`text-${colourClass}`}>
        {icon} <span className="tabular-nums font-bold">{v}</span>
      </span>
    );
  };
}

function scoreChip(v: number | null | undefined): ReactNode {
  if (v == null) return <span className="text-text-dim">—</span>;
  // Re-use the overall-score tier palette so "Tourism 78" reads the same
  // colour language as "Overall 78" on the cards.
  const tier = ratingTier(v);
  return (
    <span
      className={[
        'inline-block px-1.5 py-0 rounded border text-[10px] font-bold',
        tier.label === 'EXCELLENT' && 'bg-green/20 text-green border-green/40',
        tier.label === 'GOOD'      && 'bg-gold/20 text-gold border-gold/40',
        tier.label === 'OK'        && 'bg-orange/20 text-orange border-orange/40',
        tier.label === 'POOR'      && 'bg-red/20 text-red border-red/40',
        tier.label === 'N/A'       && 'bg-bg4 text-text-dim border-border',
      ].filter(Boolean).join(' ')}
    >
      {v}
    </span>
  );
}
