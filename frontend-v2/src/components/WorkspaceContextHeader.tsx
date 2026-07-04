import type { ReactNode } from 'react';

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
  /** Must describe the selected system's evidence/data posture, not a plan outcome. */
  selectedSystemPosture?: ReactNode;
  selectedSystemMeta?: ReactNode;
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
  selectedSystemPosture,
  selectedSystemMeta,
  status,
  actions,
  facts = [],
  headingLevel = 1,
  className,
  testId,
}: WorkspaceContextHeaderProps) {
  const HeadingTag = headingLevel === 1 ? 'h1' : headingLevel === 2 ? 'h2' : 'h3';
  const hasRightRail = Boolean(selectedSystemName || selectedSystemPosture || selectedSystemMeta || actions);

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
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
              {journeyLabel}
            </p>
          ) : null}
          {status}
        </div>

        <div className="space-y-1">
          <HeadingTag className="font-display text-xl tracking-[0.12em] text-orange sm:text-2xl">
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
                className="inline-flex min-w-0 items-center gap-1.5 rounded border border-border bg-bg3/50 px-2 py-1"
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
        {selectedSystemName || selectedSystemPosture || selectedSystemMeta ? (
          <div className="rounded-chunk-lg border border-border bg-bg3/35 p-3" data-testid="selected-system-context-card">
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
              Selected system
            </p>
            {selectedSystemName ? (
              <p className="mt-1 text-base font-semibold text-text sm:text-lg">
                {selectedSystemName}
              </p>
            ) : null}
            {selectedSystemPosture ? (
              <div className="mt-2 flex flex-wrap items-center gap-2 xl:justify-end" data-testid="selected-system-evidence-posture">
                {selectedSystemPosture}
              </div>
            ) : null}
            {selectedSystemMeta ? (
              <div className="mt-1 text-[11px] font-mono uppercase tracking-[0.16em] text-silver-dk">
                {selectedSystemMeta}
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
