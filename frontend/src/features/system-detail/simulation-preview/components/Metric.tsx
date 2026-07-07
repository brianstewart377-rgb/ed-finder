export function Metric({
  label,
  value,
  tone = 'silver',
}: {
  label: string;
  value: string | number;
  tone?: 'orange' | 'silver' | 'green' | 'gold' | 'red' | 'cyan';
}) {
  const colour = {
    orange: 'text-orange',
    silver: 'text-silver',
    green: 'text-green',
    gold: 'text-gold',
    red: 'text-red',
    cyan: 'text-cyan',
  }[tone];
  return (
    <div className="rounded-chunk-lg border border-border/70 bg-bg2/80 p-2 text-center">
      <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-silver-dk">{label}</div>
      <div className={`mt-1 font-mono text-lg font-bold tabular-nums ${colour}`}>{value}</div>
    </div>
  );
}
