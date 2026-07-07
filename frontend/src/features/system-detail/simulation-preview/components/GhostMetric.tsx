export function GhostMetric({ label }: { label: string }) {
  return (
    <div className="rounded-chunk-lg border border-border/40 bg-bg2/50 p-2 text-center">
      <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-silver-dk">{label}</div>
      <div className="mx-auto mt-2 h-5 w-12 rounded bg-bg4/60" />
    </div>
  );
}
