import * as fixtureModule from '../../artifacts/map-foundation/stage-26b/map-bakeoff-scenarios';
import {
  R3FCameraTransitionMachine,
} from '../../artifacts/map-foundation/stage-26b/map-renderer-adapter';
import {
  reduceScene,
  type CameraState,
  type MapSceneState,
  type SceneAction,
} from '../../artifacts/map-foundation/stage-26b/map-scene-contract';

type FixtureShape = {
  key: string;
  actions: Array<Record<string, unknown>>;
  assertions: Array<Record<string, unknown>>;
};

const camera = (): CameraState => ({
  center: { x: 0, z: 0 }, zoom: 64, pitchDeg: 0, bearingDeg: 0,
});

function defaultScene(): MapSceneState {
  return {
    sceneRevision: 1,
    oneTimeFitIntent: null,
    cameraIntent: 'user',
    camera: camera(),
    origin: { x: 0, z: 0 },
    systems: [],
    selectedSystemId64: null,
    selectedDetailOverride: null,
    highlights: [],
    clusters: [],
    routes: [],
    annotations: [],
    layers: [{ type: 'regions', visible: true }],
    returnWorkflow: null,
    keyboardCompanion: { phase: { type: 'idle' } },
    boundedResponse: { count: 0, truncated: false, continuationToken: null },
    guaranteedSystemIds: [],
  };
}

function partial(actual: unknown, expected: unknown): boolean {
  if (expected === null || typeof expected !== 'object') return Object.is(actual, expected);
  if (Array.isArray(expected)) {
    return Array.isArray(actual) && expected.length === actual.length
      && expected.every((value, index) => partial(actual[index], value));
  }
  if (actual === null || typeof actual !== 'object') return false;
  return Object.entries(expected).every(([key, value]) => partial((actual as Record<string, unknown>)[key], value));
}

function highlightedIds(scene: MapSceneState): number[] {
  return scene.highlights.flatMap((highlight) => highlight.type === 'compare'
    ? [highlight.leftId64, highlight.rightId64]
    : highlight.cluster.memberIds);
}

function evaluate(
  assertion: Record<string, unknown>,
  scene: MapSceneState,
  machine: R3FCameraTransitionMachine,
  errorThrown: boolean,
): boolean {
  switch (assertion.type) {
    case 'state': return partial(scene, assertion.state);
    case 'camera': return partial(machine.lastAppliedCamera ?? scene.camera, assertion.camera);
    case 'noCameraChangeFrom': return partial(scene.camera, assertion.previous);
    case 'selectedSystemId': return scene.selectedSystemId64 === assertion.id64;
    case 'selectedDetailOverride': return partial(scene.selectedDetailOverride, assertion.override);
    case 'highlightContains': return highlightedIds(scene).includes(assertion.id64 as number);
    case 'highlightDoesNotContain': return !highlightedIds(scene).includes(assertion.id64 as number);
    case 'cluster': return scene.highlights.some((highlight) => highlight.type === 'cluster' && partial(highlight.cluster, assertion.cluster));
    case 'guaranteedSystemsContain': return scene.guaranteedSystemIds.includes(assertion.id64 as number);
    case 'boundedResponse': return partial(scene.boundedResponse, assertion.metadata);
    case 'keyboardCompanionPhase': return scene.keyboardCompanion.phase.type === assertion.phaseType;
    case 'overlapFocusedId': return scene.keyboardCompanion.phase.type === 'overlapCycling'
      && scene.keyboardCompanion.phase.candidates[scene.keyboardCompanion.phase.focusedIndex]?.systemId64 === assertion.id64;
    case 'transitionPhase': return machine.transitionPhase === assertion.phase;
    case 'lastAppliedCamera': return partial(machine.lastAppliedCamera, assertion.camera);
    case 'disposed': return machine.isDisposed === assertion.value;
    case 'errorThrown': return errorThrown === assertion.value;
    default: return false;
  }
}

function runFixture(fixture: FixtureShape): string[] {
  let scene = defaultScene();
  const machine = new R3FCameraTransitionMachine();
  let errorThrown = false;

  for (const action of fixture.actions) {
    try {
      switch (action.type) {
        case 'applySceneAction': scene = reduceScene(scene, action.action as SceneAction); break;
        case 'initKeyboardPhase': scene = reduceScene(scene, {
          type: 'initKeyboardPhase',
          phase: action.phase as MapSceneState['keyboardCompanion']['phase'],
        }); break;
        case 'initMachineCamera': machine.initCamera(action.camera as CameraState); break;
        case 'startCameraTransition': void machine.start(action.target as CameraState, action.durationMs as number); break;
        case 'tickTransition': machine.tick(action.currentTime as number); break;
        case 'cancelTransition': machine.cancel(); break;
        case 'retargetTransition': machine.retarget(action.target as CameraState, action.durationMs as number); break;
        case 'contextLost': machine.contextLost(); break;
        case 'recoverContext': machine.recoverContext(); break;
        case 'dispose': machine.dispose(); break;
      }
    } catch {
      errorThrown = true;
    }
  }

  return fixture.assertions.flatMap((assertion, index) =>
    evaluate(assertion, scene, machine, errorThrown) ? [] : [`${fixture.key}: assertion ${index + 1} (${String(assertion.type)})`]);
}

export function runAllFixtures(): { results: Record<string, 'pass' | 'fail'>; failures: string[] } {
  const fixtures = (Object.values(fixtureModule) as unknown[]).filter((value): value is FixtureShape => {
    if (!value || typeof value !== 'object') return false;
    const candidate = value as Partial<FixtureShape>;
    return typeof candidate.key === 'string' && Array.isArray(candidate.actions) && Array.isArray(candidate.assertions);
  });
  const failures = fixtures.flatMap(runFixture);
  const results = Object.fromEntries(fixtures.map((fixture) => [
    fixture.key,
    failures.some((failure) => failure.startsWith(`${fixture.key}:`)) ? 'fail' : 'pass',
  ])) as Record<string, 'pass' | 'fail'>;
  return { results, failures };
}
