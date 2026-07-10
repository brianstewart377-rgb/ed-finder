import type { ReviewPreviewStatus } from './ReviewWorkflowRail';

export function ReviewReadinessStrip({
  activeMode,
  previewStatus,
  observedFactsCount,
  exportReady = null,
  exportBlockerCount = null,
}: {
  activeMode: 'evidence' | 'validation' | 'export';
  previewStatus: ReviewPreviewStatus;
  observedFactsCount: number;
  exportReady?: boolean | null;
  exportBlockerCount?: number | null;
}) {
  const previewLabel = previewStatus === 'current' ? 'Current preview' : previewStatus === 'stale' ? 'Stale preview' : 'Preview not run';
  const validationLabel = previewStatus === 'not_run'
    ? 'Validation blocked'
    : observedFactsCount === 0
      ? 'Awaiting evidence'
      : previewStatus === 'stale'
        ? 'Validation ready, preview stale'
        : 'Validation ready';
  const exportLabel = exportReady == null
    ? 'Later export step'
    : exportReady
      ? 'Export ready'
      : exportBlockerCount != null && exportBlockerCount > 0
        ? `${exportBlockerCount} export blocker${exportBlockerCount === 1 ? '' : 's'}`
        : 'Export needs review';

  return (
    <section
      data-testid="review-readiness-strip"
      className="rounded-chunk-lg border border-border/60 bg-bg2/45 px-3 py-2"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-display text-xs tracking-[0.14em] text-cyan">Shared review readiness</span>
        <span className="rounded border border-orange/35 bg-orange/10 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-orange">
          {activeMode === 'evidence' ? 'Evidence lane' : activeMode === 'validation' ? 'Validation lane' : 'Export lane'}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5 font-mono text-[10px]">
        <ReadinessChip tone={previewStatus === 'current' ? 'good' : previewStatus === 'stale' ? 'warn' : 'neutral'}>
          {previewLabel}
        </ReadinessChip>
        <ReadinessChip tone={observedFactsCount > 0 ? 'good' : 'neutral'}>
          {observedFactsCount} observed fact{observedFactsCount === 1 ? '' : 's'}
        </ReadinessChip>
        <ReadinessChip tone={previewStatus === 'not_run' ? 'neutral' : observedFactsCount === 0 || previewStatus === 'stale' ? 'warn' : 'good'}>
          {validationLabel}
        </ReadinessChip>
        <ReadinessChip tone={exportReady == null ? 'neutral' : exportReady ? 'good' : 'warn'}>
          {exportLabel}
        </ReadinessChip>
      </div>
      <p
        data-testid="review-readiness-summary"
        className="mt-2 text-[11px] leading-relaxed text-silver-dk"
      >
        {buildReviewReadinessSummary({
          activeMode,
          previewStatus,
          observedFactsCount,
          exportReady,
          exportBlockerCount,
        })}
      </p>
    </section>
  );
}

function ReadinessChip({
  children,
  tone,
}: {
  children: string;
  tone: 'good' | 'warn' | 'neutral';
}) {
  const className = tone === 'good'
    ? 'border-green/35 bg-green/10 text-green'
    : tone === 'warn'
      ? 'border-gold/35 bg-gold/10 text-gold'
      : 'border-border/60 bg-bg3/35 text-silver-dk';

  return (
    <span className={`rounded border px-2 py-1 uppercase tracking-[0.12em] ${className}`}>
      {children}
    </span>
  );
}

function buildReviewReadinessSummary({
  activeMode,
  previewStatus,
  observedFactsCount,
  exportReady,
  exportBlockerCount,
}: {
  activeMode: 'evidence' | 'validation' | 'export';
  previewStatus: ReviewPreviewStatus;
  observedFactsCount: number;
  exportReady: boolean | null;
  exportBlockerCount: number | null;
}) {
  if (previewStatus === 'not_run') {
    return activeMode === 'evidence'
      ? 'Evidence can be recorded now, but the review story will stay incomplete until Preview has been run for this plan.'
      : 'Run Preview first so Validation and Export can compare against an explicit current prediction.';
  }
  if (observedFactsCount === 0) {
    return activeMode === 'export'
      ? 'Export can assemble review packs, but the story still lacks recorded observed evidence.'
      : 'Preview exists, but the review journey still needs observed evidence before it can feel complete.';
  }
  if (previewStatus === 'stale') {
    return 'Observed evidence exists, but Preview is stale. Refresh Preview before trusting comparison or export posture.';
  }
  if (exportReady) {
    return 'Preview, observed evidence, and export posture are aligned enough for a clean review hand-off.';
  }
  if ((exportBlockerCount ?? 0) > 0) {
    return `Review continuity is in place, but ${exportBlockerCount} export blocker${exportBlockerCount === 1 ? '' : 's'} still need closeout attention.`;
  }
  return 'Preview and observed evidence are aligned, so Validation and Export can now be treated as one continuous review journey.';
}
