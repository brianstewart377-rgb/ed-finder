import type { ClusterResult } from '@/features/cluster-search/useClusterSearch';
import type { WatchlistEntry } from '@/lib/api';
import type { PinnedEntry } from '@/store/pinnedStore';
import type { EvidenceSystemSummaryResponse, SystemDetail, SystemResult } from '@/types/api';
import {
  reduceReturnWorkflow,
  type BoundedResponseMetadata,
  type ClusterRepresentation,
  type HighlightSet,
  type MapInteractionEvent,
  type MapLayerState,
  type MapReturnWorkflow,
  type MapSceneState,
  type SystemRecord,
} from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';

export type CoordinateBearingSystem = SystemResult | SystemDetail | PinnedEntry | WatchlistEntry;

export type EvidenceMapEntry = {
  summary: EvidenceSystemSummaryResponse;
  system: CoordinateBearingSystem;
};

export type FeatureHandoff =
  | { type: 'finder'; systems: SystemResult[]; selectedSystemId64?: number | null; metadata?: Partial<BoundedResponseMetadata> }
  | { type: 'compare'; systems: SystemResult[]; leftId64: number; rightId64: number }
  | { type: 'savedSystems'; systems: Array<PinnedEntry | WatchlistEntry> }
  | { type: 'evidenceMap'; entries: EvidenceMapEntry[] }
  | { type: 'systemDetail'; system: SystemDetail }
  | { type: 'clusterSearch'; cluster: ClusterResult; systemsById: ReadonlyMap<number, CoordinateBearingSystem> }
  | {
      type: 'planner';
      systems?: CoordinateBearingSystem[];
      highlights: HighlightSet[];
      layers: MapLayerState;
      clusters: ClusterRepresentation[];
      workflowPayload: Record<string, unknown>;
    };

export type FeatureHandoffResult = {
  scene: MapSceneState;
  acceptedSystemIds: number[];
  omittedSystemIds: number[];
};

export type MapHostCommand =
  | { type: 'none' }
  | { type: 'selectSystem'; systemId64: number; clusterAnchorId64: number | null }
  | { type: 'clearSelectedSystem' }
  | { type: 'openMap' }
  | { type: 'openFinder' }
  | { type: 'openSystemDetail'; systemId64: number }
  | { type: 'openCompare'; leftId64: number; rightId64: number }
  | { type: 'openSavedSystems' }
  | { type: 'openEvidenceMap' }
  | { type: 'openClusterSearch'; clusterId: string }
  | { type: 'openPlanner'; systemId64: number }
  | { type: 'plannerSelectionRequired' };

export type MapInteractionResolution = {
  scene: MapSceneState;
  command: MapHostCommand;
};

function finite(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function identity(system: CoordinateBearingSystem): { id64: number; name: string } {
  const value = system as { id64?: unknown; system_id64?: unknown; name?: unknown };
  return {
    id64: finite(value.system_id64) ? value.system_id64 : finite(value.id64) ? value.id64 : Number.NaN,
    name: typeof value.name === 'string' ? value.name : '',
  };
}

export function toSystemRecord(system: CoordinateBearingSystem): SystemRecord | null {
  const { id64, name } = identity(system);
  const value = system as {
    coords?: { x?: unknown; z?: unknown } | null;
    x?: unknown;
    z?: unknown;
    overall_development_potential?: unknown;
    archetype_score?: unknown;
    score?: unknown;
    primaryEconomy?: unknown;
    primary_economy?: unknown;
    economy?: unknown;
    economy_suggestion?: unknown;
    population?: unknown;
  };
  const coords = value.coords ?? value;
  if (!Number.isFinite(id64) || id64 <= 0 || !finite(coords.x) || !finite(coords.z)) return null;
  const scoreCandidates = [value.overall_development_potential, value.archetype_score, value.score];
  const economyCandidates = [value.primaryEconomy, value.primary_economy, value.economy, value.economy_suggestion];
  const developmentScore = scoreCandidates.find(finite) ?? null;
  const primaryEconomy = economyCandidates.find((candidate): candidate is string => typeof candidate === 'string') ?? null;

  return {
    id64,
    name: name || `System ${id64}`,
    coords: { x: coords.x, z: coords.z },
    developmentScore,
    primaryEconomy,
    population: finite(value.population) ? value.population : null,
  };
}

function collectSystems(systems: CoordinateBearingSystem[]): {
  records: SystemRecord[];
  acceptedSystemIds: number[];
  omittedSystemIds: number[];
} {
  const records = new Map<number, SystemRecord>();
  const omitted = new Set<number>();
  for (const system of systems) {
    const { id64 } = identity(system);
    const record = toSystemRecord(system);
    if (record) records.set(record.id64, record);
    else if (Number.isFinite(id64) && id64 > 0) omitted.add(id64);
  }
  return {
    records: [...records.values()],
    acceptedSystemIds: [...records.keys()],
    omittedSystemIds: [...omitted].filter((id64) => !records.has(id64)),
  };
}

function mergeSystems(current: SystemRecord[], additions: SystemRecord[]): SystemRecord[] {
  const byId = new Map(current.map((system) => [system.id64, system]));
  additions.forEach((system) => byId.set(system.id64, system));
  return [...byId.values()];
}

function clusterMembers(cluster: ClusterResult): number[] {
  const ids = new Set<number>([cluster.anchor_id64]);
  cluster.slots?.forEach((slot) => slot.matches.forEach((match) => ids.add(match.system_id64)));
  return [...ids];
}

function toClusterRepresentation(cluster: ClusterResult, acceptedIds: Set<number>): ClusterRepresentation {
  const memberIds = clusterMembers(cluster).filter((id64) => acceptedIds.has(id64));
  const anchorId64 = acceptedIds.has(cluster.anchor_id64) ? cluster.anchor_id64 : memberIds[0] ?? cluster.anchor_id64;
  return {
    anchorId64,
    memberIds,
    memberRoles: Object.fromEntries(memberIds.map((id64) => [id64, [id64 === anchorId64 ? 'anchor' : 'member']])),
    edges: memberIds.filter((id64) => id64 !== anchorId64).map((id64) => ({ fromId64: anchorId64, toId64: id64 })),
    radiusLy: cluster.cluster_radius_ly,
    hull: null,
    label: cluster.anchor_name,
    groupContext: {
      name: cluster.anchor_name,
      description: `${cluster.total_viable} viable systems · ${cluster.economy_diversity} economy groups`,
    },
  };
}

export function applyFeatureHandoff(scene: MapSceneState, handoff: FeatureHandoff): FeatureHandoffResult {
  let sources: CoordinateBearingSystem[];
  if (handoff.type === 'evidenceMap') {
    sources = handoff.entries
      .filter((entry) => identity(entry.system).id64 === entry.summary.system_id64)
      .map((entry) => entry.system);
  }
  else if (handoff.type === 'clusterSearch') {
    sources = clusterMembers(handoff.cluster)
      .map((id64) => handoff.systemsById.get(id64))
      .filter((system): system is CoordinateBearingSystem => system !== undefined);
    if (handoff.cluster.anchor_coords && !handoff.systemsById.has(handoff.cluster.anchor_id64)) {
      sources.push({
        id64: handoff.cluster.anchor_id64,
        name: handoff.cluster.anchor_name,
        coords: handoff.cluster.anchor_coords,
      } as SystemResult);
    }
  } else if (handoff.type === 'planner') sources = handoff.systems ?? [];
  else if (handoff.type === 'systemDetail') sources = [handoff.system];
  else sources = handoff.systems;

  const collected = collectSystems(sources);
  const expectedIds = handoff.type === 'clusterSearch'
    ? clusterMembers(handoff.cluster)
    : handoff.type === 'evidenceMap'
      ? handoff.entries.map((entry) => entry.summary.system_id64)
      : [];
  const missingIds = expectedIds.filter((id64) => !collected.acceptedSystemIds.includes(id64));
  const omittedSystemIds = [...new Set([...collected.omittedSystemIds, ...missingIds])];
  const withSystems: MapSceneState = {
    ...scene,
    sceneRevision: scene.sceneRevision + 1,
    systems: mergeSystems(scene.systems, collected.records),
    highlights: [...scene.highlights],
    clusters: [...scene.clusters],
    layers: [...scene.layers],
    guaranteedSystemIds: [...scene.guaranteedSystemIds],
    boundedResponse: {
      count: handoff.type === 'finder'
        ? handoff.metadata?.count ?? handoff.systems.length
        : collected.records.length,
      truncated: handoff.type === 'finder' ? handoff.metadata?.truncated ?? false : omittedSystemIds.length > 0,
      continuationToken: handoff.type === 'finder' ? handoff.metadata?.continuationToken ?? null : null,
    },
  };
  const camera = scene.camera;
  const origin = scene.origin;
  let workflow: MapReturnWorkflow;

  switch (handoff.type) {
    case 'finder':
      workflow = { type: 'finder', camera, origin };
      break;
    case 'compare':
      workflow = { type: 'compare', leftId64: handoff.leftId64, rightId64: handoff.rightId64, camera, origin };
      break;
    case 'savedSystems':
      workflow = { type: 'savedSystems', highlightedIds: collected.acceptedSystemIds, camera, origin };
      break;
    case 'evidenceMap':
      workflow = { type: 'evidenceMap', highlightedIds: collected.acceptedSystemIds, camera, origin };
      break;
    case 'systemDetail':
      workflow = { type: 'systemDetail', systemId64: handoff.system.id64, camera, origin };
      break;
    case 'clusterSearch':
      workflow = {
        type: 'clusterSearch',
        cluster: toClusterRepresentation(handoff.cluster, new Set(collected.acceptedSystemIds)),
        camera,
        origin,
      };
      break;
    case 'planner':
      workflow = {
        type: 'planner', camera, origin, highlights: handoff.highlights, layers: handoff.layers,
        clusters: handoff.clusters, workflowDiscriminator: 'planner', workflowPayload: handoff.workflowPayload,
      };
      break;
  }

  const next = reduceReturnWorkflow(withSystems, workflow);
  if (handoff.type === 'finder' && handoff.selectedSystemId64) {
    next.selectedSystemId64 = handoff.selectedSystemId64;
    next.guaranteedSystemIds = [...new Set([...next.guaranteedSystemIds, handoff.selectedSystemId64])];
  }
  return {
    scene: next,
    acceptedSystemIds: collected.acceptedSystemIds,
    omittedSystemIds,
  };
}

export function resolveMapInteraction(scene: MapSceneState, event: MapInteractionEvent): MapInteractionResolution {
  switch (event.type) {
    case 'selectSystem':
    case 'overlapChoice':
      return {
        scene: { ...scene, selectedSystemId64: event.systemId64 },
        command: { type: 'selectSystem', systemId64: event.systemId64, clusterAnchorId64: event.clusterAnchorId64 },
      };
    case 'deselectSystem':
      return { scene: { ...scene, selectedSystemId64: null }, command: { type: 'clearSelectedSystem' } };
    case 'cameraChanged':
      return { scene: { ...scene, camera: event.camera, cameraIntent: 'user' }, command: { type: 'none' } };
    case 'layerChanged':
      return { scene: { ...scene, layers: event.layers }, command: { type: 'none' } };
    case 'navigateToMap': return { scene, command: { type: 'openMap' } };
    case 'navigateToFinder': return { scene, command: { type: 'openFinder' } };
    case 'navigateToSystemDetail': return { scene, command: { type: 'openSystemDetail', systemId64: event.systemId64 } };
    case 'navigateToCompare': return { scene, command: { type: 'openCompare', leftId64: event.leftId64, rightId64: event.rightId64 } };
    case 'navigateToSavedSystems': return { scene, command: { type: 'openSavedSystems' } };
    case 'navigateToEvidenceMap': return { scene, command: { type: 'openEvidenceMap' } };
    case 'navigateToClusterSearch': return { scene, command: { type: 'openClusterSearch', clusterId: event.clusterId } };
    case 'navigateToPlanner':
      return {
        scene,
        command: scene.selectedSystemId64
          ? { type: 'openPlanner', systemId64: scene.selectedSystemId64 }
          : { type: 'plannerSelectionRequired' },
      };
    default:
      return { scene, command: { type: 'none' } };
  }
}
