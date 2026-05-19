import type { ComponentProps, ReactNode } from 'react';
import { BuildPlanSection } from './BuildPlanSection';

export function BuildPlanWorkspaceView({
  planningFocusLabel,
  roleContext,
  ...buildPlanProps
}: ComponentProps<typeof BuildPlanSection> & {
  planningFocusLabel: string | null;
  roleContext?: ReactNode;
}) {
  return (
    <div className="space-y-3" data-testid="build-plan-workspace-view">
      <section className="rounded-chunk-lg border border-cyan/25 bg-cyan/5 px-3 py-2 font-mono text-[11px] leading-snug">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-[10px] uppercase tracking-[0.16em] text-cyan">Planning focus</div>
            <p className="mt-0.5 text-silver-dk">
              <span className="font-bold text-cyan">{planningFocusLabel ?? 'Whole system'}</span>
              <span className="ml-2">Topology selection provides context only. Build Plan edits stay explicit.</span>
            </p>
          </div>
          <span className="rounded border border-border/60 bg-bg3/45 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-silver-dk">
            Active mode
          </span>
        </div>
      </section>
      {roleContext}
      <BuildPlanSection {...buildPlanProps} />
    </div>
  );
}
