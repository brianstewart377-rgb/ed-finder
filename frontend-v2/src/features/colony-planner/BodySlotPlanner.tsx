import type { BodySlotPrediction, FacilityTemplate, SimulateBuildPlacement, SystemBody } from '@/types/api';
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
  slotPrediction,
  placements,
  projectedPlacements,
  selectedPlacementIndex,
  hasTemplates,
  onSelectPlacement,
  onAddLaneStructure,
}: {
  body: SystemBody;
  slotPrediction: BodySlotPrediction | null;
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

  const orbitalSlots = readLaneSlotCount(slotPrediction, 'orbital');
  const surfaceSlots = readLaneSlotCount(slotPrediction, 'surface');
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

      <BodyRingMap
        orbitalPlanned={orbitalPlanned}
        surfacePlanned={surfacePlanned}
        flexPlanned={flexPlanned}
        orbitalProjected={orbitalProjected}
        surfaceProjected={surfaceProjected}
        flexProjected={flexProjected}
        selectedPlacementIndex={selectedPlacementIndex}
        hasTemplates={hasTemplates}
        surfaceBlocked={surfaceBlocked}
        onSelectPlacement={onSelectPlacement}
        onAddLaneStructure={onAddLaneStructure}
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

function BodyRingMap({
  orbitalPlanned,
  surfacePlanned,
  flexPlanned,
  orbitalProjected,
  surfaceProjected,
  flexProjected,
  selectedPlacementIndex,
  hasTemplates,
  surfaceBlocked,
  onSelectPlacement,
  onAddLaneStructure,
}: {
  orbitalPlanned: BodyPlannerPlacementItem[];
  surfacePlanned: BodyPlannerPlacementItem[];
  flexPlanned: BodyPlannerPlacementItem[];
  orbitalProjected: BodyPlannerProjectedPlacementItem[];
  surfaceProjected: BodyPlannerProjectedPlacementItem[];
  flexProjected: BodyPlannerProjectedPlacementItem[];
  selectedPlacementIndex: number | null;
  hasTemplates: boolean;
  surfaceBlocked: boolean;
  onSelectPlacement: (index: number) => void;
  onAddLaneStructure: (lane: BodyPlannerLane) => void;
}) {
  const orbitalNodes = [
    ...orbitalPlanned.map((item) => ({ kind: 'planned' as const, id: `p-${item.index}`, item })),
    ...orbitalProjected.map((item, i) => ({ kind: 'projected' as const, id: `g-${i}-${item.placement.facility_template_id}`, item })),
  ];
  const surfaceNodes = [
    ...surfacePlanned.map((item) => ({ kind: 'planned' as const, id: `p-${item.index}`, item })),
    ...surfaceProjected.map((item, i) => ({ kind: 'projected' as const, id: `g-${i}-${item.placement.facility_template_id}`, item })),
  ];
  const flexNodes = [
    ...flexPlanned.map((item) => ({ kind: 'planned' as const, id: `p-${item.index}`, item })),
    ...flexProjected.map((item, i) => ({ kind: 'projected' as const, id: `g-${i}-${item.placement.facility_template_id}`, item })),
  ];

  const orbitalSlots = ringSlots(orbitalNodes.length, 130);
  const surfaceSlots = ringSlots(surfaceNodes.length, 92);
  const flexSlots = railSlots(flexNodes.length);

  return (
    <section data-testid="body-slot-graph" className="mb-3 rounded border border-border/60 bg-bg3/35 px-2 py-3">
      <div className="relative mx-auto min-h-[23rem] max-w-[56rem]">
        <div className="absolute left-1/2 top-[8.9rem] h-[16rem] w-[16rem] -translate-x-1/2 -translate-y-1/2 rounded-full border border-cyan/35" />
        <div className="absolute left-1/2 top-[8.9rem] h-[11.4rem] w-[11.4rem] -translate-x-1/2 -translate-y-1/2 rounded-full border border-green/35" />
        <div className="absolute left-1/2 top-[8.9rem] h-[6.4rem] w-[6.4rem] -translate-x-1/2 -translate-y-1/2 rounded-full border border-orange/45 bg-orange/10 shadow-[0_0_30px_rgba(255,122,20,0.2)]" />

        <div className="absolute left-1/2 top-[8.9rem] -translate-x-1/2 -translate-y-1/2 text-center">
          <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">Body core</div>
        </div>

        {orbitalNodes.map((node, index) => (
          <RingPlacementToken
            key={`orb-${node.id}`}
            lane="orbital"
            left={`calc(50% + ${orbitalSlots[index].x}px)`}
            top={`calc(8.9rem + ${orbitalSlots[index].y}px)`}
            label={slotLabel(node.item)}
            projected={node.kind === 'projected'}
            selected={node.kind === 'planned' && selectedPlacementIndex === node.item.index}
            onClick={node.kind === 'planned' ? () => onSelectPlacement(node.item.index) : undefined}
          />
        ))}

        {surfaceNodes.map((node, index) => (
          <RingPlacementToken
            key={`surf-${node.id}`}
            lane="surface"
            left={`calc(50% + ${surfaceSlots[index].x}px)`}
            top={`calc(8.9rem + ${surfaceSlots[index].y}px)`}
            label={slotLabel(node.item)}
            projected={node.kind === 'projected'}
            selected={node.kind === 'planned' && selectedPlacementIndex === node.item.index}
            onClick={node.kind === 'planned' ? () => onSelectPlacement(node.item.index) : undefined}
          />
        ))}

        <div className="absolute left-1/2 top-[19.2rem] h-px w-[86%] -translate-x-1/2 bg-border/60" />
        {flexNodes.map((node, index) => (
          <RingPlacementToken
            key={`flex-${node.id}`}
            lane="flex"
            left={`${flexSlots[index]}%`}
            top="20rem"
            label={slotLabel(node.item)}
            projected={node.kind === 'projected'}
            selected={node.kind === 'planned' && selectedPlacementIndex === node.item.index}
            onClick={node.kind === 'planned' ? () => onSelectPlacement(node.item.index) : undefined}
          />
        ))}

        <LaneAddNode
          lane="orbital"
          left="50%"
          top="0.9rem"
          enabled={hasTemplates}
          disabledReason={!hasTemplates ? 'Facility catalogue loading.' : undefined}
          onAdd={() => onAddLaneStructure('orbital')}
        />
        <LaneAddNode
          lane="surface"
          left="calc(50% + 5.7rem)"
          top="8.9rem"
          enabled={hasTemplates && !surfaceBlocked}
          disabledReason={surfaceBlocked ? 'Surface blocked for this body.' : (!hasTemplates ? 'Facility catalogue loading.' : undefined)}
          onAdd={() => onAddLaneStructure('surface')}
        />
        <LaneAddNode
          lane="flex"
          left="50%"
          top="20.8rem"
          enabled={hasTemplates}
          disabledReason={!hasTemplates ? 'Facility catalogue loading.' : undefined}
          onAdd={() => onAddLaneStructure('flex')}
        />

        <div className="absolute left-2 top-2 rounded border border-cyan/35 bg-cyan/8 px-2 py-1 font-mono text-[9px] uppercase tracking-[0.12em] text-cyan">Orbital ring</div>
        <div className="absolute left-2 top-8 rounded border border-green/35 bg-green/8 px-2 py-1 font-mono text-[9px] uppercase tracking-[0.12em] text-green">Surface ring</div>
        <div className="absolute left-2 top-[19.6rem] rounded border border-border/60 bg-bg2/60 px-2 py-1 font-mono text-[9px] uppercase tracking-[0.12em] text-silver-dk">Flex lane</div>
      </div>
    </section>
  );
}

function ringSlots(count: number, radius: number) {
  if (count <= 0) return [];
  const spread = Math.min(320, Math.max(140, 50 * count));
  const start = -90 - spread / 2;
  const step = count === 1 ? 0 : spread / (count - 1);
  return new Array(count).fill(null).map((_, index) => {
    const angle = (start + step * index) * (Math.PI / 180);
    return {
      x: Math.cos(angle) * radius,
      y: Math.sin(angle) * radius,
    };
  });
}

function railSlots(count: number) {
  if (count <= 0) return [];
  const left = 24;
  const right = 76;
  if (count === 1) return [50];
  const step = (right - left) / (count - 1);
  return new Array(count).fill(null).map((_, index) => left + step * index);
}

function slotLabel(item: BodyPlannerPlacementItem | BodyPlannerProjectedPlacementItem) {
  const raw = item.template?.name ?? item.placement.facility_template_id;
  const clean = raw.replace(/[^A-Za-z0-9 ]/g, ' ').trim();
  if (!clean) return '??';
  const words = clean.split(/\s+/).slice(0, 2);
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return `${words[0][0] ?? ''}${words[1][0] ?? ''}`.toUpperCase();
}

function RingPlacementToken({
  lane,
  left,
  top,
  label,
  projected,
  selected,
  onClick,
}: {
  lane: BodyPlannerLane;
  left: string;
  top: string;
  label: string;
  projected: boolean;
  selected: boolean;
  onClick?: () => void;
}) {
  const toneClass = projected
    ? 'border-cyan/45 bg-cyan/14 text-cyan'
    : lane === 'orbital'
      ? 'border-cyan/45 bg-cyan/8 text-cyan'
      : lane === 'surface'
        ? 'border-green/45 bg-green/10 text-green'
        : 'border-border/70 bg-bg2/70 text-silver';

  const selectedClass = selected
    ? 'shadow-[0_0_20px_rgba(255,122,20,0.3)] ring-2 ring-orange/70'
    : '';

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        style={{ left, top, transform: 'translate(-50%, -50%)' }}
        className={[
          'absolute z-10 grid h-8 w-8 place-items-center rounded-full border font-mono text-[9px] font-bold uppercase tracking-[0.08em] transition-transform hover:scale-105',
          toneClass,
          selectedClass,
        ].join(' ')}
      >
        {label}
      </button>
    );
  }

  return (
    <div
      style={{ left, top, transform: 'translate(-50%, -50%)' }}
      className={[
        'absolute z-10 grid h-8 w-8 place-items-center rounded-full border font-mono text-[9px] font-bold uppercase tracking-[0.08em]',
        toneClass,
      ].join(' ')}
    >
      {label}
    </div>
  );
}

function LaneAddNode({
  lane,
  left,
  top,
  enabled,
  disabledReason,
  onAdd,
}: {
  lane: BodyPlannerLane;
  left: string;
  top: string;
  enabled: boolean;
  disabledReason?: string;
  onAdd: () => void;
}) {
  const label = lane === 'orbital'
    ? 'Add orbital structure'
    : lane === 'surface'
      ? 'Add surface structure'
      : 'Add flexible/unknown structure';
  return (
    <button
      type="button"
      aria-label={label}
      title={enabled ? label : disabledReason ?? label}
      disabled={!enabled}
      onClick={onAdd}
      style={{ left, top, transform: 'translate(-50%, -50%)' }}
      className={[
        'absolute z-20 grid h-8 w-8 place-items-center rounded-full border text-sm font-bold transition-transform',
        enabled
          ? 'border-orange/55 bg-orange/18 text-orange hover:scale-110'
          : 'cursor-not-allowed border-gold/35 bg-gold/10 text-gold/70',
      ].join(' ')}
    >
      +
    </button>
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

function readLaneSlotCount(
  prediction: BodySlotPrediction | null,
  lane: 'orbital' | 'surface',
): number | null {
  const raw = lane === 'orbital'
    ? prediction?.predicted_orbital_slots
    : prediction?.predicted_ground_slots;
  if (typeof raw !== 'number' || !Number.isFinite(raw) || raw < 0) {
    return null;
  }
  return Math.floor(raw);
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
