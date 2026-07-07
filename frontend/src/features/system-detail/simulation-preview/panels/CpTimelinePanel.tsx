import type { SimulateBuildResponse } from '@/types/api';
import { signed } from '../utils/formatters';

export function CpTimelinePanel({ timeline }: { timeline: SimulateBuildResponse['cp_timeline'] }) {
  if (!timeline || timeline.length === 0) return null;
  return (
    <div className="rounded-chunk-lg border border-border/70 bg-bg2/70 p-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
        CP build-order timeline
      </div>
      <div className="space-y-1.5">
        {timeline.slice(0, 5).map((step) => (
          <div key={`${step.step}-${step.facility_template_id}`} className="rounded border border-border/60 bg-bg3/45 px-2 py-1.5">
            <div className="flex items-center justify-between gap-2 font-mono text-[10px] text-silver">
              <span className="truncate">{step.step}. {step.facility_name}</span>
              <span className="shrink-0 tabular-nums text-orange">
                Y {signed(step.yellow_delta)} / G {signed(step.green_delta)}
              </span>
            </div>
            <div className="mt-1 font-mono text-[10px] text-silver-dk">
              {step.yellow_before} {'->'} {step.yellow_after} yellow, {step.green_before} {'->'} {step.green_after} green
            </div>
            {step.warnings.slice(0, 1).map((warning) => (
              <div key={warning} className="mt-1 text-[10px] text-gold">{warning}</div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
