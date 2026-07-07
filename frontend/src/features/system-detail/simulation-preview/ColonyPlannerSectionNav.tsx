import type { ReactNode } from 'react';

export function ColonyPlannerSectionNav() {
  return (
    <nav aria-label="Colony planner workflow" className="border-b border-border/60 bg-bg2/35 px-4 py-2">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2 font-mono text-[9px] uppercase tracking-[0.16em] text-silver-dk">
        <span>Primary planning path</span>
        <span className="text-[9px] normal-case tracking-normal text-silver/75">
          Suggested Builds {'\u2192'} Build Plan {'\u2192'} Preview Result
        </span>
        <span className="text-[9px] normal-case tracking-normal text-silver/60">Later steps: Observed Evidence, Validation</span>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-[0.12em]">
        <WorkflowChip step="1" tone="primary" ariaLabel="Suggested Builds - primary planning step">
          Suggested Builds
        </WorkflowChip>
        <FlowDivider />
        <WorkflowChip step="2" tone="primary" ariaLabel="Build Plan - primary planning step">
          Build Plan
        </WorkflowChip>
        <FlowDivider />
        <WorkflowChip step="3" tone="primary" ariaLabel="Preview Result - primary planning step">
          Preview Result
        </WorkflowChip>
        <FlowDivider />
        <NavChip step="4" tone="later" ariaLabel="Observed Evidence - later step">
          <span>Observed Evidence</span>
          <span className="normal-case text-[9px] font-normal tracking-normal text-silver-dk">Later step</span>
        </NavChip>
        <FlowDivider muted />
        <NavChip step="5" tone="later" ariaLabel="Validation - later step">
          <span>Validation</span>
          <span className="normal-case text-[9px] font-normal tracking-normal text-silver-dk">Later step</span>
        </NavChip>
      </div>
    </nav>
  );
}

function WorkflowChip({
  step,
  tone,
  children,
  ariaLabel,
}: {
  step: string;
  tone: 'primary' | 'later';
  children: ReactNode;
  ariaLabel: string;
}) {
  return (
    <span
      className={[
        'inline-flex items-center gap-1 rounded border px-2 py-1',
        tone === 'primary'
          ? 'border-orange/35 bg-orange/10 text-orange'
          : 'border-border bg-bg3/45 text-silver',
      ].join(' ')}
      aria-label={ariaLabel}
    >
      <span className="text-[9px] tracking-[0.08em] text-silver-dk">{step}</span>
      <span>{children}</span>
      {tone === 'primary' && <span className="sr-only">Primary planning step</span>}
      {tone === 'later' && <span className="sr-only">Later-step guidance</span>}
    </span>
  );
}

function NavChip({
  step,
  tone,
  children,
  ariaLabel,
}: {
  step: string;
  tone: 'primary' | 'later';
  children: ReactNode;
  ariaLabel: string;
}) {
  return (
    <span
      className={[
        'inline-flex items-center gap-1 rounded border px-2 py-1',
        tone === 'primary'
          ? 'border-orange/35 bg-orange/10 text-orange'
          : 'border-border bg-bg3/45 text-silver',
      ].join(' ')}
      aria-label={ariaLabel}
    >
      <span className="text-[9px] tracking-[0.08em] text-silver-dk">{step}</span>
      {children}
    </span>
  );
}

function FlowDivider({ muted = false }: { muted?: boolean }) {
  return (
    <span
      className={['px-1 text-[10px] uppercase tracking-[0.14em]', muted ? 'text-silver/45' : 'text-silver/70'].join(' ')}
      aria-hidden="true"
    >
      /
    </span>
  );
}
