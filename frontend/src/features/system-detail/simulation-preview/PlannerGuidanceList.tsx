import type { PlannerGuidanceItem } from './plannerGuidanceUtils';
import { guidanceTone } from './plannerGuidanceUtils';

export function PlannerGuidanceList({
  items,
  limit = 3,
  title = 'Planner guidance',
}: {
  items: PlannerGuidanceItem[];
  limit?: number;
  title?: string;
}) {
  if (items.length === 0) return null;
  const visible = items.slice(0, limit);
  const extra = items.length - visible.length;

  return (
    <div className="rounded border border-border/50 bg-bg3/30 px-2 py-2" data-testid="planner-guidance">
      <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-cyan">{title}</div>
      <div className="mt-1.5 space-y-1">
        {visible.map((item) => (
          <div key={item.id} className="flex flex-wrap items-center gap-1.5 font-mono text-[10px] leading-snug text-silver-dk">
            <span className={severityClass(item.severity)}>{item.severity}</span>
            <span>{item.text}</span>
          </div>
        ))}
        {extra > 0 && (
          <div className="font-mono text-[10px] text-silver-dk">+{extra} more guidance item{extra === 1 ? '' : 's'}</div>
        )}
      </div>
    </div>
  );
}

function severityClass(severity: PlannerGuidanceItem['severity']): string {
  const tone = guidanceTone(severity);
  const cls = tone === 'risk'
    ? 'border-red-400/40 bg-red-400/10 text-red-200'
    : tone === 'caution'
      ? 'border-gold/35 bg-gold/10 text-gold'
      : tone === 'advisory'
        ? 'border-orange/35 bg-orange/10 text-orange'
        : 'border-cyan/30 bg-cyan/10 text-cyan';
  return `inline-flex rounded border px-1.5 py-0.5 uppercase tracking-[0.12em] ${cls}`;
}
