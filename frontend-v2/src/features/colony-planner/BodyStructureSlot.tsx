import type { FacilityTemplate, SimulateBuildPlacement } from '@/types/api';
import { templateLocationKind } from '@/features/system-detail/simulation-preview/structurePickerUtils';

export interface BodyStructureSlotItem {
  placement: SimulateBuildPlacement;
  index: number;
  template?: FacilityTemplate;
  warningCount?: number;
}

export function BodyStructureSlot({
  item,
  selected,
  onSelect,
}: {
  item: BodyStructureSlotItem;
  selected: boolean;
  onSelect: () => void;
}) {
  const location = item.template ? templateLocationKind(item.template) : 'unknown';
  const locationLabel = location === 'both' ? 'orbital or surface' : location;
  const label = item.template?.name ?? item.placement.facility_template_id;

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      data-testid={`slot-planned-${item.index}`}
      className={[
        'flex min-h-[3.75rem] min-w-[11rem] flex-col justify-between rounded border px-2 py-2 text-left transition-colors',
        selected
          ? 'border-orange/70 bg-orange/16 shadow-[0_0_18px_rgba(255,122,20,0.16)]'
          : 'border-border/60 bg-bg3/45 hover:border-orange/45 hover:bg-orange/8',
      ].join(' ')}
    >
      <div className="truncate text-[11px] font-bold text-silver">
        #{item.placement.build_order || item.index + 1} {label}
      </div>
      <div className="mt-1 flex flex-wrap gap-1">
        <SlotChip label={locationLabel} tone="cyan" />
        {item.template?.category && <SlotChip label={item.template.category} />}
        {item.template?.economy && <SlotChip label={item.template.economy} />}
        {item.placement.is_primary_port && <SlotChip label="primary" tone="gold" />}
        {(item.warningCount ?? 0) > 0 && <SlotChip label={`${item.warningCount} warn`} tone="gold" />}
      </div>
    </button>
  );
}

function SlotChip({
  label,
  tone = 'silver',
}: {
  label: string;
  tone?: 'silver' | 'cyan' | 'gold';
}) {
  return (
    <span
      className={[
        'rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.12em]',
        tone === 'cyan'
          ? 'border-cyan/35 bg-cyan/10 text-cyan'
          : tone === 'gold'
            ? 'border-gold/35 bg-gold/10 text-gold'
            : 'border-border/60 bg-bg2/60 text-silver-dk',
      ].join(' ')}
    >
      {label}
    </span>
  );
}
