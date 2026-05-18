import { AlertTriangle, CircleDot, GitBranch, Orbit, Satellite, Star, Trees } from 'lucide-react';
import type { FacilityTemplate, SimulateBuildPlacement, SystemBody, SystemDetail } from '@/types/api';
import { bodyDisplayName, bodyTags, getPlacementWarnings } from '@/features/system-detail/simulation-preview/buildPlanLayoutUtils';
import { Chip } from '@/features/system-detail/simulation-preview/components';
import { formatLocation } from '@/features/system-detail/simulation-preview/utils/formatters';

export interface TopologySelection {
  kind: 'system' | 'body' | 'placement-group' | 'placement';
  bodyId?: string | null;
  placementIndex?: number;
}

export interface PlannerPlanContext {
  placements: SimulateBuildPlacement[];
  templates: FacilityTemplate[];
}

interface PlacementItem {
  placement: SimulateBuildPlacement;
  index: number;
  template?: FacilityTemplate;
  hasUnknownBody: boolean;
}

interface BodyNode {
  id: string;
  body: SystemBody;
  placements: PlacementItem[];
  children: BodyNode[];
  depth: number;
}

export interface TopologySummary {
  bodyCount: number;
  placementCount: number;
  unassignedCount: number;
  unknownCount: number;
  warningCount: number;
  primaryPortBodyName: string | null;
}

export function ColonyTopologyRail({
  system,
  planContext,
  selection,
  onSelect,
}: {
  system: SystemDetail;
  planContext: PlannerPlanContext;
  selection: TopologySelection;
  onSelect: (selection: TopologySelection) => void;
}) {
  const model = buildTopologyModel(system.bodies ?? [], planContext);
  const summary = model.summary;

  return (
    <aside className="rounded-chunk-lg border border-border/70 bg-bg2/70 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-silver-dk">Topology</div>
          <h3 className="mt-0.5 truncate text-sm font-bold text-silver">System tree</h3>
        </div>
        <GitBranch size={16} className="text-cyan" />
      </div>

      <button
        type="button"
        onClick={() => onSelect({ kind: 'system' })}
        aria-pressed={selection.kind === 'system'}
        className={rowClass(selection.kind === 'system')}
      >
        <span className="grid h-6 w-6 place-items-center rounded border border-orange/35 bg-orange/10 text-orange">
          <Star size={13} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-xs font-bold text-silver">{system.name || 'Unknown system'}</span>
          <span className="mt-0.5 flex flex-wrap gap-1 font-mono text-[9px]">
            <Chip>{summary.bodyCount} bodies</Chip>
            <Chip tone={summary.placementCount > 0 ? 'good' : 'default'}>{summary.placementCount} planned</Chip>
          </span>
        </span>
      </button>

      {model.nodes.length === 0 ? (
        <div className="mt-3 rounded border border-border/60 bg-bg3/35 px-3 py-2 text-[11px] leading-snug text-silver-dk">
          No body layout imported yet. Use the planner tools to import/refresh layout when available.
        </div>
      ) : (
        <div className="mt-3 space-y-1.5">
          {model.nodes.map((node) => (
            <BodyNodeRow
              key={node.id}
              node={node}
              selection={selection}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}

      {(model.unassigned.length > 0 || model.unknown.length > 0) && (
        <div className="mt-3 space-y-1.5 border-t border-border/60 pt-3">
          {model.unknown.length > 0 && (
            <PlacementGroup
              title="Unknown / unmatched body"
              tone="warn"
              placements={model.unknown}
              groupKey="unknown"
              selected={selection.kind === 'placement-group' && selection.bodyId === 'unknown'}
              selection={selection}
              onSelect={onSelect}
            />
          )}
          {model.unassigned.length > 0 && (
            <PlacementGroup
              title="Unassigned placements"
              tone="warn"
              placements={model.unassigned}
              groupKey="unassigned"
              selected={selection.kind === 'placement-group' && selection.bodyId === 'unassigned'}
              selection={selection}
              onSelect={onSelect}
            />
          )}
        </div>
      )}
    </aside>
  );
}

function BodyNodeRow({
  node,
  selection,
  onSelect,
}: {
  node: BodyNode;
  selection: TopologySelection;
  onSelect: (selection: TopologySelection) => void;
}) {
  const selected = selection.kind === 'body' && selection.bodyId === node.id;
  const hasPrimaryPort = node.placements.some((item) => item.placement.is_primary_port);
  const sparseMetadata = bodyTags(node.body).includes('Unknown body data');
  const isUnknown = !node.body.name && !node.body.body_type && !node.body.subtype;
  const surfaceCount = node.placements.filter((item) => placementLocation(item.template) === 'surface').length;
  const orbitalCount = node.placements.filter((item) => placementLocation(item.template) === 'orbital').length;
  const warningCount = node.placements.reduce((count, item) => count + getPlacementWarnings({
    placement: item.placement,
    index: item.index,
    template: item.template,
    bodyId: node.id,
    hasUnknownBody: item.hasUnknownBody,
  }, node.body).length, 0);

  return (
    <div>
      <button
        type="button"
        onClick={() => onSelect({ kind: 'body', bodyId: node.id })}
        aria-pressed={selected}
        data-testid={`topology-body-${node.id}`}
        className={rowClass(selected)}
        style={{ paddingLeft: `${0.5 + node.depth * 0.9}rem` }}
      >
        <span className="grid h-6 w-6 place-items-center rounded border border-cyan/35 bg-cyan/10 text-cyan">
          {node.body.body_type === 'Star' ? <Star size={13} /> : node.depth > 0 ? <Satellite size={13} /> : <CircleDot size={13} />}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5">
            <span className="truncate text-xs font-semibold text-silver">{bodyDisplayName(node.body)}</span>
            {node.children.length > 0 && <span className="font-mono text-[9px] text-silver-dk">{node.children.length}</span>}
          </span>
          <span className="mt-1 flex flex-wrap gap-1 font-mono text-[9px]">
            <Chip tone={node.placements.length > 0 ? 'good' : 'default'}>{node.placements.length} planned</Chip>
            {orbitalCount > 0 && <Chip><Orbit size={10} className="mr-1" />orbital {orbitalCount}</Chip>}
            {surfaceCount > 0 && <Chip><Trees size={10} className="mr-1" />surface {surfaceCount}</Chip>}
            {isUnknown && <Chip tone="warn">unknown body</Chip>}
            {sparseMetadata && <Chip tone="warn">sparse metadata</Chip>}
            {hasPrimaryPort && <Chip tone="good">primary port</Chip>}
            {warningCount > 0 && <Chip tone="warn">{warningCount} warnings</Chip>}
          </span>
        </span>
      </button>
      {node.placements.length > 0 && selected && (
        <div className="ml-7 mt-1 space-y-1 border-l border-border/50 pl-2">
          {node.placements.slice(0, 6).map((item) => (
            <PlacementButton
              key={`${item.index}-${item.placement.facility_template_id}`}
              item={item}
              selected={selection.kind === 'placement' && selection.placementIndex === item.index}
              onSelect={() => onSelect({ kind: 'placement', bodyId: node.id, placementIndex: item.index })}
            />
          ))}
        </div>
      )}
      {node.children.map((child) => (
        <BodyNodeRow key={child.id} node={child} selection={selection} onSelect={onSelect} />
      ))}
    </div>
  );
}

function PlacementGroup({
  title,
  tone,
  placements,
  groupKey,
  selected,
  selection,
  onSelect,
}: {
  title: string;
  tone: 'warn';
  placements: PlacementItem[];
  groupKey: string;
  selected: boolean;
  selection: TopologySelection;
  onSelect: (selection: TopologySelection) => void;
}) {
  return (
    <div>
      <button
        type="button"
        onClick={() => onSelect({ kind: 'placement-group', bodyId: groupKey })}
        aria-pressed={selected}
        className={rowClass(selected, tone)}
      >
        <AlertTriangle size={14} />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-xs font-semibold">{title}</span>
          <span className="mt-1 flex flex-wrap gap-1 font-mono text-[9px]">
            <Chip tone="warn">{placements.length} planned</Chip>
          </span>
        </span>
      </button>
      {selected && (
        <div className="ml-5 mt-1 space-y-1 border-l border-gold/35 pl-2">
          {placements.slice(0, 8).map((item) => (
            <PlacementButton
              key={`${item.index}-${item.placement.facility_template_id}`}
              item={item}
              selected={selection.kind === 'placement' && selection.placementIndex === item.index}
              onSelect={() => onSelect({ kind: 'placement', bodyId: groupKey, placementIndex: item.index })}
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
  item: PlacementItem;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      className={[
        'flex w-full items-center gap-2 rounded border px-2 py-1 text-left font-mono text-[10px] transition',
        selected ? 'border-orange/70 bg-orange/10 text-orange' : 'border-border/50 bg-bg3/35 text-silver-dk hover:border-orange/45',
      ].join(' ')}
      onClick={onSelect}
    >
      <span className="tabular-nums">{item.placement.build_order || item.index + 1}</span>
      <span className="min-w-0 flex-1 truncate">{item.template?.name ?? item.placement.facility_template_id}</span>
      {item.placement.is_primary_port && <span className="text-cyan">port</span>}
    </button>
  );
}

function rowClass(selected: boolean, tone: 'default' | 'warn' = 'default') {
  const base = 'flex w-full items-start gap-2 rounded border px-2 py-2 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan/80';
  if (selected) return `${base} border-cyan/80 bg-cyan/10 shadow-brand-glow`;
  if (tone === 'warn') return `${base} border-gold/35 bg-gold/5 text-gold hover:border-gold/60`;
  return `${base} border-border/55 bg-bg3/35 hover:border-cyan/45`;
}

export function buildTopologyModel(bodies: SystemBody[], planContext: PlannerPlanContext) {
  const templatesById = new Map(planContext.templates.map((template) => [template.id, template]));
  const bodiesWithId = bodies.filter((body) => body.id != null);
  const bodiesById = new Map(bodiesWithId.map((body) => [String(body.id), body]));
  const placementsByBody = new Map<string, PlacementItem[]>();
  const unassigned: PlacementItem[] = [];
  const unknown: PlacementItem[] = [];

  planContext.placements.forEach((placement, index) => {
    const bodyId = placement.local_body_id != null ? String(placement.local_body_id) : '';
    const item: PlacementItem = {
      placement,
      index,
      template: templatesById.get(placement.facility_template_id),
      hasUnknownBody: Boolean(bodyId && !bodiesById.has(bodyId)),
    };
    if (!bodyId) {
      unassigned.push(item);
    } else if (!bodiesById.has(bodyId)) {
      unknown.push(item);
    } else {
      const list = placementsByBody.get(bodyId) ?? [];
      list.push(item);
      placementsByBody.set(bodyId, list);
    }
  });

  const nodeMap = new Map<string, BodyNode>();
  for (const body of bodiesWithId) {
    const id = String(body.id);
    nodeMap.set(id, { id, body, placements: placementsByBody.get(id) ?? [], children: [], depth: 0 });
  }

  const roots: BodyNode[] = [];
  for (const node of nodeMap.values()) {
    const parentId = parentBodyId(node.body);
    const parent = parentId ? nodeMap.get(parentId) : null;
    if (parent) parent.children.push(node);
    else roots.push(node);
  }

  const sortedRoots = roots.sort(bodyNodeSort);
  const assignDepth = (node: BodyNode, depth: number) => {
    node.depth = depth;
    node.children.sort(bodyNodeSort);
    node.children.forEach((child) => assignDepth(child, depth + 1));
  };
  sortedRoots.forEach((node) => assignDepth(node, 0));

  const allNodes = Array.from(nodeMap.values());
  const warningCount = allNodes.reduce((count, node) => (
    count + node.placements.reduce((inner, item) => inner + getPlacementWarnings({
      placement: item.placement,
      index: item.index,
      template: item.template,
      bodyId: node.id,
      hasUnknownBody: item.hasUnknownBody,
    }, node.body).length, 0)
  ), 0) + unassigned.length + unknown.length;
  const primaryPort = planContext.placements.find((placement) => placement.is_primary_port);
  const primaryPortBody = primaryPort?.local_body_id != null ? bodiesById.get(String(primaryPort.local_body_id)) : null;

  const summary: TopologySummary = {
    bodyCount: bodiesWithId.length,
    placementCount: planContext.placements.length,
    unassignedCount: unassigned.length,
    unknownCount: unknown.length,
    warningCount,
    primaryPortBodyName: primaryPortBody ? bodyDisplayName(primaryPortBody) : null,
  };

  return { nodes: sortedRoots, unassigned, unknown, summary };
}

function parentBodyId(body: SystemBody): string | null {
  const raw = body as SystemBody & {
    parent_id?: number | string | null;
    parent_body_id?: number | string | null;
    parentId?: number | string | null;
    parents?: Array<{ id?: number | string | null; body_id?: number | string | null }> | null;
  };
  const parent = raw.parent_id ?? raw.parent_body_id ?? raw.parentId ?? raw.parents?.[0]?.id ?? raw.parents?.[0]?.body_id ?? null;
  return parent == null ? null : String(parent);
}

function bodyNodeSort(a: BodyNode, b: BodyNode) {
  const kindA = bodyKindRank(a.body);
  const kindB = bodyKindRank(b.body);
  if (kindA !== kindB) return kindA - kindB;
  const distanceA = a.body.distance_from_star ?? Number.MAX_SAFE_INTEGER;
  const distanceB = b.body.distance_from_star ?? Number.MAX_SAFE_INTEGER;
  if (distanceA !== distanceB) return distanceA - distanceB;
  return bodyDisplayName(a.body).localeCompare(bodyDisplayName(b.body));
}

function bodyKindRank(body: SystemBody) {
  if (body.body_type === 'Star') return 0;
  if (body.body_type === 'Planet') return 1;
  return 2;
}

function placementLocation(template?: FacilityTemplate): 'surface' | 'orbital' | 'both' | 'unknown' {
  const value = template?.allowed_location?.toLowerCase() ?? '';
  if (value.includes('surface') && value.includes('orbit')) return 'both';
  if (value.includes('surface')) return 'surface';
  if (value.includes('orbit')) return 'orbital';
  return 'unknown';
}

export function selectedTopologyContext({
  system,
  planContext,
  selection,
}: {
  system: SystemDetail;
  planContext: PlannerPlanContext;
  selection: TopologySelection;
}) {
  const model = buildTopologyModel(system.bodies ?? [], planContext);
  const bodiesById = new Map((system.bodies ?? []).filter((body) => body.id != null).map((body) => [String(body.id), body]));
  const templatesById = new Map(planContext.templates.map((template) => [template.id, template]));

  if (selection.kind === 'body' && selection.bodyId) {
    const body = bodiesById.get(selection.bodyId);
    const placements = planContext.placements.filter((placement) => String(placement.local_body_id ?? '') === selection.bodyId);
    return {
      title: body ? bodyDisplayName(body) : 'Unknown / unmatched body',
      subtitle: body ? bodyTags(body).join(' / ') : 'Body reference is not in the imported layout.',
      placementCount: placements.length,
      warningCount: body ? bodyWarningCount(selection.bodyId, body, placements, templatesById) : placements.length,
      primaryPort: placements.some((placement) => placement.is_primary_port),
      technicalDetail: body ? null : 'Hidden body reference is available in the Build Plan editor.',
    };
  }

  if (selection.kind === 'placement' && selection.placementIndex != null) {
    const placement = planContext.placements[selection.placementIndex];
    const template = placement ? templatesById.get(placement.facility_template_id) : null;
    const body = placement?.local_body_id != null ? bodiesById.get(String(placement.local_body_id)) : null;
    return {
      title: template?.name ?? placement?.facility_template_id ?? 'Selected placement',
      subtitle: body ? bodyDisplayName(body) : placement?.local_body_id ? 'Unknown / unmatched body' : 'Unassigned placement',
      placementCount: placement ? 1 : 0,
      warningCount: placement ? getPlacementWarnings({
        placement,
        index: selection.placementIndex,
        template: template ?? undefined,
        bodyId: placement.local_body_id ?? undefined,
        hasUnknownBody: Boolean(placement.local_body_id && !body),
      }, body ?? null).length : 0,
      primaryPort: Boolean(placement?.is_primary_port),
      technicalDetail: template ? formatLocation(template.allowed_location) : null,
    };
  }

  if (selection.kind === 'placement-group' && selection.bodyId === 'unknown') {
    return {
      title: 'Unknown / unmatched body',
      subtitle: 'Placements reference bodies that are not in the imported layout.',
      placementCount: model.unknown.length,
      warningCount: model.unknown.length,
      primaryPort: model.unknown.some((item) => item.placement.is_primary_port),
      technicalDetail: 'Raw body IDs stay in the Build Plan editor.',
    };
  }

  if (selection.kind === 'placement-group' && selection.bodyId === 'unassigned') {
    return {
      title: 'Unassigned placements',
      subtitle: 'These planned structures do not have a body assignment yet.',
      placementCount: model.unassigned.length,
      warningCount: model.unassigned.length,
      primaryPort: model.unassigned.some((item) => item.placement.is_primary_port),
      technicalDetail: null,
    };
  }

  return {
    title: system.name || 'Unknown system',
    subtitle: 'Read-only topology selection',
    placementCount: model.summary.placementCount,
    warningCount: model.summary.warningCount,
    primaryPort: Boolean(model.summary.primaryPortBodyName),
    technicalDetail: model.summary.primaryPortBodyName ? `Primary port: ${model.summary.primaryPortBodyName}` : null,
  };
}

function bodyWarningCount(
  bodyId: string,
  body: SystemBody,
  placements: SimulateBuildPlacement[],
  templatesById: Map<string, FacilityTemplate>,
) {
  return placements.reduce((count, placement, index) => count + getPlacementWarnings({
    placement,
    index,
    template: templatesById.get(placement.facility_template_id),
    bodyId,
    hasUnknownBody: false,
  }, body).length, 0);
}
