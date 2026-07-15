import { useState } from 'react';
import { getDevelopmentScore } from '@/lib/archetypes';
import { ResultCard } from '@/components/ResultCard';
import { SearchForm } from '@/features/search/SearchForm';
import { useSearch } from '@/features/search/useSearch';
import { useClusterSearch } from '@/features/cluster-search/useClusterSearch';
import { ClusterSearchForm } from '@/features/cluster-search/ClusterSearchForm';
import { ClusterResultCard } from '@/features/cluster-search/ClusterResultCard';
import { useWatchlist } from '@/features/watchlist/useWatchlist';
import { usePinned } from '@/features/pinned/usePinned';
import { toPinnedEntry } from '@/features/pinned/pinnedEntry';
import { useCompare } from '@/features/compare/useCompare';
import type { SavedSystemActionState } from './savedSystems';

type FinderMode = 'system' | 'region';

export function FinderView({
  search,
  watchlist,
  pinned,
  compare,
  savedActionStates,
  onToggleSavedForLater,
  onShowOnMap,
  onOpenDetail,
}: {
  search: ReturnType<typeof useSearch>;
  watchlist: ReturnType<typeof useWatchlist>;
  pinned: ReturnType<typeof usePinned>;
  compare: ReturnType<typeof useCompare>;
  savedActionStates: Record<number, SavedSystemActionState>;
  onToggleSavedForLater: (
    id64: number,
    hint: {
      name?: string | null;
      x?: number | null;
      y?: number | null;
      z?: number | null;
      population?: number | null;
      is_colonised?: boolean;
      developmentScore?: number | null;
      economy_suggestion?: string | null;
      primary_archetype?: string | null;
      secondary_archetype?: string | null;
      buildability_score?: number | null;
      purity_score?: number | null;
    },
  ) => Promise<void>;
  onShowOnMap: (id64: number) => void;
  onOpenDetail: (id64: number, options?: { focus?: 'colony-planner' }) => void;
}) {
  const [mode, setMode] = useState<FinderMode>('system');
  const { filters, setFilters, reset, run, state, results } = search;

  const clusterSearch = useClusterSearch();

  const subtitle =
    mode === 'system'
      ? 'Find promising systems. Save them for later or inspect them before starting a plan.'
      : 'Define colony worlds and find regions where the needed economies cluster within 500 LY of each other.';

  return (
    <div className="space-y-4">
      <header data-testid="finder-page-heading" className="max-w-4xl">
        <h1 className="font-display text-2xl tracking-[0.12em] text-text sm:text-3xl">
          Finder
        </h1>
        <p className="mt-1 max-w-2xl text-sm leading-relaxed text-silver sm:text-base">
          {subtitle}
        </p>
      </header>

      {/* Mode toggle */}
      <div className="flex gap-2" data-testid="finder-mode-toggle">
        <button
          type="button"
          onClick={() => setMode('system')}
          className={[
            'font-mono text-[10px] uppercase tracking-[0.14em] px-4 py-1.5 rounded-full border transition-colors',
            mode === 'system'
              ? 'bg-orange/20 text-orange border-orange/40'
              : 'bg-bg3 text-text-dim border-border-bright',
          ].join(' ')}
        >
          System Search
        </button>
        <button
          type="button"
          onClick={() => setMode('region')}
          className={[
            'font-mono text-[10px] uppercase tracking-[0.14em] px-4 py-1.5 rounded-full border transition-colors',
            mode === 'region'
              ? 'bg-orange/20 text-orange border-orange/40'
              : 'bg-bg3 text-text-dim border-border-bright',
          ].join(' ')}
        >
          Region Search
        </button>
      </div>

      {/* System Search mode */}
      {mode === 'system' && (
        <div className="grid lg:grid-cols-[340px_1fr] gap-6">
          <aside className="panel overflow-hidden lg:sticky lg:top-20 lg:self-start lg:max-h-[calc(100vh-11rem)] flex flex-col">
            <div className="overflow-y-auto flex-1 p-1">
              <SearchForm
                filters={filters}
                onChange={setFilters}
                onSubmit={() => void run()}
                onReset={reset}
                loading={state.kind === 'loading'}
              />
            </div>
          </aside>

          <section data-testid="results-panel">
            {state.kind === 'idle' && (
              <EmptyState
                icon="🔭"
                title="Ready to search"
                hint="Adjust the filters on the left, then run a search."
              />
            )}

            {state.kind === 'loading' && (
              <div className="text-text-dim font-mono text-sm py-12 text-center">
                Scanning systems…
              </div>
            )}

            {state.kind === 'err' && (
              <div className="rounded border border-red/50 bg-red/10 p-4 font-mono text-sm text-red">
                <div className="font-bold mb-1">Search failed</div>
                <div className="text-xs">{state.message}</div>
              </div>
            )}

            {state.kind === 'ok' && (
              <>
                <SummaryBar
                  count={state.data.count}
                  total={state.data.total}
                  queriedAt={state.queriedAt}
                />
                {results.length === 0 ? (
                  <EmptyState
                    icon="🔍"
                    title="No systems found"
                    hint="Try expanding the radius or relaxing filters."
                  />
                ) : (
                  <ul className="space-y-2">
                    {results.map((sys, i) => (
                      <li key={sys.id64}>
                        <ResultCard
                          system={sys}
                          index={i}
                          isPinned={pinned.has(sys.id64)}
                          isCompared={compare.has(sys.id64)}
                          isSavedForLater={watchlist.has(sys.id64)}
                          savedActionState={savedActionStates[sys.id64] ?? 'idle'}
                          onToggleSavedForLater={(id) => {
                            void onToggleSavedForLater(id, {
                              name: sys.name,
                              x: sys.coords?.x ?? null,
                              y: sys.coords?.y ?? null,
                              z: sys.coords?.z ?? null,
                              population: sys.population ?? null,
                              is_colonised: !!sys.is_colonised,
                              developmentScore: getDevelopmentScore(sys),
                              economy_suggestion: sys.economy_suggestion ?? null,
                              primary_archetype: sys.primary_archetype ?? null,
                              secondary_archetype: sys.secondary_archetype ?? null,
                              buildability_score: sys.buildability_score ?? null,
                              purity_score: sys.purity_score ?? null,
                            });
                          }}
                          onShowOnMap={onShowOnMap}
                          onPin={() => pinned.toggle(toPinnedEntry(sys))}
                          onCompare={() => compare.toggle(sys)}
                          onOpenDetail={onOpenDetail}
                        />
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </section>
        </div>
      )}

      {/* Region Search mode */}
      {mode === 'region' && (
        <div className="grid lg:grid-cols-[340px_1fr] gap-6">
          <aside className="panel overflow-hidden lg:sticky lg:top-20 lg:self-start lg:max-h-[calc(100vh-11rem)] flex flex-col">
            <div className="overflow-y-auto flex-1 p-1">
              <ClusterSearchForm
                filters={clusterSearch.filters}
                onChange={clusterSearch.setFilters}
                onAddSlot={clusterSearch.addSlot}
                onRemoveSlot={clusterSearch.removeSlot}
                onUpdateSlot={clusterSearch.updateSlot}
                onSubmit={() => void clusterSearch.run()}
                onReset={clusterSearch.reset}
                loading={clusterSearch.state.kind === 'loading'}
              />
            </div>
          </aside>

          <section data-testid="cluster-results-panel">
            {clusterSearch.state.kind === 'idle' && (
              <EmptyState
                icon="🌌"
                title="Find region clusters"
                hint="Define your colony worlds above and run a search to find regions where the needed economies cluster together."
              />
            )}

            {clusterSearch.state.kind === 'loading' && (
              <div className="text-text-dim font-mono text-sm py-12 text-center">
                Searching cluster regions…
              </div>
            )}

            {clusterSearch.state.kind === 'err' && (
              <div className="rounded border border-red/50 bg-red/10 p-4 font-mono text-sm text-red">
                <div className="font-bold mb-1">Cluster search failed</div>
                <div className="text-xs">{clusterSearch.state.message}</div>
              </div>
            )}

            {clusterSearch.state.kind === 'ok' && (
              <>
                <div
                  data-testid="cluster-search-summary"
                  className="premium-toolbar mb-4 flex flex-wrap items-center gap-3 rounded-2xl px-3.5 py-2.5 text-xs font-mono"
                >
                  <span className="text-orange font-bold">{clusterSearch.state.data.count}</span>
                  <span className="text-text-dim">clusters found</span>
                  <span className="flex-1" />
                  <span className="text-text-dim">
                    queried {((Date.now() - clusterSearch.state.queriedAt) / 1000).toFixed(1)}s ago
                  </span>
                </div>
                {clusterSearch.results.length === 0 ? (
                  <EmptyState
                    icon="🔍"
                    title="No clusters found"
                    hint="Try different economy requirements or relax the constraints."
                  />
                ) : (
                  <ul className="space-y-2">
                    {clusterSearch.results.map((cluster) => (
                      <li key={cluster.anchor_id64}>
                        <ClusterResultCard
                          cluster={cluster}
                          requiredEconomies={
                            new Set(clusterSearch.filters.slots.flatMap(s => s.economies.length > 0
                              ? s.economies
                              : []))
                          }
                          onOpenDetail={onOpenDetail}
                          onSystemClick={(id64) => onOpenDetail(id64)}
                        />
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

function SummaryBar({ count, total, queriedAt }: {
  count: number; total: number; queriedAt: number;
}) {
  const elapsed = ((Date.now() - queriedAt) / 1000).toFixed(1);
  return (
    <div
      data-testid="search-summary"
      className="premium-toolbar mb-4 flex flex-wrap items-center gap-3 rounded-2xl px-3.5 py-2.5 text-xs font-mono"
    >
      <span className="text-orange font-bold">{count}</span>
      <span className="text-text-dim">shown</span>
      <span className="text-text-dim">·</span>
      <span className="text-text-dim">{total.toLocaleString()} total</span>
      <span className="flex-1" />
      <span className="text-text-dim">queried {elapsed}s ago</span>
    </div>
  );
}

function EmptyState({ icon, title, hint }: {
  icon: string; title: string; hint: string;
}) {
  return (
    <div className="premium-subpanel text-center px-4 py-16">
      <div className="text-3xl mb-2" aria-hidden>{icon}</div>
      <h3 className="font-mono text-orange-lt text-sm mb-1 tracking-[0.14em] uppercase">{title}</h3>
      <p className="text-text-dim text-xs max-w-sm mx-auto">{hint}</p>
    </div>
  );
}
