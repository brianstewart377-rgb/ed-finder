import { type ThreeEvent, useThree } from '@react-three/fiber';
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import * as THREE from 'three';
import type {
  CameraState,
  MapInteractionEvent,
  SystemRecord,
} from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';
import type {
  FoundationRendererProps,
  ProjectedLabel,
  ViewportSize,
} from './types';
import { measureRendererGpuTiming } from './performance';
import { declutterRegionLabels } from './map-presentation';
import { GlowPointsMaterial } from './glowPoints';
import { RealStarLayer } from './RealStarLayer';
import { DensitySwirl } from './DensitySwirl';
import { VolumetricGalaxy } from './VolumetricGalaxy';
import { PowerplayPointLayer } from './PowerplayPointLayer';
import {
  buildClusterGeometry,
  clusterAnchorIdForSystem,
  findOverlappingSystemIds,
  selectVisibleSystems,
} from './visibility';
import {
  attenuatedPointSize,
  cameraDistanceForView,
  CAMERA_VIEWPORT_HEIGHT_RATIO,
  MAX_CAMERA_PITCH_DEG,
  MIN_CAMERA_PITCH_DEG,
} from './camera';
import { GalaxyBackdrop } from './GalaxyBackdrop';
import { RouteLayer } from './RouteLayer';
import {
  buildExplorationTrailBuffers,
  buildExplorationVisitBuffers,
} from './explorationGeometry';
import {
  CameraCenterGuide,
  RangeGrid,
  RegionBoundaryLines,
  ReferenceMarker,
} from './SceneDecorations';
import { realStarLayerTargets, useRealStarFade } from './realStarFade';

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

export function projectWorldPoint(
  cameraState: CameraState,
  viewport: ViewportSize,
  point: [number, number, number],
): { x: number; y: number; depth: number } {
  const camera = new THREE.PerspectiveCamera(
    42,
    viewport.width / Math.max(1, viewport.height),
    0.1,
    500_000,
  );
  configureRenderCamera(camera, viewport, cameraState);
  camera.updateMatrixWorld(true);
  const projected = new THREE.Vector3(...point).project(camera);
  return {
    x: (projected.x * 0.5 + 0.5) * viewport.width,
    y: (-projected.y * 0.5 + 0.5) * viewport.height,
    depth: projected.z,
  };
}

export function CameraProjection({ cameraState }: { cameraState: CameraState }) {
  const { camera, size, invalidate } = useThree();
  useEffect(() => {
    configureRenderCamera(camera as THREE.PerspectiveCamera, size, cameraState);
    invalidate();
  }, [camera, cameraState, invalidate, size]);
  return null;
}

export function RendererSizeSync({ viewport }: { viewport: ViewportSize }) {
  const {
    get,
    gl,
    invalidate,
    setDpr,
    setSize,
  } = useThree();

  useLayoutEffect(() => {
    const canvas = gl.domElement;

    let frame: number | null = null;
    let lastWidth: number | null = null;
    let lastHeight: number | null = null;
    let lastDpr: number | null = null;
    const measure = () => {
      const rect = canvas.getBoundingClientRect();
      const width = Math.max(1, Math.round(rect.width || viewport.width));
      const height = Math.max(1, Math.round(rect.height || viewport.height));
      const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
      return { width, height, dpr };
    };
    const sync = () => {
      frame = null;
      const { width, height, dpr } = measure();
      const state = get();

      if (Math.abs(state.viewport.dpr - dpr) > 0.001) setDpr(dpr);
      if (state.size.width !== width || state.size.height !== height) {
        setSize(width, height);
      }

      const expectedWidth = Math.round(width * dpr);
      const expectedHeight = Math.round(height * dpr);
      const drawingBuffer = gl.getDrawingBufferSize(new THREE.Vector2());
      if (
        Math.abs(drawingBuffer.x - expectedWidth) > 1
        || Math.abs(drawingBuffer.y - expectedHeight) > 1
      ) {
        gl.setPixelRatio(dpr);
        gl.setSize(width, height, false);
      }
      gl.setViewport(0, 0, width, height);

      const syncedBuffer = gl.getDrawingBufferSize(new THREE.Vector2());
      const context = gl.getContext();
      const syncedViewport = context.getParameter(context.VIEWPORT) as Int32Array;
      canvas.dataset.cssWidth = String(width);
      canvas.dataset.cssHeight = String(height);
      canvas.dataset.drawingBufferWidth = String(syncedBuffer.x);
      canvas.dataset.drawingBufferHeight = String(syncedBuffer.y);
      canvas.dataset.viewportX = String(syncedViewport[0]);
      canvas.dataset.viewportY = String(syncedViewport[1]);
      canvas.dataset.viewportWidth = String(syncedViewport[2]);
      canvas.dataset.viewportHeight = String(syncedViewport[3]);
      canvas.dataset.contextLost = String(context.isContextLost());
      canvas.dataset.drawingBufferSynced = String(
        Math.abs(syncedBuffer.x - expectedWidth) <= 1
        && Math.abs(syncedBuffer.y - expectedHeight) <= 1,
      );
      invalidate();
      lastWidth = width;
      lastHeight = height;
      lastDpr = dpr;
    };
    const queueSync = () => {
      const { width, height, dpr } = measure();
      if (
        lastWidth == null
        || lastHeight == null
        || lastDpr == null
        || width !== lastWidth
        || height !== lastHeight
        || Math.abs(dpr - lastDpr) > 0.001
      ) {
        canvas.dataset.drawingBufferSynced = 'false';
      }
      if (frame != null) window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(sync);
    };

    sync();
    const observer = typeof ResizeObserver === 'undefined'
      ? null
      : new ResizeObserver(queueSync);
    observer?.observe(canvas);
    window.addEventListener('resize', queueSync);
    window.visualViewport?.addEventListener('resize', queueSync);
    return () => {
      observer?.disconnect();
      window.removeEventListener('resize', queueSync);
      window.visualViewport?.removeEventListener('resize', queueSync);
      if (frame != null) window.cancelAnimationFrame(frame);
    };
  }, [
    get,
    gl,
    invalidate,
    setDpr,
    setSize,
    viewport.height,
    viewport.width,
  ]);

  return null;
}

export function GpuTimingBridge({ onReady }: { onReady: FoundationRendererProps['onGpuTimerReady'] }) {
  const { camera, gl, scene } = useThree();
  useEffect(() => {
    if (!onReady) return undefined;
    onReady((sampleCount) => measureRendererGpuTiming(gl, scene, camera, sampleCount));
    return () => onReady(null);
  }, [camera, gl, onReady, scene]);
  return null;
}

export function SceneContents(props: FoundationRendererProps & { visible: ReturnType<typeof selectVisibleSystems> }) {
  const { visible } = props;
  const [hoveredSystemId, setHoveredSystemId] = useState<number | null>(null);
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
  const selectableSystems = useMemo(
    () => [...visible.guaranteed, ...visible.background],
    [visible.background, visible.guaranteed],
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
  const emphasizedSystems = useMemo(
    () => selectableSystems.filter((system) => (
      system.id64 === props.scene.selectedSystemId64 || system.id64 === hoveredSystemId
    )),
    [hoveredSystemId, props.scene.selectedSystemId64, selectableSystems],
  );
  const heatmap = props.productionOverlays?.heatmap ?? null;
  const aggregateHulls = props.productionOverlays?.aggregateHulls ?? null;
  const realStars = props.productionOverlays?.realStars ?? null;
  const powerplay = props.productionOverlays?.powerplay ?? null;
  const explorationVisits = props.productionOverlays?.explorationVisits ?? null;
  const explorationTrail = props.productionOverlays?.explorationTrail ?? null;
  const explorationVisitBuffers = useMemo(
    () => buildExplorationVisitBuffers(
      explorationVisits ?? [],
      props.productionOverlays?.showExplorationCompleteness ?? false,
    ),
    [explorationVisits, props.productionOverlays?.showExplorationCompleteness],
  );
  const explorationTrailBuffers = useMemo(
    () => buildExplorationTrailBuffers(explorationTrail ?? []),
    [explorationTrail],
  );
  const cameraDistance = cameraDistanceForView(props.scene.camera, props.viewport);

  // ── Real-star fade logic (Phase 3) ──────────────────────────────────
  // Compute target opacities based on zoom state (box) and cap state (truncated)
  const truncated = props.productionOverlays?.realStarsTruncated ?? false;
  const {
    starsOpacity: targetStarsOpacity,
  } = realStarLayerTargets(realStars?.length ?? 0, truncated);
  const densitySwirlGroupRef = useRef<THREE.Group | null>(null);
  const starsGroupRef = useRef<THREE.Group | null>(null);
  const applyRealStarOpacities = useCallback((opacities: {
    starsOpacity: number;
  }) => {
    if (starsGroupRef.current) {
      starsGroupRef.current.traverse((child) => {
        if (child instanceof THREE.Points && child.material instanceof THREE.ShaderMaterial) {
          child.material.uniforms.uOpacity.value = opacities.starsOpacity;
        } else if (child instanceof THREE.Points && child.material instanceof THREE.Material) {
          child.material.opacity = opacities.starsOpacity;
        }
      });
    }
  }, []);
  const {
    densitySwirlOpacityRef: currentDensitySwirlOpacityRef,
    starsOpacityRef: currentStarsOpacityRef,
  } = useRealStarFade({
    densitySwirlOpacity: 1,
    starsOpacity: targetStarsOpacity,
  }, applyRealStarOpacities);

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
  const hover = useCallback((systems: SystemRecord[], event: ThreeEvent<PointerEvent>) => {
    if (event.index == null) return;
    const system = systems[event.index];
    if (system) setHoveredSystemId(system.id64);
  }, []);
  const markerRingRadius = Math.max(0.16, props.scene.camera.zoom * 10);
  const markerRingWidth = Math.max(0.02, props.scene.camera.zoom * 0.7);

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
    <CameraCenterGuide camera={props.scene.camera} viewport={props.viewport} />
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
    <VolumetricGalaxy opacity={currentDensitySwirlOpacityRef.current} />
    {heatmap && (
      <group ref={densitySwirlGroupRef}>
        <DensitySwirl
          heatmap={heatmap}
          opacity={currentDensitySwirlOpacityRef.current}
        />
      </group>
    )}
    {realStars && realStars.length > 0 && (
      <group ref={starsGroupRef}>
        <RealStarLayer
          systems={realStars}
          zoom={props.scene.camera.zoom}
          opacity={currentStarsOpacityRef.current}
          onSelect={targetStarsOpacity > 0 ? props.onViewportSystemSelect : undefined}
        />
      </group>
    )}
    {powerplay && powerplay.length > 0 && (
      <PowerplayPointLayer systems={powerplay} zoom={props.scene.camera.zoom} />
    )}
    {explorationVisits && explorationVisits.length > 0 && <points renderOrder={12}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[explorationVisitBuffers.positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[explorationVisitBuffers.colors, 3]} />
      </bufferGeometry>
      <GlowPointsMaterial
        vertexColors
        size={explorationVisits[0]?.kind === 'density'
          ? Math.min(explorationVisits[0].cell_size ?? 100, attenuatedPointSize(props.scene.camera.zoom, 16))
          : attenuatedPointSize(props.scene.camera.zoom, 10)}
        sizeAttenuation
        opacity={0.8}
      />
    </points>}
    {explorationTrailBuffers.positions.length > 0 && <lineSegments renderOrder={10}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[explorationTrailBuffers.positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[explorationTrailBuffers.colors, 3]} />
      </bufferGeometry>
      <lineBasicMaterial vertexColors transparent opacity={0.82} depthWrite={false} />
    </lineSegments>}
    {explorationTrailBuffers.arrowPositions.length > 0 && <lineSegments renderOrder={11}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[explorationTrailBuffers.arrowPositions, 3]} />
      </bufferGeometry>
      <lineBasicMaterial color="#83f3ff" transparent opacity={0.9} depthWrite={false} />
    </lineSegments>}
    {aggregateHulls && <lineSegments>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[aggregateHulls.linePositions, 3]} />
        <bufferAttribute attach="attributes-color" args={[aggregateHulls.lineColors, 3]} />
      </bufferGeometry>
      <lineBasicMaterial vertexColors transparent opacity={0.42} />
    </lineSegments>}
    <RegionBoundaryLines boundaries={props.regions.boundaries} viewport={props.viewport} spatial={spatial} />
    {props.scene.layers.some((layer) => layer.type === 'routes' && layer.visible) && (
      <RouteLayer scene={props.scene} />
    )}
    <points
      onPointerDown={(event) => select(visible.background, event)}
      onPointerOver={(event) => hover(visible.background, event)}
      onPointerOut={() => setHoveredSystemId(null)}
      renderOrder={targetStarsOpacity === 1 ? 5 : 8}
    >
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[backgroundPositions, 3]} /></bufferGeometry>
      <GlowPointsMaterial
        color="#ff9a3d"
        size={attenuatedPointSize(props.scene.camera.zoom, 8)}
        sizeAttenuation
      />
    </points>
    <points
      onPointerDown={(event) => select(visible.guaranteed, event)}
      onPointerOver={(event) => hover(visible.guaranteed, event)}
      onPointerOut={() => setHoveredSystemId(null)}
      renderOrder={targetStarsOpacity === 1 ? 6 : 9}
    >
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[guaranteedPositions, 3]} /></bufferGeometry>
      <GlowPointsMaterial
        color="#ff9a3d"
        size={attenuatedPointSize(props.scene.camera.zoom, 7)}
        sizeAttenuation
      />
    </points>
    <points onPointerDown={(event) => select(selected, event)} renderOrder={10}>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[selectedPositions, 3]} /></bufferGeometry>
      <GlowPointsMaterial
        color="#ffffff"
        size={attenuatedPointSize(props.scene.camera.zoom, 7)}
        sizeAttenuation
      />
    </points>
    {emphasizedSystems.map((system) => <mesh
      key={`marker-ring-${system.id64}`}
      position={[system.coords.x, system.coords.z, system.coords.y + 6]}
      renderOrder={11}
    >
      <ringGeometry args={[
        markerRingRadius - markerRingWidth,
        markerRingRadius + markerRingWidth,
        48,
      ]} />
      <meshBasicMaterial
        color={system.id64 === props.scene.selectedSystemId64 ? '#fff2e4' : '#ffad62'}
        transparent
        opacity={0.9}
        depthTest={false}
        side={THREE.DoubleSide}
      />
    </mesh>)}
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

export function projectLabels(
  props: FoundationRendererProps,
  persistentRegionId?: number,
): ProjectedLabel[] {
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

  const projected = props.regions.labels.map((label) => {
    const point = new THREE.Vector3(...label.position).project(camera);
    const screen = {
      x: (point.x * 0.5 + 0.5) * size.width,
      z: (-point.y * 0.5 + 0.5) * size.height,
    };
    return {
      ...label,
      screen,
      depthVisible: point.z >= -1 && point.z <= 1,
    };
  });
  return declutterRegionLabels(
    projected,
    size,
    props.scene.camera.zoom,
    persistentRegionId,
    props.labelSafeArea,
  );
}

export function projectSystemLabels(
  props: FoundationRendererProps,
  systems: SystemRecord[],
): Array<{
  id: number;
  name: string;
  screen: { x: number; z: number };
  selected: boolean;
}> {
  if (props.viewPreset === 'galaxy' || systems.length === 0) return [];
  const selected = systems.find((system) => system.id64 === props.scene.selectedSystemId64);
  if (!selected) return [];
  const size = props.viewport;
  const camera = new THREE.PerspectiveCamera(
    42,
    size.width / Math.max(1, size.height),
    0.1,
    500_000,
  );
  configureRenderCamera(camera, size, props.scene.camera);
  camera.updateMatrixWorld(true);

  return [selected]
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

      return {
        id: system.id64,
        name: system.name,
        screen,
        selected: system.id64 === props.scene.selectedSystemId64,
      };
    })
    .filter((label): label is NonNullable<typeof label> => label != null);
}
