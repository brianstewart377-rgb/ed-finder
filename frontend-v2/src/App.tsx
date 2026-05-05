import { useEffect, useMemo, useState } from 'react';
import { api, type LocalSearchBody } from '@/lib/api';
import type { SearchResponse, SystemResult } from '@/types/api';
import { ResultCard } from '@/components/ResultCard';

/** Demo / proof-of-concept page.
 *
 * Hard-codes a Sol-centric search so the entire vertical slice (API client →
 * types → component → render) can be validated end-to-end without any
 * filtering UI. Once the search-form is ported this page becomes the real
 * /v2/ home; until then it's the only screen.
 */
const DEMO_QUERY: LocalSearchBody = {
  reference_coords: { x: 0, y: 0, z: 0 },
  filters: {
    distance:   { min: 0, max: 50 },
    population: { comparison: '>', value: 0 },
  },
  sort_by:     'rating',
  size:        20,
  from:        0,
  galaxy_wide: false,
};

type LoadState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ok'; data: SearchResponse }
  | { kind: 'err'; message: string };

export default function App() {
  const [state, setState] = useState<LoadState>({ kind: 'idle' });
  const [health, setHealth] = useState<string>('checking…');

  useEffect(() => {
    let cancelled = false;
    setState({ kind: 'loading' });

    void Promise.allSettled([
      api.health(),
      api.localSearch(DEMO_QUERY),
    ]).then(([h, s]) => {
      if (cancelled) return;
      setHealth(
        h.status === 'fulfilled'
          ? `${h.value.status} · ${h.value.database} · v${h.value.version}`
          : `unreachable: ${(h.reason as Error).message}`,
      );
      if (s.status === 'fulfilled') {
        setState({ kind: 'ok', data: s.value });
      } else {
        setState({ kind: 'err', message: (s.reason as Error).message });
      }
    });

    return () => { cancelled = true; };
  }, []);

  // Keep the result list stable across renders (avoids React key churn).
  const results: SystemResult[] = useMemo(() => {
    return state.kind === 'ok' ? state.data.results : [];
  }, [state]);

  return (
    <main className="min-h-screen px-4 py-6 sm:px-8 sm:py-10 max-w-5xl mx-auto">
      <header className="mb-8 space-y-2">
        <h1 className="font-mono text-3xl sm:text-4xl text-orange tracking-wider">
          ED:FINDER <span className="text-text-dim text-base">v2</span>
        </h1>
        <p className="text-text-dim text-sm leading-relaxed max-w-2xl">
          Vite + React + TypeScript proof-of-concept. Renders the result-card
          vertical slice using live data from <code className="font-mono text-orange">/api/local/search</code>.
          The vanilla app at <a href="/" className="text-cyan underline">/</a> is unchanged.
        </p>
        <p className="font-mono text-[11px] text-text-dim">
          API: <span className="text-green">{health}</span>
        </p>
      </header>

      {state.kind === 'loading' && (
        <div className="text-text-dim font-mono text-sm py-12 text-center">
          Loading systems within 50 LY of Sol…
        </div>
      )}

      {state.kind === 'err' && (
        <div className="rounded border border-red/50 bg-red/10 p-4 font-mono text-sm text-red">
          <div className="font-bold mb-1">API error</div>
          <div className="text-xs">{state.message}</div>
          <p className="mt-3 text-text-dim text-xs leading-relaxed">
            If you're running this locally, set <code className="text-orange">VITE_DEV_API_TARGET</code>
            {' '}to your dev API URL, e.g. <code className="text-orange">VITE_DEV_API_TARGET=http://localhost:8000 yarn dev</code>.
          </p>
        </div>
      )}

      {state.kind === 'ok' && (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-3 px-3 py-2 rounded border border-border bg-bg3/40 text-xs font-mono">
            <span className="text-orange font-bold">{state.data.count}</span>
            <span className="text-text-dim">shown</span>
            <span className="text-text-dim">·</span>
            <span className="text-text-dim">{state.data.total.toLocaleString()} total found</span>
            <span className="flex-1" />
            <span className="text-text-dim">demo: 50 LY around Sol, populated only</span>
          </div>
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
        </>
      )}

      <footer className="mt-16 text-center text-[11px] font-mono text-text-dim">
        Vite {import.meta.env.MODE} build · proof of concept · not yet production
      </footer>
    </main>
  );
}
