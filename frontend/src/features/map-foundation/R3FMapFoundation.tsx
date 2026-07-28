import { Canvas, type ThreeEvent, useThree } from '@react-three/fiber';
import { useCallback, useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js';
import { LineSegments2 } from 'three/examples/jsm/lines/LineSegments2.js';
import { LineSegmentsGeometry } from 'three/examples/jsm/lines/LineSegmentsGeometry.js';
import type {
  CameraState,
  MapInteractionEvent,
  SystemRecord,
} from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';
import type {
  FoundationRendererProps,
  ProjectedLabel,
  RegionLabel,
  ViewportSize,
} from './types';
import {
  CAMERA_VIEWPORT_HEIGHT_RATIO,
  clampCameraCenter,
  MAX_CAMERA_PITCH_DEG,
  MIN_CAMERA_PITCH_DEG,
  zoomCamera,
} from './camera';
import { measureRendererGpuTiming } from './performance';
import {
  buildClusterGeometry,
  clusterAnchorIdForSystem,
  findOverlappingSystemIds,
  highlightedSystemIds,
  selectVisibleSystems,
} from './visibility';

const GALAXY_CENTER = { x: 25.2, z: 25_899.9 } as const;
const GALAXY_RADIUS_LY = 50_000;
const GALAXY_POINT_COUNT = 18_000;

function positions(
  systems: SystemRecord[],
  heightOffset = 0,
): Float32Array {
  const values = new Float32Array(systems.length * 3);
  systems.forEach((system, index) => values.set([
    system.coords.x,
    system.coords.z,
    system.coords.y + heightOffset,
  ], index * 3));
  return values;
}

function cameraDistanceForView(camera: CameraState, size: ViewportSize): number {
  const visibleHeight = Math.max(
    20,
    camera.zoom * size.height * CAMERA_VIEWPORT_HEIGHT_RATIO,
  );
  return visibleHeight / (2 * Math.tan((42 * Math.PI / 180) / 2));
}

function attenuatedPointSize(zoom: number, pixels: number): number {
  return Math.max(0.12, zoom * pixels * 0.78);
}

function configureRenderCamera(
  camera: THREE.PerspectiveCamera,
  size: ViewportSize,
  cameraState: CameraState,
) {
  const bearing = cameraState.bearingDeg * Math.PI / 180;
  const pitch = Math.max(
    MIN_CAMERA_PITCH_DEG,
    Math.min(MAX_CAMERA_PITCH_DEG, cameraState.pitchDeg),
  ) * Math.PI / 180;
  const fov = 42;
  const visibleHeight = Math.max(
    20,
    cameraState.zoom * size.height * CAMERA_VIEWPORT_HEIGHT_RATIO,
  );
  const distance = visibleHeight / (2 * Math.tan((fov * Math.PI / 180) / 2));
  const horizontalDistance = Math.sin(pitch) * distance;
  const verticalDistance = Math.cos(pitch) * distance;
  camera.fov = fov;
  camera.aspect = Math.max(0.1, size.width / Math.max(1, size.height));
  camera.position.set(
    cameraState.center.x - Math.sin(bearing) * horizontalDistance,
    cameraState.center.z - Math.cos(bearing) * horizontalDistance,
    Math.max(10, verticalDistance),
  );
  camera.up.set(0, 0, 1);
  camera.lookAt(cameraState.center.x, cameraState.center.z, 0);
  camera.near = Math.max(0.1, distance / 20_000);
  camera.far = Math.max(250_000, distance + 200_000);
  camera.updateProjectionMatrix();
}

function CameraProjection({ cameraState }: { cameraState: CameraState }) {
  const { camera, size, invalidate } = useThree();
  useEffect(() => {
    configureRenderCamera(camera as THREE.PerspectiveCamera, size, cameraState);
    invalidate();
  }, [camera, cameraState, invalidate, size]);
  return null;
}

function GpuTimingBridge({ onReady }: { onReady: FoundationRendererProps['onGpuTimerReady'] }) {
  const { camera, gl, scene } = useThree();
  useEffect(() => {
    if (!onReady) return undefined;
    onReady((sampleCount) => measureRendererGpuTiming(gl, scene, camera, sampleCount));
    return () => onReady(null);
  }, [camera, gl, onReady, scene]);
  return null;
}

function RegionBoundaryLines({
  positions: boundaryPositions,
  viewport,
  spatial,
}: {
  positions: Float32Array;
  viewport: FoundationRendererProps['viewport'];
  spatial: boolean;
}) {
  const layer = useMemo(() => {
    const geometry = new LineSegmentsGeometry();
    geometry.setPositions(boundaryPositions);
    geometry.computeBoundingBox();
    geometry.computeBoundingSphere();

    const haloMaterial = new LineMaterial({
      color: 0xff8a2c,
      linewidth: spatial ? 2.2 : 2.8,
      transparent: true,
      opacity: spatial ? 0.1 : 0.08,
      depthTest: false,
      depthWrite: false,
      alphaToCoverage: true,
    });
    const coreMaterial = new LineMaterial({
      color: spatial ? 0xf0ad56 : 0xd58b3b,
      linewidth: spatial ? 1.25 : 1.05,
      transparent: true,
      opacity: spatial ? 0.72 : 0.58,
      depthTest: false,
      depthWrite: false,
      alphaToCoverage: true,
    });
    const halo = new LineSegments2(geometry, haloMaterial);
    const core = new LineSegments2(geometry, coreMaterial);
    halo.renderOrder = 5;
    core.renderOrder = 6;
    halo.frustumCulled = false;
    core.frustumCulled = false;

    return { geometry, halo, core, haloMaterial, coreMaterial };
  }, [boundaryPositions, spatial]);

  useEffect(() => {
    layer.haloMaterial.resolution.set(viewport.width, viewport.height);
    layer.coreMaterial.resolution.set(viewport.width, viewport.height);
  }, [layer, viewport.height, viewport.width]);

  useEffect(() => () => {
    layer.haloMaterial.dispose();
    layer.coreMaterial.dispose();
    layer.geometry.dispose();
  }, [layer]);

  if (boundaryPositions.length === 0) return null;
  return <>
    <primitive object={layer.halo} />
    <primitive object={layer.core} />
  </>;
}

function makeGalaxyPointCloud() {
  const pointPositions = new Float32Array(GALAXY_POINT_COUNT * 3);
  const pointColors = new Float32Array(GALAXY_POINT_COUNT * 3);
  let seed = 0x5f3759df;
  const random = () => {
    seed = (Math.imul(seed, 1_664_525) + 1_013_904_223) >>> 0;
    return seed / 4_294_967_296;
  };

  for (let index = 0; index < GALAXY_POINT_COUNT; index += 1) {
    const inCentralBar = random() < 0.28;
    let x: number;
    let y: number;
    let radial: number;
    if (inCentralBar) {
      const along = (random() - random()) * 31_000;
      const across = (random() - random()) * (7_500 - Math.abs(along) * 0.12);
      const barAngle = -22 * Math.PI / 180;
      x = along * Math.cos(barAngle) - across * Math.sin(barAngle);
      y = along * Math.sin(barAngle) + across * Math.cos(barAngle);
      radial = Math.min(1, Math.hypot(x, y) / GALAXY_RADIUS_LY);
    } else {
      radial = Math.pow(random(), 0.68);
      const radius = radial * GALAXY_RADIUS_LY;
      const angle = random() * Math.PI * 2;
      x = Math.cos(angle) * radius + (random() - random()) * 1_250;
      y = Math.sin(angle) * radius * 0.72 + (random() - random()) * 900;
    }
    const thickness = (random() - random()) * (1 - radial * 0.8) * 1_150;
    pointPositions.set([
      GALAXY_CENTER.x + x,
      GALAXY_CENTER.z + y,
      thickness,
    ], index * 3);

    const warmth = Math.max(0, 1 - radial * 1.25);
    const brightness = 0.34 + random() * 0.28;
    pointColors.set([
      brightness + warmth * 0.24,
      brightness * 0.7 + warmth * 0.12,
      brightness * 0.54 + (1 - warmth) * 0.16,
    ], index * 3);
  }
  return { positions: pointPositions, colors: pointColors };
}

function makeGalaxyTexture(): THREE.CanvasTexture | null {
  if (typeof document === 'undefined') return null;
  const canvas = document.createElement('canvas');
  canvas.width = 1_024;
  canvas.height = 1_024;
  const context = canvas.getContext('2d');
  if (!context) return null;
  const centre = 512;

  const core = context.createRadialGradient(centre, centre, 0, centre, centre, 240);
  core.addColorStop(0, 'rgba(255, 178, 92, 0.72)');
  core.addColorStop(0.16, 'rgba(220, 111, 40, 0.32)');
  core.addColorStop(0.5, 'rgba(113, 58, 33, 0.12)');
  core.addColorStop(1, 'rgba(35, 39, 52, 0)');
  context.fillStyle = core;
  context.fillRect(0, 0, canvas.width, canvas.height);

  context.globalCompositeOperation = 'lighter';
  context.save();
  context.translate(centre, centre);
  context.rotate(-22 * Math.PI / 180);
  context.scale(1.9, 0.42);
  const bar = context.createRadialGradient(0, 0, 0, 0, 0, 245);
  bar.addColorStop(0, 'rgba(255, 177, 87, 0.32)');
  bar.addColorStop(0.48, 'rgba(185, 88, 39, 0.13)');
  bar.addColorStop(1, 'rgba(60, 53, 54, 0)');
  context.fillStyle = bar;
  context.fillRect(-260, -260, 520, 520);
  context.restore();

  let cloudSeed = 0xa511e9b3;
  const cloudRandom = () => {
    cloudSeed = (Math.imul(cloudSeed, 1_103_515_245) + 12_345) >>> 0;
    return cloudSeed / 4_294_967_296;
  };
  for (let index = 0; index < 190; index += 1) {
    const progress = Math.pow(cloudRandom(), 0.72);
    const radius = progress * 455;
    const angle = cloudRandom() * Math.PI * 2;
    const x = centre + Math.cos(angle) * radius;
    const y = centre + Math.sin(angle) * radius * 0.72;
    const cloudRadius = 18 + cloudRandom() * 42 * (1 - progress * 0.55);
    const cloud = context.createRadialGradient(x, y, 0, x, y, cloudRadius);
    const alpha = 0.012 + cloudRandom() * 0.018;
    cloud.addColorStop(0, `rgba(224, ${Math.round(120 + progress * 42)}, ${Math.round(82 + progress * 50)}, ${alpha})`);
    cloud.addColorStop(1, 'rgba(58, 66, 82, 0)');
    context.fillStyle = cloud;
    context.fillRect(x - cloudRadius, y - cloudRadius, cloudRadius * 2, cloudRadius * 2);
  }
  context.globalCompositeOperation = 'source-over';

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
}

function GalaxyBackdrop({ spatial, zoom }: { spatial: boolean; zoom: number }) {
  const galaxy = useMemo(makeGalaxyPointCloud, []);
  const texture = useMemo(makeGalaxyTexture, []);
  useEffect(() => () => texture?.dispose(), [texture]);
  return <group>
    {texture && <mesh position={[GALAXY_CENTER.x, GALAXY_CENTER.z, -1_350]} renderOrder={-5}>
      <planeGeometry args={[GALAXY_RADIUS_LY * 2.08, GALAXY_RADIUS_LY * 1.5]} />
      <meshBasicMaterial
        map={texture}
        transparent
        opacity={spatial ? 0.82 : 0.72}
        blending={THREE.AdditiveBlending}
        depthWrite={false}
      />
    </mesh>}
    <mesh position={[GALAXY_CENTER.x, GALAXY_CENTER.z, -1_250]} renderOrder={-4}>
      <circleGeometry args={[GALAXY_RADIUS_LY * 1.02, 128]} />
      <meshBasicMaterial color="#27160d" transparent opacity={spatial ? 0.18 : 0.28} depthWrite={false} />
    </mesh>
    <mesh position={[GALAXY_CENTER.x, GALAXY_CENTER.z, -1_100]} renderOrder={-3}>
      <circleGeometry args={[GALAXY_RADIUS_LY * 0.48, 128]} />
      <meshBasicMaterial color="#5d2b11" transparent opacity={spatial ? 0.13 : 0.18} depthWrite={false} />
    </mesh>
    <mesh position={[GALAXY_CENTER.x, GALAXY_CENTER.z, -1_000]} renderOrder={-2}>
      <circleGeometry args={[GALAXY_RADIUS_LY * 0.16, 96]} />
      <meshBasicMaterial color="#d06b20" transparent opacity={spatial ? 0.15 : 0.2} depthWrite={false} />
    </mesh>
    <points renderOrder={-1}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[galaxy.positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[galaxy.colors, 3]} />
      </bufferGeometry>
      <pointsMaterial
        vertexColors
        size={Math.max(18, zoom * (spatial ? 1.4 : 1.1))}
        sizeAttenuation
        transparent
        opacity={spatial ? 0.56 : 0.44}
        depthWrite={false}
      />
    </points>
  </group>;
}

function niceRangeStep(target: number): number {
  const magnitude = 10 ** Math.floor(Math.log10(Math.max(0.01, target)));
  const normalized = target / magnitude;
  const multiplier = normalized < 2.5 ? 1 : normalized < 5 ? 2.5 : normalized < 10 ? 5 : 10;
  return multiplier * magnitude;
}

function rangeStepForView(camera: CameraState, viewport: ViewportSize): number {
  const radius = camera.zoom * Math.min(viewport.width, viewport.height) * 0.48;
  return niceRangeStep(radius / 5);
}

function RangeGrid({
  reference,
  camera,
  viewport,
  spatial,
}: {
  reference: { x: number; z: number };
  camera: CameraState;
  viewport: ViewportSize;
  spatial: boolean;
}) {
  const step = rangeStepForView(camera, viewport);
  const maxRadius = step * 5;
  const lineWidth = Math.max(0.015, camera.zoom * (spatial ? 0.9 : 0.65));
  const axes = useMemo(() => new Float32Array([
    reference.x - maxRadius, reference.z, 0,
    reference.x + maxRadius, reference.z, 0,
    reference.x, reference.z - maxRadius, 0,
    reference.x, reference.z + maxRadius, 0,
  ]), [maxRadius, reference.x, reference.z]);

  return <group>
    <lineSegments position={[0, 0, -2]}>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[axes, 3]} /></bufferGeometry>
      <lineBasicMaterial color="#b36b30" transparent opacity={spatial ? 0.34 : 0.26} depthWrite={false} />
    </lineSegments>
    {Array.from({ length: 5 }, (_, index) => {
      const radius = step * (index + 1);
      return <mesh key={radius} position={[reference.x, reference.z, -1]} renderOrder={0}>
        <ringGeometry args={[Math.max(0.001, radius - lineWidth), radius + lineWidth, 160]} />
        <meshBasicMaterial
          color={index === 4 ? '#b87638' : '#714c31'}
          transparent
          opacity={index === 4 ? 0.5 : 0.34}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>;
    })}
  </group>;
}

function ReferenceMarker({
  reference,
  zoom,
}: {
  reference: { x: number; z: number };
  zoom: number;
}) {
  const inner = Math.max(0.08, zoom * 7);
  const outer = Math.max(0.14, zoom * 13);
  const lineWidth = Math.max(0.018, zoom * 0.8);
  const cross = useMemo(() => new Float32Array([
    reference.x - outer * 1.4, reference.z, 4,
    reference.x - outer * 0.65, reference.z, 4,
    reference.x + outer * 0.65, reference.z, 4,
    reference.x + outer * 1.4, reference.z, 4,
    reference.x, reference.z - outer * 1.4, 4,
    reference.x, reference.z - outer * 0.65, 4,
    reference.x, reference.z + outer * 0.65, 4,
    reference.x, reference.z + outer * 1.4, 4,
  ]), [outer, reference.x, reference.z]);

  return <group>
    {[inner, outer].map((radius, index) => <mesh
      key={radius}
      position={[reference.x, reference.z, 3]}
      renderOrder={12}
    >
      <ringGeometry args={[radius - lineWidth, radius + lineWidth, 80]} />
      <meshBasicMaterial color="#ff8a22" transparent opacity={index === 0 ? 0.9 : 0.5} depthTest={false} />
    </mesh>)}
    <lineSegments renderOrder={13}>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[cross, 3]} /></bufferGeometry>
      <lineBasicMaterial color="#ff9b43" transparent opacity={0.9} depthTest={false} />
    </lineSegments>
    <points position={[reference.x, reference.z, 6]} renderOrder={14}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[new Float32Array([0, 0, 0]), 3]} />
      </bufferGeometry>
      <pointsMaterial
        color="#ffffff"
        size={attenuatedPointSize(zoom, 4)}
        sizeAttenuation
        depthTest={false}
      />
    </points>
  </group>;
}

function SceneContents(props: FoundationRendererProps & { visible: ReturnType<typeof selectVisibleSystems> }) {
  const { visible } = props;
  const spatial = props.scene.camera.pitchDeg > 4;
  const reference = props.reference ?? { name: 'Origin', x: props.scene.origin.x, z: props.scene.origin.z };
  const backgroundPositions = useMemo(
    () => positions(visible.background),
    [visible.background],
  );
  const guaranteedPositions = useMemo(
    () => positions(visible.guaranteed, 3),
    [visible.guaranteed],
  );
  const selected = useMemo(
    () => visible.guaranteed.filter((system) => system.id64 === props.scene.selectedSystemId64),
    [props.scene.selectedSystemId64, visible.guaranteed],
  );
  const selectedPositions = useMemo(
    () => positions(selected, 8),
    [selected],
  );
  const clusters = useMemo(() => buildClusterGeometry(props.scene), [props.scene]);
  const boundaryPositions = useMemo(
    () => new Float32Array(props.regions.boundaries.flatMap((boundary) => [...boundary.source, ...boundary.target])),
    [props.regions.boundaries],
  );
  const selectableSystems = useMemo(
    () => [...visible.guaranteed, ...visible.background],
    [visible.background, visible.guaranteed],
  );
  const heatmap = props.productionOverlays?.heatmap ?? null;
  const aggregateHulls = props.productionOverlays?.aggregateHulls ?? null;
  const cameraDistance = cameraDistanceForView(props.scene.camera, props.viewport);

  const select = useCallback((systems: SystemRecord[], event: ThreeEvent<PointerEvent>) => {
    if (event.index == null) return;
    event.stopPropagation();
    const system = systems[event.index];
    if (!system) return;
    const index = selectableSystems.findIndex((candidate) => candidate.id64 === system.id64);
    const candidates = findOverlappingSystemIds(selectableSystems, index);
    const interaction: MapInteractionEvent = candidates.length > 1
      ? { type: 'overlapChoiceRequired', candidateSystemIds: candidates }
      : {
          type: 'selectSystem',
          systemId64: system.id64,
          clusterAnchorId64: clusterAnchorIdForSystem(props.scene, system.id64),
        };
    props.onInteraction(interaction);
  }, [props, selectableSystems]);

  return <>
    <CameraProjection cameraState={props.scene.camera} />
    <fog
      attach="fog"
      args={[
        '#03070b',
        Math.max(500, cameraDistance * 0.58),
        Math.max(5_000, cameraDistance * 1.65),
      ]}
    />
    <GalaxyBackdrop spatial={spatial} zoom={props.scene.camera.zoom} />
    {props.viewPreset !== 'galaxy' && (
      <>
        <RangeGrid
          reference={reference}
          camera={props.scene.camera}
          viewport={props.viewport}
          spatial={spatial}
        />
        <ReferenceMarker reference={reference} zoom={props.scene.camera.zoom} />
      </>
    )}
    {heatmap && <points>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[heatmap.positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[heatmap.colors, 3]} />
      </bufferGeometry>
      <pointsMaterial
        vertexColors
        size={Math.min(
          heatmap.voxelSize * 0.72,
          attenuatedPointSize(props.scene.camera.zoom, 10),
        )}
        sizeAttenuation
        transparent
        opacity={0.34}
      />
    </points>}
    {aggregateHulls && <lineSegments>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[aggregateHulls.linePositions, 3]} />
        <bufferAttribute attach="attributes-color" args={[aggregateHulls.lineColors, 3]} />
      </bufferGeometry>
      <lineBasicMaterial vertexColors transparent opacity={0.42} />
    </lineSegments>}
    <RegionBoundaryLines positions={boundaryPositions} viewport={props.viewport} spatial={spatial} />
    <points renderOrder={7}>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[backgroundPositions, 3]} /></bufferGeometry>
      <pointsMaterial
        color="#ff7518"
        size={attenuatedPointSize(props.scene.camera.zoom, 18)}
        sizeAttenuation
        transparent
        opacity={0.2}
        depthTest={false}
      />
    </points>
    <points onPointerDown={(event) => select(visible.background, event)} renderOrder={8}>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[backgroundPositions, 3]} /></bufferGeometry>
      <pointsMaterial
        color="#ff9a3d"
        size={attenuatedPointSize(props.scene.camera.zoom, 8)}
        sizeAttenuation
        transparent
        opacity={1}
        depthTest={false}
      />
    </points>
    <points onPointerDown={(event) => select(visible.guaranteed, event)} renderOrder={9}>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[guaranteedPositions, 3]} /></bufferGeometry>
      <pointsMaterial
        color="#ff9a3d"
        size={attenuatedPointSize(props.scene.camera.zoom, 8)}
        sizeAttenuation
        depthTest={false}
      />
    </points>
    <points onPointerDown={(event) => select(selected, event)} renderOrder={10}>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[selectedPositions, 3]} /></bufferGeometry>
      <pointsMaterial
        color="#ffffff"
        size={attenuatedPointSize(props.scene.camera.zoom, 13)}
        sizeAttenuation
        depthTest={false}
      />
    </points>
    {clusters.map(({ cluster, anchor, edgePositions, hullPositions }) => <group key={`${cluster.anchorId64}:${cluster.label}`}>
      <lineSegments>
        <bufferGeometry><bufferAttribute attach="attributes-position" args={[edgePositions, 3]} /></bufferGeometry>
        <lineBasicMaterial color="#ff8a65" />
      </lineSegments>
      {hullPositions && <lineSegments>
        <bufferGeometry><bufferAttribute attach="attributes-position" args={[hullPositions, 3]} /></bufferGeometry>
        <lineBasicMaterial color="#ffd180" />
      </lineSegments>}
      {!hullPositions && anchor && <mesh position={[anchor.coords.x, anchor.coords.z, anchor.coords.y]}>
        <ringGeometry args={[cluster.radiusLy * 0.98, cluster.radiusLy, 64]} />
        <meshBasicMaterial color="#ffd180" transparent opacity={0.75} side={THREE.DoubleSide} />
      </mesh>}
    </group>)}
  </>;
}

function stableRegionLabels(labels: RegionLabel[]): RegionLabel[] {
  if (labels.length <= 20) return labels;
  const selected = new Map<number, RegionLabel>();
  const centreLabel = labels.find((label) => label.name === 'Galactic Centre');
  if (centreLabel) selected.set(centreLabel.id, centreLabel);

  const chooseBySector = (
    sectors: number,
    score: (radius: number) => number,
  ) => {
    const buckets = new Map<number, { label: RegionLabel; score: number }>();
    labels.forEach((label) => {
      if (label.id === centreLabel?.id) return;
      const dx = label.position[0] - GALAXY_CENTER.x;
      const dz = label.position[1] - GALAXY_CENTER.z;
      const angle = (Math.atan2(dz, dx) + Math.PI * 2) % (Math.PI * 2);
      const sector = Math.floor(angle / (Math.PI * 2) * sectors);
      const candidateScore = score(Math.hypot(dx, dz));
      const current = buckets.get(sector);
      if (!current || candidateScore > current.score) {
        buckets.set(sector, { label, score: candidateScore });
      }
    });
    buckets.forEach(({ label }) => selected.set(label.id, label));
  };

  chooseBySector(12, (radius) => radius);
  chooseBySector(6, (radius) => -Math.abs(radius - 17_000));
  return [...selected.values()];
}

function projectLabels(props: FoundationRendererProps): ProjectedLabel[] {
  if (props.viewPreset !== 'galaxy') return [];
  const size = props.viewport;
  const camera = new THREE.PerspectiveCamera(
    42,
    size.width / Math.max(1, size.height),
    0.1,
    500_000,
  );
  configureRenderCamera(camera, size, props.scene.camera);
  camera.updateMatrixWorld(true);

  return stableRegionLabels(props.regions.labels).map((label) => {
    const point = new THREE.Vector3(...label.position).project(camera);
    const screen = {
      x: (point.x * 0.5 + 0.5) * size.width,
      z: (-point.y * 0.5 + 0.5) * size.height,
    };
    return {
      ...label,
      screen,
      visible: point.z >= -1 && point.z <= 1
        && screen.x > -120 && screen.x < size.width + 120
        && screen.z > -30 && screen.z < size.height + 30,
    };
  });
}

function projectSystemLabels(
  props: FoundationRendererProps,
  systems: SystemRecord[],
): Array<{
  id: number;
  name: string;
  screen: { x: number; z: number };
  selected: boolean;
}> {
  if (props.viewPreset === 'galaxy' || systems.length === 0) return [];
  const size = props.viewport;
  const camera = new THREE.PerspectiveCamera(
    42,
    size.width / Math.max(1, size.height),
    0.1,
    500_000,
  );
  configureRenderCamera(camera, size, props.scene.camera);
  camera.updateMatrixWorld(true);

  const occupied: Array<{ x: number; z: number }> = [];
  return systems
    .slice(0, 40)
    .map((system) => {
      const point = new THREE.Vector3(
        system.coords.x,
        system.coords.z,
        system.coords.y,
      ).project(camera);
      const screen = {
        x: (point.x * 0.5 + 0.5) * size.width,
        z: (-point.y * 0.5 + 0.5) * size.height,
      };
      if (
        screen.x < -80
        || screen.x > size.width + 80
        || screen.z < -30
        || screen.z > size.height + 30
      ) return null;

      const overlapCount = occupied.filter((candidate) => (
        Math.abs(candidate.x - screen.x) < 16 && Math.abs(candidate.z - screen.z) < 16
      )).length;
      occupied.push(screen);
      return {
        id: system.id64,
        name: system.name,
        screen: { x: screen.x, z: screen.z - overlapCount * 18 },
        selected: system.id64 === props.scene.selectedSystemId64,
      };
    })
    .filter((label): label is NonNullable<typeof label> => label != null);
}

export function R3FMapFoundation(props: FoundationRendererProps) {
  const { onVisibilityChange } = props;
  const pointer = useRef<{ x: number; y: number; camera: CameraState } | null>(null);
  const rendererRef = useRef<HTMLDivElement>(null);
  const visible = useMemo(
    () => selectVisibleSystems(props.scene, props.viewport, props.maxBackgroundPoints),
    [props.maxBackgroundPoints, props.scene, props.viewport],
  );
  const labels = useMemo(() => projectLabels(props), [props]);
  const highlightedIds = useMemo(() => highlightedSystemIds(props.scene.highlights), [props.scene.highlights]);
  const clusters = useMemo(() => buildClusterGeometry(props.scene), [props.scene]);
  const systemLabels = useMemo(() => {
    const byId = new Map<number, SystemRecord>();
    [...visible.background, ...visible.guaranteed].forEach((system) => byId.set(system.id64, system));
    return projectSystemLabels(props, [...byId.values()]);
  }, [props, visible.background, visible.guaranteed]);
  const spatial = props.scene.camera.pitchDeg > 4;
  const viewPreset = props.viewPreset ?? 'results';
  const reference = props.reference ?? {
    name: 'Origin',
    x: props.scene.origin.x,
    z: props.scene.origin.z,
  };
  const rangeStep = rangeStepForView(props.scene.camera, props.viewport);
  const rangeLabels = useMemo(() => {
    if (viewPreset === 'galaxy' || spatial) return [];
    const centreX = props.viewport.width / 2
      + (reference.x - props.scene.camera.center.x) / props.scene.camera.zoom;
    const centreY = props.viewport.height / 2
      - (reference.z - props.scene.camera.center.z) / props.scene.camera.zoom;
    return Array.from({ length: 5 }, (_, index) => {
      const distance = rangeStep * (index + 1);
      return {
        distance,
        x: centreX + distance / props.scene.camera.zoom,
        y: centreY,
      };
    });
  }, [
    props.scene.camera,
    props.viewport.height,
    props.viewport.width,
    rangeStep,
    reference.x,
    reference.z,
    spatial,
    viewPreset,
  ]);

  useEffect(() => onVisibilityChange?.(visible.metadata), [onVisibilityChange, visible.metadata]);

  const emitCamera = useCallback((camera: CameraState) => {
    props.onInteraction({ type: 'cameraChanged', camera });
  }, [props]);

  const handleWheel = useCallback((event: WheelEvent) => {
    event.preventDefault();
    emitCamera(zoomCamera(
      props.scene.camera,
      event.deltaY,
      props.viewport,
      props.galaxyBounds,
    ));
  }, [
    emitCamera,
    props.galaxyBounds,
    props.scene.camera,
    props.viewport,
  ]);

  useEffect(() => {
    const element = rendererRef.current;
    if (!element) return undefined;
    element.addEventListener('wheel', handleWheel, { passive: false, capture: true });
    return () => element.removeEventListener('wheel', handleWheel, { capture: true });
  }, [handleWheel]);

  return <div
    ref={rendererRef}
    className="map-foundation-renderer"
    data-projection="perspective"
    data-camera-view={spatial ? 'tilted' : 'top-down'}
    data-view-preset={viewPreset}
    data-camera-bearing={props.scene.camera.bearingDeg}
    data-camera-pitch={props.scene.camera.pitchDeg}
    data-camera-zoom={props.scene.camera.zoom}
    data-camera-center-x={props.scene.camera.center.x}
    data-camera-center-z={props.scene.camera.center.z}
    onPointerDownCapture={(event) => {
      pointer.current = { x: event.clientX, y: event.clientY, camera: props.scene.camera };
      event.currentTarget.setPointerCapture(event.pointerId);
    }}
    onPointerMove={(event) => {
      if (!pointer.current || event.buttons !== 1) return;
      const dx = event.clientX - pointer.current.x;
      const dy = event.clientY - pointer.current.y;
      if (event.shiftKey) {
        emitCamera({
          ...pointer.current.camera,
          bearingDeg: 0,
          pitchDeg: Math.max(
            MIN_CAMERA_PITCH_DEG,
            Math.min(MAX_CAMERA_PITCH_DEG, pointer.current.camera.pitchDeg + dy * 0.2),
          ),
        });
      } else {
        const bearing = pointer.current.camera.bearingDeg * Math.PI / 180;
        const screenX = -dx * pointer.current.camera.zoom;
        const screenZ = dy * pointer.current.camera.zoom;
        const center = clampCameraCenter({
          x: pointer.current.camera.center.x + screenX * Math.cos(bearing) + screenZ * Math.sin(bearing),
          z: pointer.current.camera.center.z - screenX * Math.sin(bearing) + screenZ * Math.cos(bearing),
        }, pointer.current.camera.zoom, props.viewport, props.galaxyBounds);
        emitCamera({
          ...pointer.current.camera,
          center,
        });
      }
    }}
    onPointerUp={() => { pointer.current = null; }}
    onPointerCancel={() => { pointer.current = null; }}>
    <Canvas
      frameloop="demand"
      dpr={[1, 2]}
      camera={{ fov: 42, near: 0.1, far: 500_000 }}
      gl={{ antialias: true, powerPreference: 'high-performance' }}
      onCreated={({ gl }) => {
        const canvas = gl.domElement;
        canvas.addEventListener('webglcontextlost', (event) => {
          event.preventDefault();
          props.onInteraction({ type: 'contextStateChanged', state: 'lost' });
        });
        canvas.addEventListener('webglcontextrestored', () => {
          props.onInteraction({ type: 'contextStateChanged', state: 'restored' });
        });
        props.onReady?.();
      }}>
      <color attach="background" args={['#03070b']} />
      <GpuTimingBridge onReady={props.onGpuTimerReady} />
      <SceneContents {...props} visible={visible} />
    </Canvas>
    <div className="map-foundation-map-readout" aria-hidden="true">
      <strong>
        {viewPreset === 'galaxy'
          ? 'Whole galaxy'
          : viewPreset === 'reference'
            ? `${reference.name} origin chart`
            : 'Finder result chart'}
      </strong>
      <span>
        {viewPreset === 'galaxy'
          ? `${props.regions.labels.length} named regions · galactic plane`
          : `${rangeStep.toLocaleString()} LY rings · ${reference.name} at centre`}
      </span>
      <span>
        Drag to pan · Shift-drag to tilt · Scroll to zoom
      </span>
    </div>
    <div className="map-foundation-labels" aria-hidden="true">
      {labels.filter((label) => label.visible).map((label) => <span key={label.id}
        style={{ left: label.screen.x, top: label.screen.z }}>{label.name}</span>)}
    </div>
    <div className="map-foundation-range-labels" aria-hidden="true">
      {rangeLabels.map((label) => <span
        key={label.distance}
        style={{ left: label.x, top: label.y }}
      >
        {label.distance.toLocaleString()} LY
      </span>)}
    </div>
    <div className="map-foundation-system-labels" aria-hidden="true">
      {systemLabels.map((label) => <span
        key={label.id}
        className={label.selected ? 'is-selected' : undefined}
        style={{ left: label.screen.x, top: label.screen.z }}
      >
        {label.name}
      </span>)}
    </div>
    <div className="map-foundation-cluster-labels" aria-hidden="true">
      {clusters.flatMap(({ cluster, anchor }) => {
        if (!anchor) return [];
        const label = projectLabels({
          ...props,
          viewPreset: 'galaxy',
          regions: {
            boundaries: [],
            labels: [{
              id: cluster.anchorId64,
              name: cluster.label,
              position: [
                anchor.coords.x,
                anchor.coords.z,
                anchor.coords.y,
              ],
            }],
          },
        })[0];
        return label?.visible ? [<span key={`${cluster.anchorId64}:${cluster.label}`}
          style={{ left: label.screen.x, top: label.screen.z - 18 }}>{cluster.label}</span>] : [];
      })}
    </div>
    <output className="map-foundation-render-stats" aria-label="Renderer draw summary">
      {(visible.metadata.returnedBackground + visible.metadata.guaranteedCount).toLocaleString()}
      {' Finder systems · '}{highlightedIds.size} highlighted
      {props.productionOverlays?.heatmap && ` · ${props.productionOverlays.heatmap.cellCount.toLocaleString()} heatmap`}
      {props.productionOverlays?.aggregateHulls && ` · ${props.productionOverlays.aggregateHulls.hullCount.toLocaleString()} aggregate hulls`}
    </output>
  </div>;
}
