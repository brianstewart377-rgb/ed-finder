import { useEffect, useRef } from 'react';
import { useMemo, useState } from 'react';
import { useEddnFeed, type EddnEvent } from './useEddnFeed';
import { Radio, Filter, X } from 'lucide-react';

const TYPE_COLORS: Record<string, { fg: string; bg: string }> = {
  FSDJump:           { fg: '#ffb074', bg: 'rgba(255,122,20,0.14)' },
  Scan:              { fg: '#7dd3fc', bg: 'rgba(125,211,252,0.12)' },
  Docked:            { fg: '#bef264', bg: 'rgba(190,242,100,0.12)' },
  Location:          { fg: '#a78bfa', bg: 'rgba(167,139,250,0.12)' },
  CarrierJump:       { fg: '#fbbf24', bg: 'rgba(251,191,36,0.12)' },
  Touchdown:         { fg: '#f87171', bg: 'rgba(248,113,113,0.12)' },
  FSSDiscoveryScan:  { fg: '#c8ccd1', bg: 'rgba(200,204,209,0.10)' },
};

const TICKER_TYPES = Object.keys(TYPE_COLORS);

export interface EddnTickerProps {
  onOpenSystem?: (id64: number) => void;
}

/**
 * Sticky bottom EDDN ticker bar.
 *
 * Features:
 *   • Click any pip → opens the system detail modal (via `onOpenSystem`).
 *   • Filter pop-up: toggle which event types are shown (FSDJump / Scan /
 *     Docked / etc.). Filter state lives locally; defaults to "all on".
 *   • Pause-on-hover marquee.
 */
export function EddnTicker({ onOpenSystem }: EddnTickerProps) {
  const { events, status } = useEddnFeed({ intervalMs: 4000, keep: 30 });
  const [enabled, setEnabled] = useState<Record<string, boolean>>(
    () => Object.fromEntries(TICKER_TYPES.map((t) => [t, true])),
  );
  const [filterOpen, setFilterOpen] = useState(false);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const toggleRef  = useRef<HTMLButtonElement | null>(null);

  // Close on outside click + Escape — popover doesn't trap focus, so make
  // dismissal easy. Without this, users only realise they have to click
  // the same Filter chip again to close, and report "I can't close it".
  useEffect(() => {
    if (!filterOpen) return;
    const onDocClick = (e: MouseEvent) => {
      const t = e.target as Node;
      if (popoverRef.current?.contains(t)) return;
      if (toggleRef.current?.contains(t))  return;
      setFilterOpen(false);
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setFilterOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onEsc);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onEsc);
    };
  }, [filterOpen]);

  const filtered = useMemo(
    () => events.filter((e) => enabled[e.type] !== false),
    [events, enabled],
  );

  const haveEvents = filtered.length > 0;
  const feedState = status === 'live'
    ? 'live feed'
    : status === 'reconnecting'
      ? (haveEvents ? 'recent feed' : 'reconnecting')
      : status === 'offline'
        ? 'offline'
        : 'connecting';

  return (
    <div
      data-testid="eddn-ticker"
      className="fixed bottom-0 left-0 right-0 z-20 pointer-events-none"
    >
      <div className="mx-auto max-w-[1840px] px-4 pb-3 pointer-events-auto">
        <div
          className="panel flex items-stretch overflow-visible"
          style={{ borderRadius: '20px' }}
        >
          {/* Brand pill */}
          <div
            className="flex items-center gap-2 px-4 shrink-0 border-r border-border/70 rounded-l-[20px]"
            style={{
              background: 'linear-gradient(180deg, rgba(255,122,20,0.18), rgba(255,122,20,0.04))',
            }}
          >
            <span className="relative grid place-items-center w-6 h-6">
              <span
                className={[
                  'absolute inset-0 rounded-full',
                  haveEvents ? 'bg-orange/35 animate-ping-slow' : 'bg-bg4',
                ].join(' ')}
              />
              <Radio size={13} className="relative text-orange-lt" strokeWidth={2.4} />
            </span>
            <div className="flex flex-col leading-none">
              <span className="font-display text-[11px] tracking-[0.18em] text-orange font-bold uppercase">
                EDDN
              </span>
              <span className="font-mono text-[8px] tracking-[0.22em] text-silver-dk uppercase mt-0.5">
                {feedState}
              </span>
            </div>
          </div>

          {/* Marquee */}
          <div className="flex-1 overflow-hidden relative group">
            {haveEvents ? (
              <div className="whitespace-nowrap py-2 animate-marquee group-hover:[animation-play-state:paused]">
                {[...filtered, ...filtered].map((e, i) => (
                  <Pip key={`${e.id64}-${e.timestamp}-${i}`} ev={e} onClick={onOpenSystem} />
                ))}
              </div>
            ) : (
              <div className="py-2 px-4 font-mono text-[11px] text-silver-dk italic">
                {Object.values(enabled).every((v) => !v)
                  ? 'All event types filtered out'
                  : status === 'reconnecting'
                    ? 'EDDN reconnecting'
                    : status === 'offline'
                      ? 'EDDN temporarily offline'
                      : 'Awaiting EDDN events'}
              </div>
            )}
          </div>

          {/* Filter chip popover */}
          <div className="relative flex shrink-0 border-l border-border/70">
            <button
              ref={toggleRef}
              type="button"
              data-testid="eddn-filter-toggle"
              onClick={() => setFilterOpen((v) => !v)}
              aria-expanded={filterOpen}
              className={[
                'flex items-center gap-1.5 px-3 font-display text-[10px] tracking-[0.16em] uppercase font-bold transition-colors',
                filterOpen ? 'text-orange-lt' : 'text-silver hover:text-orange-lt',
              ].join(' ')}
              title="Filter by event type"
            >
              <Filter size={12} />
              <span className="hidden md:inline">Filter</span>
              <span className="font-mono text-[10px] text-silver-dk">
                ({Object.values(enabled).filter(Boolean).length}/{TICKER_TYPES.length})
              </span>
            </button>

            {filterOpen && (
              <div
                ref={popoverRef}
                role="dialog"
                className="absolute right-0 bottom-[calc(100%+8px)] z-30 panel p-3 w-72 animate-fade-up"
                style={{ borderRadius: '20px' }}
              >
                <div className="flex items-center justify-between gap-2 mb-3">
                  <span className="font-display text-[10px] tracking-[0.18em] text-orange uppercase font-bold">
                    Event types
                  </span>
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => setEnabled(Object.fromEntries(TICKER_TYPES.map((t) => [t, true])))}
                      className="font-mono text-[9px] uppercase tracking-wider text-silver-dk hover:text-orange-lt"
                    >
                      all
                    </button>
                    <span className="text-silver-dk/40">·</span>
                    <button
                      type="button"
                      onClick={() => setEnabled(Object.fromEntries(TICKER_TYPES.map((t) => [t, false])))}
                      className="font-mono text-[9px] uppercase tracking-wider text-silver-dk hover:text-orange-lt"
                    >
                      none
                    </button>
                    <button
                      type="button"
                      data-testid="eddn-filter-close"
                      onClick={() => setFilterOpen(false)}
                      aria-label="Close filter"
                      className="ml-1 p-1 rounded-chunk-sm text-silver-dk hover:text-orange-lt hover:bg-bg3/60 transition-colors"
                    >
                      <X size={12} strokeWidth={2.4} />
                    </button>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-1.5">
                  {TICKER_TYPES.map((t) => {
                    const on = enabled[t] !== false;
                    const palette = TYPE_COLORS[t];
                    return (
                      <button
                        key={t}
                        type="button"
                        data-testid={`eddn-filter-${t}`}
                        onClick={() => setEnabled((p) => ({ ...p, [t]: !on }))}
                        aria-pressed={on}
                        className={[
                          'flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-chunk-sm border font-display text-[9.5px] uppercase tracking-[0.1em] font-bold transition-all',
                          on
                            ? 'border-orange/45 text-orange-lt bg-orange/10'
                            : 'border-border text-silver-dk bg-bg3/40 line-through opacity-60 hover:opacity-100',
                        ].join(' ')}
                        style={on ? { boxShadow: `inset 0 0 0 1px ${palette.fg}33` } : undefined}
                      >
                        <span
                          className="block w-2 h-2 rounded-full shrink-0"
                          style={{ background: palette.fg, boxShadow: on ? `0 0 6px ${palette.fg}aa` : 'none' }}
                        />
                        <span className="truncate flex-1 text-left">{t}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Counter pill */}
          <div className="hidden md:flex items-center gap-2 px-4 shrink-0 border-l border-border/70 bg-bg3/40 rounded-r-[20px]">
            <span className="font-mono text-[10px] tracking-widest text-silver-dk uppercase">
              {filtered.length} recent
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Single event chip ──────────────────────────────────────────────────

function Pip({ ev, onClick }: { ev: EddnEvent; onClick?: (id64: number) => void }) {
  const palette = TYPE_COLORS[ev.type] ?? { fg: '#c8ccd1', bg: 'rgba(200,204,209,0.10)' };
  const ago = relativeTime(ev.timestamp);
  const interactive = !!onClick;
  const Tag: 'button' | 'span' = interactive ? 'button' : 'span';

  return (
    <Tag
      type={interactive ? 'button' : undefined as never}
      data-testid={interactive ? `eddn-pip-${ev.id64}` : undefined}
      onClick={interactive ? () => onClick!(ev.id64) : undefined}
      className={[
        'inline-flex items-center gap-2 mx-3 align-middle',
        interactive ? 'cursor-pointer hover:bg-orange/10 rounded-chunk-sm px-1 py-0.5 transition-colors' : '',
      ].join(' ')}
      title={interactive ? `Open ${ev.system_name}` : undefined}
    >
      <span
        className="font-display text-[9.5px] tracking-[0.14em] uppercase font-bold px-2 py-0.5 rounded-full"
        style={{ color: palette.fg, background: palette.bg, border: `1px solid ${palette.fg}40` }}
      >
        {ev.type}
      </span>
      <span className={`font-mono text-[12px] ${interactive ? 'text-silver hover:text-orange-lt' : 'text-silver'}`}>
        {ev.system_name}
      </span>
      {ago && <span className="font-mono text-[10px] text-silver-dk">{ago}</span>}
      <span className="text-silver-dk/40 mx-1">·</span>
    </Tag>
  );
}

function relativeTime(ts: string | null): string | null {
  if (!ts) return null;
  const t = Date.parse(ts);
  if (Number.isNaN(t)) return null;
  const diff = (Date.now() - t) / 1000;
  if (diff < 60)    return `${Math.round(diff)}s ago`;
  if (diff < 3600)  return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}
