import type { ReactNode } from 'react';
import { RoleReviewCard } from '@/features/colony-planner/RoleReviewCard';
import type { RoleReviewResult } from '@/features/colony-planner/colonyRoleReview';
import type { SystemDetail } from '@/types/api';
import { ObservedEvidencePanel } from './observations';
import { ProvenanceCockpitPanel } from './provenance/ProvenanceCockpitPanel';
import { SelectedSystemReviewContext } from './SelectedSystemReviewContext';

export function EvidenceWorkspaceView({
  system,
  targetArchetype,
  roleContext,
  roleReview,
}: {
  system: SystemDetail;
  targetArchetype: string;
  roleContext?: ReactNode;
  roleReview?: RoleReviewResult;
}) {
  return (
    <div className="space-y-3" data-testid="evidence-workspace-view">
      <SelectedSystemReviewContext
        system={system}
        targetArchetype={targetArchetype}
        modeLabel="Evidence mode"
        tone="report_only"
        summary={`${system.name ?? 'This system'} stays in focus while you review read-only provenance and observed evidence. Canonical planner truth remains separate from report-only context.`}
      />
      <section className="rounded-chunk-lg border border-cyan/25 bg-cyan/5 px-3 py-2 font-mono text-[11px] leading-snug text-silver-dk">
        <span className="font-bold text-cyan">Evidence mode</span>
        <span className="ml-2">Manual observations are reviewed here for the selected system and do not run Preview or Validation automatically.</span>
      </section>
      {roleContext}
      {roleReview && (
        <RoleReviewCard
          title="Evidence Role Review"
          result={roleReview}
        />
      )}
      <ProvenanceCockpitPanel systemId64={system.id64} targetArchetype={targetArchetype} />
      <div className="rounded-chunk-lg border border-cyan/30 bg-bg1/50 p-3">
        <ObservedEvidencePanel systemId64={system.id64} suggestedArchetype={targetArchetype} />
      </div>
    </div>
  );
}
