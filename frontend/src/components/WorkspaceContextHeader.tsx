import type { ReactNode } from 'react';
import { X } from 'lucide-react';

export interface WorkspaceContextFact {
  label: string;
  value: ReactNode;
  tone?: 'default' | 'cyan' | 'orange' | 'green' | 'gold';
}

export interface WorkspaceContextHeaderProps {
  journeyLabel?: string;
  title: string;
  supportingText?: string;
  selectedSystemName?: string | null;
  selectedSystemMeta?: ReactNode;
  selectedSystemDetail?: ReactNode;
  onDismissSelectedSystem?: (() => void) | undefined;
  status?: ReactNode;
  actions?: ReactNode;
  facts?: WorkspaceContextFact[];
  headingLevel?: 1 | 2 | 3;
  className?: string;
  testId?: string;
}

const FACT_VALUE_TONE: Record<NonNullable<WorkspaceContextFact['tone']>, string> = {
  default: 'text-silver',
  cyan: 'text-cyan',
  orange: 'text-orange',
  green: 'text-green',
  gold: 'text-gold',
};

export function WorkspaceContextHeader({
  journeyLabel,
  title,
  supportingText,
  selectedSystemName,
  selectedSystemMeta,
  selectedSystemDetail,
  onDismissSelectedSystem,
  status,
  actions,
  facts = [],
  headingLevel = 1,
  className,
  testId,
}: WorkspaceContextHeaderProps) {
  const HeadingTag = headingLevel === 1 ? 'h1' : headingLevel === 2 ? 'h2' : 'h3';
  const hasRightRail = Boolean(selectedSystemName || selectedSystemMeta || actions);

  return (
    <header
      data-testid={testId}
      className={[
        'grid gap-4 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-start',
        className ?? '',
      ].join(' ').trim()}
    >
      <div className="min-w-0 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          {journeyLabel ? (
            <p className="rounded-full border border-orange/20 bg-orange/10 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.18em] text-orange-lt">
              {journeyLabel}
            </p>
          ) : null}
          {status}
        </div>

        <div className="space-y-1.5">
          <HeadingTag className="font-display text-xl tracking-[0.12em] text-text sm:text-2xl">
            {title}
          </HeadingTag>
          {supportingText ? (
            <p className={[hasRightRail ? 'max-w-3xl' : 'max-w-none', 'text-sm leading-relaxed text-silver'].join(' ')}>
              {supportingText}
            </p>
          ) : null}
        </div>

        {facts.length > 0 ? (
          <dl className="flex flex-wrap gap-2 text-[11px] font-mono">
            {facts.map((fact) => (
              <div
                key={fact.label}
                className="premium-subpanel inline-flex min-w-0 items-center gap-1.5 px-2.5 py-1.5"
              >
                <dt className="shrink-0 uppercase tracking-[0.14em] text-silver-dk">{fact.label}</dt>
                <dd className={['min-w-0 truncate', FACT_VALUE_TONE[fact.tone ?? 'default']].join(' ')}>
                  {fact.value}
                </dd>
              </div>
            ))}
          </dl>
        ) : null}
      </div>

      <div className="space-y-3 xl:max-w-sm xl:text-right">
        {selectedSystemName || selectedSystemMeta || selectedSystemDetail ? (
          <div className="premium-subpanel p-3.5">
            <div className="flex items-center justify-between gap-2">
              <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
                Selected system
              </p>
              {onDismissSelectedSystem ? (
                <button
                  type="button"
                  onClick={onDismissSelectedSystem}
                  aria-label="Clear selected system"
                  data-testid="selected-system-dismiss"
                  className="shrink-0 rounded-full p-0.5 text-silver-dk transition-colors hover:bg-white/10 hover:text-orange-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/60"
                >
                  <X size={14} />
                </button>
              ) : null}
            </div>
            {selectedSystemName ? (
              <p className="mt-1 text-base font-semibold text-text sm:text-lg">
                {selectedSystemName}
              </p>
            ) : null}
            {selectedSystemMeta ? (
              <div className="mt-1 text-[11px] font-mono uppercase tracking-[0.16em] text-silver-dk">
                {selectedSystemMeta}
              </div>
            ) : null}
            {selectedSystemDetail ? (
              <div className="mt-2">
                {selectedSystemDetail}
              </div>
            ) : null}
          </div>
        ) : null}

        {actions ? (
          <div className="flex flex-wrap gap-2 xl:justify-end">
            {actions}
          </div>
        ) : null}
      </div>
    </header>
  );
}
