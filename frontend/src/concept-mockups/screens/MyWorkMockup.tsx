import { useState } from 'react';
import { useGalleryEnv, motion } from '../env';
import { StatusPill, TierChip, SeamHeading, Instrument } from '../primitives';
import { myWork } from '../mockData';

/**
 * Mockup 4 — My Work as a personal command surface.
 * Hierarchy: Continue → Saved Systems → Plans & Expansion → My Colonies →
 * Personal Telemetry. Journal Import is a compact drawer inside Personal
 * Telemetry, not a full-width hero.
 */
export function MyWorkMockup() {
  const { reducedMotion } = useGalleryEnv();
  const [populated, setPopulated] = useState(true);
  const [importOpen, setImportOpen] = useState(false);

  return (
    <div className="flex h-full flex-col bg-bg1">
      <header className="flex shrink-0 items-center gap-3 border-b border-border bg-metal px-4 py-2.5">
        <span className="font-display text-sm tracking-[0.14em] text-orange">My Work</span>
        <span className="hidden flex-1 sm:block" />
        <div role="group" aria-label="Demo state" className="flex overflow-hidden rounded-chunk-sm border border-border">
          {(['populated', 'empty'] as const).map((s) => (
            <button key={s} type="button" aria-pressed={(s === 'populated') === populated} onClick={() => setPopulated(s === 'populated')} className={['px-2.5 py-1 font-mono text-[10px] uppercase', (s === 'populated') === populated ? 'bg-orange/20 text-orange' : 'text-silver-dk hover:text-silver'].join(' ')}>{s}</button>
          ))}
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-auto p-4">
        {!populated ? (
          <div className="flex h-full min-h-[260px] flex-col items-center justify-center rounded-chunk border border-dashed border-border bg-bg2/60 text-center">
            <p className="font-display text-base tracking-[0.12em] text-silver">Nothing saved yet</p>
            <p className="mt-1 max-w-sm px-4 text-[12px] leading-relaxed text-silver-dk">Save systems from Finder, start a plan in the Colony Cockpit, or import your journal to populate this command surface.</p>
            <div className="mt-3 flex gap-2">
              <button type="button" className="rounded-chunk-sm border border-orange/55 bg-orange/15 px-3 py-1.5 font-mono text-[11px] text-orange">Open Finder</button>
              <button type="button" className="btn-metal font-mono text-[11px]">Import journal</button>
            </div>
          </div>
        ) : (
          <div className="grid gap-3 lg:grid-cols-2">
            {/* Continue where I left off — spans full width */}
            <Instrument className="lg:col-span-2">
              <SeamHeading right={<StatusPill tone="active" label="Resume" />}>Continue where I left off</SeamHeading>
              <div className="flex flex-wrap items-center justify-between gap-3 p-4">
                <div>
                  <p className="font-mono text-[13px] text-text">{myWork.continue.title}</p>
                  <p className="mt-0.5 font-mono text-[11px] text-silver-dk">{myWork.continue.detail} · {myWork.continue.updated}</p>
                </div>
                <button type="button" className="rounded-chunk-sm border border-orange-lt/80 bg-orange-grad px-4 py-1.5 font-display text-[11px] font-bold uppercase tracking-[0.12em] text-white shadow-brand-glow">Resume plan</button>
              </div>
            </Instrument>

            <Instrument>
              <SeamHeading>Saved systems</SeamHeading>
              <ul className="divide-y divide-border/60">
                {myWork.savedSystems.map((s) => (
                  <li key={s.name} className="flex items-center justify-between gap-2 px-4 py-2.5">
                    <div className="min-w-0">
                      <p className="font-mono text-[12px] text-text">{s.name}</p>
                      <p className="truncate font-mono text-[10px] text-silver-dk">{s.note}</p>
                    </div>
                    <TierChip tier={s.tier} />
                  </li>
                ))}
              </ul>
            </Instrument>

            <Instrument>
              <SeamHeading>Plans &amp; expansion plans</SeamHeading>
              <ul className="divide-y divide-border/60">
                {myWork.plans.map((p) => (
                  <li key={p.name} className="flex items-center justify-between gap-2 px-4 py-2.5">
                    <p className="font-mono text-[12px] text-text">{p.name}</p>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[10px] text-silver-dk">{p.systems} sys</span>
                      <StatusPill tone={p.status === 'Draft' ? 'idle' : 'info'} label={p.status} />
                    </div>
                  </li>
                ))}
              </ul>
            </Instrument>

            <Instrument>
              <SeamHeading>My colonies</SeamHeading>
              <ul className="divide-y divide-border/60">
                {myWork.colonies.map((c) => (
                  <li key={c.name} className="flex items-center justify-between gap-2 px-4 py-2.5">
                    <div>
                      <p className="font-mono text-[12px] text-text">{c.name}</p>
                      <p className="font-mono text-[10px] text-silver-dk">{c.system}</p>
                    </div>
                    <StatusPill tone="warn" label={c.state} />
                  </li>
                ))}
              </ul>
            </Instrument>

            {/* Personal telemetry with Journal Import as a compact drawer */}
            <Instrument>
              <SeamHeading right={
                <button type="button" aria-expanded={importOpen} onClick={() => setImportOpen((v) => !v)} className="rounded-chunk-sm border border-border bg-bg3 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-silver hover:border-orange/50 hover:text-orange focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/70">Journal Import ▾</button>
              }>
                Personal telemetry
              </SeamHeading>
              <div className="p-4">
                <p className="font-mono text-[10px] text-silver-2">{myWork.telemetry.freshness}</p>
                <ul className="mt-2 space-y-1.5">
                  {myWork.telemetry.recent.map((r) => (
                    <li key={r.system} className="flex items-center justify-between gap-2 font-mono text-[11px]">
                      <span className="text-text">{r.system}</span>
                      <span className="text-silver-dk">{r.events}</span>
                      <span className="text-silver-2">{r.when}</span>
                    </li>
                  ))}
                </ul>
                {importOpen && (
                  <div className={['mt-3 rounded-chunk-sm border border-border bg-bg3/70 p-3', motion(reducedMotion, 'animate-fade-up')].join(' ')}>
                    <p className="font-mono text-[11px] text-silver">Drop a <span className="text-orange">Journal.*.log</span> file to enrich recently-visited systems. Utility action — not the purpose of this workspace.</p>
                    <button type="button" className="btn-metal mt-2 font-mono text-[10px]">Choose file…</button>
                  </div>
                )}
              </div>
            </Instrument>
          </div>
        )}
      </div>
    </div>
  );
}
