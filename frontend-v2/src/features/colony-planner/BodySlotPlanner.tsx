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
import { PlanningEconomyStrip } from './PlanningEconomyStrip';
import { buildPlanningEconomyLedger } from './planningEconomy';
import { ESTIMATED_SLOT_LAYOUT_DISCLAIMER, resolveSlotCapacity, type BodyDataSlotEstimate } from './slotCapacityFallback';

export type BodyPlannerLane = 'orbital' | 'surface';

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
  bodyDataSlotEstimate,
  placements,
  projectedPlacements,
  selectedPlacementIndex,
  selectedProjectedPlacementIndex,
  hasTemplates,
  onSelectPlacement,
  onSelectProjectedPlacement,
  onAddLaneStructure,
}: {
  body: SystemBody;
  slotPrediction: BodySlotPrediction | null;
  bodyDataSlotEstimate?: BodyDataSlotEstimate | null;
  placements: BodyPlannerPlacementItem[];
  projectedPlacements: BodyPlannerProjectedPlacementItem[];
  selectedPlacementIndex: number | null;
  selectedProjectedPlacementIndex: number | null;
  hasTemplates: boolean;
  onSelectPlacement: (index: number) => void;
  onSelectProjectedPlacement: (index: number) => void;
  onAddLaneStructure: (lane: BodyPlannerLane) => void;
}) {
  const tags = bodyTags(body).slice(0, 2);
  const flags = bodyFlags(body);

  const orbitalPlanned = placements.filter((item) => laneForTemplate(item.template, body) === 'orbital');
  const surfacePlanned = placements.filter((item) => laneForTemplate(item.template, body) === 'surface');

  const orbitalProjected = projectedPlacements.filter((item) => laneForTemplate(item.template, body) === 'orbital');
  const surfaceProjected = projectedPlacements.filter((item) => laneForTemplate(item.template, body) === 'surface');

  const orbitalCapacity = resolveSlotCapacity(body, slotPrediction, 'orbital', bodyDataSlotEstimate);
  const surfaceCapacity = resolveSlotCapacity(body, slotPrediction, 'surface', bodyDataSlotEstimate);
  const orbitalSlots = orbitalCapacity.value;
  const surfaceSlots = surfaceCapacity.value;
  const hasEstimatedSlots = orbitalCapacity.estimated || surfaceCapacity.estimated;
  const surfaceBlocked = body.is_water_world === true || body.is_landable === false;
  const surfaceBlockedReason = body.is_water_world
    ? 'Surface limited: water world.'
    : body.is_landable === false
      ? 'Surface limited: non-landable body.'
      : null;
  const occupiedSlots = {
    orbital: orbitalPlanned.length + orbitalProjected.length,
    surface: surfacePlanned.length + surfaceProjected.length,
  };
  const economyLedger = buildPlanningEconomyLedger({
    placements: placements.map((item) => item.placement),
    projectedPlacements: projectedPlacements.map((item) => item.placement),
    templates: [
      ...placements.map((item) => item.template).filter((template): template is FacilityTemplate => Boolean(template)),
      ...projectedPlacements.map((item) => item.template).filter((template): template is FacilityTemplate => Boolean(template)),
    ],
  });

  return (
    <section
      data-testid="body-slot-planner"
      data-readability="stage17k"
      className="mb-3 rounded-chunk-lg border border-orange/35 bg-bg2/60 px-3 py-3 text-sm leading-relaxed"
    >
      <header className="mb-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="font-mono text-[11px] uppercase tracking-[0.12em] text-orange">Body slot planner</div>
            <div className="mt-0.5 flex min-w-0 flex-wrap items-center gap-2">
              <h3 className="truncate text-base font-semibold text-silver" data-testid="selected-body-readable-title">{bodyDisplayName(body)}</h3>
              <SlotCapacityDots
                orbitalCapacity={orbitalSlots}
                surfaceCapacity={surfaceSlots}
                occupiedOrbital={occupiedSlots.orbital}
                occupiedSurface={occupiedSlots.surface}
                testId="selected-body-slot-indicators"
              />
            </div>
            {hasEstimatedSlots && (
              <p data-testid="body-slot-estimated-disclaimer" className="mt-1 font-mono text-[10px] italic text-gold">
                {ESTIMATED_SLOT_LAYOUT_DISCLAIMER}
              </p>
            )}
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
        orbitalCapacity={orbitalSlots}
        surfaceCapacity={surfaceSlots}
        orbitalPlanned={orbitalPlanned}
        surfacePlanned={surfacePlanned}
        orbitalProjected={orbitalProjected}
        surfaceProjected={surfaceProjected}
        selectedPlacementIndex={selectedPlacementIndex}
        selectedProjectedPlacementIndex={selectedProjectedPlacementIndex}
        hasTemplates={hasTemplates}
        surfaceBlocked={surfaceBlocked}
        onSelectPlacement={onSelectPlacement}
        onSelectProjectedPlacement={onSelectProjectedPlacement}
        onAddLaneStructure={onAddLaneStructure}
      />

      <div className="mb-3">
        <PlanningEconomyStrip ledger={economyLedger} testId="body-planning-economy" />
      </div>

      <div className="space-y-2.5">
        <BodySlotLane
          laneKey="orbital"
          label="Orbit"
          helper="Ports, stations, and facilities in orbit."
          slotStatus={laneSlotStatusLabel(orbitalSlots, orbitalPlanned.length, orbitalProjected.length)}
          onAdd={() => onAddLaneStructure('orbital')}
          disabled={!hasTemplates}
          disabledReason={!hasTemplates ? 'Facility catalogue loading.' : undefined}
        >
          <LaneCapacityMap
            laneKey="orbital"
            capacity={orbitalSlots}
            planned={orbitalPlanned}
            projected={orbitalProjected}
            selectedPlacementIndex={selectedPlacementIndex}
            selectedProjectedPlacementIndex={selectedProjectedPlacementIndex}
            onSelectPlacement={onSelectPlacement}
            onSelectProjectedPlacement={onSelectProjectedPlacement}
            onAddEmptySlot={hasTemplates ? () => onAddLaneStructure('orbital') : undefined}
          />
          <LaneSlots
            body={body}
            laneKey="orbital"
            planned={orbitalPlanned}
            projected={orbitalProjected}
            selectedPlacementIndex={selectedPlacementIndex}
            selectedProjectedPlacementIndex={selectedProjectedPlacementIndex}
            onSelectPlacement={onSelectPlacement}
            onSelectProjectedPlacement={onSelectProjectedPlacement}
            emptyText="No orbit structures yet."
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
          <LaneCapacityMap
            laneKey="surface"
            capacity={surfaceSlots}
            planned={surfacePlanned}
            projected={surfaceProjected}
            selectedPlacementIndex={selectedPlacementIndex}
            selectedProjectedPlacementIndex={selectedProjectedPlacementIndex}
            onSelectPlacement={onSelectPlacement}
            onSelectProjectedPlacement={onSelectProjectedPlacement}
            onAddEmptySlot={hasTemplates && !surfaceBlocked ? () => onAddLaneStructure('surface') : undefined}
          />
          <LaneSlots
            body={body}
            laneKey="surface"
            planned={surfacePlanned}
            projected={surfaceProjected}
            selectedPlacementIndex={selectedPlacementIndex}
            selectedProjectedPlacementIndex={selectedProjectedPlacementIndex}
            onSelectPlacement={onSelectPlacement}
            onSelectProjectedPlacement={onSelectProjectedPlacement}
            emptyText="No surface structures yet."
          />
        </BodySlotLane>

      </div>
    </section>
  );
}

function BodyRingMap({
  orbitalCapacity,
  surfaceCapacity,
  orbitalPlanned,
  surfacePlanned,
  orbitalProjected,
  surfaceProjected,
  selectedPlacementIndex,
  selectedProjectedPlacementIndex,
  hasTemplates,
  surfaceBlocked,
  onSelectPlacement,
  onSelectProjectedPlacement,
  onAddLaneStructure,
}: {
  orbitalCapacity: number | null;
  surfaceCapacity: number | null;
  orbitalPlanned: BodyPlannerPlacementItem[];
  surfacePlanned: BodyPlannerPlacementItem[];
  orbitalProjected: BodyPlannerProjectedPlacementItem[];
  surfaceProjected: BodyPlannerProjectedPlacementItem[];
  selectedPlacementIndex: number | null;
  selectedProjectedPlacementIndex: number | null;
  hasTemplates: boolean;
  surfaceBlocked: boolean;
  onSelectPlacement: (index: number) => void;
  onSelectProjectedPlacement: (index: number) => void;
  onAddLaneStructure: (lane: BodyPlannerLane) => void;
}) {
  const orbitRadius = scaledBandRadius(ORBIT_BAND_RADIUS);
  const surfaceRadius = scaledBandRadius(SURFACE_BAND_RADIUS);
  const orbitalNodes = buildRingNodes({
    lane: 'orbital',
    capacity: orbitalCapacity,
    planned: orbitalPlanned,
    projected: orbitalProjected,
    selectedPlacementIndex,
    selectedProjectedPlacementIndex,
    canAdd: hasTemplates,
    onAdd: () => onAddLaneStructure('orbital'),
    onSelectPlacement,
    onSelectProjectedPlacement,
  });
  const surfaceNodes = buildRingNodes({
    lane: 'surface',
    capacity: surfaceCapacity,
    planned: surfacePlanned,
    projected: surfaceProjected,
    selectedPlacementIndex,
    selectedProjectedPlacementIndex,
    canAdd: hasTemplates && !surfaceBlocked,
    onAdd: () => onAddLaneStructure('surface'),
    onSelectPlacement,
    onSelectProjectedPlacement,
  });
  const orbitalSlots = ringSlots(orbitalNodes.length, orbitRadius);
  const surfaceSlots = ringSlots(surfaceNodes.length, surfaceRadius);
  const orbitAddPoint = polarPoint(orbitRadius, -90);
  const surfaceAddPoint = polarPoint(surfaceRadius, 0);

  return (
    <section data-testid="body-slot-graph" className="mb-3 rounded border border-border/60 bg-bg3/35 px-2 py-3">
      <div className="relative mx-auto min-h-[18.5rem] max-w-[56rem]">
        <svg
          aria-hidden="true"
          viewBox="0 0 320 320"
          className="pointer-events-none absolute left-1/2 top-[8.9rem] h-[16rem] w-[16rem] -translate-x-1/2 -translate-y-1/2 overflow-visible"
        >
          <circle cx="160" cy="160" r={ORBIT_BAND_RADIUS} fill="none" stroke="#00c8ff" strokeWidth="24" strokeOpacity="0.46" />
          <circle cx="160" cy="160" r={SURFACE_BAND_RADIUS} fill="none" stroke="#ff9f1a" strokeWidth="16" strokeOpacity="0.48" />
        </svg>
        <div className="pointer-events-none absolute left-1/2 top-[8.9rem] h-[6.4rem] w-[6.4rem] -translate-x-1/2 -translate-y-1/2 rounded-full border border-orange/45 bg-orange/10 shadow-[0_0_30px_rgba(255,122,20,0.2)]" />

        <div className="pointer-events-none absolute left-1/2 top-[8.9rem] -translate-x-1/2 -translate-y-1/2 text-center">
          <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">Body core</div>
        </div>

        {orbitalNodes.map((node, index) => (
          <RingPlacementToken
            key={`orb-${node.id}`}
            lane="orbital"
            left={ringLeft(orbitalSlots[index].x)}
            top={ringTop(orbitalSlots[index].y)}
            label={node.label}
            title={node.title}
            kind={node.kind}
            selected={node.selected}
            testId={`ring-orbital-slot-${index}`}
            onClick={node.onClick}
          />
        ))}

        {surfaceNodes.map((node, index) => (
          <RingPlacementToken
            key={`surf-${node.id}`}
            lane="surface"
            left={ringLeft(surfaceSlots[index].x)}
            top={ringTop(surfaceSlots[index].y)}
            label={node.label}
            title={node.title}
            kind={node.kind}
            selected={node.selected}
            testId={`ring-surface-slot-${index}`}
            onClick={node.onClick}
          />
        ))}

        {orbitalNodes.length === 0 && (
          <LaneAddNode
            lane="orbital"
            left={ringLeft(orbitAddPoint.x)}
            top={ringTop(orbitAddPoint.y)}
            enabled={hasTemplates}
            disabledReason={!hasTemplates ? 'Facility catalogue loading.' : undefined}
            onAdd={() => onAddLaneStructure('orbital')}
          />
        )}
        {surfaceNodes.length === 0 && (
          <LaneAddNode
            lane="surface"
            left={ringLeft(surfaceAddPoint.x)}
            top={ringTop(surfaceAddPoint.y)}
            enabled={hasTemplates && !surfaceBlocked}
            disabledReason={surfaceBlocked ? 'Surface blocked for this body.' : (!hasTemplates ? 'Facility catalogue loading.' : undefined)}
            onAdd={() => onAddLaneStructure('surface')}
          />
        )}

        <div className="pointer-events-none absolute left-2 top-2 rounded border border-cyan/35 bg-cyan/8 px-2 py-1 font-mono text-[9px] uppercase tracking-[0.12em] text-cyan">Orbit band</div>
        <div className="pointer-events-none absolute left-2 top-8 rounded border border-gold/35 bg-gold/8 px-2 py-1 font-mono text-[9px] uppercase tracking-[0.12em] text-gold">Surface band</div>
      </div>
    </section>
  );
}

const RING_CENTER_TOP = '8.9rem';
const RING_VIEWBOX_SIZE = 320;
const RING_RENDER_SIZE_PX = 256;
const ORBIT_BAND_RADIUS = 130;
const SURFACE_BAND_RADIUS = 92;

type RingNodeKind = 'planned' | 'projected' | 'empty';

interface RingNode {
  id: string;
  kind: RingNodeKind;
  label: string;
  title: string;
  selected: boolean;
  onClick?: () => void;
}

function buildRingNodes({
  lane,
  capacity,
  planned,
  projected,
  selectedPlacementIndex,
  selectedProjectedPlacementIndex,
  canAdd,
  onAdd,
  onSelectPlacement,
  onSelectProjectedPlacement,
}: {
  lane: BodyPlannerLane;
  capacity: number | null;
  planned: BodyPlannerPlacementItem[];
  projected: BodyPlannerProjectedPlacementItem[];
  selectedPlacementIndex: number | null;
  selectedProjectedPlacementIndex: number | null;
  canAdd: boolean;
  onAdd: () => void;
  onSelectPlacement: (index: number) => void;
  onSelectProjectedPlacement: (index: number) => void;
}): RingNode[] {
  const structures = [
    ...planned.map((item) => structureRingNode(lane, item, selectedPlacementIndex === item.index, () => onSelectPlacement(item.index))),
    ...projected.map((item) => structureRingNode(lane, item, selectedProjectedPlacementIndex === item.index, () => onSelectProjectedPlacement(item.index), true)),
  ];

  if (capacity == null) return structures;
  if (capacity <= 0) return structures;

  const nodes = Array.from({ length: capacity }, (_unused, index) => {
    if (index < structures.length) return structures[index];
    return {
      id: `${lane}-empty-${index}`,
      kind: 'empty' as const,
      label: '+',
      title: canAdd
        ? `Add ${lane === 'orbital' ? 'orbit' : 'surface'} structure to empty slot`
        : 'Empty slot',
      selected: false,
      onClick: canAdd ? onAdd : undefined,
    };
  });

  return structures.length > capacity
    ? [...nodes, ...structures.slice(capacity)]
    : nodes;
}

function structureRingNode(
  lane: BodyPlannerLane,
  item: BodyPlannerPlacementItem | BodyPlannerProjectedPlacementItem,
  selected: boolean,
  onClick: () => void,
  projected = false,
): RingNode {
  return {
    id: `${lane}-${projected ? 'projected' : 'planned'}-${item.index}-${item.placement.facility_template_id}`,
    kind: projected ? 'projected' : 'planned',
    label: slotLabel(item),
    title: item.template?.name ?? item.placement.facility_template_id,
    selected,
    onClick,
  };
}

function scaledBandRadius(viewBoxRadius: number) {
  return viewBoxRadius * (RING_RENDER_SIZE_PX / RING_VIEWBOX_SIZE);
}

function polarPoint(radius: number, angleDegrees: number) {
  const angle = angleDegrees * (Math.PI / 180);
  return {
    x: Math.cos(angle) * radius,
    y: Math.sin(angle) * radius,
  };
}

function ringSlots(count: number, radius: number) {
  if (count <= 0) return [];
  if (count === 1) return [polarPoint(radius, -90)];
  const spread = Math.min(320, Math.max(140, 50 * count));
  const start = -90 - spread / 2;
  const step = spread / (count - 1);
  return new Array(count).fill(null).map((_, index) => polarPoint(radius, start + step * index));
}

function ringLeft(x: number) {
  return `calc(50% + ${formatCoordinate(x)})`;
}

function ringTop(y: number) {
  return `calc(${RING_CENTER_TOP} + ${formatCoordinate(y)})`;
}

function formatCoordinate(value: number) {
  return `${Math.round(value * 10) / 10}px`;
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
  title,
  kind,
  selected,
  testId,
  onClick,
}: {
  lane: BodyPlannerLane;
  left: string;
  top: string;
  label: string;
  title: string;
  kind: RingNodeKind;
  selected: boolean;
  testId: string;
  onClick?: () => void;
}) {
  const toneClass = kind === 'projected'
    ? 'border-cyan/45 bg-cyan/14 text-cyan'
    : kind === 'empty'
      ? lane === 'orbital'
        ? 'border-cyan/70 bg-cyan/18 text-cyan'
        : 'border-orange/70 bg-orange/18 text-orange-lt'
    : lane === 'orbital'
      ? 'border-cyan/70 bg-cyan/14 text-cyan'
      : 'border-orange/75 bg-orange/20 text-orange-lt';

  const selectedClass = selected
    ? 'shadow-[0_0_20px_rgba(255,122,20,0.3)] ring-2 ring-orange/70'
    : '';

  if (onClick) {
    return (
      <button
        type="button"
        data-testid={testId}
        title={title}
        aria-label={title}
        onClick={onClick}
        style={{ left, top, transform: 'translate(-50%, -50%)' }}
        className={[
          'absolute z-30 grid h-8 w-8 place-items-center rounded-full border font-mono text-[9px] font-bold uppercase tracking-[0.08em] transition-transform hover:scale-105',
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
      data-testid={testId}
      title={title}
      style={{ left, top, transform: 'translate(-50%, -50%)' }}
      className={[
        'absolute z-30 grid h-8 w-8 place-items-center rounded-full border font-mono text-[9px] font-bold uppercase tracking-[0.08em]',
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
    ? 'Add orbit structure'
    : 'Add surface structure';
  return (
    <button
      type="button"
      aria-label={label}
      title={enabled ? label : disabledReason ?? label}
      disabled={!enabled}
      onClick={onAdd}
      style={{ left, top, transform: 'translate(-50%, -50%)' }}
      className={[
        'absolute z-40 grid h-8 w-8 place-items-center rounded-full border text-sm font-bold transition-transform',
        enabled
          ? 'border-orange/55 bg-orange/18 text-orange hover:scale-110'
          : 'cursor-not-allowed border-gold/35 bg-gold/10 text-gold/70',
      ].join(' ')}
    >
      +
    </button>
  );
}

function LaneCapacityMap({
  laneKey,
  capacity,
  planned,
  projected,
  selectedPlacementIndex,
  selectedProjectedPlacementIndex,
  onSelectPlacement,
  onSelectProjectedPlacement,
  onAddEmptySlot,
}: {
  laneKey: BodyPlannerLane;
  capacity: number | null;
  planned: BodyPlannerPlacementItem[];
  projected: BodyPlannerProjectedPlacementItem[];
  selectedPlacementIndex: number | null;
  selectedProjectedPlacementIndex: number | null;
  onSelectPlacement: (index: number) => void;
  onSelectProjectedPlacement: (index: number) => void;
  onAddEmptySlot?: () => void;
}) {
  const used = planned.length + projected.length;
  if (capacity == null) {
    return (
      <div className="mb-2 rounded border border-gold/30 bg-gold/5 px-2 py-2">
        <div className="flex items-center gap-2 font-mono text-[10px] text-gold">
          <span className="uppercase tracking-[0.14em]">Predicted capacity</span>
          <span data-testid={`center-slot-unknown-${laneKey}`} className="rounded border border-gold/40 bg-gold/10 px-1">[?]</span>
        </div>
        {used > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {[...planned, ...projected].map((item, index) => {
              const projectedItem = index >= planned.length;
              const plannedItem = item as BodyPlannerPlacementItem;
              const projectedPlacement = item as BodyPlannerProjectedPlacementItem;
              const key = projectedItem
                ? `unknown-projected-${laneKey}-${projectedPlacement.index}-${projectedPlacement.placement.facility_template_id}`
                : `unknown-planned-${laneKey}-${plannedItem.index}-${plannedItem.placement.facility_template_id}`;
              return (
                <CapacityCell
                  key={key}
                  testId={`center-${laneKey}-unknown-item-${index}`}
                  label={slotLabel(item)}
                  fullLabel={item.template?.name ?? item.placement.facility_template_id}
                  projected={projectedItem}
                  selected={projectedItem ? selectedProjectedPlacementIndex === projectedPlacement.index : selectedPlacementIndex === plannedItem.index}
                  onClick={projectedItem ? () => onSelectProjectedPlacement(projectedPlacement.index) : () => onSelectPlacement(plannedItem.index)}
                />
              );
            })}
          </div>
        )}
      </div>
    );
  }

  const cells = Array.from({ length: capacity }, (_unused, index) => {
    if (index < planned.length) {
      const item = planned[index];
      return {
        key: `planned-${laneKey}-${item.index}`,
        label: slotLabel(item),
        fullLabel: item.template?.name ?? item.placement.facility_template_id,
        projected: false,
        selected: selectedPlacementIndex === item.index,
        onClick: () => onSelectPlacement(item.index),
      };
    }
    const projectedIndex = index - planned.length;
    if (projectedIndex >= 0 && projectedIndex < projected.length) {
      const item = projected[projectedIndex];
      return {
        key: `projected-${laneKey}-${item.index}`,
        label: slotLabel(item),
        fullLabel: item.template?.name ?? item.placement.facility_template_id,
        projected: true,
        selected: selectedProjectedPlacementIndex === item.index,
        onClick: () => onSelectProjectedPlacement(item.index),
      };
    }
    return {
      key: `empty-${laneKey}-${index}`,
      label: '',
      fullLabel: onAddEmptySlot
        ? `Add ${laneKey === 'orbital' ? 'orbit' : 'surface'} structure to empty slot`
        : 'Empty slot',
      projected: false,
      selected: false,
      onClick: onAddEmptySlot,
    };
  });
  const overflow = Math.max(0, used - capacity);

  return (
    <div className="mb-2 rounded border border-border/55 bg-bg3/30 px-2 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2 font-mono text-[10px]">
        <span className="uppercase tracking-[0.14em] text-silver-dk">Predicted capacity</span>
        <span className="text-silver">{used}/{capacity} slots including projection</span>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {cells.map((cell, index) => (
          <CapacityCell
            key={cell.key}
            testId={`center-${laneKey}-slot-${index}`}
            label={cell.label}
            fullLabel={cell.fullLabel}
            projected={cell.projected}
            selected={cell.selected}
            onClick={cell.onClick}
          />
        ))}
      </div>
      {overflow > 0 && (
        <div data-testid={`center-${laneKey}-overflow`} className="mt-2 font-mono text-[10px] text-gold">
          +{overflow} overflow / unconfirmed
        </div>
      )}
    </div>
  );
}

function CapacityCell({
  testId,
  label,
  fullLabel,
  projected,
  selected,
  onClick,
}: {
  testId: string;
  label: string;
  fullLabel: string;
  projected: boolean;
  selected: boolean;
  onClick?: () => void;
}) {
  const className = [
    'inline-flex h-9 min-w-9 max-w-[5.5rem] items-center justify-center rounded border px-2 font-mono text-[10px] font-bold uppercase leading-none',
    label
      ? projected
        ? 'border-cyan/45 bg-cyan/10 text-cyan'
        : 'border-orange/55 bg-orange/16 text-orange'
      : 'border-border/60 bg-bg2/45 text-silver-dk',
    selected ? 'ring-2 ring-orange/70' : '',
    onClick ? 'cursor-pointer hover:border-orange/75' : '',
  ].join(' ');

  if (onClick) {
    return (
      <button
        type="button"
        data-testid={testId}
        title={fullLabel}
        onClick={onClick}
        aria-label={fullLabel}
        className={className}
      >
        {label || ' '}
      </button>
    );
  }

  return (
    <span data-testid={testId} title={fullLabel} className={className}>
      {label || ' '}
    </span>
  );
}

function LaneSlots({
  body,
  laneKey,
  planned,
  projected,
  selectedPlacementIndex,
  selectedProjectedPlacementIndex,
  onSelectPlacement,
  onSelectProjectedPlacement,
  emptyText,
}: {
  body: SystemBody;
  laneKey: BodyPlannerLane;
  planned: BodyPlannerPlacementItem[];
  projected: BodyPlannerProjectedPlacementItem[];
  selectedPlacementIndex: number | null;
  selectedProjectedPlacementIndex: number | null;
  onSelectPlacement: (index: number) => void;
  onSelectProjectedPlacement: (index: number) => void;
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
          selected={selectedProjectedPlacementIndex === item.index}
          onSelect={() => onSelectProjectedPlacement(item.index)}
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

function laneForTemplate(template: FacilityTemplate | undefined, body: SystemBody): BodyPlannerLane {
  if (!template) return fallbackLaneForBody(body);
  const location = templateLocationKind(template);
  if (location === 'orbital') return 'orbital';
  if (location === 'surface') return 'surface';
  if (location === 'both') {
    if (template.is_port) return 'orbital';
    return body.is_landable === true && body.is_water_world !== true ? 'surface' : 'orbital';
  }
  return fallbackLaneForBody(body);
}

function fallbackLaneForBody(body: SystemBody): BodyPlannerLane {
  return body.is_landable === true && body.is_water_world !== true ? 'surface' : 'orbital';
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

export function SlotCapacityDots({
  orbitalCapacity,
  surfaceCapacity,
  occupiedOrbital,
  occupiedSurface,
  testId,
}: {
  orbitalCapacity: number | null;
  surfaceCapacity: number | null;
  occupiedOrbital: number;
  occupiedSurface: number;
  testId?: string;
}) {
  const dots = [
    ...capacityDots('orbital', orbitalCapacity, occupiedOrbital),
    ...capacityDots('surface', surfaceCapacity, occupiedSurface),
  ];
  if (dots.length === 0) {
    return (
      <span
        data-testid={testId}
        className="rounded border border-gold/35 bg-gold/10 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.1em] text-gold"
      >
        slots ?
      </span>
    );
  }
  return (
    <span
      data-testid={testId}
      className="inline-flex max-w-[12rem] flex-wrap items-center gap-1"
      title={`${occupiedOrbital}/${orbitalCapacity ?? '?'} orbit, ${occupiedSurface}/${surfaceCapacity ?? '?'} surface`}
    >
      {dots.map((dot) => (
        <span
          key={dot.key}
          data-slot-lane={dot.lane}
          data-occupied={dot.occupied ? 'true' : 'false'}
          className={[
            'h-2.5 w-2.5 rounded-full border',
            dot.lane === 'orbital'
              ? dot.occupied
                ? 'border-cyan/80 bg-cyan/80'
                : 'border-cyan/50 bg-transparent'
              : dot.occupied
                ? 'border-green/80 bg-green/80'
                : 'border-green/50 bg-transparent',
          ].join(' ')}
        />
      ))}
    </span>
  );
}

function capacityDots(lane: BodyPlannerLane, capacity: number | null, occupied: number) {
  if (capacity == null || capacity <= 0) return [];
  return Array.from({ length: capacity }, (_unused, index) => ({
    key: `${lane}-${index}`,
    lane,
    occupied: index < occupied,
  }));
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
