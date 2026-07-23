import { useState } from 'react';
import { useGalleryEnv } from '../env';
import { StatusPill, TierChip, SeamHeading } from '../primitives';
import { compareColumns, compareMetrics, bestIndex } from '../mockData';

/**
 * Mockup 5 — Compare, self-explanatory in empty and populated states.
 * Up to four Finder systems, per-metric best value, missing-data treatment,
 * Inspect / remove / clear / CSV export. A note keeps build-plan comparison in
 * the Colony Cockpit, not here.
 */
export function CompareMockup() {
  const { viewport } = useGalleryEnv();
  const mobile = viewport === 'mobile';
  const [populated, setPopulated] = useState(true);
  const [cols, setCols] = useState(compareColumns);

  const groups = Array.from(new Set(compareMetrics.map((m) => m.group)));

  return (
    <div className="flex h-full flex-col bg-bg1">
      <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-border bg-metal px-4 py-2.5">
        <span className="font-display text-sm tracking-[0.14em] text-orange">Compare</span>
        <StatusPill tone={populated ? 'ok' : 'idle'} label={populated ? `${cols.length} of 4 systems` : 'Empty'} />
        <span className="hidden flex-1 sm:block" />
        {populated && (
          <>
            <button type="button" className="btn-metal font-mono text-[10px]">Export CSV</button>
            <button type="button" onClick={() => { setCols([]); setPopulated(false); }} className="btn-metal font-mono text-[10px]">Clear all</button>
          </>
        )}
        <div role="group" aria-label="Demo state" className="flex overflow-hidden rounded-chunk-sm border border-border">
          {(['populated', 'empty'] as const).map((s) => (
            <button key={s} type="button" aria-pressed={(s === 'populated') === populated} onClick={() => { setPopulated(s === 'populated'); if (s === 'populated') setCols(compareColumns); }} className={['px-2.5 py-1 font-mono text-[10px] uppercase', (s === 'populated') === populated ? 'bg-orange/20 text-orange' : 'text-silver-dk hover:text-silver'].join(' ')}>{s}</button>
          ))}
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-auto p-4">
        {!populated || cols.length === 0 ? (
          <div className="flex h-full min-h-[260px] flex-col items-center justify-center rounded-chunk border border-dashed border-border bg-bg2/60 text-center">
            <p className="font-display text-base tracking-[0.12em] text-silver">Compare up to four systems</p>
            <p className="mt-1 max-w-md px-4 text-[12px] leading-relaxed text-silver-dk">
              Add candidates from Finder to see a side-by-side breakdown. Compare highlights the
              best value per metric, opens System Detail, removes candidates, and exports CSV.
            </p>
            <button type="button" onClick={() => { setPopulated(true); setCols(compareColumns); }} className="mt-3 rounded-chunk-sm border border-orange/55 bg-orange/15 px-3 py-1.5 font-mono text-[11px] text-orange">Open Finder</button>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Column headers */}
            <div className="grid gap-2" style={{ gridTemplateColumns: `minmax(120px, 180px) repeat(${cols.length}, minmax(0, 1fr))` }}>
              <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-2">Metric</div>
              {cols.map((c) => (
                <div key={c.id64} className="rounded-chunk-sm border border-border bg-bg2/95 p-2">
                  <div className="flex items-center justify-between gap-1">
                    <span className="truncate font-mono text-[12px] text-text">{c.name}</span>
                    <TierChip tier={c.tier} />
                  </div>
                  <div className="mt-1 flex items-center gap-1.5">
                    <button type="button" className="rounded border border-orange/50 px-1.5 py-0.5 font-mono text-[9px] uppercase text-orange">Inspect</button>
                    <button type="button" onClick={() => setCols((cs) => cs.filter((x) => x.id64 !== c.id64))} className="rounded border border-border px-1.5 py-0.5 font-mono text-[9px] uppercase text-silver-dk hover:text-red" aria-label={`Remove ${c.name}`}>Remove</button>
                  </div>
                </div>
              ))}
            </div>

            {/* Grouped metric rows with winner marking + missing-data treatment */}
            {groups.map((group) => (
              <div key={group}>
                <SeamHeading>{group}</SeamHeading>
                <div className="mt-1 space-y-1">
                  {compareMetrics.filter((m) => m.group === group).map((m) => {
                    const win = bestIndex(m);
                    return (
                      <div key={m.key} className="grid items-center gap-2" style={{ gridTemplateColumns: `minmax(120px, 180px) repeat(${cols.length}, minmax(0, 1fr))` }}>
                        <div className="font-mono text-[11px] text-silver-dk">{m.label}</div>
                        {cols.map((_, i) => {
                          const raw = m.values[i];
                          const missing = raw === null || raw === undefined;
                          const isWin = win === i;
                          return (
                            <div key={i} className={['rounded px-2 py-1 font-mono text-[12px]', isWin ? 'border border-orange/50 bg-orange/12 text-orange' : 'border border-transparent text-silver'].join(' ')}>
                              {missing ? <span className="text-silver-2" title="No data reported">— no data</span> : <>{raw}{typeof raw === 'number' && m.unit ? m.unit : ''}{isWin && <span className="ml-1 text-[9px] uppercase tracking-wide text-orange/80">best</span>}</>}
                            </div>
                          );
                        })}
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}

            <div className="rounded-chunk-sm border border-cyan/30 bg-cyan/8 p-3 font-mono text-[11px] leading-relaxed text-silver">
              <span className="text-cyan">Note:</span> best-value highlighting is descriptive, not a new score. Build-plan
              comparison belongs in the <span className="text-orange">Colony Cockpit</span> — Compare stays a candidate
              decision aid, not a second planner. {mobile ? 'Scroll horizontally to see all columns.' : ''}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
