import { describe, expect, it } from 'vitest';
import type {
  FacilityTemplate,
  RecommendedStep,
  SimulateBuildPlacement,
  SystemBody,
} from './types';
import {
  archetypeFromEconomy,
  buildRecommendedPlacements,
  preferredTemplate,
  recommendedBodyId,
  resequence,
  simulationBodies,
} from './placementHelpers';

function template(
  id: string,
  options: Partial<FacilityTemplate> = {},
): FacilityTemplate {
  return {
    id,
    name: id,
    is_port: false,
    allowed_location: 'Orbital',
    ...options,
  };
}

describe('planner placement helpers', () => {
  it('resequences in input order with fresh objects and no input mutation', () => {
    const placements: SimulateBuildPlacement[] = [
      {
        facility_template_id: 'second',
        local_body_id: '2',
        build_order: 20,
      },
      {
        facility_template_id: 'first',
        local_body_id: '1',
        build_order: 10,
      },
    ];
    const before = structuredClone(placements);

    const result = resequence(placements);

    expect(result.map((placement) => placement.facility_template_id)).toEqual([
      'second',
      'first',
    ]);
    expect(result.map((placement) => placement.build_order)).toEqual([1, 2]);
    expect(result[0]).not.toBe(placements[0]);
    expect(result[1]).not.toBe(placements[1]);
    expect(placements).toEqual(before);
  });

  it('builds recommendations in order, skips unknown steps, and assigns only the first port as primary', () => {
    const steps: RecommendedStep[] = [
      { step: 1, facility_id: 'missing' },
      { step: 2, facility_id: 'port-b', location: 'Orbital' },
      { step: 3, facility_id: null },
      { step: 4, facility_id: 'port-a', location: 'Surface' },
      { step: 5, facility_id: 'support', location: 'Surface' },
    ];
    const templates = [
      template('port-a', { is_port: true }),
      template('port-b', { is_port: true }),
      template('support', { allowed_location: 'Surface' }),
    ];
    const bodies: SystemBody[] = [
      { id: 'body-orbital', is_landable: false },
      { id: 'body-surface', is_landable: true },
    ];

    expect(buildRecommendedPlacements(steps, templates, bodies)).toEqual([
      {
        facility_template_id: 'port-b',
        local_body_id: 'body-orbital',
        is_primary_port: true,
        build_order: 1,
      },
      {
        facility_template_id: 'port-a',
        local_body_id: 'body-surface',
        is_primary_port: false,
        build_order: 2,
      },
      {
        facility_template_id: 'support',
        local_body_id: 'body-surface',
        is_primary_port: false,
        build_order: 3,
      },
    ]);
    expect(buildRecommendedPlacements([], templates, bodies)).toEqual([]);
    expect(buildRecommendedPlacements(steps, [], bodies)).toEqual([]);
  });

  it('chooses the first landable surface body and preserves opaque large string identifiers', () => {
    const largeBodyId = '900719925474099312345';
    const bodies: SystemBody[] = [
      { id: 'not-landable', is_landable: false },
      { id: largeBodyId, is_landable: true },
    ];

    expect(
      recommendedBodyId('SURFACE settlement', template('surface'), bodies),
    ).toBe(largeBodyId);
    expect(recommendedBodyId('Orbital', template('orbital'), bodies)).toBe(
      'not-landable',
    );
    expect(recommendedBodyId('Surface', template('empty'), [])).toBeNull();
  });

  it('falls back to the first body for a surface placement without a landable body', () => {
    const bodies: SystemBody[] = [
      { id: null, is_landable: false },
      { id: 'second', is_landable: false },
    ];

    expect(
      recommendedBodyId(
        null,
        template('surface', { allowed_location: 'Surface' }),
        bodies,
      ),
    ).toBeNull();
  });

  it('prefers the first port and otherwise the first template', () => {
    const first = template('first');
    const firstPort = template('port-1', { is_port: true });
    const secondPort = template('port-2', { is_port: true });

    expect(preferredTemplate([first, firstPort, secondPort])).toBe(firstPort);
    expect(preferredTemplate([first])).toBe(first);
    expect(preferredTemplate([])).toBeUndefined();
  });

  it('filters only exact Star bodies without mutating the input', () => {
    const bodies: SystemBody[] = [
      { id: 'star', body_type: 'Star' },
      { id: 'lower-star', body_type: 'star' },
      { id: 'planet', body_type: 'Planet' },
    ];

    const result = simulationBodies(bodies);

    expect(result).toEqual([bodies[1], bodies[2]]);
    expect(result).not.toBe(bodies);
    expect(simulationBodies()).toEqual([]);
  });

  it('maps economy names with the inherited deterministic priority', () => {
    expect(archetypeFromEconomy('Extraction Refinery')).toBe(
      'refinery_industrial',
    );
    expect(archetypeFromEconomy('Agriculture')).toBe(
      'agriculture_terraforming',
    );
    expect(archetypeFromEconomy('High Tech')).toBe('hitech_tourism');
    expect(archetypeFromEconomy('Tourism')).toBe('hitech_tourism');
    expect(archetypeFromEconomy('Industrial Military')).toBe(
      'military_industrial',
    );
    expect(archetypeFromEconomy('Industrial')).toBe('refinery_industrial');
    expect(archetypeFromEconomy(null)).toBeNull();
  });
});
