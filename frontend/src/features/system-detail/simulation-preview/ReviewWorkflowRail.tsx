export type ReviewWorkflowMode = 'evidence' | 'validation' | 'export';
export type ReviewPreviewStatus = 'not_run' | 'stale' | 'current';

export function ReviewWorkflowRail({
  activeMode,
  previewStatus,
  observedFactsCount,
  exportReady = null,
}: {
  activeMode: ReviewWorkflowMode;
  previewStatus: ReviewPreviewStatus;
  observedFactsCount: number;
  exportReady?: boolean | null;
}) {
  const validationStatus = getValidationStatus(previewStatus, observedFactsCount);
  const nextMove = getNextMove(activeMode, previewStatus, observedFactsCount, exportReady);

  return (
    <section
      data-testid="review-workflow-rail"
      className="rounded-chunk-lg border border-cyan/25 bg-[linear-gradient(180deg,rgba(34,211,238,0.08),rgba(15,23,42,0.18))] p-3 shadow-[0_18px_36px_-30px_rgba(34,211,238,0.7)]"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-display text-xs tracking-[0.14em] text-cyan">Review flow</span>
        <span className="rounded border border-orange/35 bg-orange/10 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-orange">
          {activeMode === 'evidence' ? 'Evidence in focus' : activeMode === 'validation' ? 'Validation in focus' : 'Export in focus'}
        </span>
      </div>
      <div className="mt-3 grid gap-2 md:grid-cols-4">
        <WorkflowCard
          title="Preview"
          status={previewStatus === 'current' ? 'Current' : previewStatus === 'stale' ? 'Stale' : 'Not run'}
          tone={previewStatus === 'current' ? 'good' : previewStatus === 'stale' ? 'warn' : 'neutral'}
          detail={
            previewStatus === 'current'
              ? 'Current explicit preview available for review surfaces.'
              : previewStatus === 'stale'
                ? 'Validation and export may still reflect an older preview.'
                : 'Run Preview before trusting downstream review.'
          }
          active={false}
        />
        <WorkflowCard
          title="Evidence"
          status={observedFactsCount > 0 ? `${observedFactsCount} fact${observedFactsCount === 1 ? '' : 's'}` : 'No facts yet'}
          tone={observedFactsCount > 0 ? 'good' : 'neutral'}
          detail={
            observedFactsCount > 0
              ? 'Observed evidence is available as read-only review context.'
              : 'Manual observations have not been recorded yet.'
          }
          active={activeMode === 'evidence'}
        />
        <WorkflowCard
          title="Validation"
          status={validationStatus.label}
          tone={validationStatus.tone}
          detail={validationStatus.detail}
          active={activeMode === 'validation'}
        />
        <WorkflowCard
          title="Export"
          status={exportReady == null ? 'Later step' : exportReady ? 'Ready' : 'Needs review'}
          tone={exportReady == null ? 'neutral' : exportReady ? 'good' : 'warn'}
          detail={
            exportReady == null
              ? 'Review/export packs are assembled when the story is ready.'
              : exportReady
                ? 'Current planner, evidence, and governance inputs are reviewable.'
                : 'Closeout blockers still need review before sharing outward.'
          }
          active={activeMode === 'export'}
        />
      </div>
      <div
        data-testid="review-workflow-next-move"
        className="mt-3 rounded border border-border/60 bg-bg3/35 px-3 py-2 text-sm leading-relaxed text-silver"
      >
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-cyan">Best next move</span>
        <span className="ml-2">{nextMove}</span>
      </div>
    </section>
  );
}

function WorkflowCard({
  title,
  status,
  detail,
  tone,
  active,
}: {
  title: string;
  status: string;
  detail: string;
  tone: 'good' | 'warn' | 'neutral';
  active: boolean;
}) {
  const toneClass = tone === 'good'
    ? 'border-green/35 bg-green/10 text-green'
    : tone === 'warn'
      ? 'border-gold/35 bg-gold/10 text-gold'
      : 'border-border/60 bg-bg3/35 text-silver-dk';

  return (
    <div
      className={[
        'rounded border p-3',
        active ? 'border-orange/45 bg-orange/10 shadow-[0_12px_24px_-22px_rgba(251,146,60,0.9)]' : toneClass,
      ].join(' ')}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em]">{title}</span>
        {active && (
          <span className="rounded border border-orange/35 bg-orange/10 px-1.5 py-0.5 text-[9px] uppercase tracking-[0.12em] text-orange">
            Active
          </span>
        )}
      </div>
      <div className="mt-1 text-sm text-silver">{status}</div>
      <p className="mt-1 text-[11px] leading-relaxed text-silver-dk">{detail}</p>
    </div>
  );
}

function getValidationStatus(previewStatus: ReviewPreviewStatus, observedFactsCount: number) {
  if (previewStatus === 'not_run') {
    return {
      label: 'Needs preview',
      tone: 'neutral' as const,
      detail: 'Validation stays blocked until an explicit preview exists.',
    };
  }
  if (observedFactsCount === 0) {
    return {
      label: 'Awaiting evidence',
      tone: 'warn' as const,
      detail: 'Preview exists, but manual observations are still missing.',
    };
  }
  return {
    label: previewStatus === 'stale' ? 'Ready, preview stale' : 'Ready to compare',
    tone: previewStatus === 'stale' ? 'warn' as const : 'good' as const,
    detail: 'Use Validation to compare the current preview against recorded observations.',
  };
}

function getNextMove(
  activeMode: ReviewWorkflowMode,
  previewStatus: ReviewPreviewStatus,
  observedFactsCount: number,
  exportReady: boolean | null,
) {
  if (activeMode === 'evidence') {
    if (previewStatus === 'not_run') return 'Run Preview first so later evidence and validation have a live prediction to compare against.';
    if (observedFactsCount === 0) return 'Record the first observed evidence for this system, then open Validation to compare it against Preview.';
    return 'Review the recorded facts, then move into Validation to see where prediction and evidence agree or drift.';
  }
  if (activeMode === 'validation') {
    if (previewStatus === 'not_run') return 'Run Preview before using Validation; there is no current prediction to compare yet.';
    if (observedFactsCount === 0) return 'Record observed evidence first, then refresh Validation to compare real observations against the current preview.';
    return 'Use the validation guidance to judge confidence, then move into Export when the review story is ready to share.';
  }
  if (previewStatus === 'not_run') return 'Run Preview and review the resulting plan state before treating export packs as decision-ready.';
  if (exportReady) return 'Review the generated packs, then share or hand off the plan knowing the review boundary is explicit.';
  if (observedFactsCount === 0) return 'Close out the readiness blockers and consider recording observed evidence before sharing this outward.';
  return 'Review the closeout blockers, validation posture, and governance notes before treating this pack as share-ready.';
}
