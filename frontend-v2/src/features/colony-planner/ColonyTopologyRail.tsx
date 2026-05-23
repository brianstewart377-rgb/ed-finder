import { Network } from 'lucide-react';
import type {
  FacilityTemplate,
  SimulateBuildPlacement,
  SlotPredictionResponse,
  SystemBody,
  SystemDetail,
} from '@/types/api';
import {
  bodyDisplayName,
  compactBodyDisplayName,
  bodyTags,
  getBodyGroupWarnings,
  getPlacementWarnings,
  type BodyGroup,
  type GroupedPlacement,
} from '@/features/system-detail/simulation-preview/buildPlanLayoutUtils';
import { bodyIdKey, sameBodyId } from '@/features/system-detail/simulation-preview/bodyIdUtils';
import { PlanningEconomyStrip } from './PlanningEconomyStrip';
import { buildPlanningEconomyLedger } from './planningEconomy';
import {
  ESTIMATED_SLOT_LAYOUT_DISCLAIMER,
  buildBodyDataSlotEstimateMap,
  hasEstimatedSlotFallback,
  resolveSlotCapacity,
  systemBodyData,
  type BodyDataSlotEstimate,
} from './slotCapacityFallback';
import type { BodyPlannerLane } from './BodySlotPlanner';

export type TopologySelection =
  | { type: 'system' }
  | { type: 'body'; bodyId: string }
  | { type: 'placement'; placementIndex: number }
  | { type: 'projected-placement'; placementIndex: number }
  | { type: 'group'; groupKey: 'unassigned' | 'unknown' };

export interface TopologyPlanSnapshot {
  placements: SimulateBuildPlacement[];
  templates: FacilityTemplate[];
  targetArchetype: string;
  slotPredictions?: SlotPredictionResponse | null;
  placementLaneHints?: Record<number, BodyPlannerLane>;
  projection?: {
    candidateId: string;
    label: string;
    placements: SimulateBuildPlacement[];
    placementLaneHints?: Record<number, BodyPlannerLane>;
  } | null;
}

export interface TopologySelectionContext {
  label: string;
  kind: string;
  placementCount: number;
  warningCount: number;
  architectStatus: string;
  detail: string;
}

interface ColonyTopologyRailProps {
  system: SystemDetail;
  snapshot: TopologyPlanSnapshot;
  selection: TopologySelection;
  onSelect: (selection: TopologySelection) => void;
}

interface BodyNode {
  body: SystemBody;
  id: string;
  depth: number;
}

interface PlacementBucket {
  knownByBody: Map<string, GroupedPlacement[]>;
  unknown: GroupedPlacement[];
  unassigned: GroupedPlacement[];
}

interface ProjectedPlacementItem {
  index: number;
  placement: SimulateBuildPlacement;
  template?: FacilityTemplate;
}

type SlotLaneKind = 'orbital' | 'ground' | 'unknown';

export function ColonyTopologyRail({
  system,
  snapshot,
  selection,
  onSelect,
}: ColonyTopologyRailProps) {
  const bodies = systemBodyData(system);
  const bodyDataSlotEstimates = buildBodyDataSlotEstimateMap(system, snapshot.slotPredictions?.predictions);
  const bodyNodes = buildBodyNodes(bodies);
  const buckets = bucketPlacements(snapshot.placements, snapshot.templates, bodies);
  const totalPlacements = snapshot.placements.length;
  const selectedIsSystem = selection.type === 'system';
  const hasEstimatedSlots = bodyDataSlotEstimates.size > 0 || hasEstimatedSlotFallback(system, snapshot);
  const projectedByBody = bucketProjectedPlacements(snapshot.projection?.placements ?? [], snapshot.templates, bodies);
  const projectedBodyIds = new Set(
    (snapshot.projection?.placements ?? [])
      .map((placement) => bodyIdKey(placement.local_body_id))
      .filter(Boolean),
  );
  const projectedBodyLabels = bodyNodes
    .filter((node) => projectedBodyIds.has(node.id))
    .map((node) => compactBodyDisplayName(node.body, system.name))
    .slice(0, 6);

  return (
    <aside
      aria-label="Whole-system slot map"
      data-testid="planner-topology-sidebar"
      className="panel p-3 xl:sticky xl:top-4 xl:max-h-[calc(100vh-14rem)] xl:overflow-y-auto"
    >
      <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">
        <Network size={13} />
        Whole-system slot map
      </div>
      {snapshot.slotPredictions && (
        <div className="mt-2 rounded border border-cyan/25 bg-cyan/5 px-2 py-1.5 font-mono text-[10px] text-silver">
          <div className="text-cyan">Predicted slots</div>
          <div className="mt-0.5">{snapshot.slotPredictions.disclaimer}</div>
          <div className="mt-0.5 italic">{snapshot.slotPredictions.validation_note}</div>
        </div>
      )}
      {hasEstimatedSlots && (
        <div
          data-testid="topology-slot-estimate-disclaimer"
          className="mt-2 rounded border border-gold/30 bg-gold/10 px-2 py-1.5 font-mono text-[10px] italic text-gold"
        >
          {ESTIMATED_SLOT_LAYOUT_DISCLAIMER}
        </div>
      )}

      <button
        type="button"
        onClick={() => onSelect({ type: 'system' })}
        data-testid="topology-root-row"
        aria-pressed={selectedIsSystem}
        className={rowClass(selectedIsSystem, projectedBodyIds.size > 0)}
      >
        <span className="mt-0.5 shrink-0 text-cyan" aria-hidden="true">SYS</span>
        <div className="min-w-0 flex-1">
          <div className="truncate font-mono text-[11px] font-bold text-silver">
            {system.name || 'Unknown system'}
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-silver">
            System root
          </div>
        </div>
        <Chip tone="cyan">{bodies.length} bodies</Chip>
        {totalPlacements > 0 && <CountChip>{totalPlacements}</CountChip>}
      </button>

      {bodies.length === 0 ? (
        <p className="mt-3 rounded border border-border/45 bg-bg2/45 px-2 py-2 font-mono text-[10px] leading-snug text-silver">
          No body layout imported yet. Use the planner tools to import/refresh layout when available.
        </p>
      ) : (
        <div className="mt-3 space-y-1.5" data-testid="topology-body-tree">
          {bodyNodes.map((node) => (
            <BodyTreeRow
              key={node.id}
              node={node}
              systemName={system.name}
              slotPrediction={snapshot.slotPredictions?.predictions?.find((item) => sameBodyId(item.body_id, node.id)) ?? null}
              bodyDataSlotEstimate={bodyDataSlotEstimates.get(node.id) ?? null}
              placements={buckets.knownByBody.get(node.id) ?? []}
              projectedPlacements={projectedByBody.get(node.id) ?? []}
              selected={selection.type === 'body' && sameBodyId(selection.bodyId, node.id)}
              selectedPlacementIndex={selection.type === 'placement' ? selection.placementIndex : null}
              projected={projectedBodyIds.has(node.id)}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}

      {(buckets.unknown.length > 0 || buckets.unassigned.length > 0) && (
        <section className="mt-3 space-y-1.5" aria-label="Topology placement groups">
          {buckets.unknown.length > 0 && (
            <PlacementGroupRow
              title="Unknown / unmatched body"
              description={`${buckets.unknown.length} unmatched placement reference${buckets.unknown.length === 1 ? '' : 's'}`}
              placements={buckets.unknown}
              selected={selection.type === 'group' && selection.groupKey === 'unknown'}
              selectedPlacementIndex={selection.type === 'placement' ? selection.placementIndex : null}
              onSelectGroup={() => onSelect({ type: 'group', groupKey: 'unknown' })}
              onSelectPlacement={(placementIndex) => onSelect({ type: 'placement', placementIndex })}
            />
          )}
          {buckets.unassigned.length > 0 && (
            <PlacementGroupRow
              title="Unassigned placements"
              description={buckets.unassigned.length === 1 ? '1 placement needs a body' : `${buckets.unassigned.length} placements need a body`}
              placements={buckets.unassigned}
              selected={selection.type === 'group' && selection.groupKey === 'unassigned'}
              selectedPlacementIndex={selection.type === 'placement' ? selection.placementIndex : null}
              onSelectGroup={() => onSelect({ type: 'group', groupKey: 'unassigned' })}
              onSelectPlacement={(placementIndex) => onSelect({ type: 'placement', placementIndex })}
            />
          )}
        </section>
      )}

      {snapshot.projection && projectedBodyLabels.length > 0 && (
        <div
          data-testid="topology-projected-bodies"
          className="mt-3 rounded border border-cyan/30 bg-cyan/5 px-2 py-1.5 font-mono text-[10px] text-cyan"
        >
          <div className="uppercase tracking-[0.14em]">Projected plan</div>
          <div className="mt-1 text-silver">
            This plan uses: <span className="text-silver">{projectedBodyLabels.join(', ')}</span>
          </div>
        </div>
      )}

      <div className="mt-3 rounded border border-border/45 bg-bg3/30 px-2 py-1.5 font-mono text-[10px] text-silver">
        Click a body to plan there.
      </div>
    </aside>
  );
}

function BodyTreeRow({
  node,
  systemName,
  slotPrediction,
  bodyDataSlotEstimate,
  placements,
  projectedPlacements,
  selected,
  selectedPlacementIndex,
  projected,
  onSelect,
}: {
  node: BodyNode;
  systemName?: string | null;
  slotPrediction: NonNullable<TopologyPlanSnapshot['slotPredictions']>['predictions'][number] | null;
  bodyDataSlotEstimate?: BodyDataSlotEstimate | null;
  placements: GroupedPlacement[];
  projectedPlacements: ProjectedPlacementItem[];
  selected: boolean;
  selectedPlacementIndex: number | null;
  projected: boolean;
  onSelect: (selection: TopologySelection) => void;
}) {
  const tags = bodyTags(node.body);
  const sparse = tags.includes('Unknown body data') || (!node.body.body_type && !node.body.subtype);
  const hasPrimary = placements.some((item) => item.placement.is_primary_port);
  const warningCount = getBodyGroupWarnings({ key: node.id, body: node.body, placements }).length;
  const fullName = bodyDisplayName(node.body);
  const compactName = compactBodyDisplayName(node.body, systemName);
  const projectedCount = projectedPlacements.length;
  const depthIndent = node.depth > 0 ? `${node.depth * 0.75}rem` : '0rem';
  const plannedOrbital = placements.filter((item) => placementLaneKind(item.template) === 'orbital');
  const plannedGround = placements.filter((item) => placementLaneKind(item.template) === 'ground');
  const plannedUnknown = placements.filter((item) => placementLaneKind(item.template) === 'unknown');
  const projectedOrbital = projectedPlacements.filter((item) => placementLaneKind(item.template) === 'orbital');
  const projectedGround = projectedPlacements.filter((item) => placementLaneKind(item.template) === 'ground');
  const projectedUnknown = projectedPlacements.filter((item) => placementLaneKind(item.template) === 'unknown');
  const economyLedger = buildPlanningEconomyLedger({
    placements: placements.map((item) => item.placement),
    projectedPlacements: projectedPlacements.map((item) => item.placement),
    templates: [
      ...placements.map((item) => item.template).filter((template): template is FacilityTemplate => Boolean(template)),
      ...projectedPlacements.map((item) => item.template).filter((template): template is FacilityTemplate => Boolean(template)),
    ],
  });
  const orbitalSlotCapacity = resolveSlotCapacity(node.body, slotPrediction, 'orbital', bodyDataSlotEstimate);
  const groundSlotCapacity = resolveSlotCapacity(node.body, slotPrediction, 'surface', bodyDataSlotEstimate);
  const orbitalCapacity = orbitalSlotCapacity.value;
  const groundCapacity = groundSlotCapacity.value;
  const orbitalOverflow = orbitalCapacity == null ? 0 : Math.max(0, plannedOrbital.length + projectedOrbital.length - orbitalCapacity);
  const groundOverflow = groundCapacity == null ? 0 : Math.max(0, plannedGround.length + projectedGround.length - groundCapacity);
  const unknownOverflow = plannedUnknown.length + projectedUnknown.length;
  const totalOverflow = orbitalOverflow + groundOverflow + unknownOverflow;
  const hasSlotOrPlanSignal = placements.length > 0
    || projectedPlacements.length > 0
    || (orbitalCapacity != null && orbitalCapacity > 0)
    || (groundCapacity != null && groundCapacity > 0);

  return (
    <div data-testid={`topology-body-${node.id}`}>
      <div className="flex items-start gap-1" style={{ marginLeft: depthIndent }}>
        {node.depth > 0 ? (
          <span className="mt-3 h-px w-2 shrink-0 bg-border/70" aria-hidden="true" />
        ) : (
          <span className="w-2 shrink-0" aria-hidden="true" />
        )}
        <button
          type="button"
          onClick={() => onSelect({ type: 'body', bodyId: node.id })}
          aria-pressed={selected}
          data-testid={`topology-body-button-${node.id}`}
          title={fullName}
          className={rowClass(selected, projected)}
        >
          <span className="mt-0.5 w-4 shrink-0 text-center text-[13px] text-cyan" aria-hidden="true">
            {bodyIcon(node.body)}
          </span>
          <div className="min-w-0 flex-1">
            <div className="truncate font-mono text-[11px] font-bold text-silver">
              {compactName}
            </div>
            <div className="mt-0.5 truncate font-mono text-[10px] text-silver">
              {compactBodyKind(node.body)}
            </div>
          </div>
          {placements.length > 0 && <CountChip>{placements.length}</CountChip>}
          {projectedCount > 0 && <Chip tone="cyan">+{projectedCount}</Chip>}
          {projected && <Marker tone="cyan" label="Used by selected suggested build">G</Marker>}
          {hasPrimary && <Marker tone="gold" label="Primary-port placement">P</Marker>}
          {warningCount > 0 && <Marker tone="gold" label={`${warningCount} warnings`}>!</Marker>}
          {sparse && <Marker tone="silver" label="Sparse body data">?</Marker>}
        </button>
      </div>
      {placements.length > 0 && (
        <div className="ml-3 mt-1 space-y-1 border-l border-border/50 pl-2">
          <div className="font-mono text-[9px] uppercase tracking-[0.12em] text-silver">Planned</div>
          {placements.map((item) => (
            <PlacementButton
              key={`${item.index}-${item.placement.facility_template_id}`}
              item={item}
              selected={selectedPlacementIndex === item.index}
              onSelect={() => onSelect({ type: 'placement', placementIndex: item.index })}
            />
          ))}
        </div>
      )}
      {hasSlotOrPlanSignal && (
        <div className="ml-3 mt-1 rounded border border-border/45 bg-bg3/35 px-2 py-1.5">
          <SlotLaneRow
            laneKey={`${node.id}-orbital`}
            label="Orbit"
            capacity={orbitalCapacity}
            planned={plannedOrbital.map((item) => item.template?.name ?? item.placement.facility_template_id)}
            projected={projectedOrbital.map((item) => item.template?.name ?? item.placement.facility_template_id)}
          />
          <SlotLaneRow
            laneKey={`${node.id}-ground`}
            label="Surface"
            capacity={groundCapacity}
            planned={plannedGround.map((item) => item.template?.name ?? item.placement.facility_template_id)}
            projected={projectedGround.map((item) => item.template?.name ?? item.placement.facility_template_id)}
          />
          {totalOverflow > 0 && (
            <div
              data-testid={`topology-overflow-${node.id}`}
              className="mt-1 font-mono text-[9px] text-gold"
            >
              +{totalOverflow} overflow / unconfirmed
            </div>
          )}
          {economyLedger.total > 0 && (
            <div className="mt-1">
              <PlanningEconomyStrip
                ledger={economyLedger}
                compact
                testId={`topology-economy-${node.id}`}
              />
            </div>
          )}
        </div>
      )}
      {projectedPlacements.length > 0 && (
        <div
          data-testid={`topology-projected-group-${node.id}`}
          className="ml-3 mt-1 space-y-1 border-l border-cyan/35 pl-2"
        >
          <div className="font-mono text-[9px] uppercase tracking-[0.12em] text-cyan">Projected</div>
          {projectedPlacements.map((item) => (
            <ProjectedPlacementRow key={`projected-${node.id}-${item.index}-${item.placement.facility_template_id}`} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}

function PlacementGroupRow({
  title,
  description,
  placements,
  selected,
  selectedPlacementIndex,
  onSelectGroup,
  onSelectPlacement,
}: {
  title: string;
  description: string;
  placements: GroupedPlacement[];
  selected: boolean;
  selectedPlacementIndex: number | null;
  onSelectGroup: () => void;
  onSelectPlacement: (placementIndex: number) => void;
}) {
  return (
    <div className="rounded border border-gold/25 bg-gold/5 p-1.5">
      <button type="button" onClick={onSelectGroup} aria-pressed={selected} className={rowClass(selected)}>
        <span className="mt-0.5 w-4 shrink-0 text-center text-gold" aria-hidden="true">?</span>
        <div className="min-w-0 flex-1">
          <div className="truncate font-mono text-[11px] text-gold">{title}</div>
          <div className="mt-0.5 truncate font-mono text-[10px] text-silver">{description}</div>
        </div>
        <CountChip>{placements.length}</CountChip>
      </button>
      {placements.length > 0 && (
        <div className="ml-3 mt-1 space-y-1 border-l border-gold/25 pl-2">
          {placements.map((item) => (
            <PlacementButton
              key={`${item.index}-${item.placement.facility_template_id}`}
              item={item}
              selected={selectedPlacementIndex === item.index}
              onSelect={() => onSelectPlacement(item.index)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function PlacementButton({
  item,
  selected,
  onSelect,
}: {
  item: GroupedPlacement;
  selected: boolean;
  onSelect: () => void;
}) {
  const label = item.template?.name ?? item.placement.facility_template_id;
  return (
    <button
      type="button"
      onClick={onSelect}
      data-testid={`topology-placement-${item.index}`}
      aria-pressed={selected}
      className={[
        'flex w-full min-w-0 cursor-pointer items-center justify-between gap-2 rounded border px-2 py-1 text-left font-mono text-[10px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/70',
        selected
          ? 'border-orange/55 bg-orange/15 text-orange'
          : 'border-border/45 bg-bg2/45 text-silver hover:border-orange/35 hover:text-white',
      ].join(' ')}
    >
      <span className="min-w-0 truncate">#{item.placement.build_order} {label}</span>
      {item.placement.is_primary_port && <span className="shrink-0 text-gold">primary</span>}
    </button>
  );
}

function placementLaneKind(template?: FacilityTemplate): SlotLaneKind {
  const value = (template?.allowed_location ?? '').toLowerCase();
  const hasOrbital = value.includes('orbit');
  const hasGround = value.includes('surface') || value.includes('ground');
  if (hasOrbital && !hasGround) return 'orbital';
  if (hasGround && !hasOrbital) return 'ground';
  return 'unknown';
}

function SlotLaneRow({
  laneKey,
  label,
  capacity,
  planned,
  projected,
}: {
  laneKey: string;
  label: string;
  capacity: number | null | undefined;
  planned: string[];
  projected: string[];
}) {
  if (capacity == null) {
    return (
      <div className="flex items-center gap-1.5 font-mono text-[9px] text-silver">
        <span className="w-10 uppercase tracking-[0.12em]">{label}</span>
        <span className="rounded border border-gold/35 bg-gold/10 px-1 text-gold" data-testid={`slot-lane-unknown-${laneKey}`}>[?]</span>
      </div>
    );
  }

  const cells = Array.from({ length: Math.max(0, capacity) }, (_unused, index) => {
    if (index < planned.length) {
      const value = planned[index] ?? '';
      return {
        key: `planned-${laneKey}-${index}`,
        label: compactFacilityName(value),
        tone: 'planned' as const,
      };
    }
    const projectedIndex = index - planned.length;
    if (projectedIndex >= 0 && projectedIndex < projected.length) {
      const value = projected[projectedIndex] ?? '';
      return {
        key: `projected-${laneKey}-${index}`,
        label: compactFacilityName(value),
        tone: 'projected' as const,
      };
    }
    return {
      key: `empty-${laneKey}-${index}`,
      label: '',
      tone: 'empty' as const,
    };
  });

  return (
    <div className="flex items-center gap-1.5 font-mono text-[9px] text-silver">
      <span className="w-10 uppercase tracking-[0.12em]">{label}</span>
      <div className="flex min-w-0 flex-wrap gap-1">
        {cells.map((cell, index) => (
          <span
            key={cell.key}
            data-testid={`${laneKey}-slot-${index}`}
            className={[
              'inline-flex h-5 min-w-5 max-w-[4.6rem] items-center justify-center rounded border px-1 text-[8px] leading-none',
              cell.tone === 'planned'
                ? 'border-orange/55 bg-orange/15 text-orange'
                : cell.tone === 'projected'
                  ? 'border-cyan/45 bg-cyan/10 text-cyan'
                  : 'border-border/60 bg-bg2/45 text-silver',
            ].join(' ')}
            title={cell.label || 'Empty slot'}
          >
            {cell.label ? cell.label : ' '}
          </span>
        ))}
      </div>
    </div>
  );
}

function compactFacilityName(value: string): string {
  const clean = value.trim();
  if (!clean) return '';
  const parts = clean.split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 6);
  return parts[0].slice(0, 5);
}

function ProjectedPlacementRow({ item }: { item: ProjectedPlacementItem }) {
  const label = item.template?.name ?? item.placement.facility_template_id;
  return (
    <div
      data-testid={`topology-projected-placement-${item.index}`}
      className="flex w-full min-w-0 items-center justify-between gap-2 rounded border border-cyan/35 bg-cyan/8 px-2 py-1 text-left font-mono text-[10px] text-cyan"
      aria-label={`Projected structure ${label}`}
    >
      <span className="min-w-0 truncate">#{item.placement.build_order} {label}</span>
      <span className="shrink-0 uppercase tracking-[0.12em]">projected</span>
    </div>
  );
}

export function describeTopologySelection(
  selection: TopologySelection,
  system: SystemDetail,
  snapshot: TopologyPlanSnapshot,
): TopologySelectionContext {
  const bodies = systemBodyData(system);
  const buckets = bucketPlacements(snapshot.placements, snapshot.templates, bodies);
  const bodyById = new Map(
    bodies
      .filter((body) => body.id != null)
      .map((body) => [bodyIdKey(body.id), body]),
  );

  if (selection.type === 'body') {
    const bodyId = bodyIdKey(selection.bodyId);
    const body = bodyById.get(bodyId);
    const placements = buckets.knownByBody.get(bodyId) ?? [];
    const warnings = body ? getBodyGroupWarnings({ key: bodyId, body, placements }) : [];
    return {
      label: body ? bodyDisplayName(body) : 'Unknown body',
      kind: body?.subtype ?? body?.body_type ?? 'Body',
      placementCount: placements.length,
      warningCount: warnings.length,
      architectStatus: 'Architect flag not recorded',
      detail: placements.length > 0
        ? 'Body selected. Review or add structures in the inline canvas expansion.'
        : 'Body selected. Add the first structure in the inline canvas expansion.',
    };
  }

  if (selection.type === 'placement') {
    const item = allPlacements(buckets).find((candidate) => candidate.index === selection.placementIndex);
    const body = item?.bodyId ? bodyById.get(item.bodyId) ?? null : null;
    const warnings = item ? getPlacementWarnings(item, body) : [];
    return {
      label: item?.template?.name ?? item?.placement.facility_template_id ?? 'Selected placement',
      kind: item?.placement.is_primary_port ? 'Primary-port placement' : 'Planned placement',
      placementCount: item ? 1 : 0,
      warningCount: warnings.length,
      architectStatus: item?.placement.is_primary_port ? 'Primary-port placement planned; Architect flag not recorded' : 'Architect flag not recorded',
      detail: body ? `Assigned to ${bodyDisplayName(body)}.` : item?.hasUnknownBody ? 'Assigned body is not in the loaded body list.' : 'No body assigned yet.',
    };
  }

  if (selection.type === 'projected-placement') {
    const placement = snapshot.projection?.placements[selection.placementIndex];
    const template = placement
      ? snapshot.templates.find((candidate) => candidate.id === placement.facility_template_id)
      : undefined;
    const bodyId = placement?.local_body_id != null ? bodyIdKey(placement.local_body_id) : null;
    const body = bodyId ? bodyById.get(bodyId) ?? null : null;
    return {
      label: template?.name ?? placement?.facility_template_id ?? 'Projected placement',
      kind: 'Projected Suggested Build placement',
      placementCount: placement ? 1 : 0,
      warningCount: placement && !body ? 1 : 0,
      architectStatus: 'Projected only; not loaded into the Build Plan',
      detail: body ? `Ghost structure projected for ${bodyDisplayName(body)}.` : 'Projected structure has no matched body.',
    };
  }

  if (selection.type === 'group') {
    const placements = selection.groupKey === 'unknown' ? buckets.unknown : buckets.unassigned;
    return {
      label: selection.groupKey === 'unknown' ? 'Unknown / unmatched body' : 'Unassigned placements',
      kind: selection.groupKey === 'unknown' ? 'Needs body match' : 'Needs assignment',
      placementCount: placements.length,
      warningCount: placements.length,
      architectStatus: 'Architect flag not recorded',
      detail: selection.groupKey === 'unknown'
        ? 'Placement body references do not match the loaded system bodies.'
        : 'Placements are not assigned to a body yet.',
    };
  }

  return {
    label: system.name || 'System',
    kind: 'System root',
    placementCount: snapshot.placements.length,
    warningCount: countWorkspaceWarnings(snapshot, bodies),
    architectStatus: 'Architect flag not recorded',
    detail: 'Select a body to inspect local suitability and planned structures.',
  };
}

function bucketPlacements(
  placements: SimulateBuildPlacement[],
  templates: FacilityTemplate[],
  bodies: SystemBody[],
): PlacementBucket {
  const templatesById = new Map(templates.map((template) => [template.id, template]));
  const bodyIds = new Set(
    bodies
      .filter((body) => body.id != null)
      .map((body) => bodyIdKey(body.id)),
  );
  const knownByBody = new Map<string, GroupedPlacement[]>();
  const unknown: GroupedPlacement[] = [];
  const unassigned: GroupedPlacement[] = [];

  placements.forEach((placement, index) => {
    const bodyId = bodyIdKey(placement.local_body_id);
    const item: GroupedPlacement = {
      placement,
      index,
      template: templatesById.get(placement.facility_template_id),
      bodyId: bodyId || undefined,
      hasUnknownBody: Boolean(bodyId && !bodyIds.has(bodyId)),
    };

    if (!bodyId) {
      unassigned.push(item);
      return;
    }
    if (!bodyIds.has(bodyId)) {
      unknown.push(item);
      return;
    }
    const list = knownByBody.get(bodyId) ?? [];
    list.push(item);
    knownByBody.set(bodyId, list);
  });

  return { knownByBody, unknown, unassigned };
}

function bucketProjectedPlacements(
  placements: SimulateBuildPlacement[],
  templates: FacilityTemplate[],
  bodies: SystemBody[],
): Map<string, ProjectedPlacementItem[]> {
  const bodyIds = new Set(
    bodies
      .filter((body) => body.id != null)
      .map((body) => bodyIdKey(body.id)),
  );
  const templatesById = new Map(templates.map((template) => [template.id, template]));
  const buckets = new Map<string, ProjectedPlacementItem[]>();
  placements.forEach((placement, index) => {
    const bodyId = placement.local_body_id != null ? bodyIdKey(placement.local_body_id) : null;
    if (!bodyId || !bodyIds.has(bodyId)) return;
    const list = buckets.get(bodyId) ?? [];
    list.push({
      index,
      placement,
      template: templatesById.get(placement.facility_template_id),
    });
    buckets.set(bodyId, list);
  });
  return buckets;
}

function buildBodyNodes(bodies: SystemBody[]): BodyNode[] {
  const withIds = bodies
    .filter((body) => body.id != null)
    .map((body) => ({ body, id: bodyIdKey(body.id) }));
  const knownIds = new Set(withIds.map((item) => item.id));
  const children = new Map<string, Array<{ body: SystemBody; id: string }>>();
  const roots: Array<{ body: SystemBody; id: string }> = [];

  for (const item of withIds) {
    const parentId = bodyParentId(item.body);
    if (parentId && knownIds.has(parentId)) {
      const list = children.get(parentId) ?? [];
      list.push(item);
      children.set(parentId, list);
    } else {
      roots.push(item);
    }
  }

  const nodes: BodyNode[] = [];
  const visit = (item: { body: SystemBody; id: string }, depth: number) => {
    nodes.push({ ...item, depth });
    for (const child of sortBodies(children.get(item.id) ?? [])) {
      visit(child, depth + 1);
    }
  };

  for (const root of sortBodies(roots)) {
    visit(root, 0);
  }
  return nodes;
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

function sortBodies(items: Array<{ body: SystemBody; id: string }>) {
  return [...items].sort((a, b) => {
    const rank = (body: SystemBody) => body.body_type === 'Star' ? 0 : body.body_type === 'Planet' ? 1 : 2;
    if (rank(a.body) !== rank(b.body)) return rank(a.body) - rank(b.body);
    return (a.body.distance_from_star ?? Number.MAX_SAFE_INTEGER)
      - (b.body.distance_from_star ?? Number.MAX_SAFE_INTEGER);
  });
}

function allPlacements(buckets: PlacementBucket): GroupedPlacement[] {
  return [
    ...Array.from(buckets.knownByBody.values()).flat(),
    ...buckets.unknown,
    ...buckets.unassigned,
  ];
}

function countWorkspaceWarnings(snapshot: TopologyPlanSnapshot, bodies: SystemBody[]): number {
  const buckets = bucketPlacements(snapshot.placements, snapshot.templates, bodies);
  const bodyById = new Map(
    bodies
      .filter((body) => body.id != null)
      .map((body) => [bodyIdKey(body.id), body]),
  );
  const bodyWarnings = Array.from(buckets.knownByBody.entries()).reduce((count, [bodyId, placements]) => {
    const body = bodyById.get(bodyId) ?? null;
    return count + getBodyGroupWarnings({ key: bodyId, body, placements } as BodyGroup).length;
  }, 0);
  return bodyWarnings + buckets.unknown.length + buckets.unassigned.length;
}

function rowClass(selected: boolean, projected = false) {
  return [
    'flex w-full min-w-0 cursor-pointer items-start gap-2 rounded border px-2 py-1.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/70',
    selected
      ? 'border-orange/70 bg-orange/18 shadow-[inset_3px_0_0_rgba(255,122,20,0.9),0_0_18px_rgba(255,125,32,0.12)]'
      : projected
        ? 'border-cyan/45 bg-cyan/6 hover:border-cyan/70 hover:bg-cyan/10 text-silver'
        : 'border-border/55 bg-bg3/35 hover:border-orange/45 hover:bg-orange/8 hover:text-silver',
  ].join(' ');
}

function bodyIcon(body: SystemBody) {
  if (body.body_type === 'Star') return 'S';
  if (body.body_type === 'Planet' && bodyParentId(body)) return 'M';
  if (body.body_type === 'Planet') return 'P';
  return 'B';
}

function compactBodyKind(body: SystemBody) {
  const type = body.body_type ?? 'Body';
  const subtype = body.subtype?.replace(/\bworld\b/i, '').trim();
  const kind = subtype || type;
  const flags = [
    body.is_landable ? 'landable' : null,
    body.is_water_world ? 'water' : null,
    body.is_terraformable ? 'terraformable' : null,
  ].filter(Boolean);
  return flags.length > 0 ? `${kind} / ${flags.slice(0, 1).join(', ')}` : kind;
}

function CountChip({ children }: { children: React.ReactNode }) {
  return <Chip tone="orange">{children}</Chip>;
}

function Marker({
  children,
  tone,
  label,
}: {
  children: React.ReactNode;
  tone: 'gold' | 'silver' | 'cyan';
  label: string;
}) {
  return (
    <span
      title={label}
      aria-label={label}
      className={[
        'grid h-5 w-5 shrink-0 place-items-center rounded border font-mono text-[9px] font-bold',
        tone === 'gold'
          ? 'border-gold/40 bg-gold/10 text-gold'
          : tone === 'cyan'
            ? 'border-cyan/35 bg-cyan/10 text-cyan'
            : 'border-border/60 bg-bg2/60 text-silver',
      ].join(' ')}
    >
      {children}
    </span>
  );
}

function Chip({ children, tone = 'silver' }: { children: React.ReactNode; tone?: 'orange' | 'cyan' | 'green' | 'gold' | 'silver' }) {
  const toneClass = {
    orange: 'border-orange/35 bg-orange/10 text-orange',
    cyan: 'border-cyan/30 bg-cyan/5 text-cyan',
    green: 'border-green/35 bg-green/10 text-green',
    gold: 'border-gold/35 bg-gold/10 text-gold',
    silver: 'border-border/60 bg-bg2/60 text-silver',
  }[tone];
  return (
    <span className={['shrink-0 rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.12em]', toneClass].join(' ')}>
      {children}
    </span>
  );
}
