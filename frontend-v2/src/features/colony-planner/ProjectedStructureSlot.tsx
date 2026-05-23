import type { FacilityTemplate, SimulateBuildPlacement } from '@/types/api';
import { templateLocationKind } from '@/features/system-detail/simulation-preview/structurePickerUtils';
import type { BodyPlannerLane } from './BodySlotPlanner';
import { normalisePlanningEconomy, type PlanningEconomyName } from './planningEconomy';
import { contextualEconomyLabel, structureFamilyLabel, templateDisplayName } from './structurePlanningRules';

export function ProjectedStructureSlot({
  item,
  selected = false,
  onSelect,
}: {
  item: {
    placement: SimulateBuildPlacement;
    index: number;
    template?: FacilityTemplate;
    lane?: BodyPlannerLane | 'unassigned';
  };
  selected?: boolean;
  onSelect?: () => void;
}) {
  const location = item.template ? templateLocationKind(item.template) : 'unknown';
  const locationLabel = item.lane === 'orbital'
    ? 'Orbit'
    : item.lane === 'surface'
      ? 'Surface'
      : item.lane === 'unassigned'
        ? 'Needs lane'
        : location === 'orbital'
          ? 'Orbit'
          : location === 'surface'
            ? 'Surface'
            : location === 'both'
              ? 'Orbit or Surface'
              : 'Unknown';
  const label = item.template ? templateDisplayName(item.template) : item.placement.facility_template_id;
  const economy = normalisePlanningEconomy(item.template?.economy);
  const economyContext = contextualEconomyLabel(item.template);
  const className = [
    'relative flex min-h-[3.75rem] min-w-[11rem] flex-col justify-between overflow-hidden rounded border border-cyan/35 bg-cyan/8 px-2 py-2 pb-3 text-left',
    selected ? 'ring-2 ring-cyan/70 shadow-[0_0_18px_rgba(125,211,252,0.18)]' : '',
    onSelect ? 'hover:border-cyan/65 hover:bg-cyan/12' : '',
  ].filter(Boolean).join(' ');
  const content = (
    <>
      <div className="truncate text-sm font-semibold leading-snug text-cyan">
        #{item.placement.build_order || item.index + 1} {label}
      </div>
      <div className="mt-1 flex flex-wrap gap-1">
        <SlotChip label={locationLabel} />
        {item.template && <SlotChip label={structureFamilyLabel(item.template)} />}
        {item.template?.economy && <SlotChip label={item.template.economy} />}
        {!item.template?.economy && economyContext && <SlotChip label="contextual economy" />}
        <SlotChip label="projected" tone="strong" />
      </div>
      {economyContext && (
        <div data-testid="projected-structure-contextual-economy" className="mt-1 text-[10px] leading-snug text-cyan">
          {economyContext}
        </div>
      )}
      {economy && <StructureEconomyMicroBar economy={economy} />}
    </>
  );

  if (onSelect) {
    return (
      <button
        type="button"
        data-testid={`slot-projected-${item.index}`}
        className={className}
        aria-label={`Projected structure ${label}`}
        aria-pressed={selected}
        onClick={onSelect}
      >
        {content}
      </button>
    );
  }

  return (
    <div
      data-testid={`slot-projected-${item.index}`}
      className={className}
      aria-label={`Projected structure ${label}`}
    >
      {content}
    </div>
  );
}

const ECONOMY_COLORS: Record<PlanningEconomyName, string> = {
  Agriculture: '#4ade80',
  Refinery: '#fbbf24',
  Industrial: '#ff7a14',
  HighTech: '#7dd3fc',
  Military: '#f87171',
  Tourism: '#a78bfa',
  Extraction: '#c8ccd1',
};

function StructureEconomyMicroBar({ economy }: { economy: PlanningEconomyName }) {
  return (
    <span
      data-testid="projected-structure-economy-micro-bar"
      aria-label={`${economy} economy`}
      title={`${economy} economy`}
      className="absolute inset-x-0 bottom-0 h-1 bg-bg4/80 opacity-70"
      style={{ backgroundColor: ECONOMY_COLORS[economy] }}
    />
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
        'rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.1em]',
        tone === 'strong'
          ? 'border-cyan/45 bg-cyan/18 text-cyan'
          : 'border-cyan/30 bg-cyan/12 text-cyan/85',
      ].join(' ')}
    >
      {label}
    </span>
  );
}
