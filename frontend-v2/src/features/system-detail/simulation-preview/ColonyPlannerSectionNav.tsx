export function ColonyPlannerSectionNav() {
  return (
    <div className="border-b border-border/60 px-4 py-2">
      <div className="flex flex-wrap gap-2 font-mono text-[10px] uppercase tracking-[0.14em]">
        <span className="rounded border border-orange/35 bg-orange/10 px-2 py-1 text-orange">Build Plan</span>
        <span className="rounded border border-cyan/35 bg-cyan/10 px-2 py-1 text-cyan">Optimiser Candidates</span>
        <span className="rounded border border-border bg-bg3 px-2 py-1 text-silver-dk">Preview Result</span>
        {/* Stage 6B adds a fourth section label for the manual Observed
            Evidence shelf. The label is intentionally neutral (silver) so
            users do not read it as part of the predicted scoring chain. */}
        <span className="rounded border border-border bg-bg3 px-2 py-1 text-silver-dk">Observed Evidence</span>
        {/* Stage 6D adds the in-page Validation section label. Cyan
            matches the Validation panel chrome so users can connect the
            label with the rendered comparison block, while the wording
            stays neutral — "Validation" describes the panel, not a
            verdict. */}
        <span className="rounded border border-cyan/35 bg-cyan/10 px-2 py-1 text-cyan">Validation</span>
      </div>
    </div>
  );
}
