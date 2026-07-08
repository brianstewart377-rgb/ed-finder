import type { ReactNode } from 'react';
import { RoleReviewCard } from '@/features/colony-planner/RoleReviewCard';
import type { RoleReviewResult } from '@/features/colony-planner/colonyRoleReview';
import type { SystemDetail } from '@/types/api';
import type { UseSimulationPreviewRunResult } from './hooks/useSimulationPreviewRun';
import { ValidationPanel } from './validation';
import { SelectedSystemReviewContext } from './SelectedSystemReviewContext';

export function ValidationWorkspaceView({
  system,
  targetArchetype,
  previewResult,
  isPreviewResultStale,
  roleContext,
  roleReview,
}: {
  system: SystemDetail;
  targetArchetype: string;
  previewResult: UseSimulationPreviewRunResult['result'];
  isPreviewResultStale: boolean;
  roleContext?: ReactNode;
  roleReview?: RoleReviewResult;
}) {
  const status = previewResult ? (isPreviewResultStale ? 'Preview stale' : 'Preview ready') : 'Needs preview';

  return (
    <div className="space-y-3" data-testid="validation-workspace-view">
      <SelectedSystemReviewContext
        system={system}
        targetArchetype={targetArchetype}
        modeLabel="Validation mode"
        tone={previewResult ? (isPreviewResultStale ? 'needs_review' : 'available') : 'needs_review'}
        summary={`${system.name ?? 'This system'} stays in focus while you compare manual validation notes against the current explicit Preview result. Validation never rewrites canonical planner truth.`}
      />
      <section className="rounded-chunk-lg border border-orange/25 bg-orange/5 px-3 py-2 font-mono text-[11px] leading-snug text-silver-dk">
        <span className="font-bold text-orange">Validation mode: {status}</span>
        <span className="ml-2">Validation remains manual, stays scoped to the selected system, and compares against the current explicit Preview result.</span>
      </section>
      {roleContext}
      {roleReview && (
        <RoleReviewCard
          title="Validation Role Review"
          result={roleReview}
        />
      )}
      <div className="rounded-chunk-lg border border-orange/30 bg-bg1/50 p-3">
        <ValidationPanel
          systemId64={system.id64}
          targetArchetype={targetArchetype}
          previewResult={previewResult}
          isPreviewResultStale={isPreviewResultStale}
        />
      </div>
    </div>
  );
}
