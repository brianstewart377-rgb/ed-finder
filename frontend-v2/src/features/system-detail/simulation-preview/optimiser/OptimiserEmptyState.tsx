export function OptimiserEmptyState({ warnings = [], assumptions = [] }: { warnings?: string[]; assumptions?: string[] }) {
  return (
    <div className="rounded-chunk-lg border border-dashed border-border bg-bg3/25 px-4 py-5 text-center">
      <div className="font-mono text-xs text-silver">No optimiser candidates generated yet.</div>
      <div className="mt-1 text-[11px] text-silver-dk">
        Generate read-only candidate suggestions for the current target archetype when you are ready to compare options.
      </div>
      {(warnings.length > 0 || assumptions.length > 0) && (
        <div className="mt-3 space-y-1 text-left font-mono text-[11px] text-silver-dk">
          {warnings.map((warning) => <div key={`warning-${warning}`} className="text-gold">Warning: {warning}</div>)}
          {assumptions.map((assumption) => <div key={`assumption-${assumption}`}>Assumption: {assumption}</div>)}
        </div>
      )}
    </div>
  );
}
