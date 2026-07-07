import type { SimulateBuildResponse } from '@/types/api';
import { titleCase } from '../utils/formatters';
import { serviceTone } from '../utils/toneHelpers';

export function ServicesPanel({ services }: { services: SimulateBuildResponse['services'] }) {
  const rows = Object.entries(services ?? {});
  if (rows.length === 0) return null;
  return (
    <div className="rounded-chunk-lg border border-border/70 bg-bg2/70 p-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
        Service unlocks
      </div>
      <div className="grid gap-1.5 sm:grid-cols-2">
        {rows.map(([service, detail]) => (
          <div key={service} className="rounded border border-border/60 bg-bg3/45 px-2 py-1.5">
            <div className="flex items-center justify-between gap-2 font-mono text-[10px]">
              <span className="truncate text-silver">{titleCase(service)}</span>
              <span className={serviceTone(detail.status)}>{titleCase(detail.status)}</span>
            </div>
            <div className="mt-1 line-clamp-2 text-[10px] leading-snug text-silver-dk">{detail.reason}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
