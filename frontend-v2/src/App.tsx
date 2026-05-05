import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { ResultCard } from '@/components/ResultCard';
import { SearchForm } from '@/features/search/SearchForm';
import { useSearch } from '@/features/search/useSearch';
import './index.css';

/**
 * v2 root view — sidebar form + results panel.
 *
 * Auto-runs the default search on first paint so first-time visitors don't
 * see an empty screen, then the form drives every subsequent search.
 */
export default function App() {
  const { filters, setFilters, reset, run, state, results } = useSearch();
  const [health, setHealth] = useState<string>('checking…');

  // First-paint: kick a health probe + the default Sol-radius search.
  useEffect(() => {
    api.health()
      .then((h) => setHealth(`${h.status} · ${h.database} · v${h.version}`))
      .catch((e: Error) => setHealth(`unreachable: ${e.message}`));
    void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <main className="min-h-screen px-4 py-6 sm:px-8 sm:py-10 max-w-7xl mx-auto">
      <header className="mb-8 space-y-2">
        <h1 className="font-mono text-3xl sm:text-4xl text-orange tracking-wider">
          ED:FINDER <span className="text-text-dim text-base">v2</span>
        </h1>
        <p className="text-text-dim text-sm leading-relaxed max-w-2xl">
          Vite + React + TypeScript. Vanilla v1 lives at{' '}
          <a href="/" className="text-cyan underline">/</a> and is unchanged.
        </p>
        <p className="font-mono text-[11px] text-text-dim">
          API: <span className="text-green">{health}</span>
        </p>
      </header>

      <div className="grid lg:grid-cols-[320px_1fr] gap-6">
        {/* ── Left rail: search form ─────────────────────────────────── */}
        <aside className="lg:sticky lg:top-6 lg:self-start lg:max-h-[calc(100vh-3rem)] lg:overflow-auto">
          <SearchForm
            filters={filters}
            onChange={setFilters}
            onSubmit={() => void run()}
            onReset={reset}
            loading={state.kind === 'loading'}
          />
        </aside>

        {/* ── Right rail: results ────────────────────────────────────── */}
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
                        onPin={(id) => console.log('pin', id)}
                        onWatch={(id) => console.log('watch', id)}
                        onShowOnMap={(id) => console.log('map', id)}
                      />
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </section>
      </div>

      <footer className="mt-16 text-center text-[11px] font-mono text-text-dim">
        Vite {import.meta.env.MODE} build · proof of concept · not yet production
      </footer>
    </main>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Local subcomponents
// ─────────────────────────────────────────────────────────────────────────

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
