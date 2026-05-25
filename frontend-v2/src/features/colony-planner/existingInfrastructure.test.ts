import { describe, expect, it } from 'vitest';
import type { SystemDetail } from '@/types/api';
import {
  classifyExistingStationLane,
  resolveExistingInfrastructure,
} from './existingInfrastructure';

const baseSystem = {
  id64: 42,
  name: 'Occupied Test',
  bodies: [
    { id: 1, name: 'Occupied Test A', body_type: 'Star', distance_from_star: 0 },
    { id: 2, name: 'Occupied Test A 1', body_type: 'Planet', is_landable: true, distance_from_star: 120 },
    { id: 3, name: 'Occupied Test A 2', body_type: 'Planet', is_landable: true, distance_from_star: 240 },
  ],
  stations: [],
} as unknown as SystemDetail;

describe('existing infrastructure resolver', () => {
  it('maps exact body names and orbital station types', () => {
    const resolution = resolveExistingInfrastructure({
      ...baseSystem,
      stations: [
        {
          id: 1001,
          market_id: 1001,
          name: 'Holden Orbital',
          station_type: 'Coriolis',
          body_name: 'Occupied Test A 1',
          primary_economy: 'Refinery',
        },
      ],
    } as unknown as SystemDetail);

    expect(resolution.mapped).toHaveLength(1);
    expect(resolution.mapped[0]).toEqual(expect.objectContaining({
      source: 'existing',
      body_id: '2',
      body_match_confidence: 'exact',
      lane: 'orbital',
      economy: 'Refinery',
    }));
  });

  it('prefers exact body ids when present', () => {
    const resolution = resolveExistingInfrastructure({
      ...baseSystem,
      stations: [
        {
          id: 1002,
          name: 'Surface Depot',
          station_type: 'PlanetaryPort',
          body_name: 'Wrong Body Name',
          body_id: 3,
        },
      ],
    } as unknown as SystemDetail);

    expect(resolution.mapped[0]).toEqual(expect.objectContaining({
      body_id: '3',
      body_match_confidence: 'exact',
      lane: 'surface',
    }));
  });

  it('keeps ambiguous distance-only associations unresolved', () => {
    const resolution = resolveExistingInfrastructure({
      ...baseSystem,
      bodies: [
        ...(baseSystem.bodies ?? []),
        { id: 4, name: 'Occupied Test A 3', body_type: 'Planet', distance_from_star: 120 },
      ],
      stations: [
        {
          id: 1003,
          name: 'Ambiguous Station',
          station_type: 'Outpost',
          distance_from_star: 120,
        },
      ],
    } as unknown as SystemDetail);

    expect(resolution.mapped).toHaveLength(0);
    expect(resolution.unresolved[0]).toEqual(expect.objectContaining({
      body_match_confidence: 'unresolved',
      unresolved_reason: 'Distance-from-star match is ambiguous.',
    }));
  });

  it('does not force unknown station types into a slot lane', () => {
    expect(classifyExistingStationLane('Coriolis')).toBe('orbital');
    expect(classifyExistingStationLane('PlanetaryOutpost')).toBe('surface');
    expect(classifyExistingStationLane('MegaShip')).toBe('unknown');
    expect(classifyExistingStationLane('Unknown')).toBe('unknown');
  });
});
