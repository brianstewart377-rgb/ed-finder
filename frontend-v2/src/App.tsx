import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { ResultCard } from '@/components/ResultCard';
import { NavBar } from '@/components/NavBar';
import { SearchForm } from '@/features/search/SearchForm';
import { useSearch } from '@/features/search/useSearch';
import { useWatchlist } from '@/features/watchlist/useWatchlist';
import { WatchlistTab } from '@/features/watchlist/WatchlistTab';
import { usePinned } from '@/features/pinned/usePinned';
import { PinnedTab, toPinnedEntry } from '@/features/pinned/PinnedTab';
import { MapTab } from '@/features/map/MapTab';
import { useHashRoute } from '@/hooks/useHashRoute';
import './index.css';

/**
 * v2 root: NavBar + tab content. State (search filters, watchlist, pins)
 * lives at this level so tabs can share data — switching from Finder → Map
 * should NOT lose the current results.
 */
export default function App() {
  const [route, navigate] = useHashRoute();
  const search    = useSearch();
  const watchlist = useWatchlist();
  const pinned    = usePinned();
  const [health, setHealth] = useState<string>('checking…');

  // First-paint: health + default search.
  useEffect(() => {
    api.health()
      .then((h) => setHealth(`${h.status} · v${h.version}`))
      .catch((e: Error) => setHealth(`unreachable: ${e.message}`));
    void search.run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <main className="min-h-screen px-4 py-6 sm:px-8 sm:py-10 max-w-7xl mx-auto">
      <NavBar
        current={route}
        onNavigate={navigate}
        watchlistCount={watchlist.entries.length}
        pinnedCount={pinned.entries.length}
        health={health}
      />

      {route === 'finder' && (
        <FinderView
          search={search}
          watchlist={watchlist}
          pinned={pinned}
          onShowOnMap={() => navigate('map')}
        />
      )}

      {route === 'watchlist' && (
        <WatchlistTab
          entries={watchlist.entries}
          loading={watchlist.loading}
          error={watchlist.error}
          onRefresh={watchlist.refresh}
          onRemove={watchlist.remove}
          onShowOnMap={() => navigate('map')}
        />
      )}

      {route === 'pinned' && (
        <PinnedTab
          pinned={pinned}
          onShowOnMap={() => navigate('map')}
        />
      )}

      {route === 'map' && (
        <MapTab
          systems={search.results}
          reference={{
            name: search.filters.refName,
            x:    search.filters.refCoords.x,
            z:    search.filters.refCoords.z,
          }}
        />
      )}

      <footer className="mt-16 text-center text-[11px] font-mono text-text-dim">
        Vite {import.meta.env.MODE} build · proof of concept · not yet production
      </footer>
    </main>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Finder tab — left rail form + right rail results
// ─────────────────────────────────────────────────────────────────────────

function FinderView({
  search, watchlist, pinned, onShowOnMap,
}: {
  search:    ReturnType<typeof useSearch>;
  watchlist: ReturnType<typeof useWatchlist>;
  pinned:    ReturnType<typeof usePinned>;
  onShowOnMap: () => void;
}) {
  const { filters, setFilters, reset, run, state, results } = search;

  return (
    <div className="grid lg:grid-cols-[320px_1fr] gap-6">
      <aside className="lg:sticky lg:top-20 lg:self-start lg:max-h-[calc(100vh-6rem)] lg:overflow-auto">
        <SearchForm
          filters={filters}
          onChange={setFilters}
          onSubmit={() => void run()}
          onReset={reset}
          loading={state.kind === 'loading'}
        />
      </aside>

      <section data-testid="results-panel">
        {state.kind === 'idle' && (
          <EmptyState
            icon="🔭"
            title="Ready to search"
            hint="Adjust the filters on the left and hit SEARCH."
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
                      onWatch={(id) => void watchlist.add(id, {
                        name:       sys.name,
                        x:          sys.coords?.x ?? 0,
                        y:          sys.coords?.y ?? 0,
                        z:          sys.coords?.z ?? 0,
                        population: sys.population,
                        is_colonised: !!sys.is_colonised,
                        score:      sys._rating?.score ?? null,
                      })}
                      onShowOnMap={onShowOnMap}
                      onPin={() => pinned.toggle(toPinnedEntry(sys))}
                    />
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </section>
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
      className="mb-4 flex flex-wrap items-center gap-3 px-3 py-2 rounded border border-border bg-bg3/40 text-xs font-mono"
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
    <div className="text-center py-16 px-4 rounded border border-dashed border-border">
      <div className="text-3xl mb-2" aria-hidden>{icon}</div>
      <h3 className="font-mono text-orange text-sm mb-1">{title}</h3>
      <p className="text-text-dim text-xs max-w-sm mx-auto">{hint}</p>
    </div>
  );
}
