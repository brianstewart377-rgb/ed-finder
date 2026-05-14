import type { RerankRow, SystemResult } from '@/types/api';
import { ratingTier } from '@/lib/format';
import { ECONOMIES, type UseOptimizer } from './useOptimizer';
import type { useSearch } from '@/features/search/useSearch';

export interface OptimizerTabProps {
  optimizer:    UseOptimizer;
  search:       ReturnType<typeof useSearch>;
  onOpenDetail?: (id64: number) => void;
}

const WEIGHT_LABELS: Array<{ key: keyof UseOptimizer['weights']; label: string; hint: string }> = [
  { key: 'economy',      label: 'Economy',      hint: 'Changes how strongly matching economies affect the rerank.' },
  { key: 'slots',        label: 'Slots',        hint: 'Build-slot capacity from body counts' },
  { key: 'strategic',    label: 'Strategic',    hint: 'Body-quality / system value' },
  { key: 'safety',       label: 'Safety',       hint: 'Orbital safety (no neutron / black hole)' },
  { key: 'terraforming', label: 'Terraforming', hint: 'Terraforming potential' },
  { key: 'diversity',    label: 'Diversity',    hint: 'Body-type diversity' },
];

/**
 * Legacy Search Tuning = re-weight the score for the current Finder results.
 *
 * This legacy optimizer feature tunes Finder result ranking. The Stage 5 colony optimiser lives under Simulation Preview.
 * UX: 6 weight sliders + economy selector + Run button.
 * The "source" is whatever Finder last returned — no separate search here.
 * If Finder has no results, the Run button is disabled with a clear hint.
 */
export function OptimizerTab({ optimizer, search, onOpenDetail }: OptimizerTabProps) {
  const { weights, setWeight, resetWeights, weightSum, economy, setEconomy, state, run, resetState } = optimizer;
  const sourceCount = search.results.length;
  const sumOk = Math.abs(weightSum - 1.0) < 0.01;

  // Index source by id64 for cheap join with rerank results.
  const sourceById = new Map(search.results.map((s) => [s.id64, s] as const));

  return (
    <section data-testid="optimizer-tab" className="space-y-5">
      <header className="panel flex flex-wrap items-center gap-3 px-5 py-3">
        <h2 className="font-display text-orange tracking-[0.14em] text-lg">🎚️ Search Tuning</h2>
        <div className="font-mono text-xs text-silver-dk">
          <div>Re-weight and reorder your current Finder results.</div>
          <div className="mt-1 text-[11px] text-gold">This tunes Finder search results only. It does not generate colony build plans.</div>
        </div>
      </header>

      <div className="grid lg:grid-cols-[360px_1fr] gap-6">
        {/* ─── Controls ───────────────────────────────────────────────── */}
        <aside className="panel space-y-4 p-5 lg:sticky lg:top-20 lg:self-start lg:max-h-[calc(100vh-11rem)] lg:overflow-y-auto">
          <SourceBadge count={sourceCount} />

          <div>
            <label className="block font-mono text-[10px] text-silver-dk uppercase tracking-[0.18em] mb-1">
              Economy preference
            </label>
            <select
              value={economy ?? ''}
              onChange={(e) => setEconomy((e.target.value || null) as never)}
              data-testid="optimizer-economy"
              className="w-full font-mono text-xs"
            >
              <option value="">Auto (per-row stored suggestion)</option>
              {ECONOMIES.map((eco) => (
                <option key={eco} value={eco}>{eco}</option>
              ))}
            </select>
            <p className="text-[10px] text-silver-dk mt-1">
              Changes how strongly matching economies affect the rerank.
            </p>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between font-mono text-[10px] text-silver-dk uppercase tracking-[0.18em]">
              <span>Weights</span>
              <button
                type="button"
                onClick={resetWeights}
                data-testid="optimizer-weights-reset"
                className="normal-case tracking-normal text-silver-dk hover:text-orange-lt"
              >
                ↺ Reset to v3.1 defaults
              </button>
            </div>
            <p className="text-[10px] text-silver-dk">
              Adjust how much each scoring dimension matters when reordering the current Finder results.
            </p>
            {WEIGHT_LABELS.map(({ key, label, hint }) => (
              <WeightSlider
                key={key}
                label={label}
                hint={hint}
                value={weights[key]}
                onChange={(v) => setWeight(key, v)}
                testid={`optimizer-weight-${key}`}
              />
            ))}
            <div className={[
              'rounded-chunk-sm border p-2 font-mono text-[11px] flex items-center justify-between',
              sumOk ? 'border-green/40 bg-green/10 text-green'
                    : 'border-gold/40  bg-gold/10  text-gold',
            ].join(' ')}>
              <span>Sum: {weightSum.toFixed(2)}</span>
              <span className="text-[10px] opacity-80">
                {sumOk ? '≈ 1.0 ✓' : 'will be normalised server-side'}
              </span>
            </div>
          </div>

          <button
            type="button"
            disabled={sourceCount === 0 || state.kind === 'busy'}
            onClick={() => void run(search.results)}
            data-testid="optimizer-run"
            className={[
              'w-full',
              sourceCount === 0 || state.kind === 'busy'
                ? 'btn-metal opacity-60 cursor-not-allowed'
                : 'btn-primary',
            ].join(' ')}
          >
            {state.kind === 'busy' ? '⟳ Reranking…' : '▶ Rerank results'}
          </button>

          {state.kind === 'err' && (
            <div className="panel-thin border-red/50 p-2 font-mono text-xs text-red flex items-start gap-2" style={{ background: 'rgba(248,113,113,0.10)' }}>
              <span>{state.message}</span>
              <button onClick={resetState} className="ml-auto text-red/70 hover:text-red" aria-label="Dismiss">✕</button>
            </div>
          )}
        </aside>

        {/* ─── Results ───────────────────────────────────────────────── */}
        <section data-testid="optimizer-results">
          {state.kind === 'idle' && (
            <EmptyState
              icon="🎚️"
              title="Ready to tune search results"
              hint={sourceCount === 0
                ? 'Run a Finder search first. Search Tuning reorders the systems already in your Finder results; it does not search or create colony build plans.'
                : 'Adjust what matters most, then rerank the current Finder results.'}
            />
          )}

          {state.kind === 'ok' && (
            <ResultsList
              results={state.data.results}
              sourceById={sourceById}
              onOpenDetail={onOpenDetail}
            />
          )}
        </section>
      </div>
    </section>
  );
}

// ─── Subcomponents ─────────────────────────────────────────────────────────

function SourceBadge({ count }: { count: number }) {
  return (
    <div className={[
      'rounded-chunk-sm p-2.5 border font-mono text-[11px]',
      count > 0 ? 'border-cyan/40 bg-cyan/10 text-cyan'
                : 'border-red/40  bg-red/10  text-red',
    ].join(' ')}>
      Source: {count} system{count === 1 ? '' : 's'} from current Finder results
    </div>
  );
}

function WeightSlider({ label, hint, value, onChange, testid }: {
  label: string; hint: string; value: number;
  onChange: (v: number) => void; testid: string;
}) {
  return (
    <div className="space-y-0.5">
      <div className="flex items-center justify-between font-mono text-[11px]">
        <span className="text-silver" title={hint}>{label}</span>
        <span className="text-orange-lt tabular-nums">{value.toFixed(2)}</span>
      </div>
      <input
        type="range"
        min={0} max={1} step={0.01}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        data-testid={testid}
        className="w-full"
      />
    </div>
  );
}

function ResultsList({
  results, sourceById, onOpenDetail,
}: {
  results:    RerankRow[];
  sourceById: Map<number, SystemResult>;
  onOpenDetail?: (id64: number) => void;
}) {
  if (results.length === 0) {
    return (
      <EmptyState
        icon="🤔"
        title="No results in source"
        hint="Search Tuning returned nothing — typically because the current Finder result IDs are not in the ratings table."
      />
    );
  }

  return (
    <ul className="space-y-2">
      {results.map((r, idx) => {
        const src     = sourceById.get(r.id64);
        const delta   = r.original_score != null ? r.reranked_score - r.original_score : null;
        const tier    = ratingTier(r.reranked_score);
        return (
          <li
            key={r.id64}
            data-testid={`optimizer-row-${r.id64}`}
            onClick={onOpenDetail ? () => onOpenDetail(r.id64) : undefined}
            className={[
              'panel-thin p-3 grid grid-cols-[40px_1fr_120px_140px] gap-3 items-center text-sm font-mono',
              onOpenDetail ? 'hover:border-orange/40 cursor-pointer transition-all' : '',
            ].join(' ')}
          >
            <span className="text-silver-dk text-xs tabular-nums text-right">#{idx + 1}</span>
            <div className="min-w-0">
              <div className="text-orange-lt font-bold truncate">
                {src?.name ?? `id ${r.id64}`}
              </div>
              {r.rationale && (
                <div className="text-[11px] text-silver-dk italic truncate">
                  {r.rationale}
                </div>
              )}
            </div>
            <div className="text-[11px] text-silver-dk">
              {r.economy_used ? <span className="text-orange-lt">{r.economy_used}</span> : '—'}
              {r.confidence != null && (
                <span className="ml-2 text-silver-dk">
                  conf {Math.round(r.confidence * 100)}%
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 justify-end">
              <span
                className="px-2.5 py-1 rounded-chunk-sm border text-[11px] font-bold tabular-nums"
                style={{
                  borderColor: tier.fillColor,
                  color: tier.fillColor,
                  background: `linear-gradient(180deg, ${tier.fillColor}33, ${tier.fillColor}11)`,
                  boxShadow: `0 0 12px -4px ${tier.fillColor}66`,
                }}
              >
                {r.reranked_score}
              </span>
              {delta !== null && delta !== 0 && (
                <span
                  data-testid={`optimizer-delta-${r.id64}`}
                  className={[
                    'text-[10px] tabular-nums',
                    delta > 0 ? 'text-green' : 'text-red',
                  ].join(' ')}
                  title={`Original score: ${r.original_score}`}
                >
                  {delta > 0 ? '▲' : '▼'} {Math.abs(delta)}
                </span>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function EmptyState({ icon, title, hint }: {
  icon: string; title: string; hint: string;
}) {
  return (
    <div className="panel-thin text-center py-16 px-4">
      <div className="text-3xl mb-2" aria-hidden>{icon}</div>
      <h3 className="font-display text-orange text-sm tracking-wider mb-1">{title}</h3>
      <p className="text-silver-dk text-xs max-w-sm mx-auto">{hint}</p>
    </div>
  );
}
