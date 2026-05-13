import type { ReactNode } from 'react';

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
