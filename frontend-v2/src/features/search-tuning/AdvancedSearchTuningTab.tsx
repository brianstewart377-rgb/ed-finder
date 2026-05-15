import type { RerankRow, SystemResult } from '@/types/api';
import { ratingTier } from '@/lib/format';
import { ECONOMIES, type SearchTuningSourceSnapshot, type UseSearchTuning } from './useSearchTuning';
import {
  buildTunedResultExplanation,
  formatContributionValue,
  getTopContributors,
  getWeakestSignals,
  hasContributionBreakdown,
} from './searchTuningExplanation';
import type { useSearch } from '@/features/search/useSearch';

export interface AdvancedSearchTuningTabProps {
  searchTuning:    UseSearchTuning;
  search:       ReturnType<typeof useSearch>;
  onOpenDetail?: (id64: number) => void;
}

const WEIGHT_LABELS: Array<{ key: keyof UseSearchTuning['weights']; label: string; hint: string }> = [
  { key: 'economy',      label: 'Economy',      hint: 'Economy-score emphasis' },
  { key: 'slots',        label: 'Slots',        hint: 'Available/buildable capacity signal' },
  { key: 'strategic',    label: 'Strategic',    hint: 'Body quality / strategic value signal' },
  { key: 'safety',       label: 'Safety',       hint: 'Orbital safety signal' },
  { key: 'terraforming', label: 'Terraforming', hint: 'Terraforming potential signal' },
  { key: 'diversity',    label: 'Diversity',    hint: 'Body diversity signal' },
];

/**
 * Advanced Search Tuning = re-weight a copy of the current Finder results.
 *
 * This is an advanced Finder tool, not Colony Planner.
 * The "source" is whatever Finder last returned - no separate search here.
 * If Finder has no results, the Run button is disabled with a clear hint.
 */
export function AdvancedSearchTuningTab({ searchTuning, search, onOpenDetail }: AdvancedSearchTuningTabProps) {
  const { weights, setWeight, resetWeights, weightSum, economy, setEconomy, state, run, resetState } = searchTuning;
  const sourceCount = search.results.length;
  const sumOk = Math.abs(weightSum - 1.0) < 0.01;

  // Live Finder data is only a fallback for names. Tuned rank movement uses
  // the source snapshot captured when the tuning run started.
  const sourceById = new Map(search.results.map((s) => [s.id64, s] as const));

  return (
    <section data-testid="search-tuning-tab" className="space-y-5">
      <header className="panel flex flex-wrap items-start justify-between gap-3 px-5 py-4">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-display text-orange tracking-[0.14em] text-lg">Advanced Search Tuning</h2>
            <span className="rounded-chunk-sm border border-cyan/40 bg-cyan/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">
              Uses current Finder results
            </span>
          </div>
          <p className="font-mono text-xs text-silver-dk max-w-4xl">
            Advanced Search Tuning re-prioritises the current Finder results. It does not run a new search, save preferences, or change Colony Planner.
          </p>
          <p className="font-mono text-[11px] text-silver-dk max-w-4xl">
            It reranks a copy of those results into a temporary tuned order; the original Finder results are not mutated.
          </p>
        </div>
      </header>

      <div className="grid lg:grid-cols-[360px_1fr] gap-6">
        {/* ─── Controls ───────────────────────────────────────────────── */}
        <aside className="panel space-y-4 p-5 lg:sticky lg:top-20 lg:self-start lg:max-h-[calc(100vh-11rem)] lg:overflow-y-auto">
          <SourceBadge count={sourceCount} />

          <div>
            <label className="block font-mono text-[10px] text-silver-dk uppercase tracking-[0.18em] mb-1">
              Economy scoring emphasis
            </label>
            <select
              value={economy ?? ''}
              onChange={(e) => setEconomy((e.target.value || null) as never)}
              data-testid="search-tuning-economy"
              className="w-full font-mono text-xs"
            >
              <option value="">Auto (per-row stored suggestion)</option>
              {ECONOMIES.map((eco) => (
                <option key={eco} value={eco}>{eco}</option>
              ))}
            </select>
            <p className="text-[10px] text-silver-dk mt-1">
              This changes which economy score is emphasised during tuning. It does not filter systems out.
              Auto uses the best available stored economy score per system.
            </p>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between font-mono text-[10px] text-silver-dk uppercase tracking-[0.18em]">
              <span>Weights</span>
              <button
                type="button"
                onClick={resetWeights}
                data-testid="search-tuning-weights-reset"
                className="normal-case tracking-normal text-silver-dk hover:text-orange-lt"
              >
                ↺ Reset to v3.1 defaults
              </button>
            </div>
            <p className="text-[10px] text-silver-dk">
              Weights apply only to this tuning run. The backend normalises them for the temporary tuned score.
            </p>
            {WEIGHT_LABELS.map(({ key, label, hint }) => (
              <WeightSlider
                key={key}
                label={label}
                hint={hint}
                value={weights[key]}
                onChange={(v) => setWeight(key, v)}
                testid={`search-tuning-weight-${key}`}
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
            data-testid="search-tuning-run"
            className={[
              'w-full',
              sourceCount === 0 || state.kind === 'busy'
                ? 'btn-metal opacity-60 cursor-not-allowed'
                : 'btn-primary',
            ].join(' ')}
          >
            {state.kind === 'busy' ? 'Building tuned order...' : 'Show tuned order'}
          </button>

          {state.kind === 'err' && (
            <div className="panel-thin border-red/50 p-2 font-mono text-xs text-red flex items-start gap-2" style={{ background: 'rgba(248,113,113,0.10)' }}>
              <span>{state.message}</span>
              <button onClick={resetState} className="ml-auto text-red/70 hover:text-red" aria-label="Dismiss">✕</button>
            </div>
          )}
        </aside>

        {/* ─── Results ───────────────────────────────────────────────── */}
        <section data-testid="search-tuning-results">
          {state.kind === 'idle' && (
            <EmptyState
              icon="🎚️"
              title={sourceCount === 0 ? 'Run a Finder search first.' : 'Ready to tune current Finder results'}
              hint={sourceCount === 0
                ? 'Advanced Search Tuning works on the current Finder results. It cannot tune systems that have not been searched yet.'
                : 'Adjust the scoring emphasis, then build a temporary tuned order from the current Finder results.'}
            />
          )}

          {state.kind === 'busy' && (
            <EmptyState
              icon="🎚️"
              title="Building tuned order..."
              hint="Advanced Search Tuning is re-prioritising a copy of the current Finder results."
            />
          )}

          {state.kind === 'ok' && (
            <ResultsList
              results={state.data.results}
              sourceById={sourceById}
              sourceSnapshot={state.sourceSnapshot}
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
      Uses current Finder results: {count} system{count === 1 ? '' : 's'}
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
  results, sourceById, sourceSnapshot, onOpenDetail,
}: {
  results:    RerankRow[];
  sourceById: Map<number, SystemResult>;
  sourceSnapshot: SearchTuningSourceSnapshot;
  onOpenDetail?: (id64: number) => void;
}) {
  if (results.length === 0) {
    return (
      <EmptyState
        icon="🤔"
        title="No results in source"
        hint="Advanced Search Tuning returned nothing - typically because the current Finder result IDs are not in the ratings table."
      />
    );
  }

  return (
    <ul className="space-y-2">
      {results.map((r, idx) => {
        const snapshot = sourceSnapshot[r.id64];
        const src = sourceById.get(r.id64);
        const displayName = snapshot?.name ?? src?.name ?? `id ${r.id64}`;
        const originalRank = snapshot?.originalRank;
        const tunedRank = idx + 1;
        const movement = describeMovement(originalRank, tunedRank);
        const explanation = buildTunedResultExplanation(r, originalRank, tunedRank);
        const delta   = r.original_score != null ? r.reranked_score - r.original_score : null;
        const tier    = ratingTier(r.reranked_score);
        return (
          <li
            key={r.id64}
            data-testid={`search-tuning-row-${r.id64}`}
            onClick={onOpenDetail ? () => onOpenDetail(r.id64) : undefined}
            className={[
              'panel-thin p-3 grid gap-3 items-center text-sm font-mono md:grid-cols-[150px_minmax(0,1fr)_120px_170px]',
              onOpenDetail ? 'hover:border-orange/40 cursor-pointer transition-all' : '',
            ].join(' ')}
          >
            <div className="text-[11px] text-silver-dk tabular-nums">
              <div className="text-silver">Finder #{originalRank ?? '?'} -&gt; Tuned #{tunedRank}</div>
              <div
                data-testid={`search-tuning-movement-${r.id64}`}
                className={movement.tone}
              >
                {movement.label}
              </div>
            </div>
            <div className="min-w-0">
              <div className="text-orange-lt font-bold truncate">
                {displayName}
              </div>
              {r.rationale && (
                <div className="text-[11px] text-silver-dk italic truncate">
                  <span className="not-italic text-silver">Stored rating rationale:</span> {r.rationale}
                </div>
              )}
              <div className="text-[10px] text-silver-dk">
                The tuned score is temporary for this run. Stored rating rationale comes from the existing rating data.
              </div>
              <TuningExplanation row={r} explanation={explanation} />
              {onOpenDetail && (
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    data-testid={`search-tuning-open-detail-${r.id64}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      onOpenDetail(r.id64);
                    }}
                    className="rounded-chunk-sm border border-orange/45 bg-orange/10 px-2 py-1 text-[10px] font-bold text-orange hover:bg-orange/20"
                  >
                    Open system detail
                  </button>
                  <button
                    type="button"
                    data-testid={`search-tuning-evaluate-${r.id64}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      onOpenDetail(r.id64);
                    }}
                    className="rounded-chunk-sm border border-cyan/35 bg-cyan/10 px-2 py-1 text-[10px] font-bold text-cyan hover:bg-cyan/20"
                  >
                    Evaluate in Colony Planner
                  </button>
                  <span className="text-[10px] text-silver-dk">
                    Opens system detail; it does not run Simulation Preview or generate builds.
                  </span>
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
              <div className="text-right text-[10px] leading-tight text-silver-dk">
                <div>Temporary tuned score</div>
                {r.original_score != null && <div>Original stored score {r.original_score}</div>}
              </div>
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
                  data-testid={`search-tuning-delta-${r.id64}`}
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

function TuningExplanation({ row, explanation }: { row: RerankRow; explanation: string[] }) {
  const hasBreakdown = hasContributionBreakdown(row);
  const helped = getTopContributors(row);
  const weakerSignals = getWeakestSignals(row);

  return (
    <div className="mt-2 rounded-chunk-sm border border-border/70 bg-bg2/50 p-2 text-[10px] text-silver-dk">
      <div className="mb-1 font-bold uppercase tracking-[0.14em] text-silver">
        Why this tuned position?
      </div>
      <div className="space-y-1">
        {explanation.map((line) => (
          <p key={line}>{line}</p>
        ))}
      </div>
      {hasBreakdown ? (
        <div className="mt-2 grid gap-1 sm:grid-cols-2">
          <ContributionGroup title="Helped" items={helped} tone="text-green" />
          <ContributionGroup title="Weaker signals" items={weakerSignals} tone="text-gold" />
        </div>
      ) : (
        <p className="mt-2 text-gold">Contribution breakdown unavailable for this row.</p>
      )}
      {row.confidence != null && (
        <p className="mt-1 text-silver-dk">
          Confidence adjustment: {Math.round(row.confidence * 100)}%.
        </p>
      )}
    </div>
  );
}

function ContributionGroup({
  title,
  items,
  tone,
}: {
  title: string;
  items: ReturnType<typeof getTopContributors>;
  tone: string;
}) {
  return (
    <div>
      <div className="uppercase tracking-[0.12em] text-silver-dk">{title}</div>
      <div className="mt-1 flex flex-wrap gap-1">
        {items.map((item) => (
          <span
            key={`${title}-${item.key}`}
            className={`rounded border border-current/30 px-1.5 py-0.5 ${tone}`}
          >
            {item.label} {formatContributionValue(item.value)}
          </span>
        ))}
      </div>
    </div>
  );
}

function describeMovement(originalRank: number | undefined, tunedRank: number) {
  if (originalRank == null) {
    return { label: 'Finder rank unavailable', tone: 'text-silver-dk' };
  }
  const places = originalRank - tunedRank;
  if (places > 0) {
    return { label: `Moved up ${places} place${places === 1 ? '' : 's'}`, tone: 'text-green' };
  }
  if (places < 0) {
    const down = Math.abs(places);
    return { label: `Moved down ${down} place${down === 1 ? '' : 's'}`, tone: 'text-red' };
  }
  return { label: 'Unchanged', tone: 'text-silver-dk' };
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
