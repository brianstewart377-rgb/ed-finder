import { Network, Plus, Sparkles, Target } from 'lucide-react';
import { useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { formatPopulationForSystem } from '@/lib/format';
import { archetypeTierFromScore, formatArchetypeLabel, getDevelopmentScore } from '@/lib/archetypes';
import type { SimulateBuildPlacement, SystemBody, SystemDetail } from '@/types/api';
import {
  compactBodyDisplayName,
} from '@/features/system-detail/simulation-preview/buildPlanLayoutUtils';
import { bodyIdKey, sameBodyId } from '@/features/system-detail/simulation-preview/bodyIdUtils';
import type { TopologyPlanSnapshot, TopologySelection, TopologySelectionContext } from './ColonyTopologyRail';
import type { BodyPlannerLane } from './BodySlotPlanner';
import { PlanningEconomyStrip } from './PlanningEconomyStrip';
import { systemBodyData } from './slotCapacityFallback';
import {
  PLANNING_ECONOMY_NOTE,
  type PlanningEconomyLedger,
  type PlanningEconomyName,
} from './planningEconomy';
import { economyColor, economySoftColor } from './economyVisuals';
import {
  existingStructureDisplayType,
  resolveExistingInfrastructure,
  type ExistingStructure,
} from './existingInfrastructure';
import {
  contextualEconomyLabel,
  contextualRoleLabel,
  missingPrerequisitesForPlacement,
  prerequisiteSummaryLabel,
  type PrerequisiteIssue,
} from './structurePlanningRules';
import {
  bodyMarker,
  buildPlannerTelemetryStats,
  buildProjectionComparison,
  buildRavenPlannerRows,
  numericValue,
  placementBodyId,
  ravenLaneForPlacement,
  structureDisplayName,
  structureEconomySegments,
  summarizeRavenPlannerRows,
} from './ravenPlannerUtils';

type RavenLane = 'orbital' | 'ground' | 'unassigned';
type VisibleRavenLane = Exclude<RavenLane, 'unassigned'>;
type RavenSlotKind = 'empty' | 'existing' | 'planned' | 'projected' | 'unknown' | 'overflow';
type ProjectionComparisonView = 'bodies' | 'economy' | 'slots';

export interface RavenEconomySegment {
  economy: PlanningEconomyName;
  share: number;
  strength: number | null;
  projected: boolean;
  /**
   * True when this segment represents an inherited contextual baseline derived
   * from ED-Finder's body economy profile formula. It is still pre-Preview:
   * Preview remains the final validator for CP, links, services, and final
   * economy order.
   */
  inherited?: boolean;
  calculationSource?: string;
  caveats?: string[];
}

export interface RavenStructureSlot {
  id: string;
  kind: RavenSlotKind;
  label: string;
  fullName: string;
  title: string;
  economySegments: RavenEconomySegment[];
  placementIndex: number | null;
  projectionIndex: number | null;
  existingStructureId: string | null;
  buildOrder: number | null;
  status: 'existing' | 'planned' | 'projected' | 'unknown';
  economyContextLabel: string | null;
  warningLabels: string[];
  trustStatus?: 'confirmed' | 'inferred' | 'unresolved';
}

export interface RavenPlannerRow {
  id: string;
  body: SystemBody;
  depth: number;
  isLast: boolean;
  guide: boolean[];
  displayName: string;
  compactName: string;
  bodyKind: string;
  bodyTags: string[];
  orbitalCapacity: number | null;
  groundCapacity: number | null;
  orbitalCapacityEstimated: boolean;
  groundCapacityEstimated: boolean;
  orbitalSlots: RavenStructureSlot[];
  groundSlots: RavenStructureSlot[];
  unassignedSlots: RavenStructureSlot[];
  bodyEconomy: PlanningEconomyLedger;
  projected: boolean;
  warningCount: number;
  existingCount: number;
  inferredExistingCount: number;
  plannedCount: number;
  projectedCount: number;
  emptySlotCount: number;
  orbitalAddDisabledReason: string | null;
  groundAddDisabledReason: string | null;
  orbitalOccupancy: RavenLaneOccupancySummary;
  groundOccupancy: RavenLaneOccupancySummary;
}

interface RavenLaneOccupancySummary {
  capacity: number | null;
  existingCount: number;
  inferredExistingCount: number;
  plannedCount: number;
  projectedCount: number;
  remainingForPlan: number | null;
  projectedOverflowCount: number;
}

export function RavenStylePlannerCanvas({
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
  const rows = buildRavenPlannerRows(system, snapshot);
  const existingResolution = resolveExistingInfrastructure(system);
  const occupancySummary = summarizeRavenPlannerRows(rows, existingResolution.unresolved.length);
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
      aria-label="Raven-style real planner canvas"
      data-testid="raven-real-planner-canvas"
      data-layout="data-driven-raven-canvas"
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
        <div data-testid="raven-existing-infrastructure-summary" className="border-b border-green/25 bg-green/8 px-3 py-2 font-mono text-[10px] uppercase tracking-[0.1em] text-green">
          Existing infrastructure detected: {occupancySummary.existingCount} matched slot occupant{occupancySummary.existingCount === 1 ? '' : 's'}.
        </div>
      )}
      {hasEstimatedSlots && (
        <div data-testid="raven-slot-estimate-disclaimer" className="border-b border-gold/25 bg-gold/8 px-3 py-2 font-mono text-[10px] italic text-gold">
          Predicted slots - verify in Architect Mode.
        </div>
      )}

      <div data-testid="raven-real-planner-scroll-region" className="overflow-x-hidden lg:overflow-x-auto">
        <div data-testid="raven-real-planner-grid-frame" className="min-w-0 lg:min-w-[860px]">
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
              <RavenPlannerBodyRow
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

export function RavenPlannerTelemetryPanel({
  system,
  snapshot,
  economyLedger,
  prerequisiteIssues = [],
  selectedContext,
  selection,
}: {
  system: SystemDetail;
  snapshot: TopologyPlanSnapshot;
  economyLedger: PlanningEconomyLedger;
  prerequisiteIssues?: PrerequisiteIssue[];
  selectedContext: TopologySelectionContext;
  selection: TopologySelection;
}) {
  const [projectionView, setProjectionView] = useState<ProjectionComparisonView>('bodies');
  const stats = buildPlannerTelemetryStats(snapshot);
  const population = formatPopulationForSystem(system);
  const score = typeof system.score === 'number' ? Math.round(system.score) : 'n/a';
  const rows = buildRavenPlannerRows(system, snapshot);
  const projectionComparison = buildProjectionComparison(system, snapshot, economyLedger, rows);
  const selectedBodyId = selectedBodyIdForSelection(snapshot, selection);
  const selectedProjectedCount = selectedBodyId ? countBodyPlacements(snapshot.projection?.placements ?? [], selectedBodyId) : 0;
  const bodyDetail = buildSelectedBodyTelemetryDetail(rows, snapshot, selection);
  const structureDetail = buildSelectedStructureTelemetryDetail(system, snapshot, selection);
  const warningItems = buildTelemetryWarningItems(system, snapshot, economyLedger, selectedContext, prerequisiteIssues);
  const unresolvedExistingCount = resolveExistingInfrastructure(system).unresolved.length;

  return (
    <aside
      aria-label="Raven-style planner telemetry"
      data-testid="raven-real-telemetry-panel"
      data-layout="wide-readable-telemetry"
      className="rounded-chunk border border-cyan/25 bg-bg2/95 p-3"
    >
      <div className="flex items-center gap-2 border-b border-border/45 pb-2">
        <div className="grid h-8 w-8 place-items-center rounded border border-orange/35 bg-orange/10 text-orange">
          <Target size={17} />
        </div>
        <div>
          <h2 className="font-display text-base text-orange">Planning Telemetry</h2>
          <p className="text-xs leading-relaxed text-silver">Live planner data, Preview remains explicit.</p>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 border-b border-border/35 pb-3">
        <TelemetryMetric label="System score" value={String(score)} />
        <TelemetryMetric label="Population" value={population} />
        <TelemetryMetric label="Planned haul" value={`${snapshot.placements.length} builds`} />
        <TelemetryMetric label="Build staged" value={`${snapshot.placements.length}${snapshot.projection ? ` +${snapshot.projection.placements.length}` : ''}`} />
      </div>

      <DevelopmentProfileCard system={system} />

      <div className="mt-4 space-y-2">
        {stats.map((stat) => (
          <ZeroCenteredStatBar key={stat.id} id={stat.id} label={stat.label} value={stat.value} />
        ))}
      </div>

      <div className="mt-4 border-t border-border/70 pt-3">
        <h3 className="font-mono text-[11px] uppercase tracking-[0.12em] text-cyan">Economy mix</h3>
        <p className="mt-1 text-xs leading-relaxed text-silver">{PLANNING_ECONOMY_NOTE}</p>
        <div className="mt-2">
          <PlanningEconomyStrip ledger={economyLedger} testId="raven-telemetry-economy-ledger" />
        </div>
      </div>

      <ProjectionComparisonCard
        summary={projectionComparison}
        view={projectionView}
        selectedProjectedCount={selectedProjectedCount}
        onViewChange={setProjectionView}
      />

      <div className="mt-4 border-t border-cyan/25 pt-3">
        <div className="font-mono text-[11px] uppercase tracking-[0.12em] text-cyan">Selected focus</div>
        <div className="mt-1 text-base font-semibold leading-snug text-silver">{selectedContext.label}</div>
        <div className="mt-1 text-sm text-silver">{selectedContext.kind}</div>
        <p className="mt-2 text-sm leading-relaxed text-silver">{selectedContext.detail}</p>
      </div>

      {bodyDetail && <SelectedBodyTelemetryCard detail={bodyDetail} />}
      {structureDetail && <SelectedStructureTelemetryCard detail={structureDetail} />}

      <div className="mt-4 border-t border-border/45 pt-3" data-testid="raven-telemetry-warning-summary">
        <div className="font-mono text-[11px] uppercase tracking-[0.12em] text-gold">Warnings / needs</div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          <TelemetryChip
            label={`${unresolvedExistingCount} unresolved existing`}
            tone={unresolvedExistingCount > 0 ? 'gold' : 'green'}
          />
          {warningItems.length > 0 && warningItems.map((item) => <TelemetryChip key={item} label={item} tone="gold" />)}
          {warningItems.length === 0 && unresolvedExistingCount === 0 && <TelemetryChip label="No active warnings" tone="green" />}
        </div>
      </div>
    </aside>
  );
}

function RavenPlannerBodyRow({
  row,
  selected,
  selectedPlacementIndex,
  selectedProjectedPlacementIndex,
  responsiveGridClassName,
  onSelect,
  onRequestAddStructure,
  prerequisiteIssues,
}: {
  row: RavenPlannerRow;
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
      data-testid={`raven-real-body-row-${row.id}`}
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
        <RavenSlotLane
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
        <RavenSlotLane
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
                <RavenSlotBox
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
      data-testid="raven-unresolved-existing-infrastructure"
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
              data-testid="raven-unresolved-existing-structure"
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
  row: RavenPlannerRow;
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
              testId={`raven-body-capacity-${row.id}`}
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

function RavenSlotLane({
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
  lane: VisibleRavenLane;
  capacity: number | null;
  occupancy: RavenLaneOccupancySummary;
  slots: RavenStructureSlot[];
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
  const plannerLane = ravenLaneToPlannerLane(lane);
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
            <RavenSlotBox
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
  occupancy: RavenLaneOccupancySummary;
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

function RavenSlotBox({
  slot,
  lane,
  bodyName,
  testId,
  selected,
  onSelect,
  onAdd,
  warningCount = 0,
}: {
  slot: RavenStructureSlot;
  lane: RavenLane;
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
      {slot.kind === 'existing' && <span data-testid="raven-existing-structure" className="sr-only">{slot.fullName}</span>}
      {slot.kind === 'projected' && <span data-testid="raven-projected-ghost-structure" className="sr-only">{slot.fullName}</span>}
      <span data-testid={isStructure ? 'raven-structure-slot-pill' : undefined} className="max-w-full truncate">
        {slot.kind === 'empty' && onAdd ? '+' : slot.label}
      </span>
      {inferredExisting && (
        <span data-testid="raven-inferred-existing-marker" className="absolute right-1 top-1 rounded border border-gold/45 bg-gold/15 px-1 text-[8px] leading-tight text-gold">
          verify
        </span>
      )}
      {confirmedExisting && (
        <span data-testid="raven-confirmed-existing-marker" className="absolute right-1 top-1 rounded border border-green/45 bg-green/15 px-1 text-[8px] leading-tight text-green">
          known
        </span>
      )}
      {slot.economySegments.length > 0 && <StructureEconomyMicroBar segments={slot.economySegments} />}
      {slot.economyContextLabel && <span data-testid="raven-contextual-economy-chip" className="sr-only">{slot.economyContextLabel}</span>}
      {(warningCount > 0 || slot.warningLabels.length > 0) && (
        <span data-testid="raven-prerequisite-warning-chip" className="sr-only">Prerequisite warning</span>
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

function ravenLaneToPlannerLane(lane: VisibleRavenLane): BodyPlannerLane {
  return lane === 'ground' ? 'surface' : 'orbital';
}

function StructureEconomyMicroBar({ segments }: { segments: RavenEconomySegment[] }) {
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
      data-testid="raven-structure-economy-micro-bar"
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

interface ProjectionEconomyDelta {
  economy: PlanningEconomyName;
  planned: number;
  projected: number;
  total: number;
}

export interface ProjectionComparisonSummary {
  label: string;
  hasProjection: boolean;
  plannedPlacements: number;
  projectedPlacements: number;
  plannedBodyCount: number;
  projectedBodyCount: number;
  sharedBodyCount: number;
  newBodyLabels: string[];
  plannedOnlyBodyLabels: string[];
  projectedOrbitalCount: number;
  projectedGroundCount: number;
  projectedUnknownLaneCount: number;
  slotOverflowCount: number;
  economyDeltas: ProjectionEconomyDelta[];
}

function ProjectionComparisonCard({
  summary,
  view,
  selectedProjectedCount,
  onViewChange,
}: {
  summary: ProjectionComparisonSummary;
  view: ProjectionComparisonView;
  selectedProjectedCount: number;
  onViewChange: (view: ProjectionComparisonView) => void;
}) {
  const controlsDisabled = !summary.hasProjection;
  return (
    <section className="mt-4 border-t border-border/35 pt-3" data-testid="raven-projection-comparison">
      <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.12em] text-orange">
        <Sparkles size={14} />
        Projection comparison
      </div>
      <p className="mt-1 text-sm leading-relaxed text-silver">{summary.label}</p>
      <div className="mt-2 grid grid-cols-3 gap-1.5" role="group" aria-label="Projection comparison view">
        <ProjectionViewButton view="bodies" active={view === 'bodies'} disabled={controlsDisabled} onSelect={onViewChange} />
        <ProjectionViewButton view="economy" active={view === 'economy'} disabled={controlsDisabled} onSelect={onViewChange} />
        <ProjectionViewButton view="slots" active={view === 'slots'} disabled={controlsDisabled} onSelect={onViewChange} />
      </div>
      {!summary.hasProjection ? (
        <p className="mt-2 text-xs leading-relaxed text-silver">
          Select a Suggested Build candidate to compare ghost structures against the current Build Plan. Loading and Preview stay explicit.
        </p>
      ) : view === 'bodies' ? (
        <ProjectionBodiesView summary={summary} selectedProjectedCount={selectedProjectedCount} />
      ) : view === 'economy' ? (
        <ProjectionEconomyView summary={summary} />
      ) : (
        <ProjectionSlotsView summary={summary} />
      )}
    </section>
  );
}

function ProjectionViewButton({
  view,
  active,
  disabled,
  onSelect,
}: {
  view: ProjectionComparisonView;
  active: boolean;
  disabled: boolean;
  onSelect: (view: ProjectionComparisonView) => void;
}) {
  const label = view === 'bodies' ? 'Bodies' : view === 'economy' ? 'Economy' : 'Slots';
  return (
    <button
      type="button"
      data-testid={`projection-comparison-${view}-toggle`}
      aria-pressed={active}
      disabled={disabled}
      onClick={() => onSelect(view)}
      className={[
        'rounded border px-2 py-1 font-mono text-[10px] uppercase tracking-[0.1em] transition-colors disabled:cursor-not-allowed disabled:opacity-45',
        active ? 'border-orange/55 bg-orange/15 text-orange' : 'border-border/60 bg-bg3/45 text-silver hover:border-cyan/45 hover:text-cyan',
      ].join(' ')}
    >
      {label}
    </button>
  );
}

function ProjectionBodiesView({ summary, selectedProjectedCount }: { summary: ProjectionComparisonSummary; selectedProjectedCount: number }) {
  return (
    <div className="mt-2 space-y-2" data-testid="projection-comparison-bodies">
      <div className="grid grid-cols-3 gap-1.5">
        <ProjectionMetric label="Planned bodies" value={summary.plannedBodyCount} tone="orange" />
        <ProjectionMetric label="Ghost bodies" value={summary.projectedBodyCount} tone="cyan" />
        <ProjectionMetric label="Shared" value={summary.sharedBodyCount} tone="silver" />
      </div>
      <ProjectionBodyList label="New ghost bodies" values={summary.newBodyLabels} />
      <ProjectionBodyList label="Plan-only bodies" values={summary.plannedOnlyBodyLabels} />
      {selectedProjectedCount > 0 && (
        <p className="rounded border border-cyan/35 bg-cyan/10 px-2 py-1 font-mono text-[10px] text-cyan">
          Selected body carries {selectedProjectedCount} projected ghost structure{selectedProjectedCount === 1 ? '' : 's'}.
        </p>
      )}
    </div>
  );
}

function ProjectionEconomyView({ summary }: { summary: ProjectionComparisonSummary }) {
  return (
    <div className="mt-2 space-y-1.5" data-testid="projection-comparison-economy">
      {summary.economyDeltas.length > 0 ? summary.economyDeltas.map((entry) => (
        <div key={entry.economy} className="grid grid-cols-[4.5rem_1fr_auto] items-center gap-2 rounded border border-border/55 bg-bg3/35 px-2 py-1 font-mono text-[10px]">
          <span className="truncate text-silver">{entry.economy}</span>
          <span className="h-1.5 overflow-hidden rounded bg-bg4/80">
            <span
              className="block h-full bg-cyan/70"
              style={{ width: `${entry.projected > 0 && entry.total > 0 ? Math.max(8, (entry.projected / entry.total) * 100) : 0}%` }}
            />
          </span>
          <span className="text-right text-silver">
            <span className="text-orange">{entry.planned}</span>
            <span className="text-cyan"> +{entry.projected}</span>
          </span>
        </div>
      )) : (
        <p className="rounded border border-border/55 bg-bg3/35 px-2 py-1 font-mono text-[10px] text-silver">No economy metadata to compare.</p>
      )}
    </div>
  );
}

function ProjectionSlotsView({ summary }: { summary: ProjectionComparisonSummary }) {
  return (
    <div className="mt-2 grid grid-cols-2 gap-1.5" data-testid="projection-comparison-slots">
      <ProjectionMetric label="Ghost orbit" value={summary.projectedOrbitalCount} tone="cyan" />
      <ProjectionMetric label="Ghost surface" value={summary.projectedGroundCount} tone="cyan" />
      <ProjectionMetric label="Needs lane" value={summary.projectedUnknownLaneCount} tone={summary.projectedUnknownLaneCount > 0 ? 'gold' : 'green'} />
      <ProjectionMetric label="Overflow risks" value={summary.slotOverflowCount} tone={summary.slotOverflowCount > 0 ? 'gold' : 'green'} />
    </div>
  );
}

function ProjectionMetric({ label, value, tone }: { label: string; value: number; tone: 'orange' | 'cyan' | 'silver' | 'gold' | 'green' }) {
  const toneClass = {
    orange: 'text-orange',
    cyan: 'text-cyan',
    silver: 'text-silver',
    gold: 'text-gold',
    green: 'text-green',
  }[tone];
  return (
    <div className="rounded border border-border/55 bg-bg3/35 px-2 py-1 font-mono">
      <div className="truncate text-[9px] uppercase tracking-[0.12em] text-silver">{label}</div>
      <div className={["mt-0.5 text-[13px] font-semibold", toneClass].join(' ')}>{value}</div>
    </div>
  );
}

function ProjectionBodyList({ label, values }: { label: string; values: string[] }) {
  return (
    <div className="rounded border border-border/55 bg-bg3/35 px-2 py-1 font-mono text-[10px]">
      <div className="uppercase tracking-[0.12em] text-silver">{label}</div>
      <div className="mt-0.5 truncate text-silver">{values.length > 0 ? values.join(', ') : 'None'}</div>
    </div>
  );
}

interface BodyTelemetryDetail {
  row: RavenPlannerRow;
  plannedCount: number;
  projectedCount: number;
  capacityLabel: string;
  emptySlotCount: number;
}

interface StructureTelemetryDetail {
  name: string;
  templateId: string;
  status: 'planned' | 'projected';
  lane: RavenLane;
  bodyName: string;
  category: string;
  buildOrder: number | null;
  economySegments: RavenEconomySegment[];
  economyContextLabel: string | null;
  roleLabel: string | null;
  prerequisiteWarnings: string[];
  strength: number | null;
}

function SelectedBodyTelemetryCard({ detail }: { detail: BodyTelemetryDetail }) {
  return (
    <section className="mt-4 border-t border-cyan/25 pt-3" data-testid="raven-telemetry-body-context">
      <div className="font-mono text-[11px] uppercase tracking-[0.12em] text-cyan">Selected body summary</div>
      <div className="mt-2 grid grid-cols-2 gap-2">
        <TelemetryField label="Capacity" value={detail.capacityLabel} />
        <TelemetryField label="Slots" value={`${detail.row.existingCount} existing / ${detail.plannedCount} planned / ${detail.projectedCount} projected`} />
        <TelemetryField label="Kind" value={detail.row.bodyKind} />
        <TelemetryField label="Empty" value={String(detail.emptySlotCount)} tone={detail.emptySlotCount > 0 ? 'green' : 'silver'} />
      </div>
      <div className="mt-2">
        <PlanningEconomyStrip ledger={detail.row.bodyEconomy} compact testId="raven-telemetry-body-economy" />
      </div>
    </section>
  );
}

function SelectedStructureTelemetryCard({ detail }: { detail: StructureTelemetryDetail }) {
  return (
    <section
      className={detail.status === 'projected' ? 'mt-4 border-t border-cyan/35 pt-3' : 'mt-4 border-t border-orange/35 pt-3'}
      data-testid="raven-telemetry-structure-context"
      data-projected={detail.status === 'projected' ? 'true' : 'false'}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <div className={detail.status === 'projected' ? 'font-mono text-[11px] uppercase tracking-[0.12em] text-cyan' : 'font-mono text-[11px] uppercase tracking-[0.12em] text-orange'}>
          Selected structure
        </div>
        <TelemetryChip label={detail.status === 'projected' ? 'Projected ghost' : 'Planned'} tone={detail.status === 'projected' ? 'cyan' : 'orange'} />
      </div>
      <div className="mt-2 text-sm font-semibold leading-snug text-silver">{detail.name}</div>
      <div className="mt-2 grid grid-cols-2 gap-2">
        <TelemetryField label="Lane" value={`${detail.lane === 'unassigned' ? 'needs lane' : detail.lane === 'ground' ? 'surface' : 'orbit'} / ${detail.bodyName}`} tone="cyan" />
        <TelemetryField label="Build order" value={detail.buildOrder == null ? 'n/a' : `#${detail.buildOrder}`} />
        <TelemetryField label="Variant" value={detail.category} />
        <TelemetryField label="Strength" value={detail.strength == null ? 'n/a' : `+${detail.strength} CP`} tone={detail.strength ? 'green' : 'silver'} />
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {detail.economySegments.length > 0
          ? detail.economySegments.map((segment) => (
            <TelemetryChip
              key={segment.economy}
              label={segment.inherited
                ? `${segment.economy} ${formatShare(segment.share)} baseline`
                : `${segment.economy} direct${segment.strength == null ? '' : ` / +${segment.strength}`}`}
              tone={detail.status === 'projected' ? 'cyan' : 'orange'}
            />
          ))
          : detail.economyContextLabel
            ? <TelemetryChip label="Contextual economy" tone="cyan" />
            : <TelemetryChip label="No economy metadata" tone="gold" />}
        {detail.roleLabel && <TelemetryChip label={detail.roleLabel} tone="cyan" />}
      </div>
      {detail.economyContextLabel && (
        <p data-testid="raven-telemetry-contextual-economy" className="mt-2 rounded border border-cyan/30 bg-cyan/8 px-2 py-1 font-mono text-[10px] leading-snug text-cyan">
          {detail.economyContextLabel}
        </p>
      )}
      {detail.prerequisiteWarnings.length > 0 && (
        <p data-testid="raven-telemetry-prerequisite-warning" className="mt-2 rounded border border-gold/35 bg-gold/10 px-2 py-1 font-mono text-[10px] leading-snug text-gold">
          Missing prerequisite: {detail.prerequisiteWarnings.join('; ')}
        </p>
      )}
      <p className="mt-2 break-all font-mono text-[10px] text-silver">{detail.templateId}</p>
    </section>
  );
}

function TelemetryField({
  label,
  value,
  tone = 'silver',
}: {
  label: string;
  value: ReactNode;
  tone?: 'silver' | 'orange' | 'cyan' | 'green' | 'gold';
}) {
  const toneClass = {
    silver: 'text-silver',
    orange: 'text-orange',
    cyan: 'text-cyan',
    green: 'text-green',
    gold: 'text-gold',
  }[tone];
  return (
    <div className="rounded border border-border/55 bg-bg3/35 px-2 py-1">
      <div className="font-mono text-[9px] uppercase tracking-[0.12em] text-silver">{label}</div>
      <div className={["mt-0.5 truncate text-[11px] font-semibold", toneClass].join(' ')}>{value}</div>
    </div>
  );
}

function TelemetryChip({
  label,
  tone = 'silver',
}: {
  label: string;
  tone?: 'silver' | 'orange' | 'cyan' | 'green' | 'gold';
}) {
  const toneClass = {
    silver: 'border-border/60 bg-bg3/45 text-silver',
    orange: 'border-orange/35 bg-orange/10 text-orange',
    cyan: 'border-cyan/35 bg-cyan/10 text-cyan',
    green: 'border-green/35 bg-green/10 text-green',
    gold: 'border-gold/35 bg-gold/10 text-gold',
  }[tone];
  return <span className={["rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.1em]", toneClass].join(' ')}>{label}</span>;
}

function buildSelectedBodyTelemetryDetail(
  rows: RavenPlannerRow[],
  snapshot: TopologyPlanSnapshot,
  selection: TopologySelection,
): BodyTelemetryDetail | null {
  const bodyId = selectedBodyIdForSelection(snapshot, selection);
  if (!bodyId) return null;
  const row = rows.find((candidate) => candidate.id === bodyId);
  if (!row) return null;
  const plannedCount = countBodyPlacements(snapshot.placements, bodyId);
  const projectedCount = countBodyPlacements(snapshot.projection?.placements ?? [], bodyId);
  return {
    row,
    plannedCount,
    projectedCount,
    capacityLabel: `O${row.orbitalCapacity ?? '?'} / S${row.groundCapacity ?? '?'}`,
    emptySlotCount: row.emptySlotCount,
  };
}

function buildSelectedStructureTelemetryDetail(
  system: SystemDetail,
  snapshot: TopologyPlanSnapshot,
  selection: TopologySelection,
): StructureTelemetryDetail | null {
  if (selection.type !== 'placement' && selection.type !== 'projected-placement') return null;
  const projected = selection.type === 'projected-placement';
  const placement = projected
    ? snapshot.projection?.placements[selection.placementIndex]
    : snapshot.placements[selection.placementIndex];
  if (!placement) return null;
  const template = snapshot.templates.find((candidate) => candidate.id === placement.facility_template_id);
  const bodyId = placement.local_body_id != null ? bodyIdKey(placement.local_body_id) : null;
  const body = bodyId
    ? systemBodyData(system).find((candidate) => sameBodyId(candidate.id, bodyId))
    : null;
  const lane = ravenLaneForPlacement(
    template,
    body ?? undefined,
    projected ? snapshot.projection?.placementLaneHints?.[selection.placementIndex] : snapshot.placementLaneHints?.[selection.placementIndex],
  );
  const strength = template ? Math.max(0, (template.yellow_cp_generated ?? 0) + (template.green_cp_generated ?? 0)) : null;
  return {
    name: structureDisplayName(template, placement.facility_template_id),
    templateId: placement.facility_template_id,
    status: projected ? 'projected' : 'planned',
    lane,
    bodyName: body ? compactBodyDisplayName(body, system.name) : 'unassigned body',
    category: template?.category ?? 'unknown variant',
    buildOrder: placement.build_order ?? null,
    economySegments: structureEconomySegments(template, projected),
    economyContextLabel: contextualEconomyLabel(template),
    roleLabel: contextualRoleLabel(template, placement),
    prerequisiteWarnings: projected ? [] : missingPrerequisitesForPlacement(placement, snapshot.placements, snapshot.templates),
    strength,
  };
}

function buildTelemetryWarningItems(
  system: SystemDetail,
  snapshot: TopologyPlanSnapshot,
  economyLedger: PlanningEconomyLedger,
  selectedContext: TopologySelectionContext,
  prerequisiteIssues: PrerequisiteIssue[] = [],
): string[] {
  const bodies = systemBodyData(system);
  const bodyIds = new Set(bodies.filter((body) => body.id != null).map((body) => bodyIdKey(body.id)));
  const unassigned = snapshot.placements.filter((placement) => placement.local_body_id == null).length;
  const unknownBodies = snapshot.placements.filter((placement) => {
    const bodyId = placement.local_body_id != null ? bodyIdKey(placement.local_body_id) : '';
    return Boolean(bodyId && !bodyIds.has(bodyId));
  }).length;
  const slotGaps = bodies.filter((body) => body.id != null && !snapshot.slotPredictions?.predictions?.some((prediction) => sameBodyId(prediction.body_id, body.id))).length;
  return [
    selectedContext.warningCount > 0 ? `${selectedContext.warningCount} selected warning${selectedContext.warningCount === 1 ? '' : 's'}` : null,
    unassigned > 0 ? `${unassigned} unassigned` : null,
    unknownBodies > 0 ? `${unknownBodies} unmatched body` : null,
    economyLedger.unknownCount > 0 ? `${economyLedger.unknownCount} no economy metadata` : null,
    prerequisiteIssues.length > 0 ? prerequisiteSummaryLabel(prerequisiteIssues.length) : null,
    slotGaps > 0 ? `${Math.min(slotGaps, 99)} slot gap${slotGaps === 1 ? '' : 's'}` : null,
  ].filter((item): item is string => Boolean(item)).slice(0, 5);
}

function selectedBodyIdForSelection(snapshot: TopologyPlanSnapshot, selection: TopologySelection): string | null {
  if (selection.type === 'body') return selection.bodyId;
  if (selection.type === 'placement') return placementBodyId(snapshot.placements[selection.placementIndex]);
  if (selection.type === 'projected-placement') return placementBodyId(snapshot.projection?.placements[selection.placementIndex]);
  return null;
}

function countBodyPlacements(placements: SimulateBuildPlacement[], bodyId: string): number {
  return placements.filter((placement) => sameBodyId(placement.local_body_id, bodyId)).length;
}

function TelemetryMetric({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="grid grid-cols-[1fr_auto] items-baseline gap-2">
      <div className="truncate font-mono text-[10px] uppercase tracking-[0.1em] text-silver">{label}</div>
      <div className="text-right font-display text-base text-silver">{value}</div>
    </div>
  );
}

function DevelopmentProfileCard({ system }: { system: SystemDetail }) {
  const score = getDevelopmentScore(system);
  const tier = archetypeTierFromScore(score);
  const tierColor =
    tier === 'S' ? '#22d3ee' :
    tier === 'A' ? '#4ade80' :
    tier === 'B' ? '#facc15' :
    tier === 'C' ? '#ff7a14' :
    tier === 'D' ? '#ef4444' :
    '#8a8f96';
  const baseFacts: Array<{ label: string; value: ReactNode | null; tone: 'silver' | 'orange' | 'green' | 'gold' }> = [
    { label: 'Primary', value: system.primary_archetype ? formatArchetypeLabel(system.primary_archetype) : null, tone: 'orange' },
    { label: 'Secondary', value: system.secondary_archetype ? formatArchetypeLabel(system.secondary_archetype) : null, tone: 'silver' },
    { label: 'Buildability', value: numericValue(system.buildability_score), tone: 'green' },
    { label: 'Purity', value: numericValue(system.purity_score), tone: 'gold' },
    { label: 'Slots', value: numericValue(system.est_total_slots), tone: 'silver' },
    { label: 'Confidence', value: system.archetype_confidence != null ? `${Math.round(system.archetype_confidence * 100)}%` : null, tone: 'silver' },
  ];

  const facts = baseFacts.filter((item): item is { label: string; value: ReactNode; tone: 'silver' | 'orange' | 'green' | 'gold' } => (
    item.value !== null && item.value !== undefined
  ));

  return (
    <section
      data-testid="raven-development-profile-card"
      className="mt-4 rounded border border-orange/30 bg-orange/5 p-2"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-mono text-[11px] uppercase tracking-[0.14em] text-orange">Development profile</h3>
          <div className="mt-1 text-[10px] leading-relaxed text-silver">
            Current planning context from the development assessment and archetype fit.
          </div>
        </div>
        <div
          data-testid="raven-development-overall-score"
          className="shrink-0 rounded border px-2 py-1 text-right font-mono"
          style={{
            borderColor: `${tierColor}88`,
            background: `linear-gradient(180deg, ${tierColor}24, rgba(18,20,24,0.52))`,
            color: tierColor,
          }}
          title={`Development score: ${score ?? 'n/a'}/100`}
        >
          <div className="text-[9px] uppercase tracking-[0.12em]">{tier ?? '-'}</div>
          <div className="text-lg font-bold leading-none">{score ?? '-'}</div>
        </div>
      </div>

      {facts.length > 0 ? (
        <div className="mt-2 grid grid-cols-2 gap-1.5 font-mono text-[10px]">
          {facts.map((fact) => (
            <RatingFact key={fact.label} label={fact.label} value={fact.value} tone={fact.tone} />
          ))}
        </div>
      ) : (
        <p className="mt-3 rounded border border-gold/35 bg-gold/10 px-2 py-1 font-mono text-[10px] text-gold">
          No development assessment is present on this system record yet.
        </p>
      )}
    </section>
  );
}

function RatingFact({
  label,
  value,
  tone = 'silver',
}: {
  label: string;
  value: ReactNode;
  tone?: 'silver' | 'orange' | 'green' | 'gold';
}) {
  const toneClass = {
    silver: 'text-silver',
    orange: 'text-orange',
    green: 'text-green',
    gold: 'text-gold',
  }[tone];
  return (
    <div className="rounded border border-border/55 bg-bg3/35 px-2 py-1">
      <div className="truncate uppercase tracking-[0.12em] text-silver">{label}</div>
      <div className={['mt-0.5 truncate font-semibold', toneClass].join(' ')} title={String(value)}>{value}</div>
    </div>
  );
}

function ZeroCenteredStatBar({ id, label, value }: { id: string; label: string; value: number }) {
  const direction = value < 0 ? 'negative' : value > 0 ? 'positive' : 'neutral';
  const halfWidth = value === 0 ? 0 : Math.max(5, Math.min(50, (Math.abs(value) / 12) * 50));

  return (
    <div
      data-testid="raven-zero-centered-stat-bar"
      data-stat-id={id}
      data-direction={direction}
      className="grid grid-cols-[7.5rem_1fr_3.6rem] items-center gap-2 font-mono text-[11px]"
    >
      <span className="truncate text-silver">{label}</span>
      <span className="relative h-4 overflow-hidden rounded-sm border border-border/60 bg-bg4/80 shadow-inner-soft">
        <span data-testid={`raven-stat-${id}-zero-axis`} aria-hidden className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-silver/55" />
        <span
          data-testid={`raven-stat-${id}-negative`}
          data-tone="negative-red"
          aria-hidden
          className="absolute right-1/2 top-1/2 h-2 -translate-y-1/2 rounded-l-sm"
          style={{
            width: direction === 'negative' ? `${halfWidth}%` : '0%',
            backgroundColor: '#f87171',
            boxShadow: direction === 'negative' ? '0 0 10px rgba(248,113,113,0.35)' : undefined,
          }}
        />
        <span
          data-testid={`raven-stat-${id}-positive`}
          data-tone="positive-green"
          aria-hidden
          className="absolute left-1/2 top-1/2 h-2 -translate-y-1/2 rounded-r-sm"
          style={{
            width: direction === 'positive' ? `${halfWidth}%` : '0%',
            backgroundColor: '#4ade80',
            boxShadow: direction === 'positive' ? '0 0 10px rgba(74,222,128,0.35)' : undefined,
          }}
        />
      </span>
      <span className={direction === 'negative' ? 'text-right text-red' : direction === 'positive' ? 'text-right text-green' : 'text-right text-silver'}>
        {value > 0 ? '+' : ''}{value}
      </span>
    </div>
  );
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
