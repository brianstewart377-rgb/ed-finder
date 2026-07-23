import { useState } from 'react';
import { useGalleryEnv, motion } from '../env';
import { StatusPill } from '../primitives';

const ROUTES = ['Finder', 'Map', 'My Work', 'Colony Planner', 'Compare', 'FC Route'];

/**
 * Mockup 1 — shared shell + legal notice.
 * A connected cockpit frame (not floating cards): orange active route, a single
 * selected-system context strip (no second nav bar), an opaque dismissible
 * legal notice, and a persistent About/Legal control. No news ticker.
 */
export function ShellMockup() {
  const { viewport, reducedMotion } = useGalleryEnv();
  const mobile = viewport === 'mobile';
  const [active, setActive] = useState('Finder');
  const [legalOpen, setLegalOpen] = useState(true);
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="flex h-full flex-col bg-bg1">
      <header className="relative shrink-0 border-b border-border bg-metal">
        <div className="flex items-center gap-3 px-4 py-2.5">
          <span aria-hidden className="inline-block h-5 w-1.5 rounded-full bg-orange" />
          <span className="font-mono text-[13px] font-bold tracking-[0.16em] text-orange">ED:FINDER</span>

          {!mobile ? (
            <nav aria-label="Primary" className="ml-3 flex items-center gap-1">
              {ROUTES.map((r) => {
                const on = r === active;
                return (
                  <button
                    key={r}
                    type="button"
                    aria-current={on ? 'page' : undefined}
                    onClick={() => setActive(r)}
                    className={[
                      'rounded-chunk-sm px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.1em] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/70',
                      motion(reducedMotion, 'transition-colors'),
                      on ? 'bg-orange/18 text-orange shadow-[inset_0_-2px_0_0_#ff7a14]' : 'text-silver hover:text-text hover:bg-bg3/60',
                    ].join(' ')}
                  >
                    {r}
                  </button>
                );
              })}
            </nav>
          ) : (
            <div className="ml-1 flex items-center gap-2">
              <button type="button" onClick={() => setMenuOpen((v) => !v)} aria-expanded={menuOpen} className="rounded-chunk-sm border border-border bg-bg3 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-silver focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/70">Menu</button>
              <span className="rounded-full border border-orange/40 bg-orange/12 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-orange">{active}</span>
            </div>
          )}

          <span className="hidden flex-1 sm:block" />
          <StatusPill tone="ok" label="API Online" />
          <button type="button" onClick={() => setLegalOpen(true)} className="rounded-chunk-sm border border-border bg-bg3 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-silver hover:border-orange/50 hover:text-orange focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/70">About / Legal</button>
        </div>

        {/* Selected-system context strip — one line, not a second nav bar */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border/70 bg-bg2/70 px-4 py-1.5">
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-2">Selected</span>
          <span className="font-mono text-[12px] text-orange">HIP 21991</span>
          <span className="font-mono text-[10px] text-silver-dk">ID64 10001</span>
          <StatusPill tone="active" label="Explore" />
          <StatusPill tone="info" label="Inspect ready" />
          <span className="hidden flex-1 sm:block" />
          <button type="button" className="font-mono text-[10px] uppercase tracking-[0.12em] text-silver-dk hover:text-orange focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/60">Clear</button>
        </div>

        {menuOpen && mobile && (
          <div className="grid grid-cols-2 gap-1 border-t border-border bg-bg2 p-2">
            {ROUTES.map((r) => (
              <button key={r} type="button" onClick={() => { setActive(r); setMenuOpen(false); }} className={['rounded-chunk-sm px-3 py-2 text-left font-mono text-[11px]', r === active ? 'bg-orange/18 text-orange' : 'text-silver hover:bg-bg3/60'].join(' ')}>{r}</button>
            ))}
          </div>
        )}
      </header>

      {legalOpen && (
        <div className={['shrink-0 border-b border-border bg-bg3 px-4 py-2.5', motion(reducedMotion, 'animate-fade-up')].join(' ')}>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <span aria-hidden className="inline-block h-3 w-1 rounded-full bg-orange" />
            <p className="min-w-0 flex-1 text-[12px] leading-relaxed text-silver">
              Data from <strong className="text-text">EDSM</strong> &amp; <strong className="text-text">EDDN</strong>. <em>Elite Dangerous</em> is a trademark of Frontier Developments plc; this is an unofficial fan tool. Full attribution stays in <span className="text-orange">About / Legal</span>.
            </p>
            <button type="button" onClick={() => setLegalOpen(false)} className="btn-metal font-mono text-[10px]">Got it — dismiss</button>
          </div>
        </div>
      )}

      <main className="min-h-0 flex-1 p-4">
        <div className="flex h-full flex-col items-center justify-center rounded-chunk border border-dashed border-border bg-bg2/60 text-center">
          <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-silver-2">Active workspace</p>
          <p className="mt-1 font-display text-lg tracking-[0.12em] text-silver">{active} content fills this region</p>
          <p className="mt-2 max-w-md px-4 text-[12px] leading-relaxed text-silver-dk">
            The shell is one connected instrument. Dismissing the legal notice reclaims its
            space; the persistent About / Legal control reopens the full attribution. No news
            ticker consumes vertical space.
          </p>
        </div>
      </main>
    </div>
  );
}
