import * as THREE from 'three';
import type { MapSceneState, Route, SystemRecord } from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';

type RouteSegment = {
  from: SystemRecord;
  to: SystemRecord;
  midpoint: [number, number, number];
  quaternion: [number, number, number, number];
};

export type RouteGeometry = {
  route: Route;
  positions: Float32Array;
  segments: RouteSegment[];
  current: SystemRecord | null;
};

export function buildRouteGeometry(scene: MapSceneState): RouteGeometry[] {
  const systems = new Map(scene.systems.map((system) => [system.id64, system]));
  return scene.routes.map((route) => {
    const routeSystems = route.waypoints
      .map((waypoint) => systems.get(waypoint.systemId64))
      .filter((system): system is SystemRecord => Boolean(system));
    const positions: number[] = [];
    const segments: RouteSegment[] = [];
    for (let index = 1; index < routeSystems.length; index += 1) {
      const from = routeSystems[index - 1]!;
      const to = routeSystems[index]!;
      const fromPosition = new THREE.Vector3(from.coords.x, from.coords.z, from.coords.y + 12);
      const toPosition = new THREE.Vector3(to.coords.x, to.coords.z, to.coords.y + 12);
      positions.push(...fromPosition.toArray(), ...toPosition.toArray());
      const direction = toPosition.clone().sub(fromPosition).normalize();
      const quaternion = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction);
      const midpoint = fromPosition.clone().lerp(toPosition, 0.64);
      segments.push({
        from,
        to,
        midpoint: midpoint.toArray() as [number, number, number],
        quaternion: quaternion.toArray() as [number, number, number, number],
      });
    }
    const currentIndex = route.currentWaypointIndex ?? null;
    return {
      route,
      positions: new Float32Array(positions),
      segments,
      current: currentIndex == null ? null : routeSystems[currentIndex] ?? null,
    };
  });
}
