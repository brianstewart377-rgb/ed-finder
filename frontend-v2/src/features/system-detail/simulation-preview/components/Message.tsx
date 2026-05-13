export function Message({
  title,
  tone,
  items,
}: {
  title?: string;
  tone: 'good' | 'warn' | 'danger' | 'info';
  items: string[];
}) {
  const toneClass = {
    good: 'border-green/35 bg-green/5 text-green',
    warn: 'border-gold/35 bg-gold/5 text-gold',
    danger: 'border-red/40 bg-red/10 text-red',
    info: 'border-cyan/30 bg-cyan/5 text-cyan',
  }[tone];
  return (
    <div className={`rounded-chunk-lg border px-3 py-2 font-mono text-[11px] ${toneClass}`}>
      {title && <div className="mb-1 text-[10px] uppercase tracking-[0.16em] opacity-80">{title}</div>}
      <ul className="space-y-1">
        {items.map((item) => (
          <li key={item} className="leading-snug">{item}</li>
        ))}
      </ul>
    </div>
  );
}
