import type { FacilityTemplate, SimulateBuildPlacement } from '@/types/api';
import type { ExistingStructure } from './existingInfrastructure';
import { existingSlotLabel, slotLabel, slotTitle, type SlotLabelItem } from './bodySlotPlannerLabels';

export type BodyPlannerLane = 'orbital' | 'surface';

export interface RingPlannedItem {
  placement: SimulateBuildPlacement;
  index: number;
  template: FacilityTemplate | undefined;
  bodyId?: string;
  hasUnknownBody?: boolean;
}

export interface RingProjectedItem {
  placement: SimulateBuildPlacement;
  index: number;
  template: FacilityTemplate | undefined;
}

export function BodyRingMap({
  orbitalCapacity,
  surfaceCapacity,
  orbitalExisting,
  surfaceExisting,
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
  orbitalExisting: ExistingStructure[];
  surfaceExisting: ExistingStructure[];
  orbitalPlanned: RingPlannedItem[];
  surfacePlanned: RingPlannedItem[];
  orbitalProjected: RingProjectedItem[];
  surfaceProjected: RingProjectedItem[];
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
  const orbitalSlotCount = slotIconCount(orbitalCapacity);
  const surfaceSlotCount = slotIconCount(surfaceCapacity);
  const orbitalNodes = buildRingNodes({
    lane: 'orbital',
    slotCount: orbitalSlotCount,
    existing: orbitalExisting,
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
    slotCount: surfaceSlotCount,
    existing: surfaceExisting,
    planned: surfacePlanned,
    projected: surfaceProjected,
    selectedPlacementIndex,
    selectedProjectedPlacementIndex,
    canAdd: hasTemplates && !surfaceBlocked,
    onAdd: () => onAddLaneStructure('surface'),
    onSelectPlacement,
    onSelectProjectedPlacement,
  });
  const orbitalSlots = ringSlots(orbitalSlotCount, orbitRadius);
  const surfaceSlots = ringSlots(surfaceSlotCount, surfaceRadius);

  return (
    <section data-testid="body-slot-graph" className="mb-3 rounded border border-border/60 bg-bg3/35 px-2 py-3">
      <div className="relative mx-auto min-h-[18.5rem] max-w-[56rem]">
        <svg
          aria-hidden="true"
          viewBox="0 0 320 320"
          className="pointer-events-none absolute left-1/2 top-[8.9rem] h-[16rem] w-[16rem] -translate-x-1/2 -translate-y-1/2 overflow-visible"
        >
          <circle cx="160" cy="160" r={ORBIT_BAND_RADIUS} fill="none" stroke="#00c8ff" strokeWidth="40" strokeOpacity="0.46" />
          <circle cx="160" cy="160" r={SURFACE_BAND_RADIUS} fill="none" stroke="#ff9f1a" strokeWidth="40" strokeOpacity="0.48" />
        </svg>
        <div className="pointer-events-none absolute left-1/2 top-[8.9rem] h-[6.4rem] w-[6.4rem] -translate-x-1/2 -translate-y-1/2 rounded-full border border-orange/45 bg-orange/10 shadow-[0_0_30px_rgba(255,122,20,0.2)]" />

        <div className="pointer-events-none absolute left-1/2 top-[8.9rem] -translate-x-1/2 -translate-y-1/2 text-center">
          <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver">Body core</div>
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

export type RingNodeKind = 'planned' | 'projected' | 'empty' | 'existing';

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
  slotCount,
  existing,
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
  slotCount: number;
  existing: ExistingStructure[];
  planned: RingPlannedItem[];
  projected: RingProjectedItem[];
  selectedPlacementIndex: number | null;
  selectedProjectedPlacementIndex: number | null;
  canAdd: boolean;
  onAdd: () => void;
  onSelectPlacement: (index: number) => void;
  onSelectProjectedPlacement: (index: number) => void;
}): RingNode[] {
  const structures = [
    ...existing.map((structure, index) => existingRingNode(lane, structure, index)),
    ...planned.map((item) => structureRingNode(lane, item, selectedPlacementIndex === item.index, () => onSelectPlacement(item.index))),
    ...projected.map((item) => structureRingNode(lane, item, selectedProjectedPlacementIndex === item.index, () => onSelectProjectedPlacement(item.index), true)),
  ];

  if (slotCount <= 0) return [];

  return Array.from({ length: slotCount }, (_unused, index) => {
    if (index < structures.length) return structures[index];
    return {
      id: `${lane}-empty-${index}`,
      kind: 'empty' as const,
      label: canAdd ? '+' : String(index + 1),
      title: canAdd
        ? `Add ${lane === 'orbital' ? 'orbit' : 'surface'} structure to slot ${index + 1}`
        : 'Empty slot',
      selected: false,
      onClick: canAdd ? onAdd : undefined,
    };
  });
}

function structureRingNode(
  lane: BodyPlannerLane,
  item: RingPlannedItem | RingProjectedItem,
  selected: boolean,
  onClick: () => void,
  projected = false,
): RingNode {
  return {
    id: `${lane}-${projected ? 'projected' : 'planned'}-${item.index}-${item.placement.facility_template_id}`,
    kind: projected ? 'projected' : 'planned',
    label: slotLabel(item as SlotLabelItem),
    title: slotTitle(item),
    selected,
    onClick,
  };
}

function existingRingNode(lane: BodyPlannerLane, structure: ExistingStructure, index: number): RingNode {
  return {
    id: `${lane}-existing-${structure.id}-${index}`,
    kind: 'existing',
    label: existingSlotLabel(structure),
    title: `Existing: ${structure.name}`,
    selected: false,
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

function slotIconCount(capacity: number | null) {
  return capacity == null ? 0 : Math.max(0, capacity);
}

function ringSlots(count: number, radius: number) {
  if (count <= 0) return [];
  return Array.from({ length: count }, (_unused, index) => (
    polarPoint(radius, (360 / count) * index)
  ));
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
    : kind === 'existing'
      ? 'border-green/45 bg-green/12 text-green'
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
          'absolute z-30 grid h-8 w-8 place-items-center rounded-full border font-mono text-base font-bold uppercase leading-none tracking-normal transition-transform hover:scale-105',
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
        'absolute z-30 grid h-8 w-8 place-items-center rounded-full border font-mono text-base font-bold uppercase leading-none tracking-normal',
        toneClass,
      ].join(' ')}
    >
      {label}
    </div>
  );
}
