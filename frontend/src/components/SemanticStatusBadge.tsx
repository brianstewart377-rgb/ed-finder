import type { ReactNode } from 'react';

export type SemanticStatusTone =
  | 'available'
  | 'unavailable'
  | 'unknown'
  | 'not_evaluated'
  | 'canonical'
  | 'observed'
  | 'report_only'
  | 'stale'
  | 'needs_review'
  | 'blocked'
  | 'caution'
  | 'loading';

const TONE_CLASS: Record<SemanticStatusTone, string> = {
  available: 'border-green/40 bg-green/10 text-green',
  unavailable: 'border-red/45 bg-red/10 text-red',
  unknown: 'border-border bg-bg4 text-silver-dk',
  not_evaluated: 'border-gold/45 bg-gold/10 text-gold',
  canonical: 'border-cyan/40 bg-cyan/10 text-cyan',
  observed: 'border-orange/40 bg-orange/10 text-orange-lt',
  report_only: 'border-orange/40 bg-orange/10 text-orange',
  stale: 'border-gold/45 bg-gold/10 text-gold',
  needs_review: 'border-gold/45 bg-gold/10 text-gold',
  blocked: 'border-red/45 bg-red/10 text-red',
  caution: 'border-gold/45 bg-gold/10 text-gold',
  loading: 'border-border bg-bg4 text-silver',
};

export interface SemanticStatusBadgeProps {
  label: string;
  tone: SemanticStatusTone;
  leadingIcon?: ReactNode;
  className?: string;
  testId?: string;
}

export function SemanticStatusBadge({
  label,
  tone,
  leadingIcon,
  className,
  testId,
}: SemanticStatusBadgeProps) {
  return (
    <span
      data-testid={testId}
      className={[
        'inline-flex min-h-7 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-mono font-semibold uppercase tracking-[0.14em]',
        TONE_CLASS[tone],
        className ?? '',
      ].join(' ').trim()}
    >
      {leadingIcon}
      <span>{label}</span>
    </span>
  );
}
