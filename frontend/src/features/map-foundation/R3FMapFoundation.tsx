import { Canvas, type ThreeEvent, useThree } from '@react-three/fiber';
import { useCallback, useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import type {
  CameraState,
  MapInteractionEvent,
  SystemRecord,
} from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';
import { toThreeJSR3F } from '../../../../artifacts/map-foundation/stage-26b/map-renderer-adapter';
import type { FoundationRendererProps, ProjectedLabel } from './types';
import {
  buildClusterGeometry,
  clusterAnchorIdForSystem,
  findOverlappingSystemIds,
  highlightedSystemIds,
  selectVisibleSystems,
} from './visibility';

const MIN_ZOOM_LY_PER_PIXEL = 2;
const MAX_ZOOM_LY_PER_PIXEL = 4_096;

function positions(systems: SystemRecord[], z = 0): Float32Array {
  const values = new Float32Array(systems.length * 3);
  systems.forEach((system, index) => values.set([system.coords.x, system.coords.z, z], index * 3));
  return values;
}

function CameraProjection({ cameraState }: { cameraState: CameraState }) {
  const { camera, size, invalidate } = useThree();
  useEffect(() => {
    const mapped = toThreeJSR3F(cameraState) as {
      position: [number, number, number];
      rotation: [number, number, number];
      zoom: number;
    };
    const orthographic = camera as THREE.OrthographicCamera;
    orthographic.left = -size.width / 2;
    orthographic.right = size.width / 2;
    orthographic.top = size.height / 2;
    orthographic.bottom = -size.height / 2;
    orthographic.position.set(...mapped.position);
    orthographic.rotation.set(...mapped.rotation);
    orthographic.zoom = mapped.zoom;
    orthographic.updateProjectionMatrix();
    invalidate();
  }, [camera, cameraState, invalidate, size]);
  return null;
}

function SceneContents(props: FoundationRendererProps & { visible: ReturnType<typeof selectVisibleSystems> }) {
  const { visible } = props;
  const backgroundPositions = useMemo(() => positions(visible.background), [visible.background]);
  const guaranteedPositions = useMemo(() => positions(visible.guaranteed, 1), [visible.guaranteed]);
  const selected = useMemo(
    () => visible.guaranteed.filter((system) => system.id64 === props.scene.selectedSystemId64),
    [props.scene.selectedSystemId64, visible.guaranteed],
  );
  const selectedPositions = useMemo(() => positions(selected, 3), [selected]);
  const clusters = useMemo(() => buildClusterGeometry(props.scene), [props.scene]);
  const boundaryPositions = useMemo(
    () => new Float32Array(props.regions.boundaries.flatMap((boundary) => [...boundary.source, ...boundary.target])),
    [props.regions.boundaries],
  );
  const selectableSystems = useMemo(
    () => [...visible.guaranteed, ...visible.background],
    [visible.background, visible.guaranteed],
  );

  const select = useCallback((systems: SystemRecord[], event: ThreeEvent<PointerEvent>) => {
    if (event.index == null) return;
    event.stopPropagation();
    const system = systems[event.index];
    if (!system) return;
    const index = selectableSystems.findIndex((candidate) => candidate.id64 === system.id64);
    const candidates = findOverlappingSystemIds(selectableSystems, index);
    const interaction: MapInteractionEvent = candidates.length > 1
      ? { type: 'overlapChoiceRequired', candidateSystemIds: candidates }
      : { type: 'selectSystem', systemId64: system.id64, clusterAnchorId64: clusterAnchorIdForSystem(props.scene, system.id64) };
    props.onInteraction(interaction);
  }, [props, selectableSystems]);

  return <>
    <CameraProjection cameraState={props.scene.camera} />
    <lineSegments>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[
          boundaryPositions,
          3,
        ]} />
      </bufferGeometry>
      <lineBasicMaterial color="#547b96" transparent opacity={0.5} />
    </lineSegments>
    <points onPointerDown={(event) => select(visible.background, event)}>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[backgroundPositions, 3]} /></bufferGeometry>
      <pointsMaterial color="#5e8093" size={1.5} sizeAttenuation={false} transparent opacity={0.7} />
    </points>
    <points onPointerDown={(event) => select(visible.guaranteed, event)}>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[guaranteedPositions, 3]} /></bufferGeometry>
      <pointsMaterial color="#ffb454" size={7} sizeAttenuation={false} />
    </points>
    <points onPointerDown={(event) => select(selected, event)}>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[selectedPositions, 3]} /></bufferGeometry>
      <pointsMaterial color="#ffffff" size={11} sizeAttenuation={false} />
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
      {!hullPositions && anchor && <mesh position={[anchor.coords.x, anchor.coords.z, 1]}>
        <ringGeometry args={[cluster.radiusLy * 0.98, cluster.radiusLy, 64]} />
        <meshBasicMaterial color="#ffd180" transparent opacity={0.75} side={THREE.DoubleSide} />
      </mesh>}
    </group>)}
  </>;
}

function projectLabels(props: FoundationRendererProps): ProjectedLabel[] {
  const { camera } = props.scene;
  const bearing = camera.bearingDeg * Math.PI / 180;
  const pitchScale = Math.cos(camera.pitchDeg * Math.PI / 180);
  const cosine = Math.cos(bearing);
  const sine = Math.sin(bearing);
  return props.regions.labels.map((label) => {
    const dx = (label.position[0] - camera.center.x) / camera.zoom;
    const dz = (label.position[1] - camera.center.z) / camera.zoom;
    const x = dx * cosine - dz * sine;
    const z = (dx * sine + dz * cosine) * pitchScale;
    const screen = { x: props.viewport.width / 2 + x, z: props.viewport.height / 2 - z };
    return {
      ...label,
      screen,
      visible: screen.x > -120 && screen.x < props.viewport.width + 120
        && screen.z > -30 && screen.z < props.viewport.height + 30,
    };
  });
}

export function R3FMapFoundation(props: FoundationRendererProps) {
  const { onVisibilityChange } = props;
  const pointer = useRef<{ x: number; y: number; camera: CameraState } | null>(null);
  const visible = useMemo(
    () => selectVisibleSystems(props.scene, props.viewport, props.maxBackgroundPoints),
    [props.maxBackgroundPoints, props.scene, props.viewport],
  );
  const labels = useMemo(() => projectLabels(props), [props]);
  const highlightedIds = useMemo(() => highlightedSystemIds(props.scene.highlights), [props.scene.highlights]);
  const clusters = useMemo(() => buildClusterGeometry(props.scene), [props.scene]);

  useEffect(() => onVisibilityChange?.(visible.metadata), [onVisibilityChange, visible.metadata]);

  const emitCamera = useCallback((camera: CameraState) => {
    props.onInteraction({ type: 'cameraChanged', camera });
  }, [props]);

  return <div className="map-foundation-renderer"
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
          bearingDeg: pointer.current.camera.bearingDeg + dx * 0.25,
          pitchDeg: Math.max(0, Math.min(65, pointer.current.camera.pitchDeg + dy * 0.2)),
        });
      } else {
        const bearing = pointer.current.camera.bearingDeg * Math.PI / 180;
        const screenX = -dx * pointer.current.camera.zoom;
        const screenZ = dy * pointer.current.camera.zoom;
        emitCamera({
          ...pointer.current.camera,
          center: {
            x: pointer.current.camera.center.x + screenX * Math.cos(bearing) + screenZ * Math.sin(bearing),
            z: pointer.current.camera.center.z - screenX * Math.sin(bearing) + screenZ * Math.cos(bearing),
          },
        });
      }
    }}
    onPointerUp={() => { pointer.current = null; }}
    onPointerCancel={() => { pointer.current = null; }}
    onWheel={(event) => {
      const zoom = Math.max(
        MIN_ZOOM_LY_PER_PIXEL,
        Math.min(MAX_ZOOM_LY_PER_PIXEL, props.scene.camera.zoom * Math.exp(event.deltaY * 0.001)),
      );
      emitCamera({ ...props.scene.camera, zoom });
    }}>
    <Canvas orthographic frameloop="demand" gl={{ antialias: false, powerPreference: 'high-performance' }}
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
      <color attach="background" args={['#05090e']} />
      <SceneContents {...props} visible={visible} />
    </Canvas>
    <div className="map-foundation-labels" aria-hidden="true">
      {labels.filter((label) => label.visible).map((label) => <span key={label.id}
        style={{ left: label.screen.x, top: label.screen.z }}>{label.name}</span>)}
    </div>
    <div className="map-foundation-cluster-labels" aria-hidden="true">
      {clusters.flatMap(({ cluster, anchor }) => {
        if (!anchor) return [];
        const label = projectLabels({
          ...props,
          regions: { boundaries: [], labels: [{ id: cluster.anchorId64, name: cluster.label, position: [anchor.coords.x, anchor.coords.z, 0] }] },
        })[0];
        return label?.visible ? [<span key={`${cluster.anchorId64}:${cluster.label}`}
          style={{ left: label.screen.x, top: label.screen.z - 18 }}>{cluster.label}</span>] : [];
      })}
    </div>
    <output className="map-foundation-render-stats" aria-label="Renderer draw summary">
      {visible.metadata.returnedBackground.toLocaleString()}
      {' background · '}{highlightedIds.size} highlighted
    </output>
  </div>;
}
