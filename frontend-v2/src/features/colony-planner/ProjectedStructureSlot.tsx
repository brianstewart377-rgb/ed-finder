import type { FacilityTemplate, SimulateBuildPlacement } from '@/types/api';
import { templateLocationKind } from '@/features/system-detail/simulation-preview/structurePickerUtils';

export function ProjectedStructureSlot({
  item,
}: {
  item: {
    placement: SimulateBuildPlacement;
    index: number;
    template?: FacilityTemplate;
  };
}) {
  const location = item.template ? templateLocationKind(item.template) : 'unknown';
  const locationLabel = location === 'both' ? 'orbital or surface' : location;
  const label = item.template?.name ?? item.placement.facility_template_id;
  return (
    <div
      data-testid={`slot-projected-${item.index}`}
      className="flex min-h-[3.75rem] min-w-[11rem] flex-col justify-between rounded border border-cyan/35 bg-cyan/8 px-2 py-2 text-left"
      aria-label={`Projected structure ${label}`}
    >
      <div className="truncate text-[11px] font-bold text-cyan">
        #{item.placement.build_order || item.index + 1} {label}
      </div>
      <div className="mt-1 flex flex-wrap gap-1">
        <SlotChip label={locationLabel} />
        <SlotChip label="projected" tone="strong" />
      </div>
    </div>
  );
}

function SlotChip({
  label,
  tone = 'default',
}: {
  label: string;
  tone?: 'default' | 'strong';
}) {
  return (
    <span
      className={[
        'rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.12em]',
        tone === 'strong'
          ? 'border-cyan/45 bg-cyan/18 text-cyan'
          : 'border-cyan/30 bg-cyan/12 text-cyan/85',
      ].join(' ')}
    >
      {label}
    </span>
  );
}
