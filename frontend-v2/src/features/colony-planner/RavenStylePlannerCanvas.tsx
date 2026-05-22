import { Network, Sparkles, Target } from 'lucide-react';
import type { CSSProperties, ReactNode } from 'react';
import { formatPopulation } from '@/lib/format';
import type { BodySlotPrediction, FacilityTemplate, SimulateBuildPlacement, SystemBody, SystemDetail } from '@/types/api';
import {
  bodyDisplayName,
  bodyTags,
  compactBodyDisplayName,
} from '@/features/system-detail/simulation-preview/buildPlanLayoutUtils';
import { templateLocationKind } from '@/features/system-detail/simulation-preview/structurePickerUtils';
import type { TopologyPlanSnapshot, TopologySelection, TopologySelectionContext } from './ColonyTopologyRail';
import { PlanningEconomyStrip } from './PlanningEconomyStrip';
import {
  buildPlanningEconomyLedger,
  normalisePlanningEconomy,
  PLANNING_ECONOMY_NOTE,
  type PlanningEconomyLedger,
  type PlanningEconomyName,
} from './planningEconomy';

type RavenLane = 'orbital' | 'ground';
type RavenSlotKind = 'empty' | 'planned' | 'projected' | 'unknown' | 'overflow';

export interface RavenEconomySegment {
  economy: PlanningEconomyName;
  share: number;
  strength: number | null;
  projected: boolean;
}

export interface RavenStructureSlot {
  id: string;
  kind: RavenSlotKind;
  label: string;
  fullName: string;
  title: string;
  economySegments: RavenEconomySegment[];
  placementIndex: number | null;
  buildOrder: number | null;
  status: 'planned' | 'projected' | 'unknown';
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
  orbitalSlots: RavenStructureSlot[];
  groundSlots: RavenStructureSlot[];
  bodyEconomy: PlanningEconomyLedger;
  projected: boolean;
  warningCount: number;
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
  placement: SimulateBuildPlacement;
  template?: FacilityTemplate;
  index: number;
  projected: boolean;
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
}: {
  system: SystemDetail;
  snapshot: TopologyPlanSnapshot;
  selection: TopologySelection;
  onSelect: (selection: TopologySelection) => void;
}) {
  const rows = buildRavenPlannerRows(system, snapshot);
  const selectedBodyId = selection.type === 'body'
    ? selection.bodyId
    : selection.type === 'placement'
      ? placementBodyId(snapshot.placements[selection.placementIndex])
      : null;
  const gridStyle: CSSProperties = {
    gridTemplateColumns: '260px minmax(270px,1fr) minmax(300px,1.08fr)',
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
            <h2 className="font-display text-lg text-orange">Whole-System Build Canvas</h2>
            <p className="truncate text-xs leading-relaxed text-silver-dk">
              Real bodies, validated slot predictions, Build Plan placements, and selected Suggested Build projection.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5 text-[11px]">
          <CanvasPill label={`${rows.length} bodies`} tone="silver" />
          <CanvasPill label={`${snapshot.placements.length} planned`} tone={snapshot.placements.length > 0 ? 'orange' : 'silver'} />
          {snapshot.projection && <CanvasPill label={`${snapshot.projection.placements.length} projected`} tone="cyan" />}
          <CanvasPill label={snapshot.slotPredictions ? 'slots loaded' : 'slots unknown'} tone={snapshot.slotPredictions ? 'green' : 'gold'} />
        </div>
      </header>

      <div className="overflow-x-auto">
        <div className="min-w-[860px]">
          <div
            className="grid border-b border-orange/20 bg-bg2/70 px-3 py-2 font-mono text-[11px] uppercase tracking-[0.1em] text-silver-dk"
            style={gridStyle}
          >
            <div className="text-cyan">System tree</div>
            <div>Orbital lane</div>
            <div>Ground lane</div>
          </div>

          <div className="divide-y divide-border/45">
            {rows.length === 0 ? (
              <div className="px-3 py-5 text-sm text-silver-dk">No real body layout is available for this system.</div>
            ) : rows.map((row) => (
              <RavenPlannerBodyRow
                key={row.id}
                row={row}
                selected={selectedBodyId === row.id}
                selectedPlacementIndex={selection.type === 'placement' ? selection.placementIndex : null}
                gridStyle={gridStyle}
                onSelect={onSelect}
              />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

export function RavenPlannerTelemetryPanel({
  system,
  snapshot,
  economyLedger,
  selectedContext,
}: {
  system: SystemDetail;
  snapshot: TopologyPlanSnapshot;
  economyLedger: PlanningEconomyLedger;
  selectedContext: TopologySelectionContext;
}) {
  const stats = buildPlannerTelemetryStats(system, snapshot, economyLedger);
  const population = system.population && system.population > 0 ? formatPopulation(system.population) : 'Uncolonised';
  const score = typeof system.score === 'number' ? Math.round(system.score) : 'n/a';
  const projectedLabel = snapshot.projection?.label ?? 'No candidate selected';

  return (
    <aside
      aria-label="Raven-style planner telemetry"
      data-testid="raven-real-telemetry-panel"
      data-layout="wide-readable-telemetry"
      className="rounded-chunk border border-cyan/25 bg-bg2/95 p-3 xl:sticky xl:top-4 xl:max-h-[calc(100vh-14rem)] xl:overflow-y-auto"
    >
      <div className="flex items-center gap-2 border-b border-border/45 pb-2">
        <div className="grid h-8 w-8 place-items-center rounded border border-orange/35 bg-orange/10 text-orange">
          <Target size={17} />
        </div>
        <div>
          <h2 className="font-display text-base text-orange">Planning Telemetry</h2>
          <p className="text-xs leading-relaxed text-silver-dk">Live planner data, Preview remains explicit.</p>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 border-b border-border/35 pb-3">
        <TelemetryMetric label="System score" value={String(score)} />
        <TelemetryMetric label="Population" value={population} />
        <TelemetryMetric label="Planned haul" value={`${snapshot.placements.length} builds`} />
        <TelemetryMetric label="Build staged" value={`${snapshot.placements.length}${snapshot.projection ? ` +${snapshot.projection.placements.length}` : ''}`} />
      </div>

      <div className="mt-4 space-y-2">
        {stats.map((stat) => (
          <ZeroCenteredStatBar key={stat.id} id={stat.id} label={stat.label} value={stat.value} />
        ))}
      </div>

      <div className="mt-4 border-t border-border/70 pt-3">
        <h3 className="font-mono text-[11px] uppercase tracking-[0.12em] text-cyan">Economy mix</h3>
        <p className="mt-1 text-xs leading-relaxed text-silver-dk">{PLANNING_ECONOMY_NOTE}</p>
        <div className="mt-2">
          <PlanningEconomyStrip ledger={economyLedger} testId="raven-telemetry-economy-ledger" />
        </div>
      </div>

      <div className="mt-4 border-t border-border/35 pt-3">
        <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.12em] text-orange">
          <Sparkles size={14} />
          Suggested Build projection
        </div>
        <p className="mt-1 text-sm leading-relaxed text-silver">{projectedLabel}</p>
        <p className="mt-1 text-xs leading-relaxed text-silver-dk">
          Selecting a candidate projects ghost structures. Loading and Preview stay explicit.
        </p>
      </div>

      <div className="mt-4 border-t border-cyan/25 pt-3">
        <div className="font-mono text-[11px] uppercase tracking-[0.12em] text-cyan">Selected focus</div>
        <div className="mt-1 text-base font-semibold leading-snug text-silver">{selectedContext.label}</div>
        <div className="mt-1 text-sm text-silver-dk">{selectedContext.kind}</div>
        <p className="mt-2 text-sm leading-relaxed text-silver-dk">{selectedContext.detail}</p>
      </div>
    </aside>
  );
}

function RavenPlannerBodyRow({
  row,
  selected,
  selectedPlacementIndex,
  gridStyle,
  onSelect,
}: {
  row: RavenPlannerRow;
  selected: boolean;
  selectedPlacementIndex: number | null;
  gridStyle: CSSProperties;
  onSelect: (selection: TopologySelection) => void;
}) {
  return (
    <div
      data-testid={`raven-real-body-row-${row.id}`}
      data-projected={row.projected ? 'true' : 'false'}
      className={[
        'grid min-h-[62px] items-stretch px-3 py-2 transition-colors',
        selected ? 'bg-orange/10 shadow-[inset_3px_0_0_rgba(255,122,20,0.95)]' : row.projected ? 'bg-cyan/5 hover:bg-cyan/10' : 'bg-transparent hover:bg-bg3/35',
      ].join(' ')}
      style={gridStyle}
    >
      <TreeCell row={row} selected={selected} onSelect={() => onSelect({ type: 'body', bodyId: row.id })} />
      <RavenSlotLane
        bodyId={row.id}
        lane="orbital"
        capacity={row.orbitalCapacity}
        slots={row.orbitalSlots}
        selectedPlacementIndex={selectedPlacementIndex}
        onSelect={onSelect}
      />
      <RavenSlotLane
        bodyId={row.id}
        lane="ground"
        capacity={row.groundCapacity}
        slots={row.groundSlots}
        selectedPlacementIndex={selectedPlacementIndex}
        onSelect={onSelect}
      />
    </div>
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
            <span className="truncate text-sm font-semibold leading-snug text-silver">{row.compactName}</span>
            {row.warningCount > 0 && <span className="rounded border border-gold/35 bg-gold/10 px-1.5 py-0.5 font-mono text-[10px] text-gold">!</span>}
            {row.projected && <span className="rounded border border-cyan/35 bg-cyan/10 px-1.5 py-0.5 font-mono text-[10px] text-cyan">ghost</span>}
          </span>
          <span className="mt-0.5 block truncate text-xs leading-snug text-silver-dk">{row.bodyKind}</span>
        </span>
      </button>
    </div>
  );
}

function RavenSlotLane({
  bodyId,
  lane,
  capacity,
  slots,
  selectedPlacementIndex,
  onSelect,
}: {
  bodyId: string;
  lane: RavenLane;
  capacity: number | null;
  slots: RavenStructureSlot[];
  selectedPlacementIndex: number | null;
  onSelect: (selection: TopologySelection) => void;
}) {
  const knownCount = capacity == null ? '?' : String(capacity);
  const laneLabel = lane === 'orbital' ? `O${knownCount}` : `G${knownCount}`;

  return (
    <div data-testid={`${bodyId}-${lane}-lane`} className="flex min-w-0 items-center gap-2 pr-2">
      <span className="w-10 shrink-0 font-mono text-[11px] uppercase tracking-[0.1em] text-cyan">{laneLabel}</span>
      <div className="flex min-w-0 flex-wrap gap-1.5">
        {slots.map((slot, index) => (
          <RavenSlotBox
            key={slot.id}
            slot={slot}
            testId={`${bodyId}-${lane}-slot-${index}`}
            selected={slot.placementIndex != null && slot.placementIndex === selectedPlacementIndex}
            onSelect={onSelect}
          />
        ))}
      </div>
    </div>
  );
}

function RavenSlotBox({
  slot,
  testId,
  selected,
  onSelect,
}: {
  slot: RavenStructureSlot;
  testId: string;
  selected: boolean;
  onSelect: (selection: TopologySelection) => void;
}) {
  const primaryEconomy = slot.economySegments[0]?.economy;
  const color = primaryEconomy ? ECONOMY_COLORS[primaryEconomy] : undefined;
  const isStructure = slot.kind === 'planned' || slot.kind === 'projected' || slot.kind === 'overflow';
  const slotStyle: CSSProperties = {};
  if (slot.kind === 'planned' && color) {
    slotStyle.borderColor = color;
    slotStyle.background = `linear-gradient(180deg, ${color}24, rgba(18,20,24,0.9))`;
  }
  if (slot.kind === 'projected' && color) {
    slotStyle.borderColor = color;
    slotStyle.background = `linear-gradient(180deg, ${color}1f, rgba(18,20,24,0.48))`;
  }

  const content = (
    <>
      {slot.kind === 'projected' && <span data-testid="raven-projected-ghost-structure" className="sr-only">{slot.fullName}</span>}
      {slot.status !== 'unknown' && (
        <span className={slot.kind === 'projected' ? 'absolute right-1 top-0.5 text-[8px] text-cyan' : 'absolute right-1 top-0.5 text-[8px] text-silver-dk'}>
          {slot.kind === 'projected' ? 'PROJ' : slot.kind === 'overflow' ? 'OVER' : 'PLAN'}
        </span>
      )}
      <span data-testid={isStructure ? 'raven-structure-slot-pill' : undefined} className="max-w-full truncate">
        {slot.label}
      </span>
      {slot.economySegments.length > 0 && <StructureEconomyMicroBar segments={slot.economySegments} />}
    </>
  );

  const className = [
    'group/slot relative flex overflow-hidden rounded border px-1.5 text-center font-mono text-[10px] font-bold uppercase leading-tight transition',
    isStructure ? 'h-10 min-w-[94px] max-w-[138px] items-start justify-center pb-2.5 pt-3' : 'h-8 min-w-[74px] max-w-[112px] items-center justify-center',
    'hover:-translate-y-0.5 hover:border-orange-lt hover:shadow-brand-glow',
    selected && 'ring-2 ring-orange/70',
    slot.kind === 'empty' && 'border-border/70 bg-bg2/75 text-silver-2',
    slot.kind === 'planned' && 'text-silver',
    slot.kind === 'projected' && 'border-dashed text-cyan opacity-80',
    slot.kind === 'unknown' && 'border-dashed border-gold/65 bg-gold/10 text-gold',
    slot.kind === 'overflow' && 'border-orange bg-orange/20 text-orange-lt',
  ].filter(Boolean).join(' ');

  if (slot.placementIndex == null) {
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
      onClick={() => onSelect({ type: 'placement', placementIndex: slot.placementIndex ?? 0 })}
      className={className}
      style={slotStyle}
    >
      {content}
    </button>
  );
}

function StructureEconomyMicroBar({ segments }: { segments: RavenEconomySegment[] }) {
  const total = Math.max(1, segments.reduce((sum, segment) => sum + segment.share, 0));
  const title = segments.map((segment) => {
    const strength = segment.strength == null ? 'strength unavailable' : `+${segment.strength} CP strength`;
    return `${segment.economy} ${segment.share}% share | ${strength}`;
  }).join(' / ');

  return (
    <span
      data-testid="raven-structure-economy-micro-bar"
      aria-label={title}
      title={title}
      className="absolute inset-x-0 bottom-0 flex h-1 overflow-hidden bg-bg4/80"
    >
      {segments.map((segment) => (
        <span
          key={segment.economy}
          className={segment.projected ? 'opacity-60' : ''}
          style={{
            width: `${(segment.share / total) * 100}%`,
            backgroundColor: ECONOMY_COLORS[segment.economy],
          }}
        />
      ))}
    </span>
  );
}

function TelemetryMetric({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="grid grid-cols-[1fr_auto] items-baseline gap-2">
      <div className="truncate font-mono text-[10px] uppercase tracking-[0.1em] text-silver-dk">{label}</div>
      <div className="text-right font-display text-base text-silver">{value}</div>
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
      <span className="truncate text-silver-dk">{label}</span>
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
    silver: 'border-border/60 bg-bg3/45 text-silver-dk',
    orange: 'border-orange/35 bg-orange/10 text-orange',
    cyan: 'border-cyan/35 bg-cyan/10 text-cyan',
    green: 'border-green/35 bg-green/10 text-green',
    gold: 'border-gold/35 bg-gold/10 text-gold',
  }[tone];
  return <span className={['rounded border px-1.5 py-0.5 font-mono uppercase tracking-[0.1em]', toneClass].join(' ')}>{label}</span>;
}

export function buildRavenPlannerRows(system: SystemDetail, snapshot: TopologyPlanSnapshot): RavenPlannerRow[] {
  const bodies = system.bodies ?? [];
  const predictionsByBodyId = new Map(
    (snapshot.slotPredictions?.predictions ?? []).map((prediction) => [String(prediction.body_id), prediction]),
  );
  const templatesById = new Map(snapshot.templates.map((template) => [template.id, template]));
  const bodyById = new Map(
    bodies
      .filter((body) => body.id != null)
      .map((body) => [String(body.id), body]),
  );
  const plannedByBody = bucketStructures(snapshot.placements, templatesById, bodyById, false);
  const projectedByBody = bucketStructures(snapshot.projection?.placements ?? [], templatesById, bodyById, true);
  const projectedBodyIds = new Set(Array.from(projectedByBody.keys()));

  return flattenBodyNodes(bodies).map((node) => {
    const prediction = predictionsByBodyId.get(node.id) ?? null;
    const planned = plannedByBody.get(node.id) ?? emptyStructureBuckets();
    const projected = projectedByBody.get(node.id) ?? emptyStructureBuckets();
    const orbitalStructures = [...planned.orbital, ...projected.orbital];
    const groundStructures = [...planned.ground, ...planned.unknown, ...projected.ground, ...projected.unknown];
    const bodyLedger = buildPlanningEconomyLedger({
      placements: [...planned.orbital, ...planned.ground, ...planned.unknown].map((item) => item.placement),
      projectedPlacements: [...projected.orbital, ...projected.ground, ...projected.unknown].map((item) => item.placement),
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
      orbitalCapacity: readSlotCount(prediction, 'orbital'),
      groundCapacity: readSlotCount(prediction, 'ground'),
      orbitalSlots: buildLaneSlots(node.id, 'orbital', readSlotCount(prediction, 'orbital'), orbitalStructures),
      groundSlots: buildLaneSlots(node.id, 'ground', readSlotCount(prediction, 'ground'), groundStructures),
      bodyEconomy: bodyLedger,
      projected: projectedBodyIds.has(node.id),
      warningCount: countRowWarnings(node.body, prediction, bodyLedger),
    };
  });
}

export function buildPlannerTelemetryStats(
  system: SystemDetail,
  snapshot: TopologyPlanSnapshot,
  economyLedger: PlanningEconomyLedger,
) {
  const bodies = system.bodies ?? [];
  const predictedBodyIds = new Set((snapshot.slotPredictions?.predictions ?? []).map((prediction) => String(prediction.body_id)));
  const unknownSlotBodies = bodies.filter((body) => body.id != null && !predictedBodyIds.has(String(body.id))).length;
  const unassigned = snapshot.placements.filter((placement) => placement.local_body_id == null).length;
  const projected = snapshot.projection?.placements.length ?? 0;
  const knownSlots = (snapshot.slotPredictions?.predicted_orbital_slots_total ?? 0) + (snapshot.slotPredictions?.predicted_ground_slots_total ?? 0);

  return [
    { id: 'planned-builds', label: 'Planned', value: snapshot.placements.length },
    { id: 'projected-builds', label: 'Projected', value: projected },
    { id: 'known-slots', label: 'Known slots', value: knownSlots > 0 ? Math.min(12, knownSlots) : 0 },
    { id: 'unassigned', label: 'Unassigned', value: unassigned > 0 ? -unassigned : 0 },
    { id: 'missing-economy', label: 'No economy', value: economyLedger.unknownCount > 0 ? -economyLedger.unknownCount : 0 },
    { id: 'unknown-slots', label: 'Slot gaps', value: unknownSlotBodies > 0 ? -Math.min(12, unknownSlotBodies) : 0 },
  ];
}

function bucketStructures(
  placements: SimulateBuildPlacement[],
  templatesById: Map<string, FacilityTemplate>,
  bodyById: Map<string, SystemBody>,
  projected: boolean,
) {
  const buckets = new Map<string, ReturnType<typeof emptyStructureBuckets>>();

  placements.forEach((placement, index) => {
    const bodyId = placementBodyId(placement);
    if (!bodyId || !bodyById.has(bodyId)) return;
    const template = templatesById.get(placement.facility_template_id);
    const lane = laneForPlacement(template, bodyById.get(bodyId));
    const current = buckets.get(bodyId) ?? emptyStructureBuckets();
    current[lane].push({ placement, template, index, projected });
    buckets.set(bodyId, current);
  });

  return buckets;
}

function emptyStructureBuckets() {
  return {
    orbital: [] as StructureBucketItem[],
    ground: [] as StructureBucketItem[],
    unknown: [] as StructureBucketItem[],
  };
}

function buildLaneSlots(
  bodyId: string,
  lane: RavenLane,
  capacity: number | null,
  structures: StructureBucketItem[],
): RavenStructureSlot[] {
  if (capacity == null) {
    return [
      unknownSlot(bodyId, lane),
      ...structures.map((item, index) => structureSlot(bodyId, lane, item, index)),
    ];
  }

  if (capacity <= 0) {
    if (structures.length === 0) return [emptySlot(bodyId, lane, 0, '0')];
    return [overflowSlot(bodyId, lane, structures.length)];
  }

  const visible = structures.slice(0, capacity).map((item, index) => structureSlot(bodyId, lane, item, index));
  const empty = Array.from({ length: Math.max(0, capacity - visible.length) }, (_unused, index) => (
    emptySlot(bodyId, lane, visible.length + index)
  ));
  const overflow = structures.length > capacity ? [overflowSlot(bodyId, lane, structures.length - capacity)] : [];
  return [...visible, ...empty, ...overflow];
}

function structureSlot(bodyId: string, lane: RavenLane, item: StructureBucketItem, index: number): RavenStructureSlot {
  const fullName = structureDisplayName(item.template, item.placement.facility_template_id);
  const segments = structureEconomySegments(item.template, item.projected);
  const status = item.projected ? 'projected' : 'planned';
  const economyText = segments.length === 0
    ? 'No economy metadata'
    : segments.map((segment) => {
      const strength = segment.strength == null ? 'strength unavailable' : `+${segment.strength} CP strength`;
      return `${segment.economy} ${segment.share}% share | ${strength}`;
    }).join(' / ');

  return {
    id: `${bodyId}-${lane}-${status}-${item.index}-${item.placement.facility_template_id}-${index}`,
    kind: item.projected ? 'projected' : 'planned',
    label: `${item.projected ? 'Ghost ' : ''}${compactStructureName(fullName)}`,
    fullName,
    title: `${fullName} | Status: ${item.projected ? 'Projected Suggested Build' : 'Planned Build Plan'} | ${economyText}`,
    economySegments: segments,
    placementIndex: item.projected ? null : item.index,
    buildOrder: item.placement.build_order ?? null,
    status,
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
    buildOrder: null,
    status: 'unknown',
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
    buildOrder: null,
    status: 'unknown',
  };
}

function overflowSlot(bodyId: string, lane: RavenLane, count: number): RavenStructureSlot {
  return {
    id: `${bodyId}-${lane}-overflow-${count}`,
    kind: 'overflow',
    label: `+${count} overflow`,
    fullName: `${count} overflow or unconfirmed structures`,
    title: `${count} structure${count === 1 ? '' : 's'} exceed known ${lane} slot capacity or need confirmation.`,
    economySegments: [],
    placementIndex: null,
    buildOrder: null,
    status: 'unknown',
  };
}

function structureEconomySegments(template: FacilityTemplate | undefined, projected: boolean): RavenEconomySegment[] {
  const economy = normalisePlanningEconomy(template?.economy);
  if (!economy) return [];
  const strength = template ? Math.max(0, (template.yellow_cp_generated ?? 0) + (template.green_cp_generated ?? 0)) : null;
  return [{
    economy,
    share: 100,
    strength,
    projected,
  }];
}

function structureDisplayName(template: FacilityTemplate | undefined, fallback: string): string {
  const displayCarrier = template as unknown as { display_name?: unknown } | undefined;
  const displayName = typeof displayCarrier?.display_name === 'string'
    ? displayCarrier.display_name.trim()
    : '';
  return displayName || template?.name || readableTemplateId(fallback);
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

function laneForPlacement(template: FacilityTemplate | undefined, body: SystemBody | undefined): 'orbital' | 'ground' | 'unknown' {
  if (!template) return 'unknown';
  const location = templateLocationKind(template);
  if (location === 'orbital') return 'orbital';
  if (location === 'surface') return 'ground';
  if (location === 'both') return template.is_port ? 'orbital' : body?.is_landable === true ? 'ground' : 'orbital';
  return 'unknown';
}

function readSlotCount(prediction: BodySlotPrediction | null, lane: RavenLane): number | null {
  const value = lane === 'orbital' ? prediction?.predicted_orbital_slots : prediction?.predicted_ground_slots;
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return null;
  return Math.floor(value);
}

function placementBodyId(placement: SimulateBuildPlacement | undefined): string | null {
  return placement?.local_body_id != null ? String(placement.local_body_id) : null;
}

function flattenBodyNodes(bodies: SystemBody[]): FlatBodyNode[] {
  const nodes = buildBodyTree(bodies);
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

function buildBodyTree(bodies: SystemBody[]): BodyNode[] {
  const nodes = bodies
    .filter((body) => body.id != null)
    .map((body) => ({ body, id: String(body.id), children: [] as BodyNode[] }));
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
      || (left.body.distance_from_star ?? Number.MAX_SAFE_INTEGER) - (right.body.distance_from_star ?? Number.MAX_SAFE_INTEGER)
      || bodyDisplayName(left.body).localeCompare(bodyDisplayName(right.body)));
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
  if (typeof raw === 'number' || typeof raw === 'string') return String(raw);
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
) {
  let count = 0;
  if (!prediction) count += 1;
  if (ledger.unknownCount > 0) count += ledger.unknownCount;
  if (bodyTags(body).includes('Unknown body data')) count += 1;
  return count;
}
