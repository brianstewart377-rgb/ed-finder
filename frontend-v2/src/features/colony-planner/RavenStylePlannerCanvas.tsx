import { Network, Plus, Sparkles, Target } from 'lucide-react';
import { useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { displayRationale } from '@/lib/rationale';
import { formatConfidence, formatPopulationForSystem, ratingTier } from '@/lib/format';
import { compareBodiesByHierarchy } from '@/lib/bodyHierarchySort';
import type { BodySlotPrediction, FacilityTemplate, SimulateBuildPlacement, SystemBody, SystemDetail } from '@/types/api';
import {
  bodyDisplayName,
  bodyTags,
  compactBodyDisplayName,
} from '@/features/system-detail/simulation-preview/buildPlanLayoutUtils';
import { bodyIdKey, sameBodyId } from '@/features/system-detail/simulation-preview/bodyIdUtils';
import type { TopologyPlanSnapshot, TopologySelection, TopologySelectionContext } from './ColonyTopologyRail';
import type { BodyPlannerLane } from './BodySlotPlanner';
import { PlanningEconomyStrip } from './PlanningEconomyStrip';
import {
  buildBodyDataSlotEstimateMap,
  resolveSlotCapacity,
  systemBodyData,
} from './slotCapacityFallback';
import {
  buildPlanningEconomyLedger,
  normalisePlanningEconomy,
  PLANNING_ECONOMY_NOTE,
  type PlanningEconomyLedger,
  type PlanningEconomyName,
} from './planningEconomy';
import { economyColor, economySoftColor } from './economyVisuals';
import { calculateStationBaselineEconomy, describeStationBaselineEconomy } from './stationBaselineEconomy';
import {
  existingStructureDisplayType,
  resolveExistingInfrastructure,
  type ExistingStructure,
} from './existingInfrastructure';
import {
  contextualEconomyLabel,
  contextualRoleLabel,
  laneDisabledReason,
  missingPrerequisitesForPlacement,
  placementLaneForTemplate,
  prerequisiteSummaryLabel,
  templateDisplayName,
  type PrerequisiteIssue,
} from './structurePlanningRules';

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
}

interface BgsTelemetryStat {
  id: string;
  label: string;
  field: string;
  value: number;
}

const BGS_TELEMETRY_FIELDS: Array<Omit<BgsTelemetryStat, 'value'>> = [
  { id: 'population', label: 'Population', field: 'population' },
  { id: 'max-population', label: 'Max population', field: 'max_population' },
  { id: 'security', label: 'Security', field: 'security' },
  { id: 'tech-level', label: 'Tech level', field: 'tech_level' },
  { id: 'wealth', label: 'Wealth', field: 'wealth' },
  { id: 'standard-of-living', label: 'Standard of living', field: 'standard_of_living' },
  { id: 'development-level', label: 'Development level', field: 'development_level' },
];

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
}

interface BodyNode {
  body: SystemBody;
  id: string;
  children: BodyNode[];
}

interface FlatBodyNode {
  body: SystemBody;
  id: string;
  depth: number;
  guide: boolean[];
  isLast: boolean;
}

interface StructureBucketItem {
  kind: 'placement';
  placement: SimulateBuildPlacement;
  template?: FacilityTemplate;
  index: number;
  projected: boolean;
  warningLabels: string[];
}

interface ExistingStructureBucketItem {
  kind: 'existing';
  structure: ExistingStructure;
  index: number;
  projected: false;
  warningLabels: string[];
}

type RavenStructureBucketItem = StructureBucketItem | ExistingStructureBucketItem;

const BODY_MARKER_COLORS: Record<string, { fill: string; ring: string; size: string }> = {
  star: { fill: 'radial-gradient(circle at 35% 30%, #ffd18c, #ff9f1a 55%, #9a4d00)', ring: 'rgba(255, 122, 20, 0.58)', size: 'h-8 w-8' },
  gas: { fill: 'radial-gradient(circle at 35% 30%, #ff8fb8, #d9467d 55%, #6d1539)', ring: 'rgba(248, 113, 113, 0.5)', size: 'h-7 w-7' },
  earth: { fill: 'radial-gradient(circle at 35% 30%, #98f5c5, #38bdf8 45%, #0f766e 78%)', ring: 'rgba(74, 222, 128, 0.5)', size: 'h-5 w-5' },
  rock: { fill: 'radial-gradient(circle at 35% 30%, #9ca3af, #525861 60%, #22262b)', ring: 'rgba(200, 204, 209, 0.45)', size: 'h-5 w-5' },
  moon: { fill: 'radial-gradient(circle at 35% 30%, #d1d5db, #7c8189 60%, #31363d)', ring: 'rgba(200, 204, 209, 0.38)', size: 'h-4 w-4' },
};

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
  const gridStyle: CSSProperties = {
    gridTemplateColumns: '280px minmax(300px,1fr) minmax(320px,1.05fr)',
  };

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

      <div className="overflow-x-auto">
        <div className="min-w-[860px]">
          <div
            className="grid border-b border-orange/20 bg-bg2/70 px-3 py-2 font-mono text-[11px] font-bold uppercase tracking-[0.14em] text-silver-dk"
            style={gridStyle}
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
                gridStyle={gridStyle}
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

      <RatingProfileCard system={system} />

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
  gridStyle,
  onSelect,
  onRequestAddStructure,
  prerequisiteIssues,
}: {
  row: RavenPlannerRow;
  selected: boolean;
  selectedPlacementIndex: number | null;
  selectedProjectedPlacementIndex: number | null;
  gridStyle: CSSProperties;
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
          'grid min-h-[62px] items-stretch px-3 py-2 transition-colors',
          rowTone,
        ].join(' ')}
        style={gridStyle}
      >
        <TreeCell row={row} selected={selected} onSelect={() => onSelect({ type: 'body', bodyId: row.id })} />
        <RavenSlotLane
          bodyId={row.id}
          bodyName={row.displayName}
          lane="orbital"
          capacity={row.orbitalCapacity}
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
          className="grid border-t border-gold/20 bg-gold/5 px-3 py-2"
          style={gridStyle}
        >
          <div />
          <div className="col-span-2 flex min-w-0 flex-wrap items-center gap-2">
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
              title={`${structure.name} | ${existingStructureDisplayType(structure)} | ${structure.unresolved_reason ?? structure.body_match_reason}`}
              className="max-w-[14rem] truncate rounded border border-gold/30 bg-bg3/45 px-2 py-1 font-mono text-[10px] text-silver"
            >
              {structure.name} / {existingStructureDisplayType(structure)}
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
    <div data-testid={`${bodyId}-${lane}-lane`} data-disabled={disabledReason ? 'true' : 'false'} className="flex min-w-0 items-center gap-2 pr-2">
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
  const inferredExisting = slot.kind === 'existing' && slot.warningLabels.includes('Inferred association');
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

function RatingProfileCard({ system }: { system: SystemDetail }) {
  const score = numericValue(system.score);
  const tier = ratingTier(score);
  const confidence = formatConfidence(system.confidence);
  const rationale = displayRationale(system.rationale);
  const axes = ratingAxes(system);
  const hasAnyAxis = axes.some((axis) => axis.value != null);
  const supplemental = [
    { label: 'Terraforming', value: numericValue(system.terraforming_potential) },
    { label: 'Diversity', value: numericValue(system.body_diversity) },
  ].filter((item): item is { label: string; value: number } => item.value != null);

  return (
    <section
      data-testid="raven-rating-profile-card"
      className="mt-4 rounded border border-orange/30 bg-orange/5 p-2"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-mono text-[11px] uppercase tracking-[0.14em] text-orange">Rating signals</h3>
          <div className="mt-1 text-[10px] leading-relaxed text-silver">
            Saved scoring signals. Validate a build plan before treating capped economy scores as exact.
          </div>
        </div>
        <div
          data-testid="raven-rating-overall-score"
          className="shrink-0 rounded border px-2 py-1 text-right font-mono"
          style={{
            borderColor: `${tier.fillColor}88`,
            background: `linear-gradient(180deg, ${tier.fillColor}24, rgba(18,20,24,0.52))`,
            color: tier.fillColor,
          }}
          title={`Stored rating score: ${score ?? 'n/a'}/100`}
        >
          <div className="text-[9px] uppercase tracking-[0.12em]">{tier.label}</div>
          <div className="text-lg font-bold leading-none">{score ?? '-'}</div>
        </div>
      </div>

      <div className="mt-2 grid grid-cols-2 gap-1.5 font-mono text-[10px]">
        <RatingFact label="Suggested" value={system.economy_suggestion ?? 'Unknown'} tone="orange" />
        <RatingFact
          label="Confidence"
          value={confidence ? `${confidence.symbol} ${confidence.tier} ${confidence.pct}%` : 'Unknown'}
          tone={confidence?.tier === 'High' ? 'green' : confidence?.tier === 'Medium' ? 'gold' : undefined}
        />
      </div>

      {hasAnyAxis ? (
        <div className="mt-3 space-y-1.5" data-testid="raven-rating-economy-breakdown">
          {axes.map((axis) => (
            <RatingAxisBar key={axis.label} label={axis.label} value={axis.value} highlighted={axis.highlighted} />
          ))}
        </div>
      ) : (
        <p className="mt-3 rounded border border-gold/35 bg-gold/10 px-2 py-1 font-mono text-[10px] text-gold">
          No per-economy rating scores are present on this system record.
        </p>
      )}

      {supplemental.length > 0 && (
        <div className="mt-2 grid grid-cols-2 gap-1.5 font-mono text-[10px]">
          {supplemental.map((item) => (
            <RatingFact key={item.label} label={item.label} value={String(item.value)} />
          ))}
        </div>
      )}

      {rationale && (
        <p data-testid="raven-rating-rationale" className="mt-2 rounded border border-border/55 bg-bg3/35 px-2 py-1.5 text-[10px] italic leading-relaxed text-silver">
          {rationale}
        </p>
      )}
    </section>
  );
}

function ratingAxes(system: SystemDetail) {
  return [
    { label: 'Agriculture', value: numericValue(system.score_agriculture) },
    { label: 'Refinery', value: numericValue(system.score_refinery) },
    { label: 'Industrial', value: numericValue(system.score_industrial) },
    { label: 'HighTech', value: numericValue(system.score_hightech) },
    { label: 'Military', value: numericValue(system.score_military) },
    { label: 'Tourism', value: numericValue(system.score_tourism) },
    { label: 'Extraction', value: numericValue(system.score_extraction) },
  ].map((axis) => ({
    ...axis,
    highlighted: system.economy_suggestion === axis.label,
  }));
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

function RatingAxisBar({
  label,
  value,
  highlighted,
}: {
  label: string;
  value: number | null;
  highlighted: boolean;
}) {
  const pct = Math.max(0, Math.min(100, value ?? 0));
  const color = highlighted ? '#ffb074' : '#c8ccd1';
  return (
    <div
      data-testid={`raven-rating-axis-${label.toLowerCase()}`}
      className="grid grid-cols-[5.9rem_1fr_2.4rem] items-center gap-2 font-mono text-[10px]"
    >
      <span className={highlighted ? 'truncate font-bold text-orange-lt' : 'truncate text-silver'}>{label}</span>
      <span className="relative h-2 overflow-hidden rounded-full border border-border/60 bg-bg4/80 shadow-inner-soft">
        <span
          aria-hidden
          className="absolute inset-y-0 left-0 rounded-full"
          style={{
            width: `${pct}%`,
            background: highlighted
              ? 'linear-gradient(90deg, #ff7a14, #ffb074)'
              : 'linear-gradient(90deg, #8a8f96, #c8ccd1)',
            boxShadow: highlighted ? '0 0 8px rgba(255,122,20,0.55)' : undefined,
          }}
        />
      </span>
      <span className={highlighted ? 'text-right font-bold text-orange-lt' : 'text-right text-silver'} style={{ color }}>
        {value ?? '-'}
      </span>
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

export function buildRavenPlannerRows(system: SystemDetail, snapshot: TopologyPlanSnapshot): RavenPlannerRow[] {
  const bodies = systemBodyData(system);
  const existingResolution = resolveExistingInfrastructure(system);
  const bodyDataSlotEstimates = buildBodyDataSlotEstimateMap(system, snapshot.slotPredictions?.predictions);
  const predictionsByBodyId = new Map(
    (snapshot.slotPredictions?.predictions ?? []).map((prediction) => [bodyIdKey(prediction.body_id), prediction]),
  );
  const templatesById = new Map(snapshot.templates.map((template) => [template.id, template]));
  const bodyById = new Map(
    bodies
      .filter((body) => body.id != null)
      .map((body) => [bodyIdKey(body.id), body]),
  );
  const plannedByBody = bucketStructures(snapshot.placements, templatesById, bodyById, false, snapshot.placementLaneHints);
  const projectedByBody = bucketStructures(snapshot.projection?.placements ?? [], templatesById, bodyById, true, snapshot.projection?.placementLaneHints);
  const projectedBodyIds = new Set(Array.from(projectedByBody.keys()));

  return flattenBodyNodes(bodies, system.name).map((node) => {
    const prediction = predictionsByBodyId.get(node.id) ?? null;
    const bodyDataSlotEstimate = bodyDataSlotEstimates.get(node.id) ?? null;
    const planned = plannedByBody.get(node.id) ?? emptyStructureBuckets();
    const projected = projectedByBody.get(node.id) ?? emptyStructureBuckets();
    const existing = existingResolution.byBodyId.get(node.id) ?? emptyExistingStructureBuckets();
    const existingOrbital = existing.orbital.map((structure, index): ExistingStructureBucketItem => ({
      kind: 'existing',
      structure,
      index,
      projected: false,
      warningLabels: [],
    }));
    const existingGround = existing.surface.map((structure, index): ExistingStructureBucketItem => ({
      kind: 'existing',
      structure,
      index,
      projected: false,
      warningLabels: [],
    }));
    const orbitalStructures = [...existingOrbital, ...planned.orbital, ...projected.orbital];
    const groundStructures = [...existingGround, ...planned.ground, ...projected.ground];
    const unassignedStructures = [...planned.unassigned, ...projected.unassigned];
    const orbitalSlotCapacity = resolveSlotCapacity(node.body, prediction, 'orbital', bodyDataSlotEstimate);
    const groundSlotCapacity = resolveSlotCapacity(node.body, prediction, 'surface', bodyDataSlotEstimate);
    const orbitalCapacity = orbitalSlotCapacity.value;
    const groundCapacity = groundSlotCapacity.value;
    const bodyLedger = buildPlanningEconomyLedger({
      placements: [...planned.orbital, ...planned.ground, ...planned.unassigned].map((item) => item.placement),
      projectedPlacements: [...projected.orbital, ...projected.ground, ...projected.unassigned].map((item) => item.placement),
      templates: snapshot.templates,
    });

    return {
      id: node.id,
      body: node.body,
      depth: node.depth,
      guide: node.guide,
      isLast: node.isLast,
      displayName: bodyDisplayName(node.body),
      compactName: compactBodyDisplayName(node.body, system.name),
      bodyKind: bodyKind(node.body),
      bodyTags: bodyTags(node.body),
      orbitalCapacity,
      groundCapacity,
      orbitalCapacityEstimated: orbitalSlotCapacity.estimated,
      groundCapacityEstimated: groundSlotCapacity.estimated,
      ...(() => {
        const orbitalSlots = buildLaneSlots(node.id, 'orbital', orbitalCapacity, orbitalStructures, node.body, system);
        const groundSlots = buildLaneSlots(node.id, 'ground', groundCapacity, groundStructures, node.body, system);
        const unassignedSlots = unassignedStructures.map((item, index) => structureSlot(node.id, 'unassigned', item, index, node.body, system));
        const overflowCount = [...orbitalSlots, ...groundSlots].filter((slot) => slot.kind === 'overflow').length;
        const placementWarningCount = [...planned.orbital, ...planned.ground, ...planned.unassigned]
          .filter((item) => item.warningLabels.length > 0).length;
        const existingCount = existing.orbital.length + existing.surface.length;
        const inferredExistingCount = [...existing.orbital, ...existing.surface]
          .filter((structure) => structure.association_status === 'inferred').length;
        const plannedCount = planned.orbital.length + planned.ground.length + planned.unassigned.length;
        const projectedCount = projected.orbital.length + projected.ground.length + projected.unassigned.length;
        const emptySlotCount = [...orbitalSlots, ...groundSlots].filter((slot) => slot.kind === 'empty').length;
        return {
          orbitalSlots,
          groundSlots,
          unassignedSlots,
          bodyEconomy: bodyLedger,
          projected: projectedBodyIds.has(node.id),
          existingCount,
          inferredExistingCount,
          plannedCount,
          projectedCount,
          emptySlotCount,
          orbitalAddDisabledReason: addDisabledReasonForLane(node.body, 'orbital', orbitalCapacity, existing.orbital.length, planned.orbital.length),
          groundAddDisabledReason: addDisabledReasonForLane(node.body, 'surface', groundCapacity, existing.surface.length, planned.ground.length),
          warningCount: countRowWarnings(node.body, prediction, bodyLedger, overflowCount) + placementWarningCount,
        };
      })(),
    };
  });
}

export interface RavenPlannerOccupancySummary {
  existingCount: number;
  inferredExistingCount: number;
  plannedCount: number;
  projectedCount: number;
  emptySlotCount: number;
  unresolvedExistingCount: number;
}

export interface RavenLaneCapacityState {
  capacity: number | null;
  existingCount: number;
  plannedCount: number;
  projectedCount: number;
  remaining: number | null;
  disabledReason: string | null;
}

export function buildRavenPlannerOccupancySummary(system: SystemDetail, snapshot: TopologyPlanSnapshot): RavenPlannerOccupancySummary {
  const rows = buildRavenPlannerRows(system, snapshot);
  const unresolvedExistingCount = resolveExistingInfrastructure(system).unresolved.length;
  return summarizeRavenPlannerRows(rows, unresolvedExistingCount);
}

export function getRavenLaneCapacityState(
  system: SystemDetail,
  snapshot: TopologyPlanSnapshot,
  bodyId: string,
  lane: BodyPlannerLane,
): RavenLaneCapacityState {
  const bodies = systemBodyData(system);
  const body = bodies.find((candidate) => sameBodyId(candidate.id, bodyId));
  if (!body) {
    return {
      capacity: null,
      existingCount: 0,
      plannedCount: 0,
      projectedCount: 0,
      remaining: null,
      disabledReason: 'Selected body is no longer available.',
    };
  }

  const bodyKey = bodyIdKey(body.id);
  const bodyDataSlotEstimates = buildBodyDataSlotEstimateMap(system, snapshot.slotPredictions?.predictions);
  const prediction = (snapshot.slotPredictions?.predictions ?? []).find((candidate) => sameBodyId(candidate.body_id, body.id)) ?? null;
  const capacity = resolveSlotCapacity(
    body,
    prediction,
    lane,
    bodyDataSlotEstimates.get(bodyKey) ?? null,
  ).value;
  const bodyById = new Map(bodies.filter((candidate) => candidate.id != null).map((candidate) => [bodyIdKey(candidate.id), candidate]));
  const templatesById = new Map(snapshot.templates.map((template) => [template.id, template]));
  const existingBuckets = resolveExistingInfrastructure(system).byBodyId.get(bodyKey) ?? emptyExistingStructureBuckets();
  const existingCount = lane === 'orbital' ? existingBuckets.orbital.length : existingBuckets.surface.length;
  const plannedCount = countPlacementsInLane(snapshot.placements, templatesById, bodyById, bodyKey, lane, snapshot.placementLaneHints);
  const projectedCount = countPlacementsInLane(snapshot.projection?.placements ?? [], templatesById, bodyById, bodyKey, lane, snapshot.projection?.placementLaneHints);
  const remaining = capacity == null ? null : Math.max(0, capacity - existingCount - plannedCount);

  return {
    capacity,
    existingCount,
    plannedCount,
    projectedCount,
    remaining,
    disabledReason: addDisabledReasonForLane(body, lane, capacity, existingCount, plannedCount),
  };
}

function summarizeRavenPlannerRows(rows: RavenPlannerRow[], unresolvedExistingCount: number): RavenPlannerOccupancySummary {
  return rows.reduce<RavenPlannerOccupancySummary>((summary, row) => ({
    existingCount: summary.existingCount + row.existingCount,
    inferredExistingCount: summary.inferredExistingCount + row.inferredExistingCount,
    plannedCount: summary.plannedCount + row.plannedCount,
    projectedCount: summary.projectedCount + row.projectedCount,
    emptySlotCount: summary.emptySlotCount + row.emptySlotCount,
    unresolvedExistingCount,
  }), {
    existingCount: 0,
    inferredExistingCount: 0,
    plannedCount: 0,
    projectedCount: 0,
    emptySlotCount: 0,
    unresolvedExistingCount,
  });
}

function countPlacementsInLane(
  placements: SimulateBuildPlacement[],
  templatesById: Map<string, FacilityTemplate>,
  bodyById: Map<string, SystemBody>,
  targetBodyId: string,
  lane: BodyPlannerLane,
  laneHints: Record<number, BodyPlannerLane> = {},
): number {
  return placements.reduce((count, placement, index) => {
    const bodyId = placementBodyId(placement);
    if (!bodyId || bodyId !== targetBodyId) return count;
    const template = templatesById.get(placement.facility_template_id);
    const assignedLane = placementLaneForTemplate(template, bodyById.get(bodyId), laneHints[index]);
    return assignedLane === lane ? count + 1 : count;
  }, 0);
}

function addDisabledReasonForLane(
  body: SystemBody,
  lane: BodyPlannerLane,
  capacity: number | null,
  existingCount: number,
  plannedCount: number,
): string | null {
  const physicalReason = laneDisabledReason(body, lane);
  if (physicalReason) return physicalReason;
  if (capacity == null) return null;
  if (capacity <= 0 || existingCount + plannedCount >= capacity) {
    return lane === 'orbital' ? 'No empty orbital slots' : 'All surface slots occupied';
  }
  return null;
}

export function buildPlannerTelemetryStats(snapshot: TopologyPlanSnapshot): BgsTelemetryStat[] {
  const templatesById = new Map(snapshot.templates.map((template) => [template.id, template]));
  return BGS_TELEMETRY_FIELDS.map((stat) => ({
    ...stat,
    value: snapshot.placements.reduce((sum, placement) => (
      sum + readTemplateStat(templatesById.get(placement.facility_template_id), stat.field)
    ), 0),
  }));
}

function readTemplateStat(template: FacilityTemplate | undefined, field: string): number {
  if (!template) return 0;
  const direct = numericValue((template as unknown as Record<string, unknown>)[field]);
  if (direct != null) return direct;
  const effects = template.stat_effects ?? (template as unknown as { statEffects?: Record<string, unknown> }).statEffects;
  return numericValue(effects?.[field]) ?? 0;
}

function numericValue(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}


export function buildProjectionComparison(
  system: SystemDetail,
  snapshot: TopologyPlanSnapshot,
  economyLedger: PlanningEconomyLedger,
  rows = buildRavenPlannerRows(system, snapshot),
): ProjectionComparisonSummary {
  const bodies = systemBodyData(system);
  const bodyById = new Map(
    bodies
      .filter((body) => body.id != null)
      .map((body) => [bodyIdKey(body.id), body]),
  );
  const templatesById = new Map(snapshot.templates.map((template) => [template.id, template]));
  const plannedBodyIds = uniquePlacementBodyIds(snapshot.placements, bodies);
  const projectedBodyIds = uniquePlacementBodyIds(snapshot.projection?.placements ?? [], bodies);
  const sharedBodyIds = projectedBodyIds.filter((id) => plannedBodyIds.includes(id));
  const newBodyIds = projectedBodyIds.filter((id) => !plannedBodyIds.includes(id));
  const plannedOnlyBodyIds = plannedBodyIds.filter((id) => !projectedBodyIds.includes(id));
  const laneCounts = (snapshot.projection?.placements ?? []).reduce((counts, placement) => {
    const bodyId = placementBodyId(placement);
    const template = templatesById.get(placement.facility_template_id);
    const lane = ravenLaneForPlacement(
      template,
      bodyId ? bodyById.get(bodyId) : undefined,
      snapshot.projection?.placementLaneHints?.[counts.index],
    );
    if (lane === 'orbital') counts.orbital += 1;
    else if (lane === 'ground') counts.ground += 1;
    else counts.unknown += 1;
    counts.index += 1;
    return counts;
  }, { orbital: 0, ground: 0, unknown: 0, index: 0 });
  const slotOverflowCount = rows.reduce((sum, row) => (
    sum
      + row.orbitalSlots.filter((slot) => slot.kind === 'overflow').length
      + row.groundSlots.filter((slot) => slot.kind === 'overflow').length
  ), 0);

  return {
    label: snapshot.projection?.label ?? 'No candidate selected',
    hasProjection: Boolean(snapshot.projection),
    plannedPlacements: snapshot.placements.length,
    projectedPlacements: snapshot.projection?.placements.length ?? 0,
    plannedBodyCount: plannedBodyIds.length,
    projectedBodyCount: projectedBodyIds.length,
    sharedBodyCount: sharedBodyIds.length,
    newBodyLabels: bodyLabelsForIds(newBodyIds, bodyById, system.name),
    plannedOnlyBodyLabels: bodyLabelsForIds(plannedOnlyBodyIds, bodyById, system.name),
    projectedOrbitalCount: laneCounts.orbital,
    projectedGroundCount: laneCounts.ground,
    projectedUnknownLaneCount: laneCounts.unknown,
    slotOverflowCount,
    economyDeltas: economyLedger.entries.map((entry) => ({
      economy: entry.economy,
      planned: entry.planned,
      projected: entry.projected,
      total: entry.total,
    })),
  };
}

function uniquePlacementBodyIds(placements: SimulateBuildPlacement[], bodies: SystemBody[]): string[] {
  const ids: string[] = [];
  placements.forEach((placement) => {
    const rawBodyId = placementBodyId(placement);
    if (!rawBodyId) return;
    const body = bodies.find((candidate) => sameBodyId(candidate.id, rawBodyId));
    const id = body?.id != null ? bodyIdKey(body.id) : rawBodyId;
    if (!ids.includes(id)) ids.push(id);
  });
  return ids;
}

function bodyLabelsForIds(ids: string[], bodyById: Map<string, SystemBody>, systemName?: string | null): string[] {
  return ids
    .map((id) => {
      const body = bodyById.get(id);
      return body ? compactBodyDisplayName(body, systemName) : 'Unknown body';
    })
    .slice(0, 4);
}

function bucketStructures(
  placements: SimulateBuildPlacement[],
  templatesById: Map<string, FacilityTemplate>,
  bodyById: Map<string, SystemBody>,
  projected: boolean,
  laneHints: Record<number, BodyPlannerLane> = {},
) {
  const buckets = new Map<string, ReturnType<typeof emptyStructureBuckets>>();

  placements.forEach((placement, index) => {
    const bodyId = placementBodyId(placement);
    if (!bodyId || !bodyById.has(bodyId)) return;
    const template = templatesById.get(placement.facility_template_id);
    const lane = ravenLaneForPlacement(template, bodyById.get(bodyId), laneHints[index]);
    const current = buckets.get(bodyId) ?? emptyStructureBuckets();
    current[lane].push({
      kind: 'placement',
      placement,
      template,
      index,
      projected,
      warningLabels: projected ? [] : missingPrerequisitesForPlacement(placement, placements, Array.from(templatesById.values())),
    });
    buckets.set(bodyId, current);
  });

  return buckets;
}

function emptyStructureBuckets() {
  return {
    orbital: [] as StructureBucketItem[],
    ground: [] as StructureBucketItem[],
    unassigned: [] as StructureBucketItem[],
  };
}

function emptyExistingStructureBuckets() {
  return {
    orbital: [] as ExistingStructure[],
    surface: [] as ExistingStructure[],
    unknown: [] as ExistingStructure[],
  };
}

function buildLaneSlots(
  bodyId: string,
  lane: RavenLane,
  capacity: number | null,
  structures: RavenStructureBucketItem[],
  body: SystemBody,
  system: SystemDetail,
): RavenStructureSlot[] {
  if (capacity == null) {
    return [
      unknownSlot(bodyId, lane),
      ...structures.map((item, index) => structureSlot(bodyId, lane, item, index, body, system)),
    ];
  }

  if (capacity <= 0) {
    if (structures.length === 0) return [];
    return [
      ...structures.map((item, index) => structureSlot(bodyId, lane, item, index, body, system)),
      overflowSlot(bodyId, lane, structures.length),
    ];
  }

  const visible = structures.slice(0, capacity).map((item, index) => structureSlot(bodyId, lane, item, index, body, system));
  const empty = Array.from({ length: Math.max(0, capacity - visible.length) }, (_unused, index) => (
    emptySlot(bodyId, lane, visible.length + index)
  ));
  const overflow = structures.length > capacity ? [overflowSlot(bodyId, lane, structures.length - capacity)] : [];
  return [...visible, ...empty, ...overflow];
}

function structureSlot(
  bodyId: string,
  lane: RavenLane,
  item: RavenStructureBucketItem,
  index: number,
  body: SystemBody,
  system: SystemDetail,
): RavenStructureSlot {
  if (item.kind === 'existing') {
    return existingStructureSlot(bodyId, lane, item, index, body, system);
  }
  const fullName = structureDisplayName(item.template, item.placement.facility_template_id);
  const directSegments = structureEconomySegments(item.template, item.projected);
  const baselineSegments = directSegments.length === 0 && item.template?.is_port
    ? stationBaselineSegments(item.template, body, system, item.projected)
    : [];
  const segments = directSegments.length > 0 ? directSegments : baselineSegments;
  const status = item.projected ? 'projected' : 'planned';
  const economyContext = contextualEconomyLabel(item.template);
  const prerequisiteWarnings = item.warningLabels;
  const directEconomyText = directSegments.map((segment) => {
    const strength = segment.strength == null ? 'CP generated unavailable' : `CP generated +${segment.strength}`;
    return `Direct facility economy: ${segment.economy} ${formatShare(segment.share)} | ${strength} | Source: catalogue/template`;
  }).join(' / ');
  const baselineEconomyText = baselineSegments.length > 0
    ? `Baseline (inherited/contextual): ${baselineSegments.map((segment) => `${segment.economy} ${formatShare(segment.share)}`).join(' / ')} | Source: ${baselineSegments[0]?.calculationSource ?? 'ED-Finder body economy profile'} | Run Preview for validated outcome.`
    : '';
  const economyText = directSegments.length > 0
    ? directEconomyText
    : baselineEconomyText
      ? economyContext
        ? `${economyContext} | ${baselineEconomyText}`
        : baselineEconomyText
      : economyContext ?? 'No economy metadata';

  return {
    id: `${bodyId}-${lane}-${status}-${item.index}-${item.placement.facility_template_id}-${index}`,
    kind: item.projected ? 'projected' : 'planned',
    label: `${item.projected ? 'Ghost ' : ''}${compactStructureName(fullName)}`,
    fullName,
    title: [
      `${fullName} | Status: ${item.projected ? 'Projected Suggested Build' : 'Planned Build Plan'} | ${economyText}`,
      prerequisiteWarnings.length > 0 ? `Missing prerequisite: ${prerequisiteWarnings.join('; ')}` : null,
    ].filter(Boolean).join(' | '),
    economySegments: segments,
    placementIndex: item.projected ? null : item.index,
    projectionIndex: item.projected ? item.index : null,
    existingStructureId: null,
    buildOrder: item.placement.build_order ?? null,
    status,
    economyContextLabel: economyContext,
    warningLabels: prerequisiteWarnings,
  };
}

function existingStructureSlot(
  bodyId: string,
  lane: RavenLane,
  item: ExistingStructureBucketItem,
  index: number,
  body: SystemBody,
  system: SystemDetail,
): RavenStructureSlot {
  const structure = item.structure;
  const directSegments = existingStructureEconomySegments(structure);
  const baselineSegments = directSegments.length === 0
    ? stationBaselineSegments(undefined, body, system, false)
    : [];
  const segments = directSegments.length > 0 ? directSegments : baselineSegments;
  const type = existingStructureDisplayType(structure);
  const bodyMatch = structure.association_status === 'inferred'
    ? `Body match inferred (${structure.association_source})`
    : structure.association_status === 'confirmed'
      ? `Body match confirmed (${structure.association_source})`
      : `Body match unresolved (${structure.association_source})`;
  const economyText = directSegments.length > 0
    ? `Existing direct economy: ${directSegments.map((segment) => segment.economy).join(' / ')} | Source: station economy metadata`
    : baselineSegments.length > 0
      ? `Baseline (inherited/contextual): ${baselineSegments.map((segment) => `${segment.economy} ${formatShare(segment.share)}`).join(' / ')} | Source: ${baselineSegments[0]?.calculationSource ?? 'ED-Finder body economy profile'} | Run Preview for validated outcome.`
      : 'No economy metadata';

  return {
    id: `${bodyId}-${lane}-existing-${structure.id}-${index}`,
    kind: 'existing',
    label: compactStructureName(structure.name),
    fullName: structure.name,
    title: [
      `${structure.name} | Existing ${type} | ${economyText}`,
      structure.pad_size ? `Pad ${structure.pad_size}` : null,
      bodyMatch,
      structure.body_match_reason,
    ].filter(Boolean).join(' | '),
    economySegments: segments,
    placementIndex: null,
    projectionIndex: null,
    existingStructureId: structure.id,
    buildOrder: null,
    status: 'existing',
    economyContextLabel: baselineSegments.length > 0 ? 'Economy: inherited/contextual baseline - run Preview for validated outcome.' : null,
    warningLabels: structure.association_status === 'inferred' ? ['Inferred association'] : [],
  };
}

function unknownSlot(bodyId: string, lane: RavenLane): RavenStructureSlot {
  return {
    id: `${bodyId}-${lane}-unknown`,
    kind: 'unknown',
    label: '?',
    fullName: 'Slot prediction unavailable',
    title: 'Slot prediction unavailable for this body and lane.',
    economySegments: [],
    placementIndex: null,
    projectionIndex: null,
    existingStructureId: null,
    buildOrder: null,
    status: 'unknown',
    economyContextLabel: null,
    warningLabels: [],
  };
}

function emptySlot(bodyId: string, lane: RavenLane, index: number, label = ''): RavenStructureSlot {
  return {
    id: `${bodyId}-${lane}-empty-${index}`,
    kind: 'empty',
    label,
    fullName: 'Empty slot',
    title: 'Empty slot',
    economySegments: [],
    placementIndex: null,
    projectionIndex: null,
    existingStructureId: null,
    buildOrder: null,
    status: 'unknown',
    economyContextLabel: null,
    warningLabels: [],
  };
}

function overflowSlot(bodyId: string, lane: RavenLane, count: number): RavenStructureSlot {
  const laneLabel = lane === 'ground' ? 'Surface' : 'Orbital';
  return {
    id: `${bodyId}-${lane}-overflow-${count}`,
    kind: 'overflow',
    label: `+${count} over`,
    fullName: `${laneLabel} capacity exceeded: +${count} over predicted slots`,
    title: `${laneLabel} capacity exceeded: ${count} more occupied structure${count === 1 ? '' : 's'} than predicted slots. Verify in Architect Mode.`,
    economySegments: [],
    placementIndex: null,
    projectionIndex: null,
    existingStructureId: null,
    buildOrder: null,
    status: 'unknown',
    economyContextLabel: null,
    warningLabels: [`${laneLabel} capacity exceeded`],
  };
}

function stationBaselineSegments(
  _template: FacilityTemplate | undefined,
  body: SystemBody | null | undefined,
  system: SystemDetail | null | undefined,
  projected: boolean,
): RavenEconomySegment[] {
  void system;
  const baseline = calculateStationBaselineEconomy(body ?? null);
  if (baseline.segments.length === 0) return [];
  const description = describeStationBaselineEconomy(baseline, { projected });
  return baseline.segments.map((segment) => ({
    economy: segment.economy,
    share: segment.percent,
    strength: null,
    projected,
    inherited: true,
    calculationSource: baseline.calculationSource,
    caveats: description ? [description, ...baseline.caveats] : baseline.caveats,
  }));
}

function structureEconomySegments(template: FacilityTemplate | undefined, projected: boolean): RavenEconomySegment[] {
  const economy = normalisePlanningEconomy(template?.economy);
  if (!economy) return [];
  const yellow = typeof template?.yellow_cp_generated === 'number' ? template.yellow_cp_generated : 0;
  const green = typeof template?.green_cp_generated === 'number' ? template.green_cp_generated : 0;
  const strength = template ? Math.max(0, yellow + green) : null;
  return [{
    economy,
    share: 100,
    strength,
    projected,
    calculationSource: 'catalogue/template economy metadata',
  }];
}

function existingStructureEconomySegments(structure: ExistingStructure): RavenEconomySegment[] {
  const economy = normalisePlanningEconomy(structure.economy);
  if (!economy) return [];
  return [{
    economy,
    share: 100,
    strength: null,
    projected: false,
    calculationSource: 'station economy metadata',
  }];
}

function structureDisplayName(template: FacilityTemplate | undefined, fallback: string): string {
  return template ? templateDisplayName(template) : readableTemplateId(fallback);
}

function compactStructureName(name: string): string {
  const clean = name.trim();
  if (!clean) return 'Structure';
  const words = clean.split(/\s+/);
  if (words.length === 1) return clean;
  if (words.length === 2 && [
    'Starport',
    'Outpost',
    'Installation',
    'Dome',
    'Relay',
    'Port',
  ].includes(words[1])) return words[0];
  if (words.length === 2) return clean;
  const facilityIndex = words.findIndex((word) => [
    'Starport',
    'Hub',
    'Outpost',
    'Lab',
    'Installation',
    'Dome',
    'Relay',
    'Port',
  ].includes(word));
  if (facilityIndex > 0) return `${words[facilityIndex - 1]} ${words[facilityIndex]}`;
  return words.slice(0, 2).join(' ');
}

function readableTemplateId(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function ravenLaneForPlacement(
  template: FacilityTemplate | undefined,
  body: SystemBody | undefined,
  laneHint?: BodyPlannerLane | null,
): RavenLane {
  const lane = placementLaneForTemplate(template, body, laneHint);
  if (lane === 'surface') return 'ground';
  return lane;
}

function placementBodyId(placement: SimulateBuildPlacement | undefined): string | null {
  return placement?.local_body_id != null ? bodyIdKey(placement.local_body_id) : null;
}

function flattenBodyNodes(bodies: SystemBody[], systemName?: string | null): FlatBodyNode[] {
  const nodes = buildBodyTree(bodies, systemName);
  const flat: FlatBodyNode[] = [];
  const visit = (node: BodyNode, depth: number, guide: boolean[], isLast: boolean) => {
    flat.push({ body: node.body, id: node.id, depth, guide, isLast });
    node.children.forEach((child, index) => {
      visit(child, depth + 1, [...guide, !isLast], index === node.children.length - 1);
    });
  };
  nodes.forEach((node, index) => visit(node, 0, [], index === nodes.length - 1));
  return flat;
}

function buildBodyTree(bodies: SystemBody[], systemName?: string | null): BodyNode[] {
  const nodes = bodies
    .filter((body) => body.id != null)
    .map((body) => ({ body, id: bodyIdKey(body.id), children: [] as BodyNode[] }));
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const roots: BodyNode[] = [];

  nodes.forEach((node) => {
    const parentId = bodyParentId(node.body);
    const parent = parentId ? byId.get(parentId) : null;
    if (parent) parent.children.push(node);
    else roots.push(node);
  });

  const sort = (items: BodyNode[]) => {
    items.sort((left, right) => bodyRank(left.body) - bodyRank(right.body)
      || compareBodiesByHierarchy(left.body, right.body, systemName));
    items.forEach((item) => sort(item.children));
  };

  sort(roots);
  return roots;
}

function bodyParentId(body: SystemBody): string | null {
  const raw = body.parent_body_id
    ?? body.parentBodyId
    ?? body.parent_id
    ?? body.parentId
    ?? body.orbiting_body_id
    ?? body.orbitingBodyId
    ?? null;
  if (typeof raw === 'number' || typeof raw === 'string') return bodyIdKey(raw);
  return null;
}

function bodyRank(body: SystemBody) {
  if (body.body_type === 'Star') return 0;
  if (body.body_type === 'Planet') return bodyParentId(body) ? 2 : 1;
  return 3;
}

function bodyKind(body: SystemBody): string {
  const subtype = body.subtype?.replace(/\bworld\b/i, '').trim();
  const type = subtype || body.body_type || 'Body';
  const flags = [
    body.is_landable ? 'landable' : null,
    body.is_water_world ? 'water' : null,
    body.is_terraformable ? 'terraformable' : null,
  ].filter(Boolean);
  return flags.length > 0 ? `${type} / ${flags.join(' / ')}` : type;
}

function bodyMarker(body: SystemBody) {
  const text = `${body.body_type ?? ''} ${body.subtype ?? ''}`.toLowerCase();
  if (body.body_type === 'Star') return BODY_MARKER_COLORS.star;
  if (text.includes('gas')) return BODY_MARKER_COLORS.gas;
  if (body.is_water_world || body.is_terraformable) return BODY_MARKER_COLORS.earth;
  if (bodyParentId(body)) return BODY_MARKER_COLORS.moon;
  return BODY_MARKER_COLORS.rock;
}

function countRowWarnings(
  body: SystemBody,
  prediction: BodySlotPrediction | null,
  ledger: PlanningEconomyLedger,
  overflowCount = 0,
) {
  let count = 0;
  if (!prediction) count += 1;
  if (ledger.unknownCount > 0) count += ledger.unknownCount;
  if (bodyTags(body).includes('Unknown body data')) count += 1;
  if (overflowCount > 0) count += overflowCount;
  return count;
}
