import type { SimulateBuildPlacement } from '@/types/api';

export function BuildOrderTimeline({ steps }: { steps: SimulateBuildPlacement[] }) {
  if (steps.length === 0) {
    return <div className="font-mono text-[11px] text-silver-dk">No build order supplied.</div>;
  }

  return (
    <ol className="space-y-2">
      {steps.map((step, index) => (
        <li key={`${step.facility_template_id}-${index}`} className="flex gap-2">
          <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full border border-orange/45 bg-orange/10 font-mono text-[10px] font-bold text-orange">
            {index + 1}
          </span>
          <div className="min-w-0 flex-1 rounded border border-border/60 bg-bg3/45 px-2 py-1.5">
            <div className="truncate font-mono text-[11px] font-bold text-silver">
              {formatFacility(step.facility_template_id)}
            </div>
            <div className="mt-0.5 flex flex-wrap gap-1.5 font-mono text-[9px] text-silver-dk">
              {step.is_primary_port && <span className="text-orange">Primary port</span>}
              {step.local_body_id && <span>Body {step.local_body_id}</span>}
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}

function formatFacility(value: string): string {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
}
