import type { OptimiserCandidatePlacement } from '@/types/api';

export function OptimiserPlacementList({ placements }: { placements: OptimiserCandidatePlacement[] }) {
  if (placements.length === 0) {
    return (
      <div className="rounded border border-border/60 bg-bg3/25 px-3 py-2 text-[11px] text-silver-dk">
        No placements are listed for this suggested build.
      </div>
    );
  }

  return (
    <ol className="space-y-1.5">
      {[...placements].sort((a, b) => a.build_order - b.build_order).map((placement) => (
        <li
          key={`${placement.build_order}-${placement.facility_template_id}-${placement.local_body_id ?? 'system'}`}
          className="rounded border border-border/50 bg-bg3/20 px-3 py-2 font-mono text-[11px] text-silver"
        >
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-orange">#{placement.build_order}</span>
            {placement.is_primary_port && (
              <span className="rounded border border-cyan/30 bg-cyan/10 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.12em] text-cyan">
                Primary port
              </span>
            )}
            <span>{placement.facility_template_id}</span>
          </div>
          <div className="mt-1 text-[10px] text-silver-dk">
            Body: {placement.local_body_id ?? 'system-level / unassigned'}
          </div>
        </li>
      ))}
    </ol>
  );
}
