import type { ReactNode } from 'react';
import { RoleReviewCard } from '@/features/colony-planner/RoleReviewCard';
import type { RoleReviewResult } from '@/features/colony-planner/colonyRoleReview';
import { ObservedEvidencePanel } from './observations';

export function EvidenceWorkspaceView({
  systemId64,
  targetArchetype,
  roleContext,
  roleReview,
}: {
  systemId64: number;
  targetArchetype: string;
  roleContext?: ReactNode;
  roleReview?: RoleReviewResult;
}) {
  return (
    <div className="space-y-3" data-testid="evidence-workspace-view">
      <section className="rounded-chunk-lg border border-cyan/25 bg-cyan/5 px-3 py-2 font-mono text-[11px] leading-snug text-silver-dk">
        <span className="font-bold text-cyan">Evidence mode</span>
        <span className="ml-2">Manual observations are reviewed here and do not run Preview or Validation automatically.</span>
      </section>
      {roleContext}
      {roleReview && (
        <RoleReviewCard
          title="Evidence Role Review"
          result={roleReview}
        />
      )}
      <div className="rounded-chunk-lg border border-cyan/30 bg-bg1/50 p-3">
        <ObservedEvidencePanel systemId64={systemId64} suggestedArchetype={targetArchetype} />
      </div>
    </div>
  );
}
