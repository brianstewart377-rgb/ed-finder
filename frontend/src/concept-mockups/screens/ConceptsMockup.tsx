import { useState } from 'react';
import { useGalleryEnv } from '../env';
import { ConceptBadge, StatusPill, SeamHeading, Instrument } from '../primitives';
import { corridor, telemetryConcept, nebulaLayers, syncCandidates } from '../mockData';

type ConceptId = 'corridor' | 'telemetry' | 'nebula' | 'account';

const TABS: { id: ConceptId; label: string }[] = [
  { id: 'corridor', label: 'B-2 Colonisation corridor' },
  { id: 'telemetry', label: 'A-3 Personal telemetry' },
  { id: 'nebula', label: 'Nebula & POI overlays' },
  { id: 'account', label: 'Account & sync direction' },
];

/**
 * Mockup 6 — roadmap-backed concept gallery.
 * Every panel carries a "Concept — not implemented" badge. Nothing here calls
 * live APIs, persists data, or implies production availability.
 */
export function ConceptsMockup() {
  const { viewport } = useGalleryEnv();
  const mobile = viewport === 'mobile';
  const [tab, setTab] = useState<ConceptId>('corridor');

  return (
    <div className="flex h-full flex-col bg-bg1">
      <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-border bg-metal px-4 py-2.5">
        <span className="font-display text-sm tracking-[0.14em] text-orange">Roadmap concepts</span>
        <ConceptBadge />
      </header>

      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <nav aria-label="Concept topics" className="flex shrink-0 gap-1 overflow-x-auto border-b border-border p-2 md:w-64 md:flex-col md:border-b-0 md:border-r">
          {TABS.map((t) => {
            const on = tab === t.id;
            return (
              <button key={t.id} type="button" aria-current={on ? 'page' : undefined} onClick={() => setTab(t.id)} className={['whitespace-nowrap rounded-chunk-sm border px-3 py-2 text-left font-mono text-[11px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/70', on ? 'border-orange/55 bg-orange/15 text-orange' : 'border-transparent text-silver hover:bg-bg3/60'].join(' ')}>{t.label}</button>
            );
          })}
        </nav>

        <main className="min-h-0 flex-1 overflow-auto p-4">
          {tab === 'corridor' && (
            <Instrument>
              <SeamHeading right={<ConceptBadge />}>Colonisation corridor · hop-count only</SeamHeading>
              <div className="space-y-3 p-4">
                <div className="flex flex-wrap items-center gap-3 font-mono text-[11px] text-silver">
                  <span>Start <span className="text-orange">{corridor.start}</span></span>
                  <span aria-hidden>→</span>
                  <span>Target <span className="text-orange">{corridor.target}</span></span>
                  <StatusPill tone="info" label={`Max jump ${corridor.maxJumpLy} LY`} />
                  <StatusPill tone="ok" label={`${corridor.waypoints.length - 1} hops`} />
                </div>
                <ol className={['flex gap-2', mobile ? 'flex-col' : 'flex-wrap items-center'].join(' ')}>
                  {corridor.waypoints.map((w, i) => (
                    <li key={w.name} className="flex items-center gap-2">
                      <span className="rounded-chunk-sm border border-border bg-bg3/70 px-3 py-1.5 font-mono text-[11px] text-text">
                        <span className="mr-1 text-silver-2">{w.hop}</span>{w.name}
                      </span>
                      {i < corridor.waypoints.length - 1 && <span aria-hidden className="font-mono text-silver-2">{mobile ? '↓' : '—'}</span>}
                    </li>
                  ))}
                </ol>
                <p className="font-mono text-[11px] leading-relaxed text-silver-dk">Shows hop count and jump range only — no score-weighted recommendations. B-3 ranking stays gated on scoring and confidence work. Waypoints offer inspect hand-offs, not automated routing.</p>
              </div>
            </Instrument>
          )}

          {tab === 'telemetry' && (
            <Instrument>
              <SeamHeading right={<ConceptBadge />}>Personal telemetry enrichment</SeamHeading>
              <div className="space-y-3 p-4">
                <p className="font-mono text-[11px] leading-relaxed text-silver-dk">How imported journal observations could enrich My Work and the Planner with recently-visited systems, observation freshness, and event mix.</p>
                <ul className="space-y-1.5">
                  {telemetryConcept.visited.map((v) => (
                    <li key={v.system} className="flex items-center justify-between gap-2 rounded-chunk-sm border border-border bg-bg2/95 px-3 py-2 font-mono text-[11px]">
                      <span className="text-text">{v.system}</span>
                      <span className="text-silver-dk">{v.events} events</span>
                      <StatusPill tone={v.freshness.startsWith('Fresh') ? 'ok' : 'warn'} label={v.freshness} />
                    </li>
                  ))}
                </ul>
                <p className="font-mono text-[11px] text-silver-2">Identity continuity is required before this becomes a durable cross-device feature.</p>
              </div>
            </Instrument>
          )}

          {tab === 'nebula' && (
            <Instrument>
              <SeamHeading right={<ConceptBadge />}>Nebula &amp; community POI overlays</SeamHeading>
              <div className="space-y-3 p-4">
                <div className="relative h-40 overflow-hidden rounded-chunk border border-border bg-[radial-gradient(ellipse_at_30%_40%,rgba(125,211,252,0.18),transparent_55%),radial-gradient(ellipse_at_70%_60%,rgba(255,122,20,0.14),transparent_55%)]">
                  <span className="absolute left-3 top-3 font-mono text-[10px] uppercase tracking-[0.16em] text-silver-2">Synthetic placeholder layer</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {nebulaLayers.map((l) => (
                    <span key={l.id} className={['rounded-chunk-sm border px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em]', l.enabled ? 'border-cyan/50 bg-cyan/12 text-cyan' : 'border-border text-silver-dk'].join(' ')}>{l.label}: {l.enabled ? 'on' : 'off'}</span>
                  ))}
                </div>
                <p className="font-mono text-[11px] text-silver-2">File-level reuse terms, provenance, and bounded ingestion must be confirmed before implementation. Data shown is synthetic.</p>
              </div>
            </Instrument>
          )}

          {tab === 'account' && (
            <Instrument>
              <SeamHeading right={<ConceptBadge />}>Account &amp; sync direction</SeamHeading>
              <div className="space-y-3 p-4">
                <p className="font-mono text-[11px] leading-relaxed text-silver-dk">A low-detail settings concept showing what could eventually sync across devices.</p>
                <ul className="space-y-1.5">
                  {syncCandidates.map((s) => (
                    <li key={s.id} className="flex items-center justify-between gap-2 rounded-chunk-sm border border-border bg-bg2/95 px-3 py-2 font-mono text-[11px]">
                      <span className="text-text">{s.label}</span>
                      <span className="text-silver-dk">{s.note}</span>
                      <span aria-hidden className="h-4 w-8 rounded-full border border-border bg-bg4" />
                    </li>
                  ))}
                </ul>
                <p className="font-mono text-[11px] text-silver-2">Accounts, OAuth, collaboration, and plan sync remain deferred pending an explicit product and identity decision.</p>
              </div>
            </Instrument>
          )}
        </main>
      </div>
    </div>
  );
}
