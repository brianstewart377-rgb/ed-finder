import { useEffect, useMemo } from 'react';
import * as THREE from 'three';
import { Line2 } from 'three/examples/jsm/lines/Line2.js';
import { LineGeometry } from 'three/examples/jsm/lines/LineGeometry.js';
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js';
import type { CameraState } from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';
import type { FoundationRendererProps, ViewportSize } from './types';
import { buildBoundaryPolylines } from './map-presentation';
import { attenuatedPointSize } from './camera';

export function RegionBoundaryLines({
  boundaries,
  viewport,
  spatial,
}: {
  boundaries: FoundationRendererProps['regions']['boundaries'];
  viewport: FoundationRendererProps['viewport'];
  spatial: boolean;
}) {
  const polylines = useMemo(() => buildBoundaryPolylines(boundaries), [boundaries]);
  const layer = useMemo(() => {
    const haloMaterial = new LineMaterial({
      color: 0xff8a2c,
      linewidth: spatial ? 3.4 : 3.8,
      transparent: true,
      opacity: spatial ? 0.16 : 0.12,
      depthTest: false,
      depthWrite: false,
    });
    const coreMaterial = new LineMaterial({
      color: spatial ? 0xf0ad56 : 0xd58b3b,
      linewidth: spatial ? 2.15 : 1.8,
      transparent: true,
      opacity: spatial ? 0.9 : 0.76,
      depthTest: false,
      depthWrite: false,
    });
    const lines = polylines.map((positions) => {
      const geometry = new LineGeometry();
      geometry.setPositions(positions);
      geometry.computeBoundingBox();
      geometry.computeBoundingSphere();
      const halo = new Line2(geometry, haloMaterial);
      const core = new Line2(geometry, coreMaterial);
      halo.renderOrder = 5;
      core.renderOrder = 6;
      halo.frustumCulled = false;
      core.frustumCulled = false;
      return { geometry, halo, core };
    });

    return { lines, haloMaterial, coreMaterial };
  }, [polylines, spatial]);

  useEffect(() => {
    layer.haloMaterial.resolution.set(viewport.width, viewport.height);
    layer.coreMaterial.resolution.set(viewport.width, viewport.height);
  }, [layer, viewport.height, viewport.width]);

  useEffect(() => () => {
    layer.haloMaterial.dispose();
    layer.coreMaterial.dispose();
    layer.lines.forEach(({ geometry }) => geometry.dispose());
  }, [layer]);

  if (boundaries.length === 0) return null;
  return <>
    {layer.lines.map(({ halo, core }, index) => <group key={index}>
      <primitive object={halo} />
      <primitive object={core} />
    </group>)}
  </>;
}

export function CameraCenterGuide({
  camera,
  viewport,
}: {
  camera: CameraState;
  viewport: ViewportSize;
}) {
  const layer = useMemo(() => {
    const halfWidth = camera.zoom * viewport.width * 0.7;
    const halfHeight = camera.zoom * viewport.height * 0.7;
    const horizontalGeometry = new LineGeometry();
    horizontalGeometry.setPositions([
      camera.center.x - halfWidth, camera.center.z, -8,
      camera.center.x + halfWidth, camera.center.z, -8,
    ]);
    const verticalGeometry = new LineGeometry();
    verticalGeometry.setPositions([
      camera.center.x, camera.center.z - halfHeight, -8,
      camera.center.x, camera.center.z + halfHeight, -8,
    ]);
    const material = new LineMaterial({
      color: 0x8b6746,
      linewidth: 1,
      transparent: true,
      opacity: 0.22,
      depthTest: false,
      depthWrite: false,
      resolution: new THREE.Vector2(viewport.width, viewport.height),
    });
    const horizontal = new Line2(horizontalGeometry, material);
    const vertical = new Line2(verticalGeometry, material);
    horizontal.renderOrder = 1;
    vertical.renderOrder = 1;
    return { horizontal, vertical, horizontalGeometry, verticalGeometry, material };
  }, [camera.center.x, camera.center.z, camera.zoom, viewport.height, viewport.width]);

  useEffect(() => () => {
    layer.horizontalGeometry.dispose();
    layer.verticalGeometry.dispose();
    layer.material.dispose();
  }, [layer]);

  return <>
    <primitive object={layer.horizontal} />
    <primitive object={layer.vertical} />
  </>;
}

function niceRangeStep(target: number): number {
  const magnitude = 10 ** Math.floor(Math.log10(Math.max(0.01, target)));
  const normalized = target / magnitude;
  const multiplier = normalized < 2.5 ? 1 : normalized < 5 ? 2.5 : normalized < 10 ? 5 : 10;
  return multiplier * magnitude;
}

export function rangeStepForView(camera: CameraState, viewport: ViewportSize): number {
  const radius = camera.zoom * Math.min(viewport.width, viewport.height) * 0.48;
  return niceRangeStep(radius / 5);
}

export function RangeGrid({
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

export function ReferenceMarker({
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
