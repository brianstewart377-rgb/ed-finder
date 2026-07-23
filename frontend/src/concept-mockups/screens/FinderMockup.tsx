import { useEffect, useRef, useState } from 'react';
import { useGalleryEnv, motion } from '../env';
import { StatusPill, TierChip, SeamHeading } from '../primitives';
import { finderSystems, finderFilterCategories } from '../mockData';

type ResultMode = 'idle' | 'loading' | 'error' | 'results';

/**
 * Mockup 2 — Finder as a compact instrument selector.
 * Category chips stay compact; activating one opens a larger adjacent editing
 * bay (desktop) or an overlay (mobile). Reference search, applied-filter
 * summaries, Reset/Search, and status remain obvious. Results own the space.
 */
export function FinderMockup() {
  const { viewport, reducedMotion } = useGalleryEnv();
  const mobile = viewport === 'mobile';
  const [mode, setMode] = useState<ResultMode>('results');
  const [openCat, setOpenCat] = useState<string | null>(null);
  const bayRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!openCat) return;
    bayRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpenCat(null); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [openCat]);

  const activeCat = finderFilterCategories.find((c) => c.id === openCat) ?? null;

  return (
    <div className="flex h-full flex-col bg-bg1">
      <header className="shrink-0 border-b border-border bg-metal px-4 py-2.5">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <span className="font-display text-sm tracking-[0.14em] text-orange">Finder</span>
          <label className="relative flex min-w-[200px] flex-1 items-center">
            <span className="sr-only">Reference system</span>
            <input
              defaultValue="Sol"
              className="w-full rounded-chunk-sm border border-border bg-bg1 px-3 py-1.5 font-mono text-[12px] text-text placeholder:text-silver-2 focus-visible:border-orange/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/50"
              aria-label="Reference system"
              placeholder="Search reference system…"
            />
          </label>
          {mode === 'loading' ? <StatusPill tone="warn" label="Searching…" />
            : mode === 'error' ? <StatusPill tone="warn" label="Search failed" />
            : mode === 'results' ? <StatusPill tone="ok" label={`${finderSystems.length} results`} />
            : <StatusPill tone="idle" label="No search yet" />}
          <button type="button" className="btn-metal font-mono text-[10px]">Reset</button>
          <button type="button" className="rounded-chunk-sm border border-orange-lt/80 bg-orange-grad px-4 py-1.5 font-display text-[11px] font-bold uppercase tracking-[0.12em] text-white shadow-brand-glow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/70">Search</button>
        </div>

        <div className="mt-2.5 flex flex-wrap items-center gap-1.5" role="group" aria-label="Filter categories">
          {finderFilterCategories.map((c) => {
            const on = openCat === c.id;
            return (
              <button
                key={c.id}
                type="button"
                aria-expanded={on}
                onClick={() => setOpenCat(on ? null : c.id)}
                className={[
                  'group flex items-center gap-2 rounded-chunk-sm border px-3 py-1.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/70',
                  motion(reducedMotion, 'transition-colors'),
                  on ? 'border-orange/55 bg-orange/15' : 'border-border bg-bg3/70 hover:border-orange/40',
                ].join(' ')}
              >
                <span className={['font-mono text-[11px] uppercase tracking-[0.1em]', on ? 'text-orange' : 'text-silver'].join(' ')}>{c.label}</span>
                <span className="font-mono text-[10px] text-silver-dk">{c.summary}</span>
                {c.active && <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-orange" title="Applied" />}
              </button>
            );
          })}
        </div>
      </header>

      <div className="relative flex min-h-0 flex-1">
        {activeCat && (
          <div
            ref={bayRef}
            tabIndex={-1}
            role="dialog"
            aria-label={`${activeCat.label} editor`}
            className={[
              mobile ? 'absolute inset-0 z-20 m-3 rounded-chunk' : 'w-80 shrink-0 border-r border-border',
              'bg-bg2 shadow-metal focus-visible:outline-none',
              motion(reducedMotion, 'animate-fade-up'),
            ].join(' ')}
          >
            <SeamHeading right={<button type="button" onClick={() => setOpenCat(null)} className="font-mono text-[10px] uppercase tracking-[0.12em] text-silver-dk hover:text-orange focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/60">Done</button>}>
              Edit · {activeCat.label}
            </SeamHeading>
            <div className="space-y-3 p-4">
              <p className="font-mono text-[11px] leading-relaxed text-silver-dk">Larger editing surface for the <span className="text-silver">{activeCat.label}</span> group. Completing or closing returns the category to its compact chip.</p>
              <div className="space-y-2">
                <div className="h-2 w-full rounded-full bg-bg4"><div className="h-2 w-2/3 rounded-full bg-orange/70" /></div>
                <div className="h-2 w-full rounded-full bg-bg4"><div className="h-2 w-1/3 rounded-full bg-cyan/70" /></div>
              </div>
              <p className="font-mono text-[10px] text-silver-2">Current summary: {activeCat.summary}</p>
            </div>
          </div>
        )}

        <main className="relative min-h-0 flex-1 overflow-auto p-4">
          {mode === 'idle' && (
            <div className="flex h-full min-h-[240px] items-center justify-center text-center">
              <div>
                <div className="text-3xl" aria-hidden>🔭</div>
                <p className="mt-2 font-display text-sm tracking-[0.12em] text-silver">Ready to search</p>
                <p className="mt-1 text-[12px] text-silver-dk">Pick categories above, then run a search.</p>
              </div>
            </div>
          )}
          {mode === 'loading' && (
            <div className="flex h-full min-h-[240px] items-center justify-center font-mono text-[12px] text-silver-dk">Scanning systems…</div>
          )}
          {mode === 'error' && (
            <div className="rounded-chunk border border-red/50 bg-red/10 p-4 font-mono text-[12px] text-red">Search failed — adjust filters and retry.</div>
          )}
          {mode === 'results' && (
            mobile ? (
              <ul className="space-y-2">
                {finderSystems.map((s) => (
                  <li key={s.id64} className="rounded-chunk border border-border bg-bg2/95 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[13px] text-text">{s.name}</span>
                      <TierChip tier={s.tier} />
                    </div>
                    <div className="mt-1 font-mono text-[11px] text-silver-dk">{s.distanceLy} LY · {s.primaryEconomy} · Dev {s.developmentScore}</div>
                  </li>
                ))}
              </ul>
            ) : (
              <table className="w-full border-collapse text-left">
                <thead>
                  <tr className="border-b border-border font-mono text-[10px] uppercase tracking-[0.12em] text-silver-2">
                    <th className="py-2 pr-3">System</th><th className="py-2 pr-3">Tier</th><th className="py-2 pr-3">Dev</th><th className="py-2 pr-3">Build</th><th className="py-2 pr-3">Distance</th><th className="py-2 pr-3">Economy</th><th className="py-2 pr-3">Status</th>
                  </tr>
                </thead>
                <tbody className="font-mono text-[12px]">
                  {finderSystems.map((s) => (
                    <tr key={s.id64} className="border-b border-border/60 hover:bg-bg3/50">
                      <td className="py-2 pr-3 text-text">{s.name}</td>
                      <td className="py-2 pr-3"><TierChip tier={s.tier} /></td>
                      <td className="py-2 pr-3 text-cyan">{s.developmentScore}</td>
                      <td className="py-2 pr-3 text-silver">{s.buildability}</td>
                      <td className="py-2 pr-3 text-silver">{s.distanceLy} LY</td>
                      <td className="py-2 pr-3 text-silver">{s.primaryEconomy}</td>
                      <td className="py-2 pr-3"><span className="text-silver-dk">{s.status}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          )}

          <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border/60 pt-3">
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-2">Demo state:</span>
            {(['idle', 'loading', 'error', 'results'] as ResultMode[]).map((m) => (
              <button key={m} type="button" aria-pressed={mode === m} onClick={() => setMode(m)} className={['rounded-full border px-2.5 py-0.5 font-mono text-[10px] uppercase', mode === m ? 'border-orange/50 bg-orange/15 text-orange' : 'border-border text-silver-dk'].join(' ')}>{m}</button>
            ))}
            <span className="ml-auto font-mono text-[10px] text-silver-2">Categories: Tab to focus · Enter opens bay · Esc closes · motion respects prefers-reduced-motion</span>
          </div>
        </main>
      </div>
    </div>
  );
}
