import { useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { GalleryEnvContext, motion, type Viewport } from './env';
import { StatusPill } from './primitives';
import { ShellMockup } from './screens/ShellMockup';
import { FinderMockup } from './screens/FinderMockup';
import { MapMockup } from './screens/MapMockup';
import { MyWorkMockup } from './screens/MyWorkMockup';
import { CompareMockup } from './screens/CompareMockup';
import { ConceptsMockup } from './screens/ConceptsMockup';

interface ScreenDef {
  id: string;
  label: string;
  group: 'Product' | 'Roadmap concepts';
  render: () => ReactNode;
}

const SCREENS: ScreenDef[] = [
  { id: 'shell', label: '1 · Shared shell & legal', group: 'Product', render: () => <ShellMockup /> },
  { id: 'finder', label: '2 · Finder', group: 'Product', render: () => <FinderMockup /> },
  { id: 'map', label: '3 · Map', group: 'Product', render: () => <MapMockup /> },
  { id: 'my-work', label: '4 · My Work', group: 'Product', render: () => <MyWorkMockup /> },
  { id: 'compare', label: '5 · Compare', group: 'Product', render: () => <CompareMockup /> },
  { id: 'concepts', label: '6 · Roadmap concepts', group: 'Roadmap concepts', render: () => <ConceptsMockup /> },
];

const VIEWPORTS: { id: Viewport; label: string; w: number; h: number }[] = [
  { id: 'desktop', label: '1440 × 900', w: 1440, h: 900 },
  { id: 'laptop', label: '1280 × 720', w: 1280, h: 720 },
  { id: 'mobile', label: '390 × 844', w: 390, h: 844 },
];

export function ConceptGalleryApp() {
  const [activeId, setActiveId] = useState<string>('shell');
  const [viewport, setViewport] = useState<Viewport>('desktop');
  const [reducedMotion, setReducedMotion] = useState<boolean>(false);
  const [aboutOpen, setAboutOpen] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    setReducedMotion(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setReducedMotion(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  const active = SCREENS.find((s) => s.id === activeId) ?? SCREENS[0];
  const dims = VIEWPORTS.find((v) => v.id === viewport) ?? VIEWPORTS[0];
  const env = useMemo(() => ({ viewport, reducedMotion }), [viewport, reducedMotion]);

  return (
    <GalleryEnvContext.Provider value={env}>
      <div className="flex h-screen flex-col overflow-hidden bg-bg1 text-text">
        {/* ── Gallery meta-toolbar (distinct from the mocked product shell) ── */}
        <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-orange/30 bg-bg2 px-4 py-2.5">
          <div className="flex items-center gap-2.5">
            <span aria-hidden className="inline-block h-4 w-1.5 rounded-full bg-orange" />
            <span className="font-mono text-[13px] font-bold tracking-[0.16em] text-orange">ED:FINDER</span>
            <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-silver-dk">UI Concept Gallery</span>
          </div>
          <StatusPill tone="warn" label="Concept mockups · not production" />
          <span className="hidden flex-1 sm:block" />

          <div role="group" aria-label="Preview breakpoint" className="flex items-center overflow-hidden rounded-chunk-sm border border-border">
            {VIEWPORTS.map((v) => (
              <button
                key={v.id}
                type="button"
                aria-pressed={viewport === v.id}
                onClick={() => setViewport(v.id)}
                className={[
                  'px-2.5 py-1 font-mono text-[10px] tracking-wider focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/70',
                  motion(reducedMotion, 'transition-colors'),
                  viewport === v.id ? 'bg-orange/20 text-orange' : 'text-silver-dk hover:text-silver',
                ].join(' ')}
              >
                {v.label}
              </button>
            ))}
          </div>

          <button
            type="button"
            aria-pressed={reducedMotion}
            onClick={() => setReducedMotion((v) => !v)}
            className="inline-flex items-center gap-2 rounded-chunk-sm border border-border bg-bg3 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-silver hover:border-cyan/50 hover:text-cyan focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan/70"
          >
            <span aria-hidden className={['h-2 w-2 rounded-full', reducedMotion ? 'bg-cyan' : 'bg-silver-2'].join(' ')} />
            Reduced motion: {reducedMotion ? 'On' : 'Off'}
          </button>

          <button
            type="button"
            onClick={() => setAboutOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-chunk-sm border border-orange/45 bg-orange/12 px-3 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-orange hover:bg-orange/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/70"
          >
            About / Legal
          </button>
        </header>

        <div className="flex min-h-0 flex-1">
          {/* ── Screen index rail ── */}
          <nav aria-label="Concept screens" className="hidden w-60 shrink-0 flex-col gap-1 overflow-y-auto border-r border-border bg-bg2/60 p-3 md:flex">
            {(['Product', 'Roadmap concepts'] as const).map((group) => (
              <div key={group} className="mb-2">
                <div className="px-2 pb-1 font-mono text-[10px] uppercase tracking-[0.16em] text-silver-2">{group}</div>
                {SCREENS.filter((s) => s.group === group).map((s) => {
                  const on = s.id === activeId;
                  return (
                    <button
                      key={s.id}
                      type="button"
                      aria-current={on ? 'page' : undefined}
                      onClick={() => setActiveId(s.id)}
                      className={[
                        'flex w-full items-center gap-2 rounded-chunk-sm border px-3 py-2 text-left font-mono text-[11px] tracking-wide focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/70',
                        motion(reducedMotion, 'transition-colors'),
                        on ? 'border-orange/55 bg-orange/15 text-orange' : 'border-transparent text-silver hover:bg-bg3/70 hover:text-text',
                      ].join(' ')}
                    >
                      <span aria-hidden className={['h-3 w-1 rounded-full', on ? 'bg-orange' : 'bg-border-bright'].join(' ')} />
                      {s.label}
                    </button>
                  );
                })}
              </div>
            ))}
            <p className="mt-auto px-2 pt-3 font-mono text-[10px] leading-relaxed text-silver-2">
              Static, isolated design exploration. No live APIs, routes, or persistence.
            </p>
          </nav>

          {/* Mobile screen selector */}
          <div className="md:hidden">
            <label className="sr-only" htmlFor="screen-select">Select concept screen</label>
          </div>

          {/* ── Preview stage ── */}
          <main className="min-h-0 flex-1 overflow-auto bg-[radial-gradient(circle_at_20%_-10%,rgba(255,122,20,0.06),transparent_45%),radial-gradient(circle_at_85%_0%,rgba(125,211,252,0.05),transparent_50%)] p-4 sm:p-6">
            <div className="mx-auto flex flex-col items-center gap-3" style={{ width: 'fit-content' }}>
              <div className="flex w-full items-center justify-between gap-3">
                <select
                  id="screen-select"
                  value={activeId}
                  onChange={(e) => setActiveId(e.target.value)}
                  className="rounded border border-border bg-bg3 px-2 py-1 font-mono text-[11px] text-silver md:hidden"
                >
                  {SCREENS.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
                </select>
                <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">
                  {active.label} · {dims.label}
                </span>
              </div>

              {/* Device frame — fixed to the chosen breakpoint so JS-driven
                  responsive layouts are demonstrable inside one browser. */}
              <div
                className="overflow-hidden rounded-chunk-lg border border-border-bright bg-bg1 shadow-metal"
                style={{ width: dims.w, height: dims.h, maxWidth: '100%' }}
                data-viewport={viewport}
              >
                <div className="h-full w-full overflow-auto">
                  {active.render()}
                </div>
              </div>
            </div>
          </main>
        </div>

        {aboutOpen && <AboutLegalDialog onClose={() => setAboutOpen(false)} reducedMotion={reducedMotion} />}
      </div>
    </GalleryEnvContext.Provider>
  );
}

function AboutLegalDialog({ onClose, reducedMotion }: { onClose: () => void; reducedMotion: boolean }) {
  const closeRef = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button type="button" aria-label="Close About and Legal" onClick={onClose} className="absolute inset-0 bg-black/70" />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="About and legal attribution"
        className={['relative w-full max-w-lg rounded-chunk border border-border bg-bg2 p-5 shadow-metal', motion(reducedMotion, 'animate-fade-up')].join(' ')}
      >
        <h2 className="font-display text-base tracking-[0.14em] text-orange">About · Legal attribution</h2>
        <div className="mt-3 space-y-3 text-sm leading-relaxed text-silver">
          <p className="rounded-chunk-sm border border-gold/40 bg-gold/10 px-3 py-2 font-mono text-[11px] text-gold">
            This is an isolated UI concept gallery. Screens use mock data and do not reflect production behaviour.
          </p>
          <p>Data provided by EDSM (Elite Dangerous Star Map) and EDDN (Elite Dangerous Data Network). Gratitude to the Elite Dangerous community for crowd-sourcing this data.</p>
          <p><em>Elite Dangerous</em> is a registered trademark of Frontier Developments plc. This is an unofficial fan-made tool, not affiliated with or endorsed by Frontier Developments.</p>
        </div>
        <div className="mt-4 flex justify-end">
          <button ref={closeRef} type="button" onClick={onClose} className="btn-metal font-mono text-[11px]">Close</button>
        </div>
      </div>
    </div>
  );
}
