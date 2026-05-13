import { Message } from '../components';

export function EconomyBars({ composition, order }: { composition: Record<string, number>; order: string[] }) {
  const rows = order.map((economy) => [economy, composition[economy] ?? 0] as const);
  if (rows.length === 0) {
    return <Message tone="warn" items={['No economy-producing facilities are present yet.']} />;
  }
  return (
    <div className="rounded-chunk-lg border border-border/70 bg-bg2/70 p-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
        Economy result
      </div>
      <div className="space-y-2">
        {rows.map(([economy, value]) => (
          <div key={economy} className="grid grid-cols-[92px_minmax(0,1fr)_48px] items-center gap-2">
            <span className="truncate font-mono text-[11px] text-silver">{economy}</span>
            <div className="h-2.5 overflow-hidden rounded-full border border-border bg-bg4">
              <div
                className="h-full rounded-full bg-orange-grad shadow-brand-glow"
                style={{ width: `${Math.max(2, Math.min(100, value))}%` }}
              />
            </div>
            <span className="text-right font-mono text-[11px] tabular-nums text-orange">{value.toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
