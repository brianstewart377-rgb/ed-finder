import type { ReactNode } from 'react';
import type { StatusTone } from './env';

// ---- Concept label -------------------------------------------------------
export function ConceptBadge({ className = '' }: { className?: string }) {
  return (
    <span
      className={[
        'inline-flex items-center gap-1.5 rounded-chunk-sm border border-gold/45 bg-gold/12 px-2.5 py-1',
        'font-mono text-[10px] uppercase tracking-[0.16em] text-gold',
        className,
      ].join(' ')}
    >
      <span aria-hidden className="inline-block h-1.5 w-1.5 rotate-45 bg-gold" />
      Concept — not implemented
    </span>
  );
}

// ---- Non-colour status pill ---------------------------------------------
const TONE_DOT: Record<StatusTone, string> = {
  ok: 'bg-cyan',
  info: 'bg-silver',
  warn: 'bg-gold',
  idle: 'bg-silver-2',
  active: 'bg-orange',
};

export function StatusPill({ tone, label, className = '' }: { tone: StatusTone; label: string; className?: string }) {
  return (
    <span
      className={[
        'inline-flex items-center gap-2 rounded-full border border-border bg-bg3/70 px-3 py-1',
        'font-mono text-[10px] uppercase tracking-[0.12em] text-silver',
        className,
      ].join(' ')}
    >
      <span aria-hidden className={['h-2 w-2 rounded-full', TONE_DOT[tone]].join(' ')} />
      {/* Label carries the meaning so status never relies on colour alone. */}
      {label}
    </span>
  );
}

// ---- Tier chip (shape + letter, not colour-only) -------------------------
export function TierChip({ tier }: { tier: 'S' | 'A' | 'B' | 'C' | 'D' }) {
  const tone: Record<string, string> = {
    S: 'border-cyan/50 text-cyan',
    A: 'border-green/50 text-green',
    B: 'border-gold/50 text-gold',
    C: 'border-orange/50 text-orange',
    D: 'border-red/50 text-red',
  };
  return (
    <span className={['inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded border px-1 font-mono text-[11px] font-bold', tone[tier]].join(' ')}>
      {tier}
    </span>
  );
}

// ---- Instrument panel (connected cockpit surface) ------------------------
export function Instrument({ children, className = '', as: Tag = 'section' }: { children: ReactNode; className?: string; as?: 'section' | 'div' | 'aside' | 'header' }) {
  return (
    <Tag
      className={[
        // A single connected instrument surface — opaque, seamed, no floating glass.
        'relative rounded-chunk border border-border bg-bg2/95 shadow-metal',
        className,
      ].join(' ')}
    >
      {children}
    </Tag>
  );
}

/** Section heading with a thin orange seam — reinforces "one instrument". */
export function SeamHeading({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-2.5">
      <h3 className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.16em] text-silver">
        <span aria-hidden className="inline-block h-3 w-1 rounded-full bg-orange" />
        {children}
      </h3>
      {right}
    </div>
  );
}
