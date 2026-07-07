import { Sparkles, Target } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { formatPopulationForSystem } from '@/lib/format';
import { archetypeTierFromScore, formatArchetypeLabel, getDevelopmentScore } from '@/lib/archetypes';
import type { SimulateBuildPlacement, SystemDetail } from '@/types/api';
import {
  compactBodyDisplayName,
} from '@/features/system-detail/simulation-preview/buildPlanLayoutUtils';
import { bodyIdKey, sameBodyId } from '@/features/system-detail/simulation-preview/bodyIdUtils';
import type { TopologyPlanSnapshot, TopologySelection, TopologySelectionContext } from './ColonyTopologyRail';
import { PlanningEconomyStrip } from './PlanningEconomyStrip';
import { systemBodyData } from './slotCapacityFallback';
import { PLANNING_ECONOMY_NOTE, type PlanningEconomyLedger } from './planningEconomy';
import { resolveExistingInfrastructure } from './existingInfrastructure';
import {
  contextualEconomyLabel,
  contextualRoleLabel,
  missingPrerequisitesForPlacement,
  prerequisiteSummaryLabel,
  type PrerequisiteIssue,
} from './structurePlanningRules';
import {
  buildPlannerTelemetryStats,
  buildPlannerCanvasRows,
  buildProjectionComparison,
  numericValue,
  placementBodyId,
  plannerCanvasLaneForPlacement,
  structureDisplayName,
  structureEconomySegments,
} from './plannerCanvasUtils';
import type {
  ProjectionComparisonSummary,
  ProjectionComparisonView,
  PlannerEconomySegment,
  PlannerCanvasLane,
  PlannerCanvasRow,
} from './plannerCanvasTypes';

export function PlannerTelemetryPanel({
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
  const rows = buildPlannerCanvasRows(system, snapshot);
  const projectionComparison = buildProjectionComparison(system, snapshot, economyLedger, rows);
  const selectedBodyId = selectedBodyIdForSelection(snapshot, selection);
  const selectedProjectedCount = selectedBodyId ? countBodyPlacements(snapshot.projection?.placements ?? [], selectedBodyId) : 0;
  const bodyDetail = buildSelectedBodyTelemetryDetail(rows, snapshot, selection);
  const structureDetail = buildSelectedStructureTelemetryDetail(system, snapshot, selection);
  const warningItems = buildTelemetryWarningItems(system, snapshot, economyLedger, selectedContext, prerequisiteIssues);
  const unresolvedExistingCount = resolveExistingInfrastructure(system).unresolved.length;

  return (
    <aside
      aria-label="Planner telemetry"
      data-testid="planner-telemetry-panel"
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
          <PlanningEconomyStrip ledger={economyLedger} testId="planner-telemetry-economy-ledger" />
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

      <div className="mt-4 border-t border-border/45 pt-3" data-testid="planner-telemetry-warning-summary">
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

function formatShare(value: number): string {
  return Number.isInteger(value) ? `${value}%` : `${value.toFixed(1)}%`;
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
    <section className="mt-4 border-t border-border/35 pt-3" data-testid="planner-projection-comparison">
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
  row: PlannerCanvasRow;
  plannedCount: number;
  projectedCount: number;
  capacityLabel: string;
  emptySlotCount: number;
}

interface StructureTelemetryDetail {
  name: string;
  templateId: string;
  status: 'planned' | 'projected';
  lane: PlannerCanvasLane;
  bodyName: string;
  category: string;
  buildOrder: number | null;
  economySegments: PlannerEconomySegment[];
  economyContextLabel: string | null;
  roleLabel: string | null;
  prerequisiteWarnings: string[];
  strength: number | null;
}

function SelectedBodyTelemetryCard({ detail }: { detail: BodyTelemetryDetail }) {
  return (
    <section className="mt-4 border-t border-cyan/25 pt-3" data-testid="planner-telemetry-body-context">
      <div className="font-mono text-[11px] uppercase tracking-[0.12em] text-cyan">Selected body summary</div>
      <div className="mt-2 grid grid-cols-2 gap-2">
        <TelemetryField label="Capacity" value={detail.capacityLabel} />
        <TelemetryField label="Slots" value={`${detail.row.existingCount} existing / ${detail.plannedCount} planned / ${detail.projectedCount} projected`} />
        <TelemetryField label="Kind" value={detail.row.bodyKind} />
        <TelemetryField label="Empty" value={String(detail.emptySlotCount)} tone={detail.emptySlotCount > 0 ? 'green' : 'silver'} />
      </div>
      <div className="mt-2">
        <PlanningEconomyStrip ledger={detail.row.bodyEconomy} compact testId="planner-telemetry-body-economy" />
      </div>
    </section>
  );
}

function SelectedStructureTelemetryCard({ detail }: { detail: StructureTelemetryDetail }) {
  return (
    <section
      className={detail.status === 'projected' ? 'mt-4 border-t border-cyan/35 pt-3' : 'mt-4 border-t border-orange/35 pt-3'}
      data-testid="planner-telemetry-structure-context"
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
        <p data-testid="planner-telemetry-contextual-economy" className="mt-2 rounded border border-cyan/30 bg-cyan/8 px-2 py-1 font-mono text-[10px] leading-snug text-cyan">
          {detail.economyContextLabel}
        </p>
      )}
      {detail.prerequisiteWarnings.length > 0 && (
        <p data-testid="planner-telemetry-prerequisite-warning" className="mt-2 rounded border border-gold/35 bg-gold/10 px-2 py-1 font-mono text-[10px] leading-snug text-gold">
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
  rows: PlannerCanvasRow[],
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
  const lane = plannerCanvasLaneForPlacement(
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
    tier === 'S' ? '#22d3ee'
      : tier === 'A' ? '#4ade80'
        : tier === 'B' ? '#facc15'
          : tier === 'C' ? '#ff7a14'
            : tier === 'D' ? '#ef4444'
              : '#8a8f96';
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
      data-testid="planner-development-profile-card"
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
          data-testid="planner-development-overall-score"
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
      data-testid="planner-zero-centered-stat-bar"
      data-stat-id={id}
      data-direction={direction}
      className="grid grid-cols-[7.5rem_1fr_3.6rem] items-center gap-2 font-mono text-[11px]"
    >
      <span className="truncate text-silver">{label}</span>
      <span className="relative h-4 overflow-hidden rounded-sm border border-border/60 bg-bg4/80 shadow-inner-soft">
        <span data-testid={`planner-stat-${id}-zero-axis`} aria-hidden className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-silver/55" />
        <span
          data-testid={`planner-stat-${id}-negative`}
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
          data-testid={`planner-stat-${id}-positive`}
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
