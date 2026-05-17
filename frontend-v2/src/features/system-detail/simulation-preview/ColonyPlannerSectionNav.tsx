import type { ReactNode } from 'react';

export function ColonyPlannerSectionNav() {
  return (
    <div className="border-b border-border/60 bg-bg2/35 px-4 py-2">
      <div className="mb-2 font-mono text-[9px] uppercase tracking-[0.16em] text-silver-dk">
        Planner workflow
      </div>
      <div className="flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em]">
        <div className="rounded border border-orange/35 bg-orange/10 px-2 py-1 text-orange">
          <div className="flex items-center gap-1.5">
            <span className="text-[9px] tracking-[0.08em] text-silver-dk">1</span>
            <span>Suggested Builds</span>
          </div>
          <span className="sr-only">Primary planning step</span>
        </div>
        <NavPathSeparator />
        <div className="rounded border border-orange/35 bg-orange/10 px-2 py-1 text-orange">
          <div className="flex items-center gap-1.5">
            <span className="text-[9px] tracking-[0.08em] text-silver-dk">2</span>
            <span>Build Plan</span>
          </div>
          <span className="sr-only">Primary planning step</span>
        </div>
        <NavPathSeparator />
        <div className="rounded border border-orange/35 bg-orange/10 px-2 py-1 text-orange">
          <div className="flex items-center gap-1.5">
            <span className="text-[9px] tracking-[0.08em] text-silver-dk">3</span>
            <span>Preview Result</span>
          </div>
          <span className="sr-only">Primary planning step</span>
        </div>
        <span className="text-silver/65" aria-hidden="true">
          |
        </span>
        <NavChip step="4" tone="later">
          <span>Observed Evidence</span>
          <span className="normal-case text-[9px] font-normal tracking-normal text-silver-dk">Later step</span>
        </NavChip>
        <span className="text-silver/50" aria-hidden="true">
          |
        </span>
        <NavChip step="5" tone="later">
          <span>Validation</span>
          <span className="normal-case text-[9px] font-normal tracking-normal text-silver-dk">Later step</span>
        </NavChip>
      </div>
    </div>
  );
}

function NavChip({
  step,
  tone,
  children,
}: {
  step: string;
  tone: 'primary' | 'later';
  children: ReactNode;
}) {
  return (
    <span className={[
      'inline-flex items-center gap-1 rounded border px-2 py-1',
      tone === 'primary'
        ? 'border-orange/35 bg-orange/10 text-orange'
        : 'border-border bg-bg3/45 text-silver',
    ].join(' ')}>
      <span className="text-[9px] tracking-[0.08em] text-silver-dk">{step}</span>
      {children}
    </span>
  );
}

function NavPathSeparator() {
  return (
    <span className="px-1 text-[9px] uppercase tracking-[0.16em] text-silver/55" aria-hidden="true">
      →
    </span>
  );
}
