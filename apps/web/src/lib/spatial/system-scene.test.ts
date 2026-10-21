import { describe, expect, it } from 'vitest';

import { systemDetailFromV3 } from '$lib/api/client';
import {
  referenceSystemDetail,
  v3Body,
  v3Ring,
  v3Station,
  v3System,
} from '$lib/api/v3-system-fixtures';

import {
  buildSystemScene,
  stellarPresentationSubtype,
  systemBodyLayout,
} from './system-scene';
import { stellarPresentation } from './stellar-presentation';

const fixture = referenceSystemDetail();

describe('system scene', () => {
  it('keeps V3 body facts authoritative and layout explicitly schematic', () => {
    const scene = buildSystemScene(fixture, 4);
    expect(scene.kind).toBe('system');
    expect(scene.fidelity).toBe('S1');
    // Only bodies with a unique Frontier BodyID are placed.
    expect(scene.bodies.map((body) => body.ref.bodyId)).toEqual([0, 3]);
    expect(scene.bodies[0]).toMatchObject({
      name: 'Reference System',
      class: { value: 'Star', representation: 'AUTHORITATIVE' },
      subtype: { value: 'G (G2 V) Star', representation: 'DERIVED' },
      physicalRadiusM: { value: 695_700_000 },
      rings: { state: 'UNKNOWN', bands: [] },
    });
    expect(scene.bodies[1]).toMatchObject({
      name: 'Reference System 3',
      class: { value: 'Planet', representation: 'AUTHORITATIVE' },
      distanceFromArrivalLs: {
        value: 11_450,
        representation: 'AUTHORITATIVE',
      },
      orbital: { placement: 'DETERMINISTIC_SCHEMATIC' },
      rings: {
        state: 'PRESENT',
        bands: [
          {
            id: '900719925632971229',
            ringClass: { value: 'icy' },
            innerRadiusM: { value: 90_000_000 },
            outerRadiusM: { value: 130_000_000 },
          },
        ],
      },
    });
    expect(scene.bodies[1]).not.toHaveProperty('subtype');
  });

  it('uses catalogue distance only to order a deterministic semantic layout', () => {
    const scene = buildSystemScene(fixture, 4);
    const layout = systemBodyLayout(scene.bodies);
    expect(layout[0]?.position).toEqual({ x: 0, y: 0, z: 0 });
    expect(layout[1]?.orbitRadius).toBeGreaterThan(4.8);
    expect(layout[1]?.position.y).toBe(0);
    expect(systemBodyLayout(scene.bodies)).toEqual(layout);
  });

  it('focuses a known selected body without inventing missing body ids', () => {
    const scene = buildSystemScene(fixture, 8, 3);
    expect(scene.bodies).toHaveLength(2);
    expect(scene.camera.focus).toEqual({
      kind: 'body',
      ref: { systemId64: fixture.id64, bodyId: 3 },
    });
    expect(buildSystemScene(fixture, 9, 99).camera.focus).toEqual({
      kind: 'system',
      systemId64: fixture.id64,
    });
  });

  it('omits bodies, rings and stations the generation no longer holds as current', () => {
    const detail = systemDetailFromV3(
      v3System({ lifecycle_state: 'MISSING_CANDIDATE' }),
      [
        v3Body({ body_id: '1', frontier_body_id: '0', name: 'Current' }),
        v3Body({
          body_id: '2',
          frontier_body_id: '0',
          name: 'Retired',
          lifecycle_state: 'RETIRED',
        }),
        v3Body({
          body_id: '3',
          frontier_body_id: '4',
          name: 'Missing',
          lifecycle_state: 'MISSING_CANDIDATE',
        }),
      ],
      [
        v3Ring({ ring_id: '10', body_id: '1' }),
        v3Ring({ ring_id: '11', body_id: '1', lifecycle_state: 'RETIRED' }),
      ],
      [
        v3Station({ station_id: '20' }),
        v3Station({ station_id: '21', lifecycle_state: 'RETIRED' }),
      ],
    );
    expect(detail.lifecycleState).toBe('MISSING_CANDIDATE');
    expect(detail.bodies.map((body) => body.name)).toEqual(['Current']);
    // A retired body sharing the BodyID no longer makes the current one ambiguous.
    expect(detail.bodies[0]?.id).toBe(0);
    expect(detail.bodies[0]?.rings.map((ring) => ring.ringKey)).toEqual(['10']);
    expect(detail.stations.map((station) => station.stationKey)).toEqual([
      '20',
    ]);
  });

  it('never selects by an ambiguous or unsafe Frontier BodyID', () => {
    const detail = systemDetailFromV3(
      v3System(),
      [
        v3Body({ body_id: '1', frontier_body_id: '7', name: 'A' }),
        v3Body({ body_id: '2', frontier_body_id: '7', name: 'B' }),
        v3Body({
          body_id: '3',
          frontier_body_id: '9007199254740993',
          name: 'C',
        }),
        v3Body({ body_id: '4', frontier_body_id: '05', name: 'D' }),
      ],
      [],
      [],
    );
    expect(detail.bodies.map((body) => body.id)).toEqual([
      null,
      null,
      null,
      null,
    ]);
    expect(buildSystemScene(detail, 1).fidelity).toBe('S0');
  });

  it('phrases catalogued stellar classes so the shared presentation recognises them', () => {
    const glyph = (spectral: string, luminosity: string | null = null) =>
      stellarPresentation({
        type: 'Star',
        subtype:
          stellarPresentationSubtype({
            bodyType: 'star',
            spectralClass: spectral,
            luminosityClass: luminosity,
          }) ?? undefined,
      }).glyph;
    expect(glyph('G2', 'V')).toBe('main-sequence-g');
    expect(glyph('M5', 'Va')).toBe('main-sequence-m');
    expect(glyph('K3', 'III')).toBe('giant-warm');
    expect(glyph('DA')).toBe('white-dwarf');
    expect(glyph('N')).toBe('neutron');
    expect(glyph('H')).toBe('black-hole');
    // Catalogued classes carry numeric subclasses.
    expect(glyph('N0')).toBe('neutron');
    expect(glyph('H0')).toBe('black-hole');
    expect(glyph('DA6')).toBe('white-dwarf');
    expect(glyph('WC8')).toBe('wolf-rayet');
    expect(glyph('Y3')).toBe('brown-dwarf-y-t');
    expect(glyph('WC')).toBe('wolf-rayet');
    expect(glyph('TTS')).toBe('ttauri-herbig');
    expect(
      stellarPresentationSubtype({
        bodyType: 'planet',
        spectralClass: 'G2',
        luminosityClass: null,
      }),
    ).toBeNull();
  });
});
