import { useCallback, useEffect, useMemo, useRef } from 'react';
import DeckGL, { type DeckGLRef } from '@deck.gl/react';
import { COORDINATE_SYSTEM, OrbitView, OrthographicView, type OrbitViewState } from '@deck.gl/core';
import { LineLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import {
  toDeckOrbitView,
  toDeckOrthoView,
  toThreeJSR3F,
} from '../../artifacts/map-foundation/stage-26b/map-renderer-adapter';
import type { CameraState, SystemRecord } from '../../artifacts/map-foundation/stage-26b/map-scene-contract';
import type { CandidateProps, RegionBoundary, RegionLabel } from './types';

const INITIAL_CAMERA: CameraState = {
  center: { x: 0, z: 0 }, zoom: 64, pitchDeg: 0, bearingDeg: 0,
};

function deckLayers({ systems, regions }: CandidateProps) {
  return [
    new LineLayer<RegionBoundary>({
      id: 'regions', data: regions.boundaries, coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
      getSourcePosition: (d) => d.source, getTargetPosition: (d) => d.target,
      getColor: [85, 126, 156, 110], getWidth: 1, widthUnits: 'pixels', pickable: false,
    }),
    new ScatterplotLayer<SystemRecord>({
      id: 'systems', data: systems, coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
      getPosition: (d) => [d.coords.x, d.coords.z, 0],
      getRadius: (d) => d.id64 === 100_000_000 ? 10 : 2,
      radiusUnits: 'pixels', radiusMinPixels: 1, getFillColor: [104, 211, 255, 190],
      pickable: true,
    }),
    new ScatterplotLayer<SystemRecord>({
      id: 'guaranteed-pick-target', data: systems.slice(0, 1),
      coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
      getPosition: (d) => [d.coords.x, d.coords.z, 1], getRadius: 10,
      radiusUnits: 'pixels', getFillColor: [255, 151, 64, 255], pickable: true,
    }),
    new TextLayer<RegionLabel>({
      id: 'region-labels', data: regions.labels, coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
      getPosition: (d) => d.position, getText: (d) => d.name, getSize: 11,
      sizeUnits: 'pixels', getColor: [195, 207, 217, 180], getTextAnchor: 'middle',
    }),
  ];
}

export function DeckOrbitCandidate(props: CandidateProps) {
  const deckRef = useRef<DeckGLRef>(null);
  const layers = useMemo(() => deckLayers(props), [props.systems, props.regions, props.onSelect]);
  const viewState = useMemo(() => toDeckOrbitView(INITIAL_CAMERA) as OrbitViewState, []);
  return <div onPointerDownCapture={(event) => {
    const startedAt = performance.now();
    const bounds = event.currentTarget.getBoundingClientRect();
    const picked = deckRef.current?.deck?.pickObject({
      x: event.clientX - bounds.left, y: event.clientY - bounds.top, radius: 12,
    });
    if (picked?.object) props.onSelect((picked.object as SystemRecord).id64, startedAt);
  }}>
    <DeckGL ref={deckRef} views={new OrbitView({ id: 'orbit', orbitAxis: 'Z', orthographic: true, controller: true })}
      initialViewState={viewState} layers={layers} onAfterRender={props.onReady} />
  </div>;
}

export function DeckOrthoCandidate(props: CandidateProps) {
  const deckRef = useRef<DeckGLRef>(null);
  const layers = useMemo(() => deckLayers(props), [props.systems, props.regions, props.onSelect]);
  const viewState = useMemo(() => toDeckOrthoView(INITIAL_CAMERA), []);
  return <div onPointerDownCapture={(event) => {
    const startedAt = performance.now();
    const bounds = event.currentTarget.getBoundingClientRect();
    const picked = deckRef.current?.deck?.pickObject({
      x: event.clientX - bounds.left, y: event.clientY - bounds.top, radius: 12,
    });
    if (picked?.object) props.onSelect((picked.object as SystemRecord).id64, startedAt);
  }}>
    <DeckGL ref={deckRef} views={new OrthographicView({ id: 'ortho', flipY: false, controller: true })}
      initialViewState={viewState} layers={layers} onAfterRender={props.onReady} />
  </div>;
}

function ReadySignal({ onReady }: { onReady: () => void }) {
  const fired = useRef(false);
  useFrame(() => {
    if (!fired.current) { fired.current = true; onReady(); }
  });
  return null;
}

function CameraSetup() {
  const { camera, size } = useThree();
  useEffect(() => {
    const mapped = toThreeJSR3F(INITIAL_CAMERA) as {
      position: [number, number, number]; rotation: [number, number, number]; zoom: number;
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
  }, [camera, size]);
  return null;
}

function ThreeScene({ systems, regions, onReady, onSelect }: CandidateProps) {
  const systemPositions = useMemo(() => {
    const values = new Float32Array(systems.length * 3);
    systems.forEach((system, index) => values.set([system.coords.x, system.coords.z, 0], index * 3));
    return values;
  }, [systems]);
  const boundaryPositions = useMemo(() => {
    const values = new Float32Array(regions.boundaries.length * 6);
    regions.boundaries.forEach((boundary, index) => values.set([...boundary.source, ...boundary.target], index * 6));
    return values;
  }, [regions]);
  const select = useCallback((event: { index?: number; stopPropagation: () => void }) => {
    if (event.index == null) return;
    event.stopPropagation();
    onSelect(systems[event.index].id64, performance.now());
  }, [onSelect, systems]);
  return <>
    <CameraSetup />
    <ReadySignal onReady={onReady} />
    <lineSegments>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[boundaryPositions, 3]} /></bufferGeometry>
      <lineBasicMaterial color="#557e9c" transparent opacity={0.45} />
    </lineSegments>
    <points onPointerDown={select}>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[systemPositions, 3]} /></bufferGeometry>
      <pointsMaterial color="#68d3ff" size={2} sizeAttenuation={false} />
    </points>
    <mesh position={[16_000, 0, 1]} onPointerDown={(event) => {
      event.stopPropagation();
      onSelect(100_000_000, performance.now());
    }}>
      <circleGeometry args={[640, 24]} />
      <meshBasicMaterial color="#ff9740" />
    </mesh>
  </>;
}

export function ThreeCandidate(props: CandidateProps) {
  const pointerStartedAt = useRef(0);
  const onSelect = useCallback((id64: number) => {
    const startedAt = pointerStartedAt.current || performance.now();
    pointerStartedAt.current = 0;
    props.onSelect(id64, startedAt);
  }, [props.onSelect]);
  return <div className="three-host" onPointerDownCapture={() => {
    pointerStartedAt.current = performance.now();
  }}>
    <Canvas orthographic gl={{ antialias: false, powerPreference: 'high-performance' }}>
      <color attach="background" args={['#060a0f']} />
      <ThreeScene {...props} onSelect={onSelect} />
    </Canvas>
    <div className="three-labels" aria-hidden="true">
      {props.regions.labels.map((label) => <span key={label.id} style={{
        left: `calc(50% + ${label.position[0] / INITIAL_CAMERA.zoom}px)`,
        top: `calc(50% - ${label.position[1] / INITIAL_CAMERA.zoom}px)`,
      }}>{label.name}</span>)}
    </div>
  </div>;
}
