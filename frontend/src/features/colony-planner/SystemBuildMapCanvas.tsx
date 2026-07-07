import { Network, Plus } from 'lucide-react';
import type { CSSProperties } from 'react';
import type { SystemDetail } from '@/types/api';
import type { TopologyPlanSnapshot, TopologySelection } from './ColonyTopologyRail';
import type { BodyPlannerLane } from './BodySlotPlanner';
import { economyColor, economySoftColor } from './economyVisuals';
import {
  existingStructureDisplayType,
  resolveExistingInfrastructure,
  type ExistingStructure,
} from './existingInfrastructure';
import type {
  PlannerEconomySegment,
  PlannerCanvasLane,
  PlannerCanvasRow,
  PlannerLaneOccupancySummary,
  PlannerStructureSlot,
  VisiblePlannerCanvasLane,
} from './plannerCanvasTypes';
export type {
  PlannerEconomySegment,
  PlannerCanvasLane,
  PlannerCanvasRow,
  PlannerLaneOccupancySummary,
  PlannerStructureSlot,
  VisiblePlannerCanvasLane,
} from './plannerCanvasTypes';
import {
  type PrerequisiteIssue,
} from './structurePlanningRules';
import {
  bodyMarker,
  buildPlannerCanvasRows,
  placementBodyId,
  summarizePlannerCanvasRows,
} from './plannerCanvasUtils';

export function SystemBuildMapCanvas({
  system,
  snapshot,
  selection,
  onSelect,
  onRequestAddStructure,
  prerequisiteIssues = [],
}: {
  system: SystemDetail;
  snapshot: TopologyPlanSnapshot;
  selection: TopologySelection;
  onSelect: (selection: TopologySelection) => void;
  onRequestAddStructure?: (bodyId: string, lane: BodyPlannerLane) => void;
  prerequisiteIssues?: PrerequisiteIssue[];
}) {
  const rows = buildPlannerCanvasRows(system, snapshot);
  const existingResolution = resolveExistingInfrastructure(system);
  const occupancySummary = summarizePlannerCanvasRows(rows, existingResolution.unresolved.length);
  const selectedBodyId = selection.type === 'body'
    ? selection.bodyId
    : selection.type === 'placement'
      ? placementBodyId(snapshot.placements[selection.placementIndex])
      : selection.type === 'projected-placement'
        ? placementBodyId(snapshot.projection?.placements[selection.placementIndex])
        : null;
  const selectedProjectedPlacementIndex = selection.type === 'projected-placement' ? selection.placementIndex : null;
  const hasEstimatedSlots = rows.some((row) => row.orbitalCapacityEstimated || row.groundCapacityEstimated);
  const responsiveGridClassName = 'grid-cols-1 lg:[grid-template-columns:280px_minmax(300px,1fr)_minmax(320px,1.05fr)]';

  return (
    <section
      aria-label="Live system build map"
      data-testid="planner-canvas"
      data-layout="system-build-map-canvas"
      className="min-w-0 overflow-hidden rounded-chunk-lg border border-orange/30 bg-bg1/85 shadow-metal"
    >
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-orange/25 bg-bg2/80 px-3 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <div className="grid h-8 w-8 shrink-0 place-items-center rounded border border-cyan/35 bg-cyan/10 text-cyan">
            <Network size={16} />
          </div>
          <div className="min-w-0">
            <h2 className="font-display text-lg text-orange">System Build Map</h2>
            <p className="truncate text-xs leading-relaxed text-silver">
              Plan structures directly into predicted orbital and surface slots.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5 text-[11px]">
          <CanvasPill label={`${rows.length} bodies`} tone="silver" />
          <CanvasPill label={`${occupancySummary.existingCount} existing`} tone={occupancySummary.existingCount > 0 ? 'green' : 'silver'} />
          {occupancySummary.inferredExistingCount > 0 && <CanvasPill label={`${occupancySummary.inferredExistingCount} inferred`} tone="gold" />}
          <CanvasPill label={`${snapshot.placements.length} planned`} tone={snapshot.placements.length > 0 ? 'orange' : 'silver'} />
          <CanvasPill label={`${snapshot.projection?.placements.length ?? 0} projected`} tone={snapshot.projection ? 'cyan' : 'silver'} />
          <CanvasPill label={`${occupancySummary.emptySlotCount} empty`} tone="silver" />
          <CanvasPill label={`${occupancySummary.unresolvedExistingCount} unresolved existing`} tone={occupancySummary.unresolvedExistingCount > 0 ? 'gold' : 'green'} />
          <CanvasPill label={hasEstimatedSlots ? 'slots estimated' : snapshot.slotPredictions ? 'slots loaded' : 'slots unknown'} tone={hasEstimatedSlots ? 'gold' : snapshot.slotPredictions ? 'green' : 'gold'} />
        </div>
      </header>
      {occupancySummary.existingCount > 0 && (
        <div data-testid="planner-canvas-existing-summary" className="border-b border-green/25 bg-green/8 px-3 py-2 font-mono text-[10px] uppercase tracking-[0.1em] text-green">
          Existing infrastructure detected: {occupancySummary.existingCount} matched slot occupant{occupancySummary.existingCount === 1 ? '' : 's'}.
        </div>
      )}
      {hasEstimatedSlots && (
        <div data-testid="planner-canvas-slot-estimate" className="border-b border-gold/25 bg-gold/8 px-3 py-2 font-mono text-[10px] italic text-gold">
          Predicted slots - verify in Architect Mode.
        </div>
      )}

      <div data-testid="planner-canvas-scroll-region" className="overflow-x-hidden lg:overflow-x-auto">
        <div data-testid="planner-canvas-grid-frame" className="min-w-0 lg:min-w-[860px]">
          <div
            className={[
              'grid gap-1.5 border-b border-orange/20 bg-bg2/70 px-3 py-2 font-mono text-[11px] font-bold uppercase tracking-[0.14em] text-silver-dk lg:gap-0',
              responsiveGridClassName,
            ].join(' ')}
          >
            <div className="text-cyan">System Tree</div>
            <div>Orbit</div>
            <div>Surface</div>
          </div>

          <div className="divide-y divide-border/45">
            {rows.length === 0 ? (
              <div className="px-3 py-5 text-sm text-silver">No real body layout is available for this system.</div>
            ) : rows.map((row) => (
              <PlannerCanvasBodyRow
                key={row.id}
                row={row}
                selected={selectedBodyId === row.id}
                selectedPlacementIndex={selection.type === 'placement' ? selection.placementIndex : null}
                selectedProjectedPlacementIndex={selectedProjectedPlacementIndex}
                responsiveGridClassName={responsiveGridClassName}
                onSelect={onSelect}
                onRequestAddStructure={onRequestAddStructure}
                prerequisiteIssues={prerequisiteIssues}
              />
            ))}
          </div>
        </div>
      </div>
      {existingResolution.unresolved.length > 0 && (
        <UnresolvedExistingInfrastructure structures={existingResolution.unresolved} />
      )}
    </section>
  );
}

export { PlannerTelemetryPanel } from './PlannerTelemetryPanel';

function PlannerCanvasBodyRow({
  row,
  selected,
  selectedPlacementIndex,
  selectedProjectedPlacementIndex,
  responsiveGridClassName,
  onSelect,
  onRequestAddStructure,
  prerequisiteIssues,
}: {
  row: PlannerCanvasRow;
  selected: boolean;
  selectedPlacementIndex: number | null;
  selectedProjectedPlacementIndex: number | null;
  responsiveGridClassName: string;
  onSelect: (selection: TopologySelection) => void;
  onRequestAddStructure?: (bodyId: string, lane: BodyPlannerLane) => void;
  prerequisiteIssues: PrerequisiteIssue[];
}) {
  const rowTone = selected
    ? 'bg-orange/10 shadow-[inset_4px_0_0_rgba(255,122,20,0.95)]'
    : row.projected
      ? 'bg-cyan/5'
      : 'bg-transparent';

  return (
    <div
      data-testid={`planner-canvas-body-row-${row.id}`}
      data-projected={row.projected ? 'true' : 'false'}
      data-selected={selected ? 'true' : 'false'}
      className={row.projected ? 'bg-cyan/5' : undefined}
    >
      <div
        className={[
          'grid min-h-[62px] items-stretch gap-2 px-3 py-2 transition-colors lg:gap-0',
          responsiveGridClassName,
          rowTone,
        ].join(' ')}
      >
        <TreeCell row={row} selected={selected} onSelect={() => onSelect({ type: 'body', bodyId: row.id })} />
        <PlannerCanvasLaneSlots
          bodyId={row.id}
          bodyName={row.displayName}
          lane="orbital"
          capacity={row.orbitalCapacity}
          occupancy={row.orbitalOccupancy}
          slots={row.orbitalSlots}
          selectedPlacementIndex={selectedPlacementIndex}
          selectedProjectedPlacementIndex={selectedProjectedPlacementIndex}
          onSelect={onSelect}
          onRequestAddStructure={onRequestAddStructure}
          disabledReason={row.orbitalAddDisabledReason}
          selectedBody={selected}
          prerequisiteIssues={prerequisiteIssues}
        />
        <PlannerCanvasLaneSlots
          bodyId={row.id}
          bodyName={row.displayName}
          lane="ground"
          capacity={row.groundCapacity}
          occupancy={row.groundOccupancy}
          slots={row.groundSlots}
          selectedPlacementIndex={selectedPlacementIndex}
          selectedProjectedPlacementIndex={selectedProjectedPlacementIndex}
          onSelect={onSelect}
          onRequestAddStructure={onRequestAddStructure}
          disabledReason={row.groundAddDisabledReason}
          selectedBody={selected}
          prerequisiteIssues={prerequisiteIssues}
        />
      </div>
      {row.unassignedSlots.length > 0 && (
        <div
          data-testid={`${row.id}-unassigned-lane`}
          className={[
            'grid gap-2 border-t border-gold/20 bg-gold/5 px-3 py-2 lg:gap-0',
            responsiveGridClassName,
          ].join(' ')}
        >
          <div className="hidden lg:block" />
          <div className="flex min-w-0 flex-wrap items-center gap-2 lg:col-span-2">
            <span className="rounded border border-gold/35 bg-gold/10 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-gold">
              Needs lane
            </span>
            <div className="flex min-w-0 flex-wrap gap-1.5">
              {row.unassignedSlots.map((slot, index) => (
                <PlannerSlotBox
                  key={slot.id}
                  slot={slot}
                  lane="unassigned"
                  bodyName={row.displayName}
                  testId={`${row.id}-unassigned-slot-${index}`}
                  selected={(slot.placementIndex != null && slot.placementIndex === selectedPlacementIndex) || (slot.projectionIndex != null && slot.projectionIndex === selectedProjectedPlacementIndex)}
                  onSelect={onSelect}
                  warningCount={slot.placementIndex != null ? prerequisiteIssues.find((issue) => issue.placementIndex === slot.placementIndex)?.missing.length ?? 0 : 0}
                />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function UnresolvedExistingInfrastructure({ structures }: { structures: ExistingStructure[] }) {
  const visible = structures.slice(0, 5);
  const extra = Math.max(0, structures.length - visible.length);
  return (
    <section
      data-testid="planner-canvas-unresolved-existing"
      className="border-t border-gold/25 bg-gold/6 px-3 py-2"
      aria-label="Existing infrastructure not matched to body"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded border border-gold/35 bg-gold/10 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-gold">
          Existing infrastructure not matched to body
        </span>
        <div className="flex min-w-0 flex-wrap gap-1.5">
          {visible.map((structure) => (
            <span
              key={structure.id}
              data-testid="planner-canvas-unresolved-existing-structure"
              title={[
                structure.name,
                existingStructureDisplayType(structure),
                `Association: ${existingAssociationLabel(structure)}`,
                `Source: ${structure.association_source}`,
                structure.unresolved_reason ?? structure.body_match_reason,
              ].filter(Boolean).join(' | ')}
              className="max-w-[14rem] truncate rounded border border-gold/30 bg-bg3/45 px-2 py-1 font-mono text-[10px] text-silver"
            >
              {structure.name} / {existingStructureDisplayType(structure)} / {existingAssociationLabel(structure)}
            </span>
          ))}
          {extra > 0 && (
            <span className="rounded border border-gold/30 bg-bg3/45 px-2 py-1 font-mono text-[10px] text-gold">
              +{extra} more
            </span>
          )}
        </div>
      </div>
    </section>
  );
}

function existingAssociationLabel(structure: ExistingStructure): string {
  if (structure.transient) return 'transient';
  if (structure.association_status === 'unresolved') return 'unresolved';
  if (structure.lane === 'unknown') return 'lane unknown';
  if (structure.association_status === 'inferred') return 'verify';
  return 'confirmed';
}

function TreeCell({
  row,
  selected,
  onSelect,
}: {
  row: PlannerCanvasRow;
  selected: boolean;
  onSelect: () => void;
}) {
  const markerLeft = 16 + row.depth * 28;
  const marker = bodyMarker(row.body);

  return (
    <div className="relative min-h-full">
      {row.guide.map((continues, index) => continues && (
        <span
          key={index}
          aria-hidden
          className="absolute bottom-[-0.5rem] top-[-0.5rem] w-px bg-cyan/30"
          style={{ left: 16 + index * 28 }}
        />
      ))}
      {row.depth > 0 && (
        <>
          <span aria-hidden className="absolute top-[-0.5rem] h-[calc(50%+0.5rem)] w-px bg-cyan/40" style={{ left: markerLeft }} />
          {!row.isLast && <span aria-hidden className="absolute bottom-[-0.5rem] top-1/2 w-px bg-cyan/40" style={{ left: markerLeft }} />}
          <span aria-hidden className="absolute top-1/2 h-px bg-cyan/40" style={{ left: markerLeft - 28, width: 28 }} />
        </>
      )}

      <button
        type="button"
        data-testid={`topology-body-button-${row.id}`}
        aria-pressed={selected}
        title={row.displayName}
        onClick={onSelect}
        className="absolute inset-y-0 right-1 z-10 flex items-center rounded-chunk-sm border border-transparent text-left hover:border-cyan/35 focus:outline-none focus-visible:border-orange"
        style={{ left: markerLeft + 4 }}
      >
        <span
          aria-hidden
          className={['mr-3 shrink-0 rounded-full border shadow-[0_0_18px_-6px_currentColor]', marker.size, selected ? 'ring-2 ring-orange/70' : ''].join(' ')}
          style={{ background: marker.fill, borderColor: marker.ring, color: marker.ring }}
        />
        <span className="min-w-0">
          <span className="flex min-w-0 items-center gap-2">
            <span className="truncate text-sm font-semibold leading-snug text-silver-lt">{row.compactName}</span>
            {row.warningCount > 0 && <span className="rounded border border-gold/35 bg-gold/10 px-1.5 py-0.5 font-mono text-[10px] text-gold">!</span>}
            {row.projected && <span className="rounded border border-cyan/35 bg-cyan/10 px-1.5 py-0.5 font-mono text-[10px] text-cyan">ghost</span>}
            <BodyCapacitySummary
              testId={`planner-canvas-body-capacity-${row.id}`}
              orbitalCapacity={row.orbitalCapacity}
              groundCapacity={row.groundCapacity}
            />
          </span>
          <span className="mt-0.5 block truncate text-xs leading-snug text-silver/85">{row.bodyKind}</span>
        </span>
      </button>
    </div>
  );
}

function BodyCapacitySummary({
  testId,
  orbitalCapacity,
  groundCapacity,
}: {
  testId: string;
  orbitalCapacity: number | null;
  groundCapacity: number | null;
}) {
  const renderChip = (lane: 'orbital' | 'ground', capacity: number | null) => {
    if (capacity === 0) return null;
    const label = lane === 'orbital' ? 'O' : 'S';
    const value = capacity == null ? '?' : String(capacity);
    const tone = lane === 'orbital'
      ? 'border-cyan/40 bg-cyan/10 text-cyan'
      : 'border-green/40 bg-green/10 text-green';
    return (
      <span
        key={lane}
        data-testid={`${testId}-${lane}`}
        data-capacity={value}
        className={[
          'inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.12em]',
          tone,
        ].join(' ')}
      >
        <span className="text-[9px]">{label}</span>
        <span className="font-display text-[13px] leading-none">{value}</span>
      </span>
    );
  };
  return (
    <span data-testid={testId} className="inline-flex items-center gap-1">
      {renderChip('orbital', orbitalCapacity)}
      {renderChip('ground', groundCapacity)}
    </span>
  );
}

function PlannerCanvasLaneSlots({
  bodyId,
  bodyName,
  lane,
  capacity,
  occupancy,
  slots,
  selectedPlacementIndex,
  selectedProjectedPlacementIndex,
  onSelect,
  onRequestAddStructure,
  disabledReason,
  selectedBody,
  prerequisiteIssues,
}: {
  bodyId: string;
  bodyName: string;
  lane: VisiblePlannerCanvasLane;
  capacity: number | null;
  occupancy: PlannerLaneOccupancySummary;
  slots: PlannerStructureSlot[];
  selectedPlacementIndex: number | null;
  selectedProjectedPlacementIndex: number | null;
  onSelect: (selection: TopologySelection) => void;
  onRequestAddStructure?: (bodyId: string, lane: BodyPlannerLane) => void;
  disabledReason?: string | null;
  selectedBody: boolean;
  prerequisiteIssues: PrerequisiteIssue[];
}) {
  const laneFullName = lane === 'orbital' ? 'Orbit' : 'Surface';
  const knownCount = capacity == null ? '?' : String(capacity);
  const plannerLane = plannerCanvasLaneToPlannerLane(lane);
  const addLabel = lane === 'orbital'
    ? `Add orbit structure to ${bodyName}`
    : `Add surface structure to ${bodyName}`;
  const hasKnownZeroCapacity = capacity === 0;
  const showAddControl = Boolean(selectedBody && onRequestAddStructure && !hasKnownZeroCapacity);
  const requestAdd = showAddControl && onRequestAddStructure && !disabledReason
    ? () => onRequestAddStructure(bodyId, plannerLane)
    : undefined;
  const visibleSlots = slots;
  const laneName = lane === 'orbital' ? 'orbital' : 'surface';

  return (
    <div data-testid={`${bodyId}-${lane}-lane`} data-disabled={disabledReason ? 'true' : 'false'} className="flex min-w-0 flex-col gap-1 pr-2">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <span className="flex min-w-[7rem] shrink-0 items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.1em] text-cyan">
          <span
            data-testid={`${bodyId}-${lane}-capacity-badge`}
            data-capacity={knownCount}
            className="inline-flex items-baseline gap-0.5 rounded border border-cyan/35 bg-cyan/8 px-2 py-0.5 text-cyan"
          >
            <span className="text-[11px] font-semibold tracking-wide">{laneFullName}</span>
            <span className="font-display text-[15px] font-bold leading-none tabular-nums">{knownCount}</span>
          </span>
          {showAddControl && (
            <button
              type="button"
              data-testid={`${bodyId}-${lane}-add`}
              aria-label={addLabel}
              title={disabledReason ?? addLabel}
              disabled={Boolean(disabledReason)}
              onClick={requestAdd}
              className="inline-flex items-center gap-1 rounded border border-orange/55 bg-orange/15 px-2.5 py-1 text-[11px] font-semibold text-orange hover:bg-orange/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/70 disabled:cursor-not-allowed disabled:border-gold/35 disabled:bg-gold/10 disabled:text-gold/70 disabled:hover:bg-gold/10"
            >
              <Plus size={12} />
              {lane === 'orbital' ? 'Add Orbit' : 'Add Surface'}
            </button>
          )}
        </span>
        <div className="flex min-w-0 flex-wrap gap-1.5">
          {visibleSlots.length > 0 ? visibleSlots.map((slot, index) => (
            <PlannerSlotBox
              key={slot.id}
              slot={slot}
              lane={lane}
              bodyName={bodyName}
              testId={`${bodyId}-${lane}-slot-${index}`}
              selected={(slot.placementIndex != null && slot.placementIndex === selectedPlacementIndex) || (slot.projectionIndex != null && slot.projectionIndex === selectedProjectedPlacementIndex)}
              onSelect={onSelect}
              onAdd={undefined}
              warningCount={slot.placementIndex != null ? prerequisiteIssues.find((issue) => issue.placementIndex === slot.placementIndex)?.missing.length ?? 0 : 0}
            />
          )) : (
            <LaneCompactState
              laneName={laneName}
              capacity={capacity}
              selectedBody={selectedBody}
              disabledReason={disabledReason}
              testId={`${bodyId}-${lane}-compact-state`}
            />
          )}
          {selectedBody && disabledReason && (
            <span data-testid={`${bodyId}-${lane}-disabled-reason`} className="rounded border border-gold/35 bg-gold/10 px-1.5 py-1 font-mono text-[10px] text-gold">
              {disabledReason}
            </span>
          )}
        </div>
      </div>
      <LaneOccupancySummary
        testId={`${bodyId}-${lane}-occupancy-summary`}
        laneLabel={laneName}
        occupancy={occupancy}
      />
    </div>
  );
}

function LaneOccupancySummary({
  testId,
  laneLabel,
  occupancy,
}: {
  testId: string;
  laneLabel: string;
  occupancy: PlannerLaneOccupancySummary;
}) {
  const slotsLabel = occupancy.capacity == null ? 'unknown' : String(occupancy.capacity);
  const remainingLabel = occupancy.remainingForPlan == null ? 'unknown' : String(occupancy.remainingForPlan);
  const inferredLabel = occupancy.inferredExistingCount > 0 ? ` / verify ${occupancy.inferredExistingCount}` : '';
  const title = [
    `${laneLabel} slots: ${slotsLabel}`,
    `existing occupied: ${occupancy.existingCount}${inferredLabel}`,
    `planned occupied: ${occupancy.plannedCount}`,
    `projected ghost occupied: ${occupancy.projectedCount}`,
    `remaining for Build Plan: ${remainingLabel}`,
    'Projected ghosts do not reserve Build Plan capacity until loaded.',
    occupancy.projectedOverflowCount > 0 ? `projection over capacity: +${occupancy.projectedOverflowCount}` : null,
  ].filter(Boolean).join(' | ');

  return (
    <div
      data-testid={testId}
      title={title}
      className="flex min-w-0 flex-wrap gap-1 font-mono text-[9px] uppercase tracking-[0.08em] text-silver-dk"
    >
      <span className="rounded border border-cyan/25 bg-cyan/8 px-1.5 py-0.5 text-cyan">Slots {slotsLabel}</span>
      <span className="rounded border border-green/25 bg-green/8 px-1.5 py-0.5 text-green">Existing {occupancy.existingCount}{inferredLabel}</span>
      <span className="rounded border border-orange/25 bg-orange/8 px-1.5 py-0.5 text-orange">Planned {occupancy.plannedCount}</span>
      <span className="rounded border border-cyan/25 bg-cyan/8 px-1.5 py-0.5 text-cyan">Ghost {occupancy.projectedCount}</span>
      <span className={occupancy.remainingForPlan === 0 ? 'rounded border border-gold/35 bg-gold/10 px-1.5 py-0.5 text-gold' : 'rounded border border-border/45 bg-bg3/30 px-1.5 py-0.5 text-silver'}>
        Open {remainingLabel}
      </span>
      {occupancy.projectedOverflowCount > 0 && (
        <span className="rounded border border-gold/35 bg-gold/10 px-1.5 py-0.5 text-gold">Ghost over +{occupancy.projectedOverflowCount}</span>
      )}
    </div>
  );
}

function LaneCompactState({
  laneName,
  capacity,
  selectedBody,
  disabledReason,
  testId,
}: {
  laneName: string;
  capacity: number | null;
  selectedBody: boolean;
  disabledReason?: string | null;
  testId: string;
}) {
  if (disabledReason && !selectedBody) {
    return <span data-testid={testId} className="sr-only">{disabledReason}</span>;
  }
  if (capacity == null) {
    return (
      <span data-testid={testId} title={`${laneName} slot count unknown`} className="rounded border border-gold/35 bg-gold/10 px-2 py-1 font-mono text-[10px] text-gold">
        ? slots
      </span>
    );
  }
  if (capacity <= 0) {
    return selectedBody ? (
      <span data-testid={testId} className="rounded border border-border/45 bg-bg3/30 px-2 py-1 font-mono text-[10px] text-silver-dk">
        No {laneName} slots
      </span>
    ) : <span data-testid={testId} className="sr-only">No {laneName} slots</span>;
  }
  const dotCount = Math.min(capacity, 5);
  return (
    <span
      data-testid={testId}
      title={`${capacity} open ${laneName} slot${capacity === 1 ? '' : 's'}`}
      className="inline-flex items-center gap-1 rounded border border-border/35 bg-bg3/25 px-2 py-1"
    >
      {Array.from({ length: dotCount }, (_unused, index) => (
        <span key={index} className="h-1.5 w-1.5 rounded-full bg-silver-dk/70" />
      ))}
      {capacity > dotCount && <span className="font-mono text-[9px] text-silver-dk">+{capacity - dotCount}</span>}
    </span>
  );
}

function PlannerSlotBox({
  slot,
  lane,
  bodyName,
  testId,
  selected,
  onSelect,
  onAdd,
  warningCount = 0,
}: {
  slot: PlannerStructureSlot;
  lane: PlannerCanvasLane;
  bodyName: string;
  testId: string;
  selected: boolean;
  onSelect: (selection: TopologySelection) => void;
  onAdd?: () => void;
  warningCount?: number;
}) {
  const primaryEconomy = slot.economySegments[0]?.economy;
  const color = primaryEconomy ? economyColor(primaryEconomy) : undefined;
  const isStructure = slot.kind === 'existing' || slot.kind === 'planned' || slot.kind === 'projected' || slot.kind === 'overflow';
  const inferredExisting = slot.kind === 'existing' && slot.trustStatus === 'inferred';
  const confirmedExisting = slot.kind === 'existing' && slot.trustStatus === 'confirmed';
  const interactive = Boolean(onAdd || slot.placementIndex != null || slot.projectionIndex != null);
  const slotStyle: CSSProperties = {};
  if (slot.kind === 'existing') {
    slotStyle.background = 'linear-gradient(180deg, rgba(74,222,128,0.18), rgba(18,20,24,0.9))';
  }
  if (slot.kind === 'planned' && color) {
    slotStyle.borderColor = color;
    slotStyle.background = `linear-gradient(180deg, ${economySoftColor(primaryEconomy)}, rgba(18,20,24,0.9))`;
  }
  if (slot.kind === 'projected' && color) {
    slotStyle.borderColor = color;
    slotStyle.background = `linear-gradient(180deg, ${economySoftColor(primaryEconomy)}, rgba(18,20,24,0.48))`;
  }

  const content = (
    <>
      {slot.kind === 'existing' && <span data-testid="planner-canvas-existing-structure" className="sr-only">{slot.fullName}</span>}
      {slot.kind === 'projected' && <span data-testid="planner-canvas-projected-structure" className="sr-only">{slot.fullName}</span>}
      <span data-testid={isStructure ? 'planner-canvas-structure-pill' : undefined} className="max-w-full truncate">
        {slot.kind === 'empty' && onAdd ? '+' : slot.label}
      </span>
      {inferredExisting && (
        <span data-testid="planner-canvas-inferred-existing" className="absolute right-1 top-1 rounded border border-gold/45 bg-gold/15 px-1 text-[8px] leading-tight text-gold">
          verify
        </span>
      )}
      {confirmedExisting && (
        <span data-testid="planner-canvas-confirmed-existing" className="absolute right-1 top-1 rounded border border-green/45 bg-green/15 px-1 text-[8px] leading-tight text-green">
          known
        </span>
      )}
      {slot.economySegments.length > 0 && <StructureEconomyMicroBar segments={slot.economySegments} />}
      {slot.economyContextLabel && <span data-testid="planner-canvas-contextual-economy" className="sr-only">{slot.economyContextLabel}</span>}
      {(warningCount > 0 || slot.warningLabels.length > 0) && (
        <span data-testid="planner-canvas-prerequisite-warning" className="sr-only">Prerequisite warning</span>
      )}
    </>
  );

  const className = [
    'group/slot relative flex overflow-hidden rounded border px-1.5 text-center font-mono text-[11px] font-bold uppercase leading-tight transition',
    isStructure ? 'h-11 min-w-[94px] max-w-[148px] items-start justify-center pb-3 pt-1.5' : 'h-8 min-w-[74px] max-w-[112px] items-center justify-center',
    interactive && 'hover:-translate-y-0.5 hover:border-orange-lt hover:shadow-brand-glow',
    selected && 'ring-2 ring-orange/70',
    slot.kind === 'empty' && (onAdd ? 'border-orange/55 bg-orange/15 text-orange font-semibold' : 'border-border/70 bg-bg2/45 text-silver-2'),
    slot.kind === 'existing' && (inferredExisting ? 'border-dashed border-gold/65 text-gold' : 'border-green/65 text-green'),
    slot.kind === 'planned' && 'text-silver-lt',
    slot.kind === 'projected' && 'border-dashed text-cyan/90 opacity-75',
    slot.kind === 'unknown' && 'border-dashed border-gold/65 bg-gold/10 text-gold',
    slot.kind === 'overflow' && 'border-orange bg-orange/20 text-orange-lt',
  ].filter(Boolean).join(' ');

  const selectionTarget = slot.placementIndex != null
    ? { type: 'placement' as const, placementIndex: slot.placementIndex }
    : slot.projectionIndex != null
      ? { type: 'projected-placement' as const, placementIndex: slot.projectionIndex }
      : null;

  if (!selectionTarget && slot.kind === 'empty' && onAdd) {
    const addLabel = lane === 'orbital'
      ? `Add orbit structure to ${bodyName} from empty slot`
      : `Add surface structure to ${bodyName} from empty slot`;
    return (
      <button
        type="button"
        data-testid={testId}
        title={addLabel}
        aria-label={addLabel}
        onClick={onAdd}
        className={className}
        style={slotStyle}
      >
        {content}
      </button>
    );
  }

  if (!selectionTarget) {
    return (
      <span data-testid={testId} title={slot.title} className={className} style={slotStyle}>
        {content}
      </span>
    );
  }

  return (
    <button
      type="button"
      data-testid={testId}
      title={slot.title}
      aria-pressed={selected}
      onClick={() => onSelect(selectionTarget)}
      className={className}
      style={slotStyle}
    >
      {content}
    </button>
  );
}

function plannerCanvasLaneToPlannerLane(lane: VisiblePlannerCanvasLane): BodyPlannerLane {
  return lane === 'ground' ? 'surface' : 'orbital';
}

function StructureEconomyMicroBar({ segments }: { segments: PlannerEconomySegment[] }) {
  const hasInherited = segments.some((segment) => segment.inherited);
  const total = Math.max(1, segments.reduce((sum, segment) => sum + segment.share, 0));
  const title = hasInherited
    ? `Inherited/contextual baseline: ${segments.map((segment) => `${segment.economy} ${formatShare(segment.share)}`).join(' / ')}. Source: ${segments[0]?.calculationSource ?? 'ED-Finder body economy profile'}. Run Preview for validated outcome.`
    : segments.map((segment) => {
      const strength = segment.strength == null ? 'CP generated unavailable' : `CP generated +${segment.strength}`;
      return `Direct facility economy: ${segment.economy} ${formatShare(segment.share)} | ${strength} | Source: catalogue/template`;
    }).join(' / ');

  return (
    <span
      data-testid="planner-canvas-structure-economy"
      aria-label={title}
      title={title}
      className="absolute inset-x-0 bottom-0 flex h-2.5 overflow-hidden bg-bg4/80"
    >
      {segments.map((segment) => (
        <span
          key={segment.economy}
          data-economy={segment.economy}
          data-economy-color={economyColor(segment.economy)}
          className={segment.projected ? 'opacity-60' : ''}
          style={{
            width: `${(segment.share / total) * 100}%`,
            backgroundColor: economyColor(segment.economy),
          }}
        />
      ))}
    </span>
  );
}

function formatShare(value: number): string {
  return Number.isInteger(value) ? `${value}%` : `${value.toFixed(1)}%`;
}

function CanvasPill({ label, tone }: { label: string; tone: 'silver' | 'orange' | 'cyan' | 'green' | 'gold' }) {
  const toneClass = {
    silver: 'border-border/60 bg-bg3/45 text-silver',
    orange: 'border-orange/35 bg-orange/10 text-orange',
    cyan: 'border-cyan/35 bg-cyan/10 text-cyan',
    green: 'border-green/35 bg-green/10 text-green',
    gold: 'border-gold/35 bg-gold/10 text-gold',
  }[tone];
  return <span className={['rounded border px-1.5 py-0.5 font-mono uppercase tracking-[0.1em]', toneClass].join(' ')}>{label}</span>;
}
