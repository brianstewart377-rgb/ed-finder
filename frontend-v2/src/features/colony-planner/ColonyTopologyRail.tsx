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
import { rolesForBody, type DeclaredColonyRole } from './colonyRoles';

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
  declaredRoles?: DeclaredColonyRole[];
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
  declaredRoles = [],
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
        aria-pressed={selectedIsSystem}
        className={rowClass(selectedIsSystem)}
      >
        <span className="mt-0.5 shrink-0 text-cyan" aria-hidden="true">SYS</span>
        <div className="min-w-0 flex-1">
          <div className="truncate font-mono text-[11px] font-bold text-silver">
            {system.name || 'Unknown system'}
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-silver-dk">
            System root
          </div>
        </div>
        <Chip tone="cyan">{bodies.length} bodies</Chip>
        {totalPlacements > 0 && <CountChip>{totalPlacements}</CountChip>}
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
              declaredRoles={rolesForBody(declaredRoles, node.id)}
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

      <div className="mt-3 rounded border border-border/45 bg-bg3/30 px-2 py-1.5 font-mono text-[10px] text-silver-dk">
        Click a body to plan there.
      </div>
    </aside>
  );
}

function BodyTreeRow({
  node,
  placements,
  declaredRoles,
  selected,
  selectedPlacementIndex,
  onSelect,
}: {
  node: BodyNode;
  placements: GroupedPlacement[];
  declaredRoles: DeclaredColonyRole[];
  selected: boolean;
  selectedPlacementIndex: number | null;
  onSelect: (selection: TopologySelection) => void;
}) {
  const tags = bodyTags(node.body);
  const sparse = tags.includes('Unknown body data') || (!node.body.body_type && !node.body.subtype);
  const hasPrimary = placements.some((item) => item.placement.is_primary_port);
  const warningCount = getBodyGroupWarnings({ key: node.id, body: node.body, placements }).length;
  const roleCount = declaredRoles.length;

  return (
    <div data-testid={`topology-body-${node.id}`} style={{ marginLeft: `${node.depth * 0.75}rem` }}>
      <button
        type="button"
        onClick={() => onSelect({ type: 'body', bodyId: node.id })}
        aria-pressed={selected}
        className={rowClass(selected)}
      >
        <span className="mt-0.5 w-4 shrink-0 text-center text-[13px] text-cyan" aria-hidden="true">
          {bodyIcon(node.body)}
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate font-mono text-[11px] font-bold text-silver">
            {bodyDisplayName(node.body)}
          </div>
          <div className="mt-0.5 truncate font-mono text-[10px] text-silver-dk">
            {compactBodyKind(node.body)}
          </div>
        </div>
        {placements.length > 0 && <CountChip>{placements.length}</CountChip>}
        {hasPrimary && <Marker tone="gold" label="Primary-port placement">P</Marker>}
        {warningCount > 0 && <Marker tone="gold" label={`${warningCount} warnings`}>!</Marker>}
        {sparse && <Marker tone="silver" label="Sparse body data">?</Marker>}
        {roleCount > 0 && <Marker tone="green" label={`${roleCount} declared roles`}>R</Marker>}
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
  return (
    <div className="rounded border border-gold/25 bg-gold/5 p-1.5">
      <button type="button" onClick={onSelectGroup} aria-pressed={selected} className={rowClass(selected)}>
        <span className="mt-0.5 w-4 shrink-0 text-center text-gold" aria-hidden="true">?</span>
        <div className="min-w-0 flex-1">
          <div className="truncate font-mono text-[11px] text-gold">{title}</div>
          <div className="mt-0.5 truncate font-mono text-[10px] text-silver-dk">{description}</div>
        </div>
        <CountChip>{placements.length}</CountChip>
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
      aria-pressed={selected}
      className={[
        'flex w-full min-w-0 cursor-pointer items-center justify-between gap-2 rounded border px-2 py-1 text-left font-mono text-[10px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/70',
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
      detail: placements.length > 0
        ? 'Body selected. Review or add structures for this body in the central planner.'
        : 'Body selected. Add the first structure for this body in the central planner.',
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
    'flex w-full min-w-0 cursor-pointer items-start gap-2 rounded border px-2 py-1.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/70',
    selected
      ? 'border-orange/70 bg-orange/18 shadow-[inset_3px_0_0_rgba(255,122,20,0.9),0_0_18px_rgba(255,125,32,0.12)]'
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
  tone: 'gold' | 'silver' | 'green';
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
          : tone === 'green'
            ? 'border-green/35 bg-green/10 text-green'
            : 'border-border/60 bg-bg2/60 text-silver-dk',
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
    silver: 'border-border/60 bg-bg2/60 text-silver-dk',
  }[tone];
  return (
    <span className={['shrink-0 rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.12em]', toneClass].join(' ')}>
      {children}
    </span>
  );
}
