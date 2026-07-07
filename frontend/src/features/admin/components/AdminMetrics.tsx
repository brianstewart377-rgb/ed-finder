export function Stat({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div
      className={[
        'rounded-chunk-sm p-2.5 border',
        highlight ? 'border-red/40 bg-red/10' : 'border-border bg-bg3/40',
      ].join(' ')}
    >
      <div className="text-silver-dk uppercase tracking-[0.16em] text-[10px]">{label}</div>
      <div className={['tabular-nums font-bold mt-0.5', highlight ? 'text-red' : 'text-silver'].join(' ')}>
        {value}
      </div>
    </div>
  );
}

export function Flag({ label, value }: { label: string; value: boolean }) {
  return (
    <div className="rounded-chunk-sm p-2.5 border border-border bg-bg3/40 flex items-center justify-between">
      <span className="text-silver-dk uppercase tracking-[0.16em] text-[10px]">{label}</span>
      <span className={value ? 'text-green' : 'text-red'}>
        {value ? '✓' : '✕'}
      </span>
    </div>
  );
}
