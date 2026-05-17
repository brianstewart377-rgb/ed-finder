import type { ReactNode } from 'react';

export function ColonyPlannerSectionNav() {
  return (
    <div className="border-b border-border/60 bg-bg2/35 px-4 py-2">
      <div className="mb-2 font-mono text-[9px] uppercase tracking-[0.16em] text-silver-dk">
        Planner workflow
      </div>
      <div className="flex flex-wrap gap-2 font-mono text-[10px] uppercase tracking-[0.12em]">
        <NavChip step="1" tone="primary">
          <span>Suggested Builds</span>
        </NavChip>
        <NavChip step="2" tone="primary">
          <span>Build Plan</span>
        </NavChip>
        <NavChip step="3" tone="primary">
          <span>Preview Result</span>
        </NavChip>
        {/* Stage 6B adds a fourth section label for the manual Observed
            Evidence shelf. The label is intentionally subdued so users do
            not read it as part of the predicted scoring chain. */}
        <NavChip step="4" tone="later">
          <span>Observed Evidence</span>
          <span className="normal-case text-[9px] tracking-normal text-silver-dk">Later step</span>
        </NavChip>
        {/* Stage 6D adds the in-page Validation section label. The wording
            remains conservative - "Validation" names the panel, not a
            verdict about correctness. */}
        <NavChip step="5" tone="later">
          <span>Validation</span>
          <span className="normal-case text-[9px] tracking-normal text-silver-dk">Later step</span>
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
        : 'border-border bg-bg3 text-silver',
    ].join(' ')}>
      <span className="text-[9px] tracking-[0.08em] text-silver-dk">{step}</span>
      {children}
    </span>
  );
}
