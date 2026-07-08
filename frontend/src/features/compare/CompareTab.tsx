import type { ReactNode } from 'react';
import type { SystemResult } from '@/types/api';
import type { UseCompare } from './useCompare';
import { COMPARE_MAX } from './useCompare';
import { ReviewWorkspaceHeader, type ReviewSelectedSystem } from '@/components/ReviewWorkspaceHeader';
import {
  formatPopulationForSystem,
  formatDistance,
  systemStatusLabel,
} from '@/lib/format';
import { archetypeTierFromScore, formatArchetypeLabel, getDevelopmentScore } from '@/lib/archetypes';

export interface CompareTabProps {
  compare: UseCompare;
  onOpenDetail?: (id64: number) => void;
  selectedSystem?: ReviewSelectedSystem | null;
}

export function CompareTab({ compare, onOpenDetail, selectedSystem = null }: CompareTabProps) {
  const { entries } = compare;

  if (entries.length === 0) {
    return (
      <section data-testid="compare-tab" className="space-y-5">
        <CompareHeader compare={compare} selectedSystem={selectedSystem} />
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

  const rows = buildMetricRows(entries);

  return (
    <section data-testid="compare-tab" className="space-y-5">
      <CompareHeader compare={compare} selectedSystem={selectedSystem} />

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
                      )}
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

function CompareHeader({
  compare,
  selectedSystem,
}: {
  compare: UseCompare;
  selectedSystem: ReviewSelectedSystem | null;
}) {
  return (
    <ReviewWorkspaceHeader
      testId="compare-workspace-header"
      title="Compare"
      supportingText="Review candidate systems side-by-side while the selected-system context stays visible for the wider player journey."
      selectedSystem={selectedSystem}
      facts={[
        {
          label: 'Compared',
          value: `${compare.entries.length} / ${COMPARE_MAX}`,
          tone: compare.entries.length > 0 ? 'cyan' : 'default',
        },
      ]}
      actions={(
        <>
          <button
            type="button"
            onClick={compare.exportCsv}
            disabled={compare.entries.length === 0}
            data-testid="compare-export-csv"
            className="btn-metal text-[11px] py-1.5 px-3 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            ↓ Export CSV
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
        </>
      )}
    />
  );
}

interface Cell { display: ReactNode; winner: boolean }
interface MetricRow { label: string; cells: Cell[] }

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
      'Development score',
      (s) => getDevelopmentScore(s),
      (v) => {
        const tier = archetypeTierFromScore(v ?? null);
        return (
          <span
            className={[
              'inline-block px-2 py-0.5 rounded border text-[11px] font-bold',
              tier === 'S' && 'bg-cyan/20 text-cyan border-cyan/50',
              tier === 'A' && 'bg-green/20 text-green border-green/50',
              tier === 'B' && 'bg-gold/20 text-gold border-gold/50',
              tier === 'C' && 'bg-orange/20 text-orange border-orange/50',
              tier === 'D' && 'bg-red/20 text-red border-red/50',
              tier == null && 'bg-bg4 text-text-dim border-border',
            ].filter(Boolean).join(' ')}
          >
            {tier ?? '—'} {v ?? '—'}
          </span>
        );
      },
    ),
    plainRow('Primary archetype', (s) => (
      <span className="text-cyan">{s.primary_archetype ? formatArchetypeLabel(s.primary_archetype) : '—'}</span>
    )),
    plainRow('Secondary archetype', (s) => (
      <span className="text-text-dim">{s.secondary_archetype ? formatArchetypeLabel(s.secondary_archetype) : '—'}</span>
    )),
    plainRow('Archetype confidence', (s) => {
      const value = s.archetype_confidence ?? null;
      if (value == null) return <span className="text-text-dim">—</span>;
      return <span className="text-cyan text-xs">{Math.round(value * 100)}%</span>;
    }),
    numericRow('Buildability', (s) => s.buildability_score,
      (v) => v == null ? <span className="text-text-dim">—</span> : <span className="tabular-nums">{v}</span>),
    numericRow('Purity', (s) => s.purity_score,
      (v) => v == null ? <span className="text-text-dim">—</span> : <span className="tabular-nums">{v}</span>),
    numericRow('Estimated slots', (s) => s.est_total_slots,
      (v) => v == null ? <span className="text-text-dim">—</span> : <span className="tabular-nums">{v}</span>),
    plainRow('Primary economy',   (s) => <span className="text-text">{s.primaryEconomy ?? '—'}</span>),
    numericRow(
      'Distance from ref',
      (s) => s.distance,
      (v) => {
        const fmt = formatDistance(v);
        return fmt ? <span className="tabular-nums">{fmt}</span> : <span className="text-text-dim">—</span>;
      },
      false,
    ),
    plainRow('Population', (s) => (
      <span className={s.population ? 'text-text' : 'text-text-dim'}>
        {formatPopulationForSystem(s)}
      </span>
    )),
    plainRow('Status', (s) => (
      systemStatusLabel(s) === 'Colonised'
        ? <span className="text-red">Colonised</span>
        : systemStatusLabel(s) === 'Colonising'
          ? <span className="text-gold">Colonising</span>
          : <span className="text-green">Available</span>
    )),
    plainRow('Main star', (s) => (
      <span className="text-text-dim text-xs">
        {s.main_star_subtype ?? s.main_star_type ?? '—'}
      </span>
    )),
    plainRow('Security',   (s) => <span className="text-text-dim text-xs">{s.security ?? '—'}</span>),
    plainRow('Allegiance', (s) => <span className="text-text-dim text-xs">{s.allegiance ?? '—'}</span>),
    numericRow('ELW',           (s) => s.elw_count,          chipOrDash('🌍', 'green')),
    numericRow('Water worlds',  (s) => s.ww_count,           chipOrDash('🌊', 'cyan')),
    numericRow('Ammonia',       (s) => s.ammonia_count,      chipOrDash('🟣', 'text-dim')),
    numericRow('Terraformable', (s) => s.terraformable_count, chipOrDash('🌱', 'gold')),
    numericRow('Landable',      (s) => s.landable_count,     chipOrDash('🪨', 'text-dim')),
    numericRow('Bio signals',   (s) => s.bio_signal_total,   chipOrDash('🧬', 'green')),
    numericRow('Geo signals',   (s) => s.geo_signal_total,   chipOrDash('🌋', 'orange')),
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

function chipOrDash(icon: string, colourClass: string) {
  return (v: number | null | undefined) => {
    if (v == null || v === 0) return <span className="text-text-dim">—</span>;
    return (
      <span className={colourClass}>
        {icon} <span className="tabular-nums font-bold">{v}</span>
      </span>
    );
  };
}
