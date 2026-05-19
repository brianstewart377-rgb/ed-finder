import type { ComponentProps, ReactNode } from 'react';
import { OptimiserCandidatePanel } from './optimiser';

export function SuggestedBuildsWorkspaceView({
  planningFocusLabel,
  highlighted,
  roleContext,
  ...optimiserProps
}: ComponentProps<typeof OptimiserCandidatePanel> & {
  planningFocusLabel: string | null;
  highlighted: boolean;
  roleContext?: ReactNode;
}) {
  return (
    <div
      data-testid="suggested-builds-workspace-view"
      className={[
        'space-y-3 rounded-chunk-lg outline-none transition-[box-shadow,border-color] duration-300',
        highlighted ? 'ring-2 ring-cyan/70 shadow-brand-glow' : '',
      ].join(' ')}
    >
      <section className="rounded-chunk-lg border border-cyan/25 bg-cyan/5 px-3 py-2 font-mono text-[11px] leading-snug text-silver-dk">
        <span className="font-bold text-cyan">Current topology focus: {planningFocusLabel ?? 'Whole system'}</span>
        <span className="ml-2">Suggested Builds remain strategic options until you deliberately load one into the Build Plan.</span>
      </section>
      {roleContext}
      <OptimiserCandidatePanel {...optimiserProps} />
    </div>
  );
}
