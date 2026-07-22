// === Map Bake‑Off Scenarios ===
// ED‑Finder Stage 26B — Shared Vite/React harness, deterministic datasets,
// candidate IDs/camera mappings, viewports, measurement/decision plans,
// Playwright journey, and 17 precondition/action/assertion fixtures.
// Imports only emitted relative artifacts; must compile but must not claim execution.

import type {
  MapSceneState,
  CameraState,
  SystemRecord,
  ClusterRepresentation,
  KeyboardCompanionPhase,
  SceneAction,
} from './map-scene-contract';
import {
  initSystemTraversal,
  initOverlayToggle,
  initSearchResultTraversal,
  initOverlapCycling,
} from './map-scene-contract';
import type {
  MeasurementRecord,
  DecisionLog,
  RendererCandidateId,
} from './map-renderer-adapter';

// ── Shared Harness Specification ──
export const HARNESS_CONFIG = {
  framework: 'React 19 + Vite 6',
  componentTree: 'App → MapSceneProvider → MapCanvas (adapter mount point)',
  route: '/map-bakeoff',
  uiControls: ['renderer‑selector (radio)', 'dataset‑selector (dropdown)', 'run‑all button'],
} as const;

// ── Deterministic Dataset Specs ──
export type DatasetSize = 100_000 | 500_000;

export function generateDataset(size: DatasetSize): SystemRecord[] {
  const systems: SystemRecord[] = [];
  const N = size;
  for (let i = 0; i < N; i++) {
    const id64 = 100_000_000 + i;
    const angle = (i * 2 * Math.PI) / N;
    const radius = 25000 * (0.5 + 0.5 * Math.sin(i * 0.0001));
    systems.push({
      id64,
      name: `System ${i}`,
      // Index zero is a deterministic centre-screen pick target shared by all
      // candidates; the remaining systems retain the spiral distribution.
      coords: i === 0 ? { x: 16_000, z: 0 } : {
        x: radius * Math.cos(angle),
        z: radius * Math.sin(angle),
      },
      developmentScore: 50 + (i % 50),
      primaryEconomy: i % 2 === 0 ? 'Refinery' : 'Agriculture',
      population: 1_000_000 + (i % 1000),
    });
  }
  return systems;
}

// ── Candidate IDs and Camera Mappings ──
export const CANDIDATES: Array<{ id: RendererCandidateId; label: string }> = [
  { id: 'deckgl-orbit', label: 'deck.gl OrbitView' },
  { id: 'deckgl-ortho', label: 'deck.gl OrthographicView' },
  { id: 'threejs-r3f',  label: 'Three.js + R3F' },
];

// ── Viewports ──
export const VIEWPORTS = [
  { width: 1280, height: 720 },
  { width: 1440, height: 900 },
] as const;

// ── Measurement / Environment Records ──
export const UNKNOWN_MEASUREMENT: MeasurementRecord = {
  frameTimeP50Ms: null, frameTimeP95Ms: null, frameTimeP99Ms: null,
  initialLoadMs: null, clickLatencyMs: null, memoryUsageMB: null,
  compressedBundleBytes: null, contextLossRecoveryMs: null,
  regionCorrectness: null, overlapHandlingCorrect: null,
  keyboardWorkflowCorrect: null, scenarioResultsPassed: null,
  gpuFrameTimeMs: null,
};

export function decisionLogForCandidate(
  candidate: RendererCandidateId,
  dataset: DatasetSize,
  viewport: { width: number; height: number }
): DecisionLog {
  return {
    environment: {
      candidateId: candidate,
      datasetSize: dataset,
      viewportWidth: viewport.width,
      viewportHeight: viewport.height,
      browser: 'Chromium (Playwright)',
      os: 'Linux CI',
      timestamp: new Date().toISOString(),
    },
    measurements: UNKNOWN_MEASUREMENT,
    scenarioStatuses: {},
    legalConclusion: 'unresolved',
    notes: 'Unexecuted design fixtures.',
  };
}

// ── Playwright Journey (shared across candidates) ──
export const PLAYWRIGHT_JOURNEY = {
  steps: [
    'Navigate to /map-bakeoff',
    'Select candidate',
    'Select dataset 100k',
    'Click Start button',
    'Wait for canvas to render',
    'Execute scroll/pan/click interactions from scenario fixtures',
    'Assert visual states',
    'Collect performance metrics',
    'Switch to dataset 500k and repeat',
  ],
};

// ── Fixture Actions / Assertions (internal to this file) ──
type FixtureAction =
  | { type: 'applySceneAction'; action: SceneAction }
  | { type: 'startCameraTransition'; target: CameraState; durationMs: number }
  | { type: 'tickTransition'; currentTime: number }
  | { type: 'cancelTransition' }
  | { type: 'retargetTransition'; target: CameraState; durationMs: number }
  | { type: 'contextLost' }
  | { type: 'recoverContext' }
  | { type: 'dispose' }
  | { type: 'initMachineCamera'; camera: CameraState }
  | { type: 'initKeyboardPhase'; phase: KeyboardCompanionPhase };

type FixtureAssertion =
  | { type: 'state'; state: Partial<MapSceneState> }
  | { type: 'camera'; camera: Partial<CameraState> }
  | { type: 'noCameraChangeFrom'; previous: CameraState }
  | { type: 'selectedSystemId'; id64: number }
  | { type: 'selectedDetailOverride'; override: { systemId64: number; tier: string } }
  | { type: 'highlightContains'; id64: number }
  | { type: 'highlightDoesNotContain'; id64: number }
  | { type: 'cluster'; cluster: Partial<ClusterRepresentation> }
  | { type: 'guaranteedSystemsContain'; id64: number }
  | { type: 'boundedResponse'; metadata: { count: number; truncated: boolean } }
  | { type: 'keyboardCompanionPhase'; phaseType: string }
  | { type: 'overlapFocusedId'; id64: number }
  | { type: 'transitionPhase'; phase: string }
  | { type: 'lastAppliedCamera'; camera: Partial<CameraState> }
  | { type: 'disposed'; value: boolean }
  | { type: 'errorThrown'; value: boolean };

export type Fixture = {
  key: string;
  scenario: string;
  description: string;
  actions: FixtureAction[];
  assertions: FixtureAssertion[];
};

// ── Helper: create a minimal default scene ──
function defaultScene(revision: number = 1): MapSceneState {
  return {
    sceneRevision: revision,
    oneTimeFitIntent: null,
    cameraIntent: 'user',
    camera: { center: { x: 0, z: 0 }, zoom: 1, pitchDeg: 0, bearingDeg: 0 },
    origin: { x: 0, z: 0 },
    systems: [],
    selectedSystemId64: null,
    selectedDetailOverride: null,
    highlights: [],
    clusters: [],
    routes: [],
    annotations: [],
    layers: [],
    returnWorkflow: null,
    keyboardCompanion: { phase: { type: 'idle' } },
    boundedResponse: { count: 0, truncated: false, continuationToken: null },
    guaranteedSystemIds: [],
  };
}

// ── 17 Named Fixtures ──

export const CLUSTER_FIXTURE: Fixture = {
  key: 'clusterFixture',
  scenario: 'Cluster selection and round‑trip',
  description: 'Verify that selecting a cluster correctly sets up the ClusterRepresentation, preserves all members as guaranteed renderable, and that the full cluster contract is present after selection and round‑trip.',
  actions: [
    { type: 'applySceneAction', action: { type: 'setHighlights', highlights: [{ type: 'cluster', cluster: {
      anchorId64: 100_000_001,
      memberIds: [100_000_001, 100_000_002, 100_000_003],
      memberRoles: { 100_000_001: ['anchor'], 100_000_002: ['member'], 100_000_003: ['edge'] },
      edges: [{ fromId64: 100_000_001, toId64: 100_000_002 }, { fromId64: 100_000_002, toId64: 100_000_003 }],
      radiusLy: 15,
      hull: [{ x: 10, z: 0 }, { x: 20, z: 10 }, { x: 30, z: -5 }],
      label: 'Test Cluster',
      groupContext: { name: 'Nearby Systems', description: 'A test group' },
    } }] } },
    { type: 'applySceneAction', action: { type: 'selectSystem', systemId64: 100_000_001 } },
    { type: 'applySceneAction', action: { type: 'returnFromWorkflow', workflow: {
      type: 'clusterSearch',
      cluster: {
        anchorId64: 100_000_001,
        memberIds: [100_000_001, 100_000_002, 100_000_003],
        memberRoles: { 100_000_001: ['anchor'], 100_000_002: ['member'], 100_000_003: ['edge'] },
        edges: [{ fromId64: 100_000_001, toId64: 100_000_002 }, { fromId64: 100_000_002, toId64: 100_000_003 }],
        radiusLy: 15,
        hull: [{ x: 10, z: 0 }, { x: 20, z: 10 }, { x: 30, z: -5 }],
        label: 'Test Cluster',
        groupContext: { name: 'Nearby Systems', description: 'A test group' },
      },
      camera: defaultScene().camera,
      origin: { x: 0, z: 0 },
    } } },
  ],
  assertions: [
    { type: 'guaranteedSystemsContain', id64: 100_000_001 },
    { type: 'guaranteedSystemsContain', id64: 100_000_002 },
    { type: 'guaranteedSystemsContain', id64: 100_000_003 },
    { type: 'cluster', cluster: { anchorId64: 100_000_001, label: 'Test Cluster' } },
    { type: 'cluster', cluster: { memberIds: [100_000_001, 100_000_002, 100_000_003] } },
    { type: 'cluster', cluster: { memberRoles: { 100_000_001: ['anchor'], 100_000_002: ['member'], 100_000_003: ['edge'] } } },
    { type: 'cluster', cluster: { edges: [{ fromId64: 100_000_001, toId64: 100_000_002 }, { fromId64: 100_000_002, toId64: 100_000_003 }] } },
    { type: 'cluster', cluster: { radiusLy: 15 } },
    { type: 'cluster', cluster: { groupContext: { name: 'Nearby Systems', description: 'A test group' } } },
  ],
};

export const COMPARISON_FIXTURE: Fixture = {
  key: 'comparisonFixture',
  scenario: 'Two‑system comparison and return',
  description: 'Verify that setting a compare highlight correctly marks both systems as guaranteed renderable, and that returning from the compare workflow restores the proper highlight and guaranteed IDs.',
  actions: [
    { type: 'applySceneAction', action: { type: 'selectSystem', systemId64: 100_000_040 } },
    { type: 'applySceneAction', action: { type: 'setHighlights', highlights: [{ type: 'compare', leftId64: 100_000_040, rightId64: 100_000_041 }] } },
    { type: 'applySceneAction', action: { type: 'returnFromWorkflow', workflow: { type: 'compare', leftId64: 100_000_040, rightId64: 100_000_041, camera: defaultScene().camera, origin: { x: 0, z: 0 } } } },
  ],
  assertions: [
    { type: 'selectedSystemId', id64: 100_000_040 },
    { type: 'highlightContains', id64: 100_000_040 },
    { type: 'highlightContains', id64: 100_000_041 },
    { type: 'guaranteedSystemsContain', id64: 100_000_040 },
    { type: 'guaranteedSystemsContain', id64: 100_000_041 },
  ],
};

export const FINDER_SELECTION_FIXTURE: Fixture = {
  key: 'finderSelectionFixture',
  scenario: 'Finder selection and detail navigation',
  description: 'Verify that selecting a system from the Finder marks it as selected and guaranteed renderable, and that returning from the Finder workflow preserves the selected system.',
  actions: [
    { type: 'applySceneAction', action: { type: 'selectSystem', systemId64: 100_000_060 } },
    { type: 'applySceneAction', action: { type: 'returnFromWorkflow', workflow: { type: 'finder', camera: defaultScene().camera, origin: { x: 0, z: 0 } } } },
  ],
  assertions: [
    { type: 'selectedSystemId', id64: 100_000_060 },
    { type: 'guaranteedSystemsContain', id64: 100_000_060 },
  ],
};

export const SELECTED_SYSTEM_LOD_OVERRIDE_FIXTURE: Fixture = {
  key: 'selectedSystemLODOverrideFixture',
  scenario: 'Selected‑system LOD/detail override',
  description: 'Verify that the selected system detail tier can be overridden to full/simplified/dot, that the override is stored in the scene state, and that the system remains guaranteed renderable.',
  actions: [
    { type: 'applySceneAction', action: { type: 'selectSystem', systemId64: 100_000_050 } },
    { type: 'applySceneAction', action: { type: 'activateSelectedDetailOverride', systemId64: 100_000_050, tier: 'full' } },
  ],
  assertions: [
    { type: 'selectedSystemId', id64: 100_000_050 },
    { type: 'selectedDetailOverride', override: { systemId64: 100_000_050, tier: 'full' } },
    { type: 'guaranteedSystemsContain', id64: 100_000_050 },
  ],
};

export const PLANNER_RETURN_FIXTURE: Fixture = {
  key: 'plannerReturnFixture',
  scenario: 'Return from planner restores exact map state',
  description: 'Verify that returning from the planner with a full workflow payload restores camera, origin, highlights, layers, clusters, workflow discriminator, and guaranteed IDs exactly.',
  actions: [
    { type: 'applySceneAction', action: { type: 'returnFromWorkflow', workflow: {
      type: 'planner',
      camera: { center: { x: 50, z: 100 }, zoom: 2, pitchDeg: 45, bearingDeg: 90 },
      origin: { x: 50, z: 100 },
      highlights: [{ type: 'cluster', cluster: {
        anchorId64: 100_000_200,
        memberIds: [100_000_200, 100_000_201],
        memberRoles: { 100_000_200: ['anchor'], 100_000_201: ['member'] },
        edges: [],
        radiusLy: 5,
        hull: null,
        label: 'Planner Cluster',
        groupContext: null,
      } }],
      layers: [{ type: 'regions', visible: true }],
      clusters: [],
      workflowDiscriminator: 'planner',
      workflowPayload: { planId: 'abc' },
    } } },
  ],
  assertions: [
    { type: 'camera', camera: { center: { x: 50, z: 100 }, zoom: 2 } },
    { type: 'state', state: { origin: { x: 50, z: 100 } } },
    { type: 'highlightContains', id64: 100_000_200 },
    { type: 'highlightContains', id64: 100_000_201 },
    { type: 'guaranteedSystemsContain', id64: 100_000_200 },
    { type: 'guaranteedSystemsContain', id64: 100_000_201 },
    { type: 'state', state: { cameraIntent: 'returnFromWorkflow' } },
    { type: 'state', state: { layers: [{ type: 'regions', visible: true }] } },
    { type: 'state', state: { clusters: [] } },
    { type: 'state', state: { returnWorkflow: { type: 'planner', workflowDiscriminator: 'planner', workflowPayload: { planId: 'abc' } } as any } },
  ],
};

export const SIMULTANEOUS_OVERLAY_FIXTURE: Fixture = {
  key: 'simultaneousOverlayFixture',
  scenario: 'Simultaneous saved and evidence overlays',
  description: 'Verify that returning from both saved systems and evidence map correctly overlays both sets of guaranteed renderable systems.',
  actions: [
    { type: 'applySceneAction', action: { type: 'returnFromWorkflow', workflow: { type: 'savedSystems', highlightedIds: [100_000_070, 100_000_071], camera: defaultScene().camera, origin: { x: 0, z: 0 } } } },
    { type: 'applySceneAction', action: { type: 'returnFromWorkflow', workflow: { type: 'evidenceMap', highlightedIds: [100_000_080, 100_000_081], camera: defaultScene().camera, origin: { x: 0, z: 0 } } } },
  ],
  assertions: [
    { type: 'highlightContains', id64: 100_000_070 },
    { type: 'highlightContains', id64: 100_000_071 },
    { type: 'highlightContains', id64: 100_000_080 },
    { type: 'highlightContains', id64: 100_000_081 },
    { type: 'guaranteedSystemsContain', id64: 100_000_070 },
    { type: 'guaranteedSystemsContain', id64: 100_000_071 },
    { type: 'guaranteedSystemsContain', id64: 100_000_080 },
    { type: 'guaranteedSystemsContain', id64: 100_000_081 },
  ],
};

export const AUTO_FIT_FIXTURE: Fixture = {
  key: 'autoFitFixture',
  scenario: 'One‑time auto‑fit survives manual pan and mutations',
  description: 'Verify that manual camera movement survives selection, data loading, layer toggles, and highlight/cluster changes until sceneRevision changes, and that auto‑fit does not re‑trigger.',
  actions: [
    { type: 'applySceneAction', action: { type: 'enableOneTimeFit', center: { x: 5, z: 10 }, zoom: 4 } },
    { type: 'applySceneAction', action: { type: 'advanceSceneRevision', revision: 2 } },
    { type: 'applySceneAction', action: { type: 'dragCamera', newCenter: { x: 20, z: 30 } } },
    { type: 'applySceneAction', action: { type: 'selectSystem', systemId64: 100_000_010 } },
    { type: 'applySceneAction', action: { type: 'loadMoreSystems', newSystems: [{ id64: 100_000_010, name: 'Sys010', coords: { x: 10, z: 10 }, developmentScore: null, primaryEconomy: null, population: null }] } },
    { type: 'applySceneAction', action: { type: 'layerToggle', layerType: 'regions' } },
    { type: 'applySceneAction', action: { type: 'setHighlights', highlights: [{ type: 'cluster', cluster: { anchorId64: 100_000_020, memberIds: [100_000_020], memberRoles: {}, edges: [], radiusLy: 0, hull: null, label: 'Test', groupContext: null } }] } },
  ],
  assertions: [
    { type: 'camera', camera: { center: { x: 20, z: 30 } } },
    { type: 'state', state: { sceneRevision: 2, oneTimeFitIntent: null, cameraIntent: 'user' } },
    { type: 'guaranteedSystemsContain', id64: 100_000_010 },
  ],
};

export const MAP_DEFAULT_FIXTURE: Fixture = {
  key: 'mapDefaultFixture',
  scenario: 'Default map handoff (navigate to map)',
  description: 'Verify that the default map return-workflow applies camera and layers and sets cameraIntent to returnFromWorkflow.',
  actions: [
    { type: 'applySceneAction', action: { type: 'returnFromWorkflow', workflow: { type: 'map', camera: defaultScene().camera, origin: { x: 0, z: 0 }, layers: [] } } },
  ],
  assertions: [
    { type: 'camera', camera: defaultScene().camera },
    { type: 'state', state: { origin: { x: 0, z: 0 } } },
    { type: 'state', state: { layers: [] } },
    { type: 'state', state: { cameraIntent: 'returnFromWorkflow' } },
  ],
};

export const SYSTEM_DETAIL_FIXTURE: Fixture = {
  key: 'systemDetailFixture',
  scenario: 'System Detail handoff and return',
  description: 'Verify that the system detail return-workflow applies the selected system and guarantees its renderability.',
  actions: [
    { type: 'applySceneAction', action: { type: 'returnFromWorkflow', workflow: { type: 'systemDetail', systemId64: 100_000_090, camera: defaultScene().camera, origin: { x: 0, z: 0 } } } },
  ],
  assertions: [
    { type: 'selectedSystemId', id64: 100_000_090 },
    { type: 'guaranteedSystemsContain', id64: 100_000_090 },
  ],
};

export const OVERLAP_KEYBOARD_FIXTURE: Fixture = {
  key: 'overlapKeyboardFixture',
  scenario: 'Overlap disambiguation via keyboard',
  description: 'Verify that the overlap keyboard companion correctly cycles candidates with Tab/Shift+Tab, selects the focused candidate on Enter, and dismisses without selection on Escape.',
  actions: [
    { type: 'initKeyboardPhase', phase: initOverlapCycling([
      { systemId64: 100_000_010, distancePx: 5 },
      { systemId64: 100_000_011, distancePx: 8 },
      { systemId64: 100_000_012, distancePx: 12 },
    ]) },
    { type: 'applySceneAction', action: { type: 'pressKey', key: 'Tab' } },
    { type: 'applySceneAction', action: { type: 'pressKey', key: 'Tab' } },
    { type: 'applySceneAction', action: { type: 'pressKey', key: 'Shift+Tab' } },
    { type: 'applySceneAction', action: { type: 'pressKey', key: 'Enter' } },
    { type: 'initKeyboardPhase', phase: initOverlapCycling([
      { systemId64: 100_000_010, distancePx: 5 },
      { systemId64: 100_000_011, distancePx: 8 },
    ]) },
    { type: 'applySceneAction', action: { type: 'pressKey', key: 'Escape' } },
  ],
  assertions: [
    { type: 'selectedSystemId', id64: 100_000_011 },
    { type: 'keyboardCompanionPhase', phaseType: 'idle' },
  ],
};

export const KEYBOARD_SYSTEM_TRAVERSAL_FIXTURE: Fixture = {
  key: 'keyboardSystemTraversalFixture',
  scenario: 'Keyboard traversal through selected systems',
  description: 'Verify that initializing the system traversal keyboard phase and pressing Tab/Enter correctly selects a target system and dismisses the keyboard phase.',
  actions: [
    { type: 'initKeyboardPhase', phase: initSystemTraversal([100_000_005, 100_000_006, 100_000_007]) },
    { type: 'applySceneAction', action: { type: 'pressKey', key: 'Tab' } },
    { type: 'applySceneAction', action: { type: 'pressKey', key: 'Tab' } },
    { type: 'applySceneAction', action: { type: 'pressKey', key: 'Enter' } },
  ],
  assertions: [
    { type: 'selectedSystemId', id64: 100_000_007 },
    { type: 'keyboardCompanionPhase', phaseType: 'idle' },
  ],
};

export const KEYBOARD_OVERLAY_TOGGLE_FIXTURE: Fixture = {
  key: 'keyboardOverlayToggleFixture',
  scenario: 'Keyboard overlay toggling',
  description: 'Verify that toggling a layer via the keyboard overlay phase correctly flips its visibility and dismisses the phase.',
  actions: [
    { type: 'applySceneAction', action: { type: 'returnFromWorkflow', workflow: { type: 'map', camera: { center: { x: 0, z: 0 }, zoom: 1, pitchDeg: 0, bearingDeg: 0 }, origin: { x: 0, z: 0 }, layers: [{ type: 'regions', visible: true }, { type: 'routes', visible: false }] } } },
    { type: 'initKeyboardPhase', phase: initOverlayToggle([{ type: 'regions', visible: true }, { type: 'routes', visible: false }]) },
    { type: 'applySceneAction', action: { type: 'pressKey', key: 'ArrowDown' } },
    { type: 'applySceneAction', action: { type: 'pressKey', key: 'Enter' } },
  ],
  assertions: [
    { type: 'keyboardCompanionPhase', phaseType: 'idle' },
    { type: 'state', state: { layers: [{ type: 'regions', visible: true }, { type: 'routes', visible: true }] } },
  ],
};

export const KEYBOARD_SEARCH_RESULT_FIXTURE: Fixture = {
  key: 'keyboardSearchResultFixture',
  scenario: 'Keyboard search result traversal',
  description: 'Verify that the keyboard search-result phase cycles through candidates with ArrowDown and selects on Enter.',
  actions: [
    { type: 'initKeyboardPhase', phase: initSearchResultTraversal([100_000_100, 100_000_101, 100_000_102]) },
    { type: 'applySceneAction', action: { type: 'pressKey', key: 'ArrowDown' } },
    { type: 'applySceneAction', action: { type: 'pressKey', key: 'ArrowDown' } },
    { type: 'applySceneAction', action: { type: 'pressKey', key: 'Enter' } },
  ],
  assertions: [
    { type: 'selectedSystemId', id64: 100_000_102 },
    { type: 'keyboardCompanionPhase', phaseType: 'idle' },
  ],
};

// R3F transition fixtures
export const R3F_ZERO_DURATION_FIXTURE: Fixture = {
  key: 'r3fZeroDurationFixture',
  scenario: 'Zero‑duration camera transition',
  description: 'Verify that a zero‑duration R3F camera transition immediately applies the target and resolves the promise synchronously.',
  actions: [
    { type: 'initMachineCamera', camera: { center: { x: 0, z: 0 }, zoom: 1, pitchDeg: 0, bearingDeg: 0 } },
    { type: 'startCameraTransition', target: { center: { x: 100, z: 200 }, zoom: 5, pitchDeg: 0, bearingDeg: 0 }, durationMs: 0 },
    { type: 'tickTransition', currentTime: 1000 },
  ],
  assertions: [
    { type: 'camera', camera: { center: { x: 100, z: 200 } } },
    { type: 'transitionPhase', phase: 'idle' },
  ],
};

export const R3F_IDLE_RETARGETING_FIXTURE: Fixture = {
  key: 'r3fIdleRetargetingFixture',
  scenario: 'Idle retarget throws deterministically',
  description: 'Verify that calling retarget when the machine is idle throws an error (deterministic rejection).',
  actions: [
    { type: 'initMachineCamera', camera: { center: { x: 0, z: 0 }, zoom: 1, pitchDeg: 0, bearingDeg: 0 } },
    { type: 'startCameraTransition', target: { center: { x: 0, z: 0 }, zoom: 1, pitchDeg: 0, bearingDeg: 0 }, durationMs: 0 },
    { type: 'tickTransition', currentTime: 0 },
    { type: 'retargetTransition', target: { center: { x: 50, z: 50 }, zoom: 2, pitchDeg: 0, bearingDeg: 0 }, durationMs: 1000 },
  ],
  assertions: [
    { type: 'errorThrown', value: true },
  ],
};

export const R3F_CANCEL_FIXTURE: Fixture = {
  key: 'r3fCancelFixture',
  scenario: 'Cancel preserves last‑applied camera',
  description: 'Verify that cancelling an in-progress transition preserves the lastApplied camera (not the target) and resolves the promise.',
  actions: [
    { type: 'initMachineCamera', camera: { center: { x: 50, z: 50 }, zoom: 2, pitchDeg: 0, bearingDeg: 0 } },
    { type: 'startCameraTransition', target: { center: { x: 200, z: 300 }, zoom: 10, pitchDeg: 0, bearingDeg: 0 }, durationMs: 1000 },
    { type: 'tickTransition', currentTime: 150 },
    { type: 'cancelTransition' },
  ],
  assertions: [
    { type: 'transitionPhase', phase: 'idle' },
    { type: 'lastAppliedCamera', camera: { center: { x: 50, z: 50 } } },
  ],
};

export const R3F_RECOVERY_FIXTURE: Fixture = {
  key: 'r3fRecoveryFixture',
  scenario: 'Context loss and recovery',
  description: 'Verify that after context loss and recovery, the transition machine can start and complete a new transition.',
  actions: [
    { type: 'contextLost' },
    { type: 'recoverContext' },
    { type: 'initMachineCamera', camera: { center: { x: 0, z: 0 }, zoom: 1, pitchDeg: 0, bearingDeg: 0 } },
    { type: 'startCameraTransition', target: { center: { x: -50, z: -50 }, zoom: 1, pitchDeg: 0, bearingDeg: 0 }, durationMs: 200 },
    { type: 'tickTransition', currentTime: 400 },
    { type: 'tickTransition', currentTime: 600 },
  ],
  assertions: [
    { type: 'camera', camera: { center: { x: -50, z: -50 } } },
    { type: 'transitionPhase', phase: 'idle' },
  ],
};

// Fixture‑invariant matrix: each row is a fixture, each column an invariant.
export const FIXTURE_INVARIANT_MATRIX = [
  { fixture: 'clusterFixture',                   invariants: ['guaranteedRenderability', 'clusterIntegrity'] },
  { fixture: 'comparisonFixture',               invariants: ['guaranteedRenderability', 'highlightIntegrity'] },
  { fixture: 'finderSelectionFixture',          invariants: ['guaranteedRenderability'] },
  { fixture: 'selectedSystemLODOverrideFixture', invariants: ['guaranteedRenderability', 'lodOverride'] },
  { fixture: 'plannerReturnFixture',            invariants: ['stateRestoration', 'guaranteedRenderability'] },
  { fixture: 'simultaneousOverlayFixture',      invariants: ['highlightIntegrity'] },
  { fixture: 'autoFitFixture',                   invariants: ['manualCameraSurvival'] },
  { fixture: 'mapDefaultFixture',               invariants: ['returnWorkflowState'] },
  { fixture: 'systemDetailFixture',             invariants: ['guaranteedRenderability'] },
  { fixture: 'r3fZeroDurationFixture',          invariants: ['transitionSync'] },
  { fixture: 'r3fIdleRetargetingFixture',       invariants: ['idleRejection'] },
  { fixture: 'r3fCancelFixture',                invariants: ['preserveLastApplied'] },
  { fixture: 'r3fRecoveryFixture',               invariants: ['recoveryUsability'] },
  { fixture: 'overlapKeyboardFixture',          invariants: ['overlapDisambiguation'] },
  { fixture: 'keyboardSystemTraversalFixture',  invariants: ['keyboardTraversal'] },
  { fixture: 'keyboardOverlayToggleFixture',    invariants: ['keyboardOverlay'] },
  { fixture: 'keyboardSearchResultFixture',     invariants: ['keyboardSearch'] },
];
