import { describe, expect, it } from 'vitest';
import type { MapSceneState } from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';
import { buildRouteGeometry } from './routeGeometry';

const scene = {
  systems: [
    { id64: 1, name: 'Sol', coords: { x: 0, y: 0, z: 0 }, developmentScore: null, primaryEconomy: null, population: null },
    { id64: 2, name: 'Achenar', coords: { x: 10, y: 2, z: -4 }, developmentScore: null, primaryEconomy: null, population: null },
    { id64: 3, name: 'Missing route point', coords: { x: 20, y: 0, z: 0 }, developmentScore: null, primaryEconomy: null, population: null },
  ],
  routes: [{
    id: 'route-1',
    color: '#74d8ff',
    currentWaypointIndex: 1,
    waypoints: [{ systemId64: 1 }, { systemId64: 2 }],
  }],
} as MapSceneState;

describe('route map geometry', () => {
  it('builds connected line segments, direction markers, and current waypoint state', () => {
    const [route] = buildRouteGeometry(scene);
    expect(route?.positions).toHaveLength(6);
    expect(route?.segments).toHaveLength(1);
    expect(route?.segments[0]?.from.name).toBe('Sol');
    expect(route?.segments[0]?.to.name).toBe('Achenar');
    expect(route?.current?.id64).toBe(2);
  });
});
