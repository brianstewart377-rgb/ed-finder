import type { SimulateBuildResponse } from '@/types/api';
import { titleCase } from '../utils/formatters';

export function MechanicsTracePanel({ trace }: { trace: SimulateBuildResponse['mechanics_trace'] }) {
  const categories = Object.entries(trace ?? {}).filter(([, events]) => Array.isArray(events) && events.length > 0);
  if (categories.length === 0) return null;
  return (
    <details data-testid="mechanics-trace-accordion" className="rounded-chunk-lg border border-border/70 bg-bg2/70 p-3">
      <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-[0.18em] text-silver">
        Mechanics Trace
      </summary>
      <div className="mt-3 space-y-2">
        {categories.slice(0, 6).map(([category, events]) => (
          <div key={category} className="rounded border border-border/60 bg-bg3/45 px-2 py-1.5">
            <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-orange">{titleCase(category)}</div>
            <div className="mt-1 space-y-1">
              {events.slice(0, 3).map((event) => (
                <div key={`${category}-${event.label}-${event.description}`} className="font-mono text-[10px] leading-snug text-silver-dk">
                  <span className="text-silver">{event.label}:</span> {event.description}
                  {event.delta != null && <span className="text-orange"> ({event.delta > 0 ? '+' : ''}{event.delta})</span>}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </details>
  );
}
