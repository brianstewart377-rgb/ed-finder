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
import { EmptyState } from '@/components/ui/EmptyState';
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
  const [filterWorkspaceOpen, setFilterWorkspaceOpen] = useState(false);
  const { filters, setFilters, reset, run, state, results } = search;
  const clusterSearch = useClusterSearch();

  const subtitle = mode === 'system'
    ? 'Find promising systems. Save them for later or inspect them before starting a plan.'
    : 'Find regions where the economies your colony needs cluster within 500 LY.';

  return (
    <section className="finder-console">
      <header data-testid="finder-page-heading" className="finder-console__header">
        <div className="finder-console__title">
          <h1>System <em>Finder</em></h1>
          <p>{subtitle}</p>
        </div>
        <div className="finder-console__mode" data-testid="finder-mode-toggle">
          <span>Search mode</span>
          <div>
            <button
              type="button"
              onClick={() => setMode('system')}
              data-active={mode === 'system' ? 'true' : 'false'}
            >
              Systems
            </button>
            <button
              type="button"
              onClick={() => setMode('region')}
              data-active={mode === 'region' ? 'true' : 'false'}
            >
              Regions
            </button>
          </div>
        </div>
      </header>

      {mode === 'system' && (
        <div
          className="finder-workspace-grid"
          data-filters-open={filterWorkspaceOpen ? 'true' : 'false'}
        >
          <aside className="finder-workspace-grid__filters" aria-label="Finder filters">
            <SearchForm
              filters={filters}
              onChange={setFilters}
              onSubmit={() => void run()}
              onReset={reset}
              loading={state.kind === 'loading'}
              onWorkspaceChange={setFilterWorkspaceOpen}
            />
          </aside>

          <section className="finder-results-stage" data-testid="results-panel">
            <div className="finder-results-stage__masthead">
              <div>
                <span>Search results</span>
                <strong>
                  {state.kind === 'ok'
                    ? `${state.data.count} matches`
                    : state.kind === 'loading'
                      ? 'Searching systems…'
                      : state.kind === 'err'
                        ? 'Search failed'
                        : 'Ready to search'}
                </strong>
              </div>
              <small data-testid="finder-search-context">
                Origin: {filters.refName} · {filters.galaxyWide
                  ? 'Range: entire galaxy'
                  : `Range: ${filters.minDistance}–${filters.maxDistance} LY`}
              </small>
            </div>

            {state.kind === 'idle' && (
              <div className="finder-results-idle">
                <div className="finder-results-idle__orbit" aria-hidden>
                  <span />
                  <span />
                  <span />
                </div>
                <div>
                  <span>Ready to search</span>
                  <h2>Search the galaxy,<br /><em>find your future.</em></h2>
                  <span className="sr-only">Adjust the filters on the left, then run a search.</span>
                  <p>
                    Open a filter module to shape the search. Results appear here without
                    replacing the controls or sending you down a long sidebar.
                  </p>
                </div>
              </div>
            )}

            {state.kind === 'loading' && (
              <div className="finder-results-loading">
                <span aria-hidden />
                Scanning systems…
              </div>
            )}

            {state.kind === 'err' && (
              <div className="finder-results-error">
                <strong>Search failed</strong>
                <span>{state.message}</span>
              </div>
            )}

            {state.kind === 'ok' && (
              <div className="finder-results-list">
                <SummaryBar
                  count={state.data.count}
                  total={state.data.total}
                  queriedAt={state.queriedAt}
                />
                {results.length === 0 ? (
                  <EmptyState
                    icon="⌁"
                    title="No systems found"
                    description="Try expanding the radius or relaxing filters."
                  />
                ) : (
                  <ul className="space-y-2">
                    {results.map((system, index) => (
                      <li key={system.id64}>
                        <ResultCard
                          system={system}
                          index={index}
                          isPinned={pinned.has(system.id64)}
                          isCompared={compare.has(system.id64)}
                          isSavedForLater={watchlist.has(system.id64)}
                          savedActionState={savedActionStates[system.id64] ?? 'idle'}
                          onToggleSavedForLater={(id) => {
                            void onToggleSavedForLater(id, {
                              name: system.name,
                              x: system.coords?.x ?? null,
                              y: system.coords?.y ?? null,
                              z: system.coords?.z ?? null,
                              population: system.population ?? null,
                              is_colonised: !!system.is_colonised,
                              developmentScore: getDevelopmentScore(system),
                              economy_suggestion: system.economy_suggestion ?? null,
                              primary_archetype: system.primary_archetype ?? null,
                              secondary_archetype: system.secondary_archetype ?? null,
                              buildability_score: system.buildability_score ?? null,
                              purity_score: system.purity_score ?? null,
                            });
                          }}
                          onShowOnMap={onShowOnMap}
                          onPin={() => pinned.toggle(toPinnedEntry(system))}
                          onCompare={() => compare.toggle(system)}
                          onOpenDetail={onOpenDetail}
                        />
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </section>
        </div>
      )}

      {mode === 'region' && (
        <div className="finder-region-workspace">
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
                icon="◎"
                title="Find region clusters"
                description="Choose the economies your colony needs, then search for regions where matching systems cluster."
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
                    icon="⌁"
                    title="No clusters found"
                    description="Try different economy requirements or relax the constraints."
                  />
                ) : (
                  <ul className="space-y-2">
                    {clusterSearch.results.map((cluster) => (
                      <li key={cluster.anchor_id64}>
                        <ClusterResultCard
                          cluster={cluster}
                          requiredEconomies={
                            new Set(clusterSearch.filters.slots.flatMap((slot) => slot.economies.length > 0
                              ? slot.economies
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
    </section>
  );
}

function SummaryBar({
  count,
  total,
  queriedAt,
}: {
  count: number;
  total: number;
  queriedAt: number;
}) {
  const elapsed = ((Date.now() - queriedAt) / 1000).toFixed(1);
  return (
    <div data-testid="search-summary" className="finder-search-summary">
      <strong>{count}</strong>
      <span>shown</span>
      <i />
      <span>{total.toLocaleString()} total</span>
      <small>queried {elapsed}s ago</small>
    </div>
  );
}
