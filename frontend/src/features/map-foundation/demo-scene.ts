import { generateDataset, type DatasetSize } from '../../../../artifacts/map-foundation/stage-26b/map-bakeoff-scenarios';
import type {
  ClusterRepresentation,
  MapSceneState,
  SystemRecord,
} from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';

export const OVERLAP_TARGET = { x: 16_000, z: 0 };

function withFoundationFixtures(systems: SystemRecord[]): SystemRecord[] {
  return systems.map((system, index) => index < 2
    ? { ...system, coords: OVERLAP_TARGET, name: index === 0 ? 'Overlap Alpha' : 'Overlap Beta' }
    : system);
}

export function createFoundationDemoScene(size: DatasetSize): MapSceneState {
  const systems = withFoundationFixtures(generateDataset(size));
  const [anchor, memberA, memberB, compareLeft, compareRight] = systems;
  if (!anchor || !memberA || !memberB || !compareLeft || !compareRight) {
    throw new Error('Stage 26C demo dataset is incomplete');
  }
  const cluster: ClusterRepresentation = {
    anchorId64: anchor.id64,
    memberIds: [anchor.id64, memberA.id64, memberB.id64],
    memberRoles: {
      [anchor.id64]: ['anchor'],
      [memberA.id64]: ['member'],
      [memberB.id64]: ['member'],
    },
    edges: [
      { fromId64: anchor.id64, toId64: memberA.id64 },
      { fromId64: anchor.id64, toId64: memberB.id64 },
    ],
    radiusLy: 1_800,
    hull: null,
    label: 'Foundation cluster',
    groupContext: { name: 'Stage 26C fixture', description: 'Anchor and members remain a single typed group.' },
  };
  return {
    sceneRevision: 1,
    oneTimeFitIntent: null,
    cameraIntent: 'user',
    camera: { center: { x: 0, z: 0 }, zoom: 64, pitchDeg: 0, bearingDeg: 0 },
    origin: { x: 0, z: 0 },
    systems,
    selectedSystemId64: null,
    selectedDetailOverride: null,
    highlights: [
      { type: 'compare', leftId64: compareLeft.id64, rightId64: compareRight.id64 },
      { type: 'cluster', cluster },
    ],
    clusters: [cluster],
    routes: [],
    annotations: [],
    layers: [
      { type: 'regions', visible: true },
      { type: 'routes', visible: false },
      { type: 'annotations', visible: false },
    ],
    returnWorkflow: null,
    keyboardCompanion: { phase: { type: 'idle' } },
    boundedResponse: { count: systems.length, truncated: false, continuationToken: null },
    guaranteedSystemIds: [anchor.id64, memberA.id64, memberB.id64, compareLeft.id64, compareRight.id64],
  };
}
