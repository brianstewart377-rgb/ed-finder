import { useMemo } from 'react';
import * as THREE from 'three';
import type { MapSceneState } from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';
import { buildRouteGeometry } from './routeGeometry';

export function RouteLayer({ scene }: { scene: MapSceneState }) {
  const geometry = useMemo(() => buildRouteGeometry(scene), [scene]);
  const markerSize = Math.max(0.3, scene.camera.zoom * 14);
  return <>
    {geometry.map(({ route, positions, segments, current }) => (
      <group key={route.id}>
        {positions.length > 0 && (
          <lineSegments renderOrder={12}>
            <bufferGeometry>
              <bufferAttribute attach="attributes-position" args={[positions, 3]} />
            </bufferGeometry>
            <lineBasicMaterial color={route.color} transparent opacity={0.9} depthTest={false} />
          </lineSegments>
        )}
        {segments.map((segment, index) => (
          <mesh
            key={`${route.id}-direction-${index}`}
            position={segment.midpoint}
            quaternion={segment.quaternion}
            renderOrder={13}
          >
            <coneGeometry args={[Math.max(0.18, markerSize * 0.22), Math.max(0.5, markerSize * 0.72), 12]} />
            <meshBasicMaterial color={route.color} transparent opacity={0.95} depthTest={false} />
          </mesh>
        ))}
        {current && (
          <mesh position={[current.coords.x, current.coords.z, current.coords.y + 14]} renderOrder={14}>
            <ringGeometry args={[markerSize * 0.72, markerSize, 48]} />
            <meshBasicMaterial color="#ffffff" transparent opacity={0.96} depthTest={false} side={THREE.DoubleSide} />
          </mesh>
        )}
      </group>
    ))}
  </>;
}
