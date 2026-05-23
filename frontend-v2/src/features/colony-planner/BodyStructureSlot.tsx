import type { FacilityTemplate, SimulateBuildPlacement } from '@/types/api';
import { templateLocationKind } from '@/features/system-detail/simulation-preview/structurePickerUtils';
import type { BodyPlannerLane } from './BodySlotPlanner';
import { normalisePlanningEconomy, type PlanningEconomyName } from './planningEconomy';
import { contextualEconomyLabel, contextualRoleLabel, structureFamilyLabel, templateDisplayName } from './structurePlanningRules';

export interface BodyStructureSlotItem {
  placement: SimulateBuildPlacement;
  index: number;
  template?: FacilityTemplate;
  lane?: BodyPlannerLane | 'unassigned';
  warningCount?: number;
  warningLabels?: string[];
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
  const roleLabel = contextualRoleLabel(item.template, item.placement);
  const warningLabels = item.warningLabels ?? [];

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      data-testid={`slot-planned-${item.index}`}
      className={[
        'relative flex min-h-[3.75rem] min-w-[11rem] flex-col justify-between overflow-hidden rounded border px-2 py-2 pb-3 text-left transition-colors',
        selected
          ? 'border-orange/70 bg-orange/16 shadow-[0_0_18px_rgba(255,122,20,0.16)]'
          : 'border-border/60 bg-bg3/45 hover:border-orange/45 hover:bg-orange/8',
      ].join(' ')}
    >
      <div className="truncate text-sm font-semibold leading-snug text-silver">
        #{item.placement.build_order || item.index + 1} {label}
      </div>
      <div className="mt-1 flex flex-wrap gap-1">
        <SlotChip label={locationLabel} tone="cyan" />
        {item.template && <SlotChip label={structureFamilyLabel(item.template)} />}
        {item.template?.category && <SlotChip label={item.template.category} />}
        {item.template?.economy && <SlotChip label={item.template.economy} />}
        {!item.template?.economy && economyContext && <SlotChip label="contextual economy" tone="cyan" />}
        {roleLabel && <SlotChip label={roleLabel} tone="cyan" />}
        {item.placement.is_primary_port && <SlotChip label="primary" tone="gold" />}
        {(item.warningCount ?? 0) > 0 && <SlotChip label={`${item.warningCount} warn`} tone="gold" />}
      </div>
      {economyContext && (
        <div data-testid="body-structure-contextual-economy" className="mt-1 text-[10px] leading-snug text-cyan">
          {economyContext}
        </div>
      )}
      {warningLabels.length > 0 && (
        <div data-testid="body-structure-prerequisite-warning" className="mt-1 text-[10px] leading-snug text-gold">
          Missing prerequisite: {warningLabels.join('; ')}
        </div>
      )}
      {economy && <StructureEconomyMicroBar economy={economy} />}
    </button>
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
      data-testid="body-structure-economy-micro-bar"
      aria-label={`${economy} economy`}
      title={`${economy} economy`}
      className="absolute inset-x-0 bottom-0 h-1 bg-bg4/80"
      style={{ backgroundColor: ECONOMY_COLORS[economy] }}
    />
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
        'rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.1em]',
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
