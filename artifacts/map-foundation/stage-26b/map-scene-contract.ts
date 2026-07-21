// === Map Scene Contract ===
// ED‑Finder Stage 26B — Renderer‑independent typed map scene, camera, return‑workflow,
// systems, clusters, highlights, routes, annotations, layers, keyboard companion,
// bounded response, interior label point, feature handoff matrix, scene reducer,
// and keyboard‑companion reducer.
// All types are JSON‑safe (no callbacks, no runtime objects).

export type GalaxyCoord = { x: number; z: number };
export type CameraState = {
  center: GalaxyCoord;
  zoom: number;           // LY per pixel at the map centre
  pitchDeg: number;       // 0 = top‑down; positive tilts toward horizon
  bearingDeg: number;     // 0 = galactic north up
};

export type MapCameraIntent = 'user' | 'autoFit' | 'returnFromWorkflow';
export type MapOneTimeFitIntent = {
  enabled: boolean;
  center: GalaxyCoord;
  zoom: number;
} | null;

export type SceneRevision = number; // monotonically increasing

export type SystemRecord = {
  id64: number;
  name: string;
  coords: GalaxyCoord;     // must be non‑null for renderability
  developmentScore: number | null;
  primaryEconomy: string | null;
  population: number | null;
};

export type ClusterRole = 'anchor' | 'member' | 'edge';
export type ClusterEdge = { fromId64: number; toId64: number };
export type ClusterRepresentation = {
  anchorId64: number;
  memberIds: number[];
  memberRoles: Record<number, ClusterRole[]>;
  edges: ClusterEdge[];
  radiusLy: number;
  hull: GalaxyCoord[] | null;   // convex hull vertices, or null if radius suffices
  label: string;
  groupContext: { name: string; description: string } | null;
};

export type HighlightSet =
  | { type: 'compare'; leftId64: number; rightId64: number }
  | { type: 'cluster'; cluster: ClusterRepresentation };

export type Route = {
  id: string;
  waypoints: { systemId64: number; label?: string }[];
  color: string;
};

export type Annotation = {
  id: string;
  text: string;
  position: GalaxyCoord;
};

export type MapLayer =
  | { type: 'regions'; visible: boolean }
  | { type: 'heatmap'; visible: boolean; economy?: string | null }
  | { type: 'timeline'; visible: boolean; bucket?: 'day' | 'week' | 'month' | 'quarter' | 'year' }
  | { type: 'routes'; visible: boolean }
  | { type: 'annotations'; visible: boolean };

export type MapLayerState = MapLayer[];

export type SelectedSystemDetailOverride = {
  systemId64: number;
  tier: 'full' | 'simplified' | 'dot';
} | null;

// ── Keyboard Companion ──
export type KeyboardCompanionPhase =
  | { type: 'idle' }
  | { type: 'systemTraversal'; candidateIds: number[]; focusedIndex: number }
  | { type: 'overlayToggle'; availableLayers: MapLayer[]; focusedIndex: number }
  | { type: 'searchResultTraversal'; candidateIds: number[]; focusedIndex: number }
  | { type: 'overlapCycling'; candidates: { systemId64: number; distancePx: number }[]; focusedIndex: number };

export type KeyboardCompanionState = {
  phase: KeyboardCompanionPhase;
};

// Initialization functions for each keyboard phase.
export function initSystemTraversal(ids: number[]): KeyboardCompanionPhase {
  return ids.length > 0 ? { type: 'systemTraversal', candidateIds: ids, focusedIndex: 0 } : { type: 'idle' };
}
export function initOverlayToggle(layers: MapLayer[]): KeyboardCompanionPhase {
  return layers.length > 0 ? { type: 'overlayToggle', availableLayers: layers, focusedIndex: 0 } : { type: 'idle' };
}
export function initSearchResultTraversal(ids: number[]): KeyboardCompanionPhase {
  return ids.length > 0 ? { type: 'searchResultTraversal', candidateIds: ids, focusedIndex: 0 } : { type: 'idle' };
}
export function initOverlapCycling(candidates: { systemId64: number; distancePx: number }[]): KeyboardCompanionPhase {
  const sorted = [...candidates].sort((a, b) => a.distancePx - b.distancePx || a.systemId64 - b.systemId64);
  return sorted.length > 0 ? { type: 'overlapCycling', candidates: sorted, focusedIndex: 0 } : { type: 'idle' };
}

// Keyboard Companion Reducer — processes key events and returns new KeyboardCompanionState + side effects.
export type KeyboardSideEffect =
  | { type: 'selectSystem'; systemId64: number }
  | { type: 'toggleLayer'; layerType: MapLayer['type'] }
  | { type: 'none' };

export function reduceKeyboardCompanion(
  state: KeyboardCompanionState,
  key: string,
  _context: { systems: SystemRecord[]; layers: MapLayerState }
): { nextState: KeyboardCompanionState; effect: KeyboardSideEffect } {
  const { phase } = state;

  if (phase.type === 'idle') {
    return { nextState: state, effect: { type: 'none' } };
  }

  const nextFocus = (length: number, current: number, reverse: boolean): number =>
    length === 0 ? current : reverse ? (current - 1 + length) % length : (current + 1) % length;

  const idle = (): KeyboardCompanionState => ({ phase: { type: 'idle' } });

  switch (phase.type) {
    case 'systemTraversal': {
      const len = phase.candidateIds.length;
      if (len === 0) return { nextState: idle(), effect: { type: 'none' } };
      const idx = phase.focusedIndex;
      if (key === 'ArrowDown' || key === 'Tab') {
        const newIdx = nextFocus(len, idx, false);
        return {
          nextState: { phase: { type: 'systemTraversal', candidateIds: phase.candidateIds, focusedIndex: newIdx } },
          effect: { type: 'none' },
        };
      }
      if (key === 'ArrowUp' || key === 'Shift+Tab') {
        const newIdx = nextFocus(len, idx, true);
        return {
          nextState: { phase: { type: 'systemTraversal', candidateIds: phase.candidateIds, focusedIndex: newIdx } },
          effect: { type: 'none' },
        };
      }
      if (key === 'Enter') {
        const id = phase.candidateIds[idx];
        if (id === undefined) return { nextState: idle(), effect: { type: 'none' } };
        return { nextState: idle(), effect: { type: 'selectSystem', systemId64: id } };
      }
      if (key === 'Escape') return { nextState: idle(), effect: { type: 'none' } };
      break;
    }
    case 'overlayToggle': {
      const len = phase.availableLayers.length;
      if (len === 0) return { nextState: idle(), effect: { type: 'none' } };
      const idx = phase.focusedIndex;
      if (key === 'ArrowDown' || key === 'Tab') {
        const newIdx = nextFocus(len, idx, false);
        return {
          nextState: { phase: { type: 'overlayToggle', availableLayers: phase.availableLayers, focusedIndex: newIdx } },
          effect: { type: 'none' },
        };
      }
      if (key === 'ArrowUp' || key === 'Shift+Tab') {
        const newIdx = nextFocus(len, idx, true);
        return {
          nextState: { phase: { type: 'overlayToggle', availableLayers: phase.availableLayers, focusedIndex: newIdx } },
          effect: { type: 'none' },
        };
      }
      if (key === 'Enter') {
        const layer = phase.availableLayers[idx];
        if (layer === undefined) return { nextState: idle(), effect: { type: 'none' } };
        return { nextState: idle(), effect: { type: 'toggleLayer', layerType: layer.type } };
      }
      if (key === 'Escape') return { nextState: idle(), effect: { type: 'none' } };
      break;
    }
    case 'searchResultTraversal': {
      const len = phase.candidateIds.length;
      if (len === 0) return { nextState: idle(), effect: { type: 'none' } };
      const idx = phase.focusedIndex;
      if (key === 'ArrowDown' || key === 'Tab') {
        const newIdx = nextFocus(len, idx, false);
        return {
          nextState: { phase: { type: 'searchResultTraversal', candidateIds: phase.candidateIds, focusedIndex: newIdx } },
          effect: { type: 'none' },
        };
      }
      if (key === 'ArrowUp' || key === 'Shift+Tab') {
        const newIdx = nextFocus(len, idx, true);
        return {
          nextState: { phase: { type: 'searchResultTraversal', candidateIds: phase.candidateIds, focusedIndex: newIdx } },
          effect: { type: 'none' },
        };
      }
      if (key === 'Enter') {
        const id = phase.candidateIds[idx];
        if (id === undefined) return { nextState: idle(), effect: { type: 'none' } };
        return { nextState: idle(), effect: { type: 'selectSystem', systemId64: id } };
      }
      if (key === 'Escape') return { nextState: idle(), effect: { type: 'none' } };
      break;
    }
    case 'overlapCycling': {
      const len = phase.candidates.length;
      if (len === 0) return { nextState: idle(), effect: { type: 'none' } };
      const idx = phase.focusedIndex;
      if (key === 'Tab') {
        const newIdx = nextFocus(len, idx, false);
        return {
          nextState: { phase: { type: 'overlapCycling', candidates: phase.candidates, focusedIndex: newIdx } },
          effect: { type: 'none' },
        };
      }
      if (key === 'Shift+Tab') {
        const newIdx = nextFocus(len, idx, true);
        return {
          nextState: { phase: { type: 'overlapCycling', candidates: phase.candidates, focusedIndex: newIdx } },
          effect: { type: 'none' },
        };
      }
      if (key === 'Enter') {
        const cand = phase.candidates[idx];
        if (cand === undefined) return { nextState: idle(), effect: { type: 'none' } };
        return { nextState: idle(), effect: { type: 'selectSystem', systemId64: cand.systemId64 } };
      }
      if (key === 'Escape') return { nextState: idle(), effect: { type: 'none' } };
      break;
    }
  }
  return { nextState: state, effect: { type: 'none' } };
}

// ── Interior Label Point ──
export function computeInteriorLabelPoint(
  regionId: number,
  regionMapRows: Array<Array<[number, number]>>,
  origin: GalaxyCoord,
  pixelScalePxPerLy: number
): GalaxyCoord | null {
  if (regionId < 1 || regionId > 42) return null;
  let sumPx = 0, sumPz = 0, count = 0;
  for (let pz = 0; pz < regionMapRows.length; pz++) {
    let px = 0;
    for (const [runLength, rId] of regionMapRows[pz]!) {
      if (rId === regionId) {
        for (let i = 0; i < runLength; i++) {
          sumPx += px + i;
          sumPz += pz;
          count++;
        }
      }
      px += runLength;
    }
  }
  if (count === 0) return null;
  const meanPx = sumPx / count;
  const meanPz = sumPz / count;
  const x = origin.x + meanPx / pixelScalePxPerLy;
  const z = origin.z + meanPz / pixelScalePxPerLy;
  return { x, z };
}

export const AUTHORITATIVE_PIXEL_SCALE_PX_PER_LY = 83 / 4096; // 0.020263671875

// ── Map Scene State ──
export type MapSceneState = {
  sceneRevision: SceneRevision;
  oneTimeFitIntent: MapOneTimeFitIntent;
  cameraIntent: MapCameraIntent;
  camera: CameraState;
  origin: GalaxyCoord;
  systems: SystemRecord[];
  selectedSystemId64: number | null;
  selectedDetailOverride: SelectedSystemDetailOverride;
  highlights: HighlightSet[];               // array for simultaneous independent groups
  clusters: ClusterRepresentation[];
  routes: Route[];
  annotations: Annotation[];
  layers: MapLayerState;
  returnWorkflow: MapReturnWorkflow | null;
  keyboardCompanion: KeyboardCompanionState;
  boundedResponse: BoundedResponseMetadata;
  guaranteedSystemIds: number[];
};

export type BoundedResponseMetadata = {
  count: number;
  truncated: boolean;
  continuationToken: string | null;
};

export type BoundedResponse<T> = {
  data: T[];
  metadata: BoundedResponseMetadata;
};

// ── Outbound Interaction Events ──
export type MapInteractionEvent =
  | { type: 'navigateToMap' }
  | { type: 'navigateToFinder' }
  | { type: 'navigateToSystemDetail'; systemId64: number }
  | { type: 'navigateToCompare'; leftId64: number; rightId64: number }
  | { type: 'navigateToSavedSystems' }
  | { type: 'navigateToEvidenceMap' }
  | { type: 'navigateToClusterSearch'; clusterId: string }
  | { type: 'navigateToPlanner' };

// ── Inbound Return Workflow ──
export type MapReturnWorkflow =
  | { type: 'map'; camera: CameraState; origin: GalaxyCoord; layers: MapLayerState }
  | { type: 'finder'; camera: CameraState; origin: GalaxyCoord }
  | { type: 'systemDetail'; systemId64: number; camera: CameraState; origin: GalaxyCoord }
  | { type: 'compare'; leftId64: number; rightId64: number; camera: CameraState; origin: GalaxyCoord }
  | { type: 'savedSystems'; highlightedIds: number[]; camera: CameraState; origin: GalaxyCoord }
  | { type: 'evidenceMap'; highlightedIds: number[]; camera: CameraState; origin: GalaxyCoord }
  | { type: 'clusterSearch'; cluster: ClusterRepresentation; camera: CameraState; origin: GalaxyCoord }
  | { type: 'planner'; camera: CameraState; origin: GalaxyCoord; highlights: HighlightSet[]; layers: MapLayerState; clusters: ClusterRepresentation[]; workflowDiscriminator: 'planner'; workflowPayload: Record<string, unknown> };

// ── Workflow Return Reducer ──
export function reduceReturnWorkflow(
  state: MapSceneState,
  workflow: MapReturnWorkflow
): MapSceneState {
  const base = { ...state };

  base.camera = workflow.camera;
  base.origin = workflow.origin;
  base.cameraIntent = 'returnFromWorkflow';
  base.keyboardCompanion = { phase: { type: 'idle' } };

  switch (workflow.type) {
    case 'map':
      base.layers = workflow.layers;
      break;
    case 'finder':
      break;
    case 'systemDetail':
      base.selectedSystemId64 = workflow.systemId64;
      base.guaranteedSystemIds = includeId(base.guaranteedSystemIds, workflow.systemId64);
      break;
    case 'compare':
      base.highlights = [{ type: 'compare', leftId64: workflow.leftId64, rightId64: workflow.rightId64 }];
      base.guaranteedSystemIds = includeIds(base.guaranteedSystemIds, [workflow.leftId64, workflow.rightId64]);
      break;
    case 'savedSystems':
    case 'evidenceMap': {
      const clusterHighlight: HighlightSet = {
        type: 'cluster',
        cluster: {
          anchorId64: workflow.highlightedIds[0] ?? -1,
          memberIds: workflow.highlightedIds,
          memberRoles: {},
          edges: [],
          radiusLy: 0,
          hull: null,
          label: workflow.type === 'savedSystems' ? 'Saved Systems' : 'Evidence Systems',
          groupContext: null,
        },
      };
      base.highlights = [...base.highlights, clusterHighlight];
      base.guaranteedSystemIds = includeIds(base.guaranteedSystemIds, workflow.highlightedIds);
      break;
    }
    case 'clusterSearch':
      base.clusters = includeCluster(base.clusters, workflow.cluster);
      base.highlights = [...base.highlights, { type: 'cluster', cluster: workflow.cluster }];
      base.guaranteedSystemIds = includeIds(base.guaranteedSystemIds, workflow.cluster.memberIds);
      break;
    case 'planner':
      base.layers = workflow.layers;
      base.highlights = workflow.highlights;
      base.clusters = workflow.clusters;
      base.guaranteedSystemIds = recomputeGuaranteedIds(base);
      break;
  }

  base.returnWorkflow = workflow;
  return base;
}

// ── Helper utilities (used by reducers) ──
function includeId(ids: number[], id: number): number[] {
  if (!ids.includes(id)) ids.push(id);
  return ids;
}
function includeIds(ids: number[], newIds: number[]): number[] {
  const set = new Set(ids);
  newIds.forEach(id => set.add(id));
  return Array.from(set);
}
function includeCluster(clusters: ClusterRepresentation[], cluster: ClusterRepresentation): ClusterRepresentation[] {
  const idx = clusters.findIndex(c => c.label === cluster.label);
  if (idx >= 0) clusters[idx] = cluster;
  else clusters.push(cluster);
  return clusters;
}
function recomputeGuaranteedIds(state: MapSceneState): number[] {
  const ids = new Set<number>();
  if (state.selectedSystemId64) ids.add(state.selectedSystemId64);
  for (const h of state.highlights) {
    if (h.type === 'compare') {
      ids.add(h.leftId64);
      ids.add(h.rightId64);
    } else {
      h.cluster.memberIds.forEach(id => ids.add(id));
    }
  }
  return Array.from(ids);
}

// ── Feature Handoff Matrix ──
export const FEATURE_HANDOFF_MATRIX: Array<{
  surface: string;
  outboundEvent: MapInteractionEvent['type'];
  returnWorkflow: MapReturnWorkflow['type'];
  fixtureKey: string;
}> = [
  { surface: 'Map',                  outboundEvent: 'navigateToMap',          returnWorkflow: 'map',             fixtureKey: 'mapDefaultFixture' },
  { surface: 'Finder',               outboundEvent: 'navigateToFinder',       returnWorkflow: 'finder',          fixtureKey: 'finderSelectionFixture' },
  { surface: 'System Detail',        outboundEvent: 'navigateToSystemDetail', returnWorkflow: 'systemDetail',    fixtureKey: 'systemDetailFixture' },
  { surface: 'Compare',              outboundEvent: 'navigateToCompare',      returnWorkflow: 'compare',         fixtureKey: 'comparisonFixture' },
  { surface: 'Saved Systems',        outboundEvent: 'navigateToSavedSystems', returnWorkflow: 'savedSystems',    fixtureKey: 'simultaneousOverlayFixture' },
  { surface: 'Evidence Map',          outboundEvent: 'navigateToEvidenceMap',  returnWorkflow: 'evidenceMap',     fixtureKey: 'simultaneousOverlayFixture' },
  { surface: 'Cluster Search',       outboundEvent: 'navigateToClusterSearch',returnWorkflow: 'clusterSearch',    fixtureKey: 'clusterFixture' },
  { surface: 'Planner',              outboundEvent: 'navigateToPlanner',      returnWorkflow: 'planner',         fixtureKey: 'plannerReturnFixture' },
];

// ── Scene Actions and Reducer (one‑time auto‑fit, manual camera survival) ──
export type SceneAction =
  | { type: 'enableOneTimeFit'; center: GalaxyCoord; zoom: number }
  | { type: 'advanceSceneRevision'; revision: SceneRevision }
  | { type: 'selectSystem'; systemId64: number }
  | { type: 'setHighlights'; highlights: HighlightSet[] }
  | { type: 'layerToggle'; layerType: string }
  | { type: 'loadMoreSystems'; newSystems: SystemRecord[] }
  | { type: 'dragCamera'; newCenter: GalaxyCoord }
  | { type: 'returnFromWorkflow'; workflow: MapReturnWorkflow }
  | { type: 'pressKey'; key: string }
  | { type: 'initKeyboardPhase'; phase: KeyboardCompanionPhase }
  | { type: 'activateSelectedDetailOverride'; systemId64: number; tier: 'full' | 'simplified' | 'dot' };

export function reduceScene(state: MapSceneState, action: SceneAction): MapSceneState {
  const next = { ...state };

  switch (action.type) {
    case 'enableOneTimeFit':
      next.oneTimeFitIntent = { enabled: true, center: action.center, zoom: action.zoom };
      break;
    case 'advanceSceneRevision':
      next.sceneRevision = action.revision;
      break;
    case 'selectSystem':
      next.selectedSystemId64 = action.systemId64;
      next.guaranteedSystemIds = includeId([...next.guaranteedSystemIds], action.systemId64);
      break;
    case 'setHighlights':
      next.highlights = action.highlights;
      for (const h of action.highlights) {
        if (h.type === 'compare') {
          next.guaranteedSystemIds = includeIds([...next.guaranteedSystemIds], [h.leftId64, h.rightId64]);
        } else {
          next.guaranteedSystemIds = includeIds([...next.guaranteedSystemIds], h.cluster.memberIds);
        }
      }
      break;
    case 'layerToggle': {
      next.layers = next.layers.map(l => {
        if (l.type === action.layerType) {
          const updated: MapLayer = { ...l, visible: !l.visible };
          return updated;
        }
        return l;
      });
      break;
    }
    case 'loadMoreSystems':
      next.systems = [...next.systems, ...action.newSystems];
      next.boundedResponse = {
        count: next.systems.length,
        truncated: false,
        continuationToken: null,
      };
      break;
    case 'dragCamera':
      next.camera = { ...next.camera, center: action.newCenter };
      next.cameraIntent = 'user';
      break;
    case 'returnFromWorkflow':
      return reduceReturnWorkflow(state, action.workflow);
    case 'pressKey': {
      const { nextState, effect } = reduceKeyboardCompanion(
        state.keyboardCompanion,
        action.key,
        { systems: state.systems, layers: state.layers }
      );
      next.keyboardCompanion = nextState;
      if (effect.type === 'selectSystem') {
        next.selectedSystemId64 = effect.systemId64;
        next.guaranteedSystemIds = includeId([...next.guaranteedSystemIds], effect.systemId64);
      } else if (effect.type === 'toggleLayer') {
        next.layers = next.layers.map(l => {
          if (l.type === effect.layerType) {
            const updated: MapLayer = { ...l, visible: !l.visible };
            return updated;
          }
          return l;
        });
      }
      break;
    }
    case 'initKeyboardPhase':
      next.keyboardCompanion = { phase: action.phase };
      break;
    case 'activateSelectedDetailOverride':
      next.selectedDetailOverride = { systemId64: action.systemId64, tier: action.tier };
      break;
  }

  // Apply an armed fit exactly once, when a new scene revision arrives.
  if (state.oneTimeFitIntent?.enabled && next.sceneRevision !== state.sceneRevision) {
    next.camera = {
      ...next.camera,
      center: state.oneTimeFitIntent.center,
      zoom: state.oneTimeFitIntent.zoom,
    };
    next.cameraIntent = 'autoFit';
    next.oneTimeFitIntent = null;
  }
  return next;
}
