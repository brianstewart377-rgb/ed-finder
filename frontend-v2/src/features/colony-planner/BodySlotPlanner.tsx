import type { FacilityTemplate, SimulateBuildPlacement, SystemBody } from '@/types/api';
import {
  bodyDisplayName,
  bodyTags,
  getPlacementWarnings,
} from '@/features/system-detail/simulation-preview/buildPlanLayoutUtils';
import { templateLocationKind } from '@/features/system-detail/simulation-preview/structurePickerUtils';
import { BodySlotLane } from './BodySlotLane';
import { BodyStructureSlot, type BodyStructureSlotItem } from './BodyStructureSlot';
import { ProjectedStructureSlot } from './ProjectedStructureSlot';

export type BodyPlannerLane = 'orbital' | 'surface' | 'flex';

export interface BodyPlannerPlacementItem {
  placement: SimulateBuildPlacement;
  index: number;
  template: FacilityTemplate | undefined;
  bodyId: string;
  hasUnknownBody: boolean;
}

export interface BodyPlannerProjectedPlacementItem {
  placement: SimulateBuildPlacement;
  index: number;
  template: FacilityTemplate | undefined;
}

export function BodySlotPlanner({
  body,
  placements,
  projectedPlacements,
  selectedPlacementIndex,
  hasTemplates,
  onSelectPlacement,
  onAddLaneStructure,
}: {
  body: SystemBody;
  placements: BodyPlannerPlacementItem[];
  projectedPlacements: BodyPlannerProjectedPlacementItem[];
  selectedPlacementIndex: number | null;
  hasTemplates: boolean;
  onSelectPlacement: (index: number) => void;
  onAddLaneStructure: (lane: BodyPlannerLane) => void;
}) {
  const tags = bodyTags(body).slice(0, 2);
  const flags = bodyFlags(body);

  const orbitalPlanned = placements.filter((item) => laneForTemplate(item.template) === 'orbital');
  const surfacePlanned = placements.filter((item) => laneForTemplate(item.template) === 'surface');
  const flexPlanned = placements.filter((item) => laneForTemplate(item.template) === 'flex');

  const orbitalProjected = projectedPlacements.filter((item) => laneForTemplate(item.template) === 'orbital');
  const surfaceProjected = projectedPlacements.filter((item) => laneForTemplate(item.template) === 'surface');
  const flexProjected = projectedPlacements.filter((item) => laneForTemplate(item.template) === 'flex');

  const orbitalSlots = readLaneSlotCount(body, 'orbital');
  const surfaceSlots = readLaneSlotCount(body, 'surface');
  const surfaceBlocked = body.is_water_world === true || body.is_landable === false;
  const surfaceBlockedReason = body.is_water_world
    ? 'Surface lane limited: water world.'
    : body.is_landable === false
      ? 'Surface lane limited: non-landable body.'
      : null;

  return (
    <section
      data-testid="body-slot-planner"
      className="mb-3 rounded-chunk-lg border border-orange/35 bg-bg2/60 px-3 py-3"
    >
      <header className="mb-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-orange">Body slot planner</div>
            <h3 className="mt-0.5 truncate text-sm font-bold text-silver">{bodyDisplayName(body)}</h3>
            <div className="mt-1 flex flex-wrap gap-1.5">
              <FactChip label={body.subtype ?? body.body_type ?? 'Body'} />
              {tags.map((tag) => <FactChip key={tag} label={tag} />)}
              {flags.map((flag) => <FactChip key={flag.label} label={flag.label} tone={flag.tone} />)}
              <FactChip label={`${placements.length} planned`} tone={placements.length > 0 ? 'orange' : 'silver'} />
              {projectedPlacements.length > 0 && <FactChip label={`${projectedPlacements.length} projected`} tone="cyan" />}
            </div>
          </div>
        </div>
      </header>

      <BodySchematicStrip
        orbital={{ planned: orbitalPlanned.length, projected: orbitalProjected.length }}
        surface={{ planned: surfacePlanned.length, projected: surfaceProjected.length }}
        flex={{ planned: flexPlanned.length, projected: flexProjected.length }}
      />

      <div className="space-y-2.5">
        <BodySlotLane
          laneKey="orbital"
          label="Orbital"
          helper="Ports, stations, and orbital facilities."
          slotStatus={laneSlotStatusLabel(orbitalSlots, orbitalPlanned.length, orbitalProjected.length)}
          onAdd={() => onAddLaneStructure('orbital')}
          disabled={!hasTemplates}
          disabledReason={!hasTemplates ? 'Facility catalogue loading.' : undefined}
        >
          <LaneSlots
            body={body}
            laneKey="orbital"
            planned={orbitalPlanned}
            projected={orbitalProjected}
            selectedPlacementIndex={selectedPlacementIndex}
            onSelectPlacement={onSelectPlacement}
            emptyText="No orbital structures yet."
          />
        </BodySlotLane>

        <BodySlotLane
          laneKey="surface"
          label="Surface"
          helper="Planetary outposts and ground facilities."
          slotStatus={laneSlotStatusLabel(surfaceSlots, surfacePlanned.length, surfaceProjected.length)}
          onAdd={() => onAddLaneStructure('surface')}
          disabled={!hasTemplates || surfaceBlocked}
          disabledReason={!hasTemplates ? 'Facility catalogue loading.' : surfaceBlockedReason ?? undefined}
        >
          <LaneSlots
            body={body}
            laneKey="surface"
            planned={surfacePlanned}
            projected={surfaceProjected}
            selectedPlacementIndex={selectedPlacementIndex}
            onSelectPlacement={onSelectPlacement}
            emptyText="No surface structures yet."
          />
        </BodySlotLane>

        <BodySlotLane
          laneKey="flex"
          label="Flexible / Unknown"
          helper="Supports dual-location or unresolved location templates."
          slotStatus="slots unknown"
          onAdd={() => onAddLaneStructure('flex')}
          disabled={!hasTemplates}
          disabledReason={!hasTemplates ? 'Facility catalogue loading.' : undefined}
        >
          <LaneSlots
            body={body}
            laneKey="flex"
            planned={flexPlanned}
            projected={flexProjected}
            selectedPlacementIndex={selectedPlacementIndex}
            onSelectPlacement={onSelectPlacement}
            emptyText="No flexible/unknown structures yet."
          />
        </BodySlotLane>
      </div>
    </section>
  );
}

function BodySchematicStrip({
  orbital,
  surface,
  flex,
}: {
  orbital: { planned: number; projected: number };
  surface: { planned: number; projected: number };
  flex: { planned: number; projected: number };
}) {
  const totalPlanned = orbital.planned + surface.planned + flex.planned;
  const totalProjected = orbital.projected + surface.projected + flex.projected;
  return (
    <div
      data-testid="body-slot-graph"
      className="mb-3 rounded border border-border/60 bg-bg3/35 p-2.5"
    >
      <div className="grid gap-3 lg:grid-cols-[13rem_minmax(0,1fr)] lg:items-center">
        <div className="relative mx-auto h-28 w-28">
          <div className="absolute inset-0 rounded-full border border-cyan/35 bg-cyan/5" />
          <div className="absolute left-1/2 top-1/2 h-14 w-14 -translate-x-1/2 -translate-y-1/2 rounded-full border border-orange/45 bg-orange/10 shadow-[0_0_22px_rgba(255,122,20,0.2)]" />
          <div className="absolute left-1/2 top-1/2 h-20 w-20 -translate-x-1/2 -translate-y-1/2 rounded-full border border-cyan/30" />
          <div className="absolute left-1/2 top-1/2 h-24 w-24 -translate-x-1/2 -translate-y-1/2 rounded-full border border-green/25" />
          <div className="absolute bottom-0 left-1/2 -translate-x-1/2 rounded border border-border/60 bg-bg2/60 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.12em] text-silver-dk">
            body core
          </div>
        </div>
        <div className="grid gap-2 sm:grid-cols-3">
          <LaneStatBlock
            label="Orbital ring"
            planned={orbital.planned}
            projected={orbital.projected}
            tone="cyan"
          />
          <LaneStatBlock
            label="Surface grid"
            planned={surface.planned}
            projected={surface.projected}
            tone="green"
          />
          <LaneStatBlock
            label="Flex lane"
            planned={flex.planned}
            projected={flex.projected}
            tone="silver"
          />
        </div>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <FactChip label={`${totalPlanned} planned structures`} tone={totalPlanned > 0 ? 'orange' : 'silver'} />
        {totalProjected > 0 && <FactChip label={`${totalProjected} projected ghosts`} tone="cyan" />}
      </div>
    </div>
  );
}

function LaneStatBlock({
  label,
  planned,
  projected,
  tone,
}: {
  label: string;
  planned: number;
  projected: number;
  tone: 'cyan' | 'green' | 'silver';
}) {
  const toneClass = tone === 'cyan'
    ? 'border-cyan/35 bg-cyan/8 text-cyan'
    : tone === 'green'
      ? 'border-green/35 bg-green/8 text-green'
      : 'border-border/60 bg-bg2/60 text-silver';
  return (
    <div className={['rounded border px-2 py-1.5 font-mono', toneClass].join(' ')}>
      <div className="text-[9px] uppercase tracking-[0.14em]">{label}</div>
      <div className="mt-1 text-[11px] font-bold">
        {planned} planned
      </div>
      <div className="text-[10px] text-silver-dk">
        {projected > 0 ? `+${projected} projected` : 'no projection'}
      </div>
    </div>
  );
}

function LaneSlots({
  body,
  laneKey,
  planned,
  projected,
  selectedPlacementIndex,
  onSelectPlacement,
  emptyText,
}: {
  body: SystemBody;
  laneKey: BodyPlannerLane;
  planned: BodyPlannerPlacementItem[];
  projected: BodyPlannerProjectedPlacementItem[];
  selectedPlacementIndex: number | null;
  onSelectPlacement: (index: number) => void;
  emptyText: string;
}) {
  const hasAny = planned.length > 0 || projected.length > 0;
  if (!hasAny) {
    return (
      <div
        data-testid={`slot-lane-empty-${laneKey}`}
        className="rounded border border-dashed border-border/55 bg-bg3/30 px-3 py-2 font-mono text-[10px] text-silver-dk"
      >
        {emptyText}
      </div>
    );
  }
  return (
    <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3" data-testid={`slot-lane-items-${laneKey}`}>
      {planned.map((item) => (
        <BodyStructureSlot
          key={`planned-${laneKey}-${item.index}-${item.placement.facility_template_id}`}
          item={toStructureSlotItem(item, body)}
          selected={selectedPlacementIndex === item.index}
          onSelect={() => onSelectPlacement(item.index)}
        />
      ))}
      {projected.map((item) => (
        <ProjectedStructureSlot
          key={`projected-${laneKey}-${item.index}-${item.placement.facility_template_id}`}
          item={item}
        />
      ))}
    </div>
  );
}

function toStructureSlotItem(item: BodyPlannerPlacementItem, body: SystemBody): BodyStructureSlotItem {
  return {
    placement: item.placement,
    index: item.index,
    template: item.template,
    warningCount: getPlacementWarnings(item, body).length,
  };
}

function laneForTemplate(template: FacilityTemplate | undefined): BodyPlannerLane {
  if (!template) return 'flex';
  const location = templateLocationKind(template);
  if (location === 'orbital') return 'orbital';
  if (location === 'surface') return 'surface';
  return 'flex';
}

function readLaneSlotCount(body: SystemBody, lane: 'orbital' | 'surface'): number | null {
  const paths = lane === 'orbital'
    ? [
      'orbital_slot_count',
      'orbital_slots',
      'estimated_orbital_slots',
      'architect_observation.orbitalSlotCount',
      'architectObservation.orbitalSlotCount',
      'slot_counts.orbital',
      'slots.orbital',
    ]
    : [
      'ground_slot_count',
      'ground_slots',
      'surface_slot_count',
      'surface_slots',
      'estimated_surface_slots',
      'architect_observation.groundSlotCount',
      'architectObservation.groundSlotCount',
      'slot_counts.surface',
      'slots.surface',
    ];
  for (const path of paths) {
    const value = readPath(body as Record<string, unknown>, path);
    if (typeof value === 'number' && Number.isFinite(value) && value >= 0) {
      return Math.floor(value);
    }
  }
  return null;
}

function readPath(obj: Record<string, unknown>, path: string): unknown {
  return path.split('.').reduce<unknown>((current, part) => {
    if (!current || typeof current !== 'object') return null;
    return (current as Record<string, unknown>)[part];
  }, obj);
}

function laneSlotStatusLabel(slotCount: number | null, plannedCount: number, projectedCount: number) {
  if (slotCount == null) {
    return projectedCount > 0
      ? `${plannedCount} planned + ${projectedCount} projected / slots unknown`
      : 'slots unknown';
  }
  if (projectedCount > 0) {
    return `${plannedCount}/${slotCount} planned (+${projectedCount} projected)`;
  }
  return `${plannedCount}/${slotCount} planned`;
}

function bodyFlags(body: SystemBody): Array<{ label: string; tone: 'silver' | 'green' | 'gold' }> {
  const values: Array<{ label: string; tone: 'silver' | 'green' | 'gold' }> = [];
  if (body.is_landable === true) values.push({ label: 'landable', tone: 'green' });
  if (body.is_landable === false) values.push({ label: 'non-landable', tone: 'gold' });
  if (body.is_water_world) values.push({ label: 'water world', tone: 'gold' });
  if (body.is_terraformable) values.push({ label: 'terraformable', tone: 'green' });
  return values.slice(0, 2);
}

function FactChip({
  label,
  tone = 'silver',
}: {
  label: string;
  tone?: 'silver' | 'orange' | 'cyan' | 'green' | 'gold';
}) {
  return (
    <span
      className={[
        'rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.12em]',
        tone === 'orange'
          ? 'border-orange/35 bg-orange/10 text-orange'
          : tone === 'cyan'
            ? 'border-cyan/35 bg-cyan/10 text-cyan'
            : tone === 'green'
              ? 'border-green/35 bg-green/10 text-green'
              : tone === 'gold'
                ? 'border-gold/35 bg-gold/10 text-gold'
                : 'border-border/60 bg-bg2/60 text-silver-dk',
      ].join(' ')}
    >
      {label}
    </span>
  );
}
