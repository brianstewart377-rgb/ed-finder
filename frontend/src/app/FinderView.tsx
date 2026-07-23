import { useEffect, useRef, useState } from 'react';
import { Filter, PanelLeftClose, PanelLeftOpen, X } from 'lucide-react';
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
const DRAWER_FOCUSABLE = [
  'button:not([disabled])',
  'a[href]',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

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
  // Desktop: the filter rail can be collapsed to give results more room.
  const [railCollapsed, setRailCollapsed] = useState(false);
  // Mobile / tablet: filters live in an off-canvas drawer instead of a long
  // permanent column stacked above the results.
  const [drawerOpen, setDrawerOpen] = useState(false);
  const drawerRef = useRef<HTMLDivElement | null>(null);
  const drawerToggleRef = useRef<HTMLButtonElement | null>(null);
  const drawerCloseRef = useRef<HTMLButtonElement | null>(null);

  const { filters, setFilters, reset, run, state, results } = search;
  const clusterSearch = useClusterSearch();

  const activeState = mode === 'system' ? state : clusterSearch.state;

  useEffect(() => {
    if (!drawerOpen) return;
    const previousBodyOverflow = document.body.style.overflow;
    const drawerToggle = drawerToggleRef.current;
    document.body.style.overflow = 'hidden';
    drawerCloseRef.current?.focus();

    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        setDrawerOpen(false);
        return;
      }
      if (event.key !== 'Tab') return;

      const focusable = Array.from(
        drawerRef.current?.querySelectorAll<HTMLElement>(DRAWER_FOCUSABLE) ?? [],
      ).filter((element) => !element.hasAttribute('disabled'));
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = previousBodyOverflow;
      drawerToggle?.focus();
    };
  }, [drawerOpen]);

  const subtitle =
    mode === 'system'
      ? 'Find promising systems. Save them for later or inspect them before starting a plan.'
      : 'Define colony worlds and find regions where the needed economies cluster within 500 LY of each other.';

  const statusChip = (() => {
    if (activeState.kind === 'loading') return { tone: 'loading' as const, text: 'Searching…' };
    if (activeState.kind === 'err') return { tone: 'error' as const, text: 'Search failed' };
    if (activeState.kind === 'ok') {
      const count = activeState.data.count;
      return { tone: 'ok' as const, text: `${count} ${mode === 'system' ? 'shown' : 'clusters'}` };
    }
    return { tone: 'idle' as const, text: 'No search yet' };
  })();

  const formPanel = mode === 'system' ? (
    <SearchForm
      filters={filters}
      onChange={setFilters}
      onSubmit={() => { void run(); setDrawerOpen(false); }}
      onReset={reset}
      loading={state.kind === 'loading'}
    />
  ) : (
    <ClusterSearchForm
      filters={clusterSearch.filters}
      onChange={clusterSearch.setFilters}
      onAddSlot={clusterSearch.addSlot}
      onRemoveSlot={clusterSearch.removeSlot}
      onUpdateSlot={clusterSearch.updateSlot}
      onSubmit={() => { void clusterSearch.run(); setDrawerOpen(false); }}
      onReset={clusterSearch.reset}
      loading={clusterSearch.state.kind === 'loading'}
    />
  );

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

      {/* Context toolbar — mode toggle, filter controls, and a live status
       * chip that keeps result count / loading / error visible at all times. */}
      <div className="panel flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2 sm:px-4">
        <div className="flex gap-2" data-testid="finder-mode-toggle">
          <button
            type="button"
            onClick={() => setMode('system')}
            aria-pressed={mode === 'system'}
            className={[
              'rounded-full border px-4 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan/70',
              mode === 'system'
                ? 'border-cyan/40 bg-cyan/20 text-cyan'
                : 'border-border-bright bg-bg3 text-text-dim hover:text-silver',
            ].join(' ')}
          >
            System Search
          </button>
          <button
            type="button"
            onClick={() => setMode('region')}
            aria-pressed={mode === 'region'}
            className={[
              'rounded-full border px-4 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan/70',
              mode === 'region'
                ? 'border-cyan/40 bg-cyan/20 text-cyan'
                : 'border-border-bright bg-bg3 text-text-dim hover:text-silver',
            ].join(' ')}
          >
            Region Search
          </button>
        </div>

        <span className="hidden flex-1 sm:block" />

        <StatusChip tone={statusChip.tone} text={statusChip.text} />

        {/* Mobile: open the filter drawer */}
        <button
          ref={drawerToggleRef}
          type="button"
          data-testid="finder-open-filters"
          onClick={() => setDrawerOpen(true)}
          aria-controls="finder-search-filter-dialog"
          aria-expanded={drawerOpen}
          className="inline-flex items-center gap-1.5 rounded-chunk-sm border border-border bg-bg3 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-silver transition-colors hover:border-cyan/50 hover:text-cyan focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan/70 lg:hidden"
        >
          <Filter size={12} aria-hidden />
          Filters
        </button>

        {/* Desktop: collapse / expand the persistent rail */}
        <button
          type="button"
          data-testid="finder-toggle-rail"
          onClick={() => setRailCollapsed((v) => !v)}
          aria-pressed={!railCollapsed}
          className="hidden items-center gap-1.5 rounded-chunk-sm border border-border bg-bg3 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-silver transition-colors hover:border-cyan/50 hover:text-cyan focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan/70 lg:inline-flex"
        >
          {railCollapsed ? <PanelLeftOpen size={12} aria-hidden /> : <PanelLeftClose size={12} aria-hidden />}
          {railCollapsed ? 'Show filters' : 'Hide filters'}
        </button>
      </div>

      <div
        className={[
          'grid gap-6',
          railCollapsed ? 'lg:grid-cols-1' : 'lg:grid-cols-[340px_1fr]',
        ].join(' ')}
      >
        {/* Desktop persistent rail (collapsible) */}
        {!railCollapsed && (
          <aside className="panel hidden overflow-hidden lg:sticky lg:top-24 lg:flex lg:max-h-[calc(100vh-11rem)] lg:flex-col lg:self-start">
            <div className="flex-1 overflow-y-auto p-1">
              {formPanel}
            </div>
          </aside>
        )}

        {mode === 'system' ? (
          <section data-testid="results-panel">
            {state.kind === 'idle' && (
              <div className="flex min-h-[55vh] items-center justify-center">
                <EmptyState
                  icon="🔭"
                  title="Ready to search"
                  description="Adjust the filters on the left, then run a search."
                />
              </div>
            )}

            {state.kind === 'loading' && (
              <div className="py-12 text-center font-mono text-sm text-text-dim">
                Scanning systems…
              </div>
            )}

            {state.kind === 'err' && (
              <div className="rounded border border-red/50 bg-red/10 p-4 font-mono text-sm text-red">
                <div className="mb-1 font-bold">Search failed</div>
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
                    description="Try expanding the radius or relaxing filters."
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
        ) : (
          <section data-testid="cluster-results-panel">
            {clusterSearch.state.kind === 'idle' && (
              <div className="flex min-h-[55vh] items-center justify-center">
                <EmptyState
                  icon="🌌"
                  title="Find region clusters"
                  description="Define your colony worlds above and run a search to find regions where the needed economies cluster together."
                />
              </div>
            )}

            {clusterSearch.state.kind === 'loading' && (
              <div className="py-12 text-center font-mono text-sm text-text-dim">
                Searching cluster regions…
              </div>
            )}

            {clusterSearch.state.kind === 'err' && (
              <div className="rounded border border-red/50 bg-red/10 p-4 font-mono text-sm text-red">
                <div className="mb-1 font-bold">Cluster search failed</div>
                <div className="text-xs">{clusterSearch.state.message}</div>
              </div>
            )}

            {clusterSearch.state.kind === 'ok' && (
              <>
                <div
                  data-testid="cluster-search-summary"
                  className="premium-toolbar mb-4 flex flex-wrap items-center gap-3 rounded-2xl px-3.5 py-2.5 font-mono text-xs"
                >
                  <span className="font-bold text-cyan">{clusterSearch.state.data.count}</span>
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
                    description="Try different economy requirements or relax the constraints."
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
        )}
      </div>

      {/* ── Mobile filter drawer ─────────────────────────────────────── */}
      {drawerOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" data-testid="finder-filter-drawer">
          <button
            type="button"
            aria-hidden="true"
            tabIndex={-1}
            onClick={() => setDrawerOpen(false)}
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
          />
          <div
            ref={drawerRef}
            id="finder-search-filter-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="finder-search-filter-title"
            className="absolute inset-y-0 left-0 flex w-[88%] max-w-sm flex-col border-r border-border bg-bg2 shadow-metal"
          >
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <span id="finder-search-filter-title" className="font-mono text-[11px] uppercase tracking-[0.14em] text-cyan">
                {mode === 'system' ? 'System filters' : 'Region filters'}
              </span>
              <button
                ref={drawerCloseRef}
                type="button"
                onClick={() => setDrawerOpen(false)}
                aria-label="Close filters"
                className="rounded-full p-1 text-silver-dk transition-colors hover:bg-white/10 hover:text-cyan focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan/70"
              >
                <X size={16} aria-hidden />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-3">
              {formPanel}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function StatusChip({ tone, text }: { tone: 'idle' | 'loading' | 'ok' | 'error'; text: string }) {
  const dot =
    tone === 'ok' ? 'bg-cyan' :
    tone === 'loading' ? 'bg-gold animate-pulse' :
    tone === 'error' ? 'bg-red' :
    'bg-silver-2';
  return (
    <span
      data-testid="finder-status-chip"
      className="inline-flex items-center gap-2 rounded-full border border-border bg-bg3/70 px-3 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-silver"
    >
      <span className={['h-2 w-2 rounded-full', dot].join(' ')} aria-hidden />
      {text}
    </span>
  );
}

function SummaryBar({ count, total, queriedAt }: {
  count: number; total: number; queriedAt: number;
}) {
  const elapsed = ((Date.now() - queriedAt) / 1000).toFixed(1);
  return (
    <div
      data-testid="search-summary"
      className="premium-toolbar mb-4 flex flex-wrap items-center gap-3 rounded-2xl px-3.5 py-2.5 font-mono text-xs"
    >
      <span className="font-bold text-cyan">{count}</span>
      <span className="text-text-dim">shown</span>
      <span className="text-text-dim">·</span>
      <span className="text-text-dim">{total.toLocaleString()} total</span>
      <span className="flex-1" />
      <span className="text-text-dim">queried {elapsed}s ago</span>
    </div>
  );
}
