import type { ReactNode } from 'react';
import { useId, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { SemanticStatusBadge, type SemanticStatusTone } from './SemanticStatusBadge';

export interface EvidencePostureSummaryProps {
  title: string;
  statusLabel: string;
  statusTone: SemanticStatusTone;
  summary: string;
  nextAction: string;
  plannerBoundary: string;
  caution?: string;
  highlights?: ReactNode;
  disclosureLabel?: string;
  disclosureContent?: ReactNode;
  className?: string;
  testIdPrefix?: string;
}

export function EvidencePostureSummary({
  title,
  statusLabel,
  statusTone,
  summary,
  nextAction,
  plannerBoundary,
  caution,
  highlights,
  disclosureLabel = 'Technical evidence detail',
  disclosureContent,
  className,
  testIdPrefix = 'evidence-posture',
}: EvidencePostureSummaryProps) {
  const [isOpen, setIsOpen] = useState(false);
  const disclosureId = useId();

  return (
    <section
      data-testid={`${testIdPrefix}-surface`}
      className={[
        'space-y-3 rounded-chunk-lg border border-border bg-bg2/55 p-4',
        className ?? '',
      ].join(' ').trim()}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-2">
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
            {title}
          </p>
          <SemanticStatusBadge
            label={statusLabel}
            tone={statusTone}
            testId={`${testIdPrefix}-badge`}
          />
        </div>
      </div>

      <div className="space-y-2 text-sm leading-relaxed text-silver">
        <p data-testid={`${testIdPrefix}-summary`}>{summary}</p>
        <p data-testid={`${testIdPrefix}-next-action`}>
          <span className="font-semibold text-text">Next:</span> {nextAction}
        </p>
        <p data-testid={`${testIdPrefix}-planner-boundary`}>
          <span className="font-semibold text-text">Planner:</span> {plannerBoundary}
        </p>
        {caution ? (
          <p data-testid={`${testIdPrefix}-caution`} className="text-gold">
            <span className="font-semibold">Caution:</span> {caution}
          </p>
        ) : null}
      </div>

      {highlights ? (
        <div
          data-testid={`${testIdPrefix}-highlights`}
          className="flex flex-wrap items-center gap-2 border-t border-border pt-3"
        >
          {highlights}
        </div>
      ) : null}

      {disclosureContent ? (
        <div className="border-t border-border pt-3">
          <button
            type="button"
            aria-expanded={isOpen}
            aria-controls={disclosureId}
            data-testid={`${testIdPrefix}-disclosure-toggle`}
            onClick={() => setIsOpen((current) => !current)}
            className="inline-flex items-center gap-2 rounded-chunk-sm border border-border bg-bg4 px-3 py-2 text-xs font-mono font-semibold text-silver transition-colors hover:text-orange focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/80"
          >
            <ChevronDown
              size={14}
              className={[
                'transition-transform motion-reduce:transition-none',
                isOpen ? 'rotate-180' : 'rotate-0',
              ].join(' ')}
            />
            {isOpen ? `Hide ${disclosureLabel}` : `Show ${disclosureLabel}`}
          </button>
          <div
            id={disclosureId}
            data-testid={`${testIdPrefix}-disclosure-panel`}
            hidden={!isOpen}
            aria-hidden={!isOpen}
            className="mt-3 space-y-3 text-[11px] leading-relaxed text-silver-dk"
          >
            {disclosureContent}
          </div>
        </div>
      ) : null}
    </section>
  );
}
