import type { ReactNode } from 'react';

export function Message({
  title,
  tone,
  items,
}: {
  title?: string;
  tone: 'good' | 'warn' | 'danger' | 'info';
  items: string[];
}) {
  const toneClass = {
    good: 'border-green/35 bg-green/5 text-green',
    warn: 'border-gold/35 bg-gold/5 text-gold',
    danger: 'border-red/40 bg-red/10 text-red',
    info: 'border-cyan/30 bg-cyan/5 text-cyan',
  }[tone];
  return (
    <div className={`rounded-chunk-lg border px-3 py-2 font-mono text-[11px] ${toneClass}`}>
      {title && <div className="mb-1 text-[10px] uppercase tracking-[0.16em] opacity-80">{title}</div>}
      <ul className="space-y-1">
        {items.map((item) => (
          <li key={item} className="leading-snug">{item}</li>
        ))}
      </ul>
    </div>
  );
}

export function Metric({
  label,
  value,
  tone = 'silver',
}: {
  label: string;
  value: string | number;
  tone?: 'orange' | 'silver' | 'green' | 'gold' | 'red' | 'cyan';
}) {
  const colour = {
    orange: 'text-orange',
    silver: 'text-silver',
    green: 'text-green',
    gold: 'text-gold',
    red: 'text-red',
    cyan: 'text-cyan',
  }[tone];
  return (
    <div className="rounded-chunk-lg border border-border/70 bg-bg2/80 p-2 text-center">
      <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-silver-dk">{label}</div>
      <div className={`mt-1 font-mono text-lg font-bold tabular-nums ${colour}`}>{value}</div>
    </div>
  );
}

export function GhostMetric({ label }: { label: string }) {
  return (
    <div className="rounded-chunk-lg border border-border/40 bg-bg2/50 p-2 text-center">
      <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-silver-dk">{label}</div>
      <div className="mx-auto mt-2 h-5 w-12 rounded bg-bg4/60" />
    </div>
  );
}

export function CpCell({ label, value, colour }: { label: string; value: number; colour: string }) {
  return (
    <div className="rounded border border-border/60 bg-bg3/60 p-2 text-center">
      <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-silver-dk">{label}</div>
      <div className="font-mono text-sm font-bold tabular-nums" style={{ color: colour }}>
        {value > 0 ? `+${value}` : value}
      </div>
    </div>
  );
}

export function IconButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className="grid h-9 w-9 place-items-center rounded-chunk-sm border border-border bg-bg3 text-silver-dk hover:border-orange/50 hover:text-orange disabled:opacity-35 disabled:cursor-not-allowed"
    >
      {children}
    </button>
  );
}

export function Chip({ children, tone = 'default' }: { children: ReactNode; tone?: 'default' | 'good' | 'warn' }) {
  const cls = tone === 'good'
    ? 'border-green/35 bg-green/10 text-green'
    : tone === 'warn'
      ? 'border-gold/35 bg-gold/10 text-gold'
      : 'border-border bg-bg4 text-silver-dk';
  return (
    <span className={`inline-flex items-center rounded px-1.5 py-0.5 border ${cls}`}>
      {children}
    </span>
  );
}
