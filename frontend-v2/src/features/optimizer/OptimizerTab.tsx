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
  { key: 'economy',      label: 'Economy',      hint: 'Per-economy match (Tourism, HighTech, …)' },
  { key: 'slots',        label: 'Slots',        hint: 'Build-slot capacity from body counts' },
  { key: 'strategic',    label: 'Strategic',    hint: 'Body-quality / system value' },
  { key: 'safety',       label: 'Safety',       hint: 'Orbital safety (no neutron / black hole)' },
  { key: 'terraforming', label: 'Terraforming', hint: 'Terraforming potential' },
  { key: 'diversity',    label: 'Diversity',    hint: 'Body-type diversity' },
];

/**
 * Optimizer = re-weight the score for the current Finder results.
 *
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
    <section data-testid="optimizer-tab" className="space-y-6">
      <header className="flex flex-wrap items-center gap-3">
        <h2 className="font-mono text-orange tracking-wider text-lg">🎚️ Optimizer</h2>
        <span className="font-mono text-xs text-text-dim">
          re-weight rating dimensions and rerank current Finder results
        </span>
      </header>

      <div className="grid lg:grid-cols-[360px_1fr] gap-6">
        {/* ─── Controls ───────────────────────────────────────────────── */}
        <aside className="space-y-4 rounded border border-border p-4 lg:sticky lg:top-20 lg:self-start">
          <SourceBadge count={sourceCount} />

          <div>
            <label className="block font-mono text-[11px] text-text-dim uppercase tracking-wider mb-1">
              Economy preference
            </label>
            <select
              value={economy ?? ''}
              onChange={(e) => setEconomy((e.target.value || null) as never)}
              data-testid="optimizer-economy"
              className="w-full bg-bg4 border border-border rounded px-2 py-1 text-text font-mono text-xs"
            >
              <option value="">Auto (per-row stored suggestion)</option>
              {ECONOMIES.map((eco) => (
                <option key={eco} value={eco}>{eco}</option>
              ))}
            </select>
            <p className="text-[10px] text-text-dim mt-1">
              Drives the &ldquo;Economy&rdquo; weight column for every row.
            </p>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between font-mono text-[11px] text-text-dim uppercase tracking-wider">
              <span>Weights</span>
              <button
                type="button"
                onClick={resetWeights}
                data-testid="optimizer-weights-reset"
                className="normal-case tracking-normal text-text-dim hover:text-orange"
              >
                ↺ Reset to v3.1 defaults
              </button>
            </div>
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
              'rounded border p-2 font-mono text-[11px] flex items-center justify-between',
              sumOk ? 'border-green/40 bg-green/5 text-green'
                    : 'border-gold/40  bg-gold/5  text-gold',
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
              'w-full px-3 py-2 rounded font-mono text-sm border transition-colors',
              sourceCount === 0 || state.kind === 'busy'
                ? 'bg-bg4 border-border text-text-dim opacity-60 cursor-not-allowed'
                : 'bg-orange text-bg1 border-orange hover:bg-orange-dk',
            ].join(' ')}
          >
            {state.kind === 'busy' ? '⟳ Reranking…' : '▶ Rerank'}
          </button>

          {state.kind === 'err' && (
            <div className="rounded border border-red/50 bg-red/10 p-2 font-mono text-xs text-red flex items-start gap-2">
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
              title="Ready to rerank"
              hint={sourceCount === 0
                ? 'Run a Finder search first to populate the source list.'
                : `Tweak the weights and hit Rerank to reorder ${sourceCount} systems.`}
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
      'rounded p-2 border font-mono text-[11px]',
      count > 0 ? 'border-cyan/40 bg-cyan/5 text-cyan'
                : 'border-red/40  bg-red/5  text-red',
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
        <span className="text-text" title={hint}>{label}</span>
        <span className="text-orange tabular-nums">{value.toFixed(2)}</span>
      </div>
      <input
        type="range"
        min={0} max={1} step={0.01}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        data-testid={testid}
        className="w-full accent-orange"
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
        hint="The rerank service returned nothing — typically because the source IDs aren't in the ratings table."
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
              'rounded border border-border p-3 grid grid-cols-[40px_1fr_120px_140px] gap-3 items-center text-sm font-mono',
              onOpenDetail ? 'hover:bg-bg3/40 cursor-pointer transition-colors' : '',
            ].join(' ')}
          >
            <span className="text-text-dim text-xs tabular-nums text-right">#{idx + 1}</span>
            <div className="min-w-0">
              <div className="text-orange font-bold truncate">
                {src?.name ?? `id ${r.id64}`}
              </div>
              {r.rationale && (
                <div className="text-[11px] text-text-dim italic truncate">
                  {r.rationale}
                </div>
              )}
            </div>
            <div className="text-[11px] text-text-dim">
              {r.economy_used ? <span className="text-orange">{r.economy_used}</span> : '—'}
              {r.confidence != null && (
                <span className="ml-2 text-text-dim">
                  conf {Math.round(r.confidence * 100)}%
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 justify-end">
              <span
                className="px-2 py-0.5 rounded border text-[11px] font-bold tabular-nums"
                style={{ borderColor: tier.fillColor, color: tier.fillColor, backgroundColor: `${tier.fillColor}22` }}
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
    <div className="text-center py-16 px-4 rounded border border-dashed border-border">
      <div className="text-3xl mb-2" aria-hidden>{icon}</div>
      <h3 className="font-mono text-orange text-sm mb-1">{title}</h3>
      <p className="text-text-dim text-xs max-w-sm mx-auto">{hint}</p>
    </div>
  );
}
