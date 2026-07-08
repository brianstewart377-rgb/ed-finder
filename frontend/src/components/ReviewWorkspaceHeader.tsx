import type { ReactNode } from 'react';
import { SemanticStatusBadge, type SemanticStatusTone } from '@/components/SemanticStatusBadge';
import { WorkspaceContextHeader, type WorkspaceContextFact } from '@/components/WorkspaceContextHeader';

export interface ReviewSelectedSystem {
  id64: number;
  name: string | null;
  loading: boolean;
  evidenceLabel: string;
  evidenceTone: SemanticStatusTone;
  evidenceSummary: string;
}

export interface ReviewWorkspaceHeaderProps {
  title: string;
  supportingText: string;
  selectedSystem?: ReviewSelectedSystem | null;
  facts?: WorkspaceContextFact[];
  actions?: ReactNode;
  testId?: string;
}

export function ReviewWorkspaceHeader({
  title,
  supportingText,
  selectedSystem = null,
  facts = [],
  actions,
  testId,
}: ReviewWorkspaceHeaderProps) {
  const selectedSystemName = selectedSystem
    ? (selectedSystem.name ?? (selectedSystem.loading ? 'Refreshing selected system...' : `System ${selectedSystem.id64}`))
    : 'No selected system';
  const selectedSystemMeta = selectedSystem
    ? (selectedSystem.loading ? 'Refreshing selected-system context' : 'Selected-system context')
    : 'Selected-system context';

  return (
    <header className="panel overflow-hidden p-4 sm:p-5">
      <WorkspaceContextHeader
        journeyLabel="Review"
        title={title}
        supportingText={supportingText}
        facts={facts}
        actions={actions}
        testId={testId}
        selectedSystemName={selectedSystemName}
        selectedSystemMeta={<span>{selectedSystemMeta}</span>}
        selectedSystemDetail={(
          <div className="space-y-2 text-left xl:text-right" data-testid="review-workspace-selected-system">
            {selectedSystem ? (
              <>
                <SemanticStatusBadge
                  label={selectedSystem.evidenceLabel}
                  tone={selectedSystem.evidenceTone}
                />
                <p className="text-xs leading-relaxed text-silver">
                  {selectedSystem.evidenceSummary}
                </p>
                <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">
                  ID64 {selectedSystem.id64}
                </p>
              </>
            ) : (
              <>
                <SemanticStatusBadge
                  label="Waiting for selection"
                  tone="not_evaluated"
                />
                <p className="text-xs leading-relaxed text-silver">
                  Choose a system in Explore, Inspect, or Plan to pin that player-journey context here while you review supporting tools.
                </p>
              </>
            )}
          </div>
        )}
      />
    </header>
  );
}
