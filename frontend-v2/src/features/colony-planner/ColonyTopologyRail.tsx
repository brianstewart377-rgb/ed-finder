import { Network } from 'lucide-react';
import type {
  FacilityTemplate,
  SimulateBuildPlacement,
  SystemBody,
  SystemDetail,
} from '@/types/api';
import {
  bodyDisplayName,
  bodyTags,
  getBodyGroupWarnings,
  getPlacementWarnings,
  type BodyGroup,
  type GroupedPlacement,
} from '@/features/system-detail/simulation-preview/buildPlanLayoutUtils';
import { templateLocationKind } from '@/features/system-detail/simulation-preview/structurePickerUtils';

export type TopologySelection =
  | { type: 'system' }
  | { type: 'body'; bodyId: string }
  | { type: 'placement'; placementIndex: number }
  | { type: 'group'; groupKey: 'unassigned' | 'unknown' };

export interface TopologyPlanSnapshot {
  placements: SimulateBuildPlacement[];
  templates: FacilityTemplate[];
  targetArchetype: string;
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

export function ColonyTopologyRail({
  system,
  snapshot,
  selection,
  onSelect,
}: ColonyTopologyRailProps) {
  const bodies = system.bodies ?? [];
  const bodyNodes = buildBodyNodes(bodies);
  const buckets = bucketPlacements(snapshot.placements, snapshot.templates, bodies);
  const totalPlacements = snapshot.placements.length;
  const selectedIsSystem = selection.type === 'system';

  return (
    <aside
      aria-label="Topology body tree"
      data-testid="planner-topology-sidebar"
      className="panel p-3 xl:sticky xl:top-4 xl:max-h-[calc(100vh-14rem)] xl:overflow-y-auto"
    >
      <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">
        <Network size={13} />
        System topology
      </div>

      <button
        type="button"
        onClick={() => onSelect({ type: 'system' })}
        data-testid="topology-root-row"
        className={rowClass(selectedIsSystem)}
      >
        <div className="min-w-0 flex-1">
          <div className="truncate font-mono text-[11px] text-silver">
            {system.name || 'Unknown system'}
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-silver-dk">
            Root system context
          </div>
        </div>
        <Chip tone="cyan">{bodies.length} bodies</Chip>
        {totalPlacements > 0 && <Chip tone="orange">{totalPlacements} planned</Chip>}
      </button>

      {bodies.length === 0 ? (
        <p className="mt-3 rounded border border-border/45 bg-bg2/45 px-2 py-2 font-mono text-[10px] leading-snug text-silver-dk">
          No body layout imported yet. Use the planner tools to import/refresh layout when available.
        </p>
      ) : (
        <div className="mt-3 space-y-1.5" data-testid="topology-body-tree">
          {bodyNodes.map((node) => (
            <BodyTreeRow
              key={node.id}
              node={node}
              placements={buckets.knownByBody.get(node.id) ?? []}
              selected={selection.type === 'body' && selection.bodyId === node.id}
              selectedPlacementIndex={selection.type === 'placement' ? selection.placementIndex : null}
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

      <div className="mt-3 rounded border border-gold/30 bg-gold/5 px-2 py-2 font-mono text-[10px] leading-snug text-silver-dk">
        <span className="text-gold">Architect:</span> primary-port flag not recorded in this workspace yet.
      </div>
    </aside>
  );
}

function BodyTreeRow({
  node,
  placements,
  selected,
  selectedPlacementIndex,
  onSelect,
}: {
  node: BodyNode;
  placements: GroupedPlacement[];
  selected: boolean;
  selectedPlacementIndex: number | null;
  onSelect: (selection: TopologySelection) => void;
}) {
  const tags = bodyTags(node.body);
  const sparse = tags.includes('Unknown body data') || (!node.body.body_type && !node.body.subtype);
  const hasPrimary = placements.some((item) => item.placement.is_primary_port);
  const locationCounts = countPlacementLocations(placements);

  return (
    <div data-testid={`topology-body-${node.id}`} style={{ marginLeft: `${node.depth * 0.75}rem` }}>
      <button
        type="button"
        onClick={() => onSelect({ type: 'body', bodyId: node.id })}
        className={rowClass(selected)}
      >
        <div className="min-w-0 flex-1">
          <div className="truncate font-mono text-[11px] text-silver">
            {bodyDisplayName(node.body)}
          </div>
          <div className="mt-0.5 truncate font-mono text-[10px] text-silver-dk">
            {node.body.subtype ?? node.body.body_type ?? 'Sparse body data'}
          </div>
        </div>
        {placements.length > 0 && <Chip tone="orange">{placements.length} planned</Chip>}
        {locationCounts.orbital > 0 && <Chip tone="cyan">{locationCounts.orbital} orbital</Chip>}
        {locationCounts.surface > 0 && <Chip tone="green">{locationCounts.surface} surface</Chip>}
        {locationCounts.flex > 0 && <Chip tone="silver">{locationCounts.flex} flex</Chip>}
        {hasPrimary && <Chip tone="gold">primary</Chip>}
        {sparse && <Chip tone="silver">sparse</Chip>}
      </button>
      {placements.length > 0 && (
        <div className="ml-3 mt-1 space-y-1 border-l border-border/50 pl-2">
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
  const locationCounts = countPlacementLocations(placements);

  return (
    <div className="rounded border border-gold/25 bg-gold/5 p-1.5">
      <button type="button" onClick={onSelectGroup} className={rowClass(selected)}>
        <div className="min-w-0 flex-1">
          <div className="truncate font-mono text-[11px] text-gold">{title}</div>
          <div className="mt-0.5 truncate font-mono text-[10px] text-silver-dk">{description}</div>
        </div>
        <Chip tone="orange">{placements.length} planned</Chip>
        {locationCounts.orbital > 0 && <Chip tone="cyan">{locationCounts.orbital} orbital</Chip>}
        {locationCounts.surface > 0 && <Chip tone="green">{locationCounts.surface} surface</Chip>}
      </button>
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
      className={[
        'flex w-full min-w-0 items-center justify-between gap-2 rounded border px-2 py-1 text-left font-mono text-[10px] transition-colors',
        selected
          ? 'border-orange/55 bg-orange/15 text-orange'
          : 'border-border/45 bg-bg2/45 text-silver-dk hover:border-orange/35 hover:text-silver',
      ].join(' ')}
    >
      <span className="min-w-0 truncate">#{item.placement.build_order} {label}</span>
      {item.placement.is_primary_port && <span className="shrink-0 text-gold">primary</span>}
    </button>
  );
}

export function describeTopologySelection(
  selection: TopologySelection,
  system: SystemDetail,
  snapshot: TopologyPlanSnapshot,
): TopologySelectionContext {
  const bodies = system.bodies ?? [];
  const buckets = bucketPlacements(snapshot.placements, snapshot.templates, bodies);
  const bodyById = new Map(
    bodies
      .filter((body) => body.id != null)
      .map((body) => [String(body.id), body]),
  );

  if (selection.type === 'body') {
    const body = bodyById.get(selection.bodyId);
    const placements = buckets.knownByBody.get(selection.bodyId) ?? [];
    const warnings = body ? getBodyGroupWarnings({ key: selection.bodyId, body, placements }) : [];
    return {
      label: body ? bodyDisplayName(body) : 'Unknown body',
      kind: body?.subtype ?? body?.body_type ?? 'Body',
      placementCount: placements.length,
      warningCount: warnings.length,
      architectStatus: 'Architect flag not recorded',
      detail: 'Read-only topology selection. Build Plan editing stays in the central planner.',
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
    detail: 'Read-only topology selection. Select a body or placement for local context.',
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
      .map((body) => String(body.id)),
  );
  const knownByBody = new Map<string, GroupedPlacement[]>();
  const unknown: GroupedPlacement[] = [];
  const unassigned: GroupedPlacement[] = [];

  placements.forEach((placement, index) => {
    const bodyId = placement.local_body_id != null ? String(placement.local_body_id) : '';
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

function buildBodyNodes(bodies: SystemBody[]): BodyNode[] {
  const withIds = bodies
    .filter((body) => body.id != null)
    .map((body) => ({ body, id: String(body.id) }));
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
  if (typeof raw === 'number' || typeof raw === 'string') return String(raw);
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

function countPlacementLocations(placements: GroupedPlacement[]) {
  return placements.reduce((counts, item) => {
    const kind = item.template ? templateLocationKind(item.template) : 'unknown';
    if (kind === 'orbital') counts.orbital += 1;
    else if (kind === 'surface') counts.surface += 1;
    else if (kind === 'both') counts.flex += 1;
    else counts.unknown += 1;
    return counts;
  }, { orbital: 0, surface: 0, flex: 0, unknown: 0 });
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
      .map((body) => [String(body.id), body]),
  );
  const bodyWarnings = Array.from(buckets.knownByBody.entries()).reduce((count, [bodyId, placements]) => {
    const body = bodyById.get(bodyId) ?? null;
    return count + getBodyGroupWarnings({ key: bodyId, body, placements } as BodyGroup).length;
  }, 0);
  return bodyWarnings + buckets.unknown.length + buckets.unassigned.length;
}

function rowClass(selected: boolean) {
  return [
    'flex w-full min-w-0 items-start gap-2 rounded border px-2 py-2 text-left transition-colors',
    selected
      ? 'border-orange/60 bg-orange/15 shadow-[0_0_18px_rgba(255,125,32,0.12)]'
      : 'border-border/55 bg-bg3/35 hover:border-orange/35 hover:bg-orange/5',
  ].join(' ');
}

function Chip({ children, tone = 'silver' }: { children: React.ReactNode; tone?: 'orange' | 'cyan' | 'green' | 'gold' | 'silver' }) {
  const toneClass = {
    orange: 'border-orange/35 bg-orange/10 text-orange',
    cyan: 'border-cyan/30 bg-cyan/5 text-cyan',
    green: 'border-green/35 bg-green/10 text-green',
    gold: 'border-gold/35 bg-gold/10 text-gold',
    silver: 'border-border/60 bg-bg2/60 text-silver-dk',
  }[tone];
  return (
    <span className={['shrink-0 rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.12em]', toneClass].join(' ')}>
      {children}
    </span>
  );
}
