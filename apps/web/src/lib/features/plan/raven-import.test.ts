import { describe, expect, it } from 'vitest';
import catalogue from '../../../../../api/src/domain/facility_catalogue_v1.json';
import sample from './__fixtures__/raven-layout-sample.json';
import { matchRavenBodies, parseRavenLayout } from './raven-import';

// An interoperability table supplied for this importer, independent of Raven code.
const buildTypes = [
  ['aerecura', 'surface_settlement_extraction_t2_l', 'surface'],
  ['aletheia', 'orbital_installation_comm_station', 'orbital'],
  ['atropos', 'surface_planetary_port_outpost_civilian', 'surface'],
  ['bacchus', 'orbital_installation_space_bar', 'orbital'],
  ['ceres', 'surface_settlement_agriculture_t2_l', 'surface'],
  ['chronos', 'surface_settlement_research_bio_t2_l', 'surface'],
  ['dec_truss', 'dodecahedron_t3', 'orbital'],
  ['demeter', 'orbital_installation_space_farm', 'orbital'],
  ['euthenia', 'orbital_installation_mining_outpost', 'orbital'],
  ['fufluns', 'surface_settlement_tourism_t2_l', 'surface'],
  ['hephaestus', 'surface_planetary_port_outpost_industrial', 'surface'],
  ['hermes', 'orbital_installation_satellite', 'orbital'],
  ['minerva', 'surface_settlement_military_t2_l', 'surface'],
  ['molae', 'industrial_facility', 'surface'],
  ['nemesis', 'orbital_outpost_military', 'orbital'],
  ['ocellus', 'ocellus_station', 'orbital'],
  ['opis', 'surface_planetary_port_outpost_industrial', 'surface'],
  ['pistis', 'orbital_installation_comm_station', 'orbital'],
  ['plutus', 'orbital_outpost_commercial', 'orbital'],
  ['prometheus', 'orbital_outpost_scientific', 'orbital'],
  ['quad_truss', 'coriolis_station', 'orbital'],
  ['silenus', 'refinery', 'surface'],
  ['vulcan', 'orbital_outpost_industrial', 'orbital'],
] as const;

function site(overrides: Record<string, unknown> = {}) {
  return {
    id: 'synthetic-site',
    name: 'Copper Finch Dock',
    bodyNum: 16,
    buildType: 'vulcan',
    status: 'complete',
    ...overrides,
  };
}

function layout(overrides: Record<string, unknown> = {}) {
  return {
    v: '6',
    name: 'Velora Lantern',
    id64: '1234567890123456789',
    bodies: [{ num: 16, name: 'Velora Lantern A 1' }],
    sites: [site()],
    slots: { '16': [4, 10] },
    ...overrides,
  };
}

function expectFatal(input: unknown, code?: string) {
  const result = parseRavenLayout(input);
  expect(result.ok).toBe(false);
  expect(result.errors.length).toBeGreaterThan(0);
  if (code)
    expect(result.errors).toContainEqual(expect.objectContaining({ code }));
  expect(result.system).toBeNull();
  expect(result.sites).toEqual([]);
  expect(result.slots).toEqual([]);
}

describe('parseRavenLayout', () => {
  it('parses the synthetic layout in site order with recorded slot counts', () => {
    const result = parseRavenLayout(sample);
    expect(result.ok).toBe(true);
    expect(result.errors).toEqual([]);
    expect(result.warnings).toEqual([]);
    expect(result.system).toEqual({
      id64: '1234567890123456789',
      name: 'Velora Lantern',
    });
    expect(result.sites).toHaveLength(4);
    expect(result.sites.map((entry) => entry.raven_site_id)).toEqual([
      'synthetic-dock',
      'synthetic-farm',
      'synthetic-port',
      'synthetic-works',
    ]);
    expect(result.sites[0]).toEqual({
      raven_site_id: 'synthetic-dock',
      raven_build_type: 'vulcan',
      name: 'Copper Finch Dock',
      facility_id: 'orbital_outpost_industrial',
      slot_kind: 'orbital',
      status: 'complete',
      raven_body_name: 'Velora Lantern A 1',
    });
    expect(result.slots).toEqual([
      {
        raven_body_name: 'Velora Lantern A 1',
        orbital_slots: 4,
        surface_slots: 10,
      },
      {
        raven_body_name: 'Velora Lantern A 1 a',
        orbital_slots: 2,
        surface_slots: 6,
      },
      {
        raven_body_name: 'Velora Lantern A 2',
        orbital_slots: 0,
        surface_slots: 8,
      },
    ]);
  });

  it.each([
    ['plan', 'planned'],
    ['build', 'building'],
    ['complete', 'complete'],
    ['demolish', 'demolished'],
  ])('maps status %s to %s', (status, expected) => {
    const result = parseRavenLayout(layout({ sites: [site({ status })] }));
    expect(result.ok).toBe(true);
    expect(result.sites[0]?.status).toBe(expected);
    expect(result.warnings).toEqual([]);
  });

  it.each(buildTypes)(
    'maps build type %s',
    (buildType, facilityId, slotKind) => {
      const result = parseRavenLayout(layout({ sites: [site({ buildType })] }));
      expect(result.ok).toBe(true);
      expect(result.sites[0]).toMatchObject({
        raven_build_type: buildType,
        facility_id: facilityId,
        slot_kind: slotKind,
      });
      expect(result.warnings).toEqual([]);
    },
  );

  it('maps every interoperability entry to an existing facility in the real catalogue', () => {
    const facilities = new Map(
      catalogue.templates.map((entry) => [entry.id, entry]),
    );
    for (const [buildType, facilityId, slotKind] of buildTypes) {
      const result = parseRavenLayout(layout({ sites: [site({ buildType })] }));
      const facility = facilities.get(result.sites[0].facility_id);
      expect(facility, buildType).toBeDefined();
      expect(facility?.id).toBe(facilityId);
      expect(facility?.allowed_location).toBe(slotKind);
    }
  });

  it('skips an unknown build type with a warning identifying the type and site', () => {
    const result = parseRavenLayout(
      layout({
        sites: [
          site({ buildType: 'invented_type', name: 'Lost Lantern' }),
          site(),
        ],
      }),
    );
    expect(result.ok).toBe(true);
    expect(result.sites).toHaveLength(1);
    expect(result.warnings).toHaveLength(1);
    expect(result.warnings[0]?.code).toBe('unknown_build_type');
    expect(result.warnings[0]?.detail).toContain('invented_type');
    expect(result.warnings[0]?.detail).toContain('Lost Lantern');
  });

  it('skips an unknown status with a warning and preserves the remaining site order', () => {
    const result = parseRavenLayout(
      layout({
        sites: [
          site({ id: 'first' }),
          site({ status: 'paused' }),
          site({ id: 'last' }),
        ],
      }),
    );
    expect(result.ok).toBe(true);
    expect(result.sites.map((entry) => entry.raven_site_id)).toEqual([
      'first',
      'last',
    ]);
    expect(result.warnings).toHaveLength(1);
    expect(result.warnings[0]?.code).toBe('unknown_status');
  });

  it.each([-1, -2, 0.5, 65, NaN, Infinity, '4', null])(
    'turns invalid orbital and surface slot count %s into null with one warning per entry',
    (count) => {
      const result = parseRavenLayout(
        layout({ slots: { '16': [count, count] } }),
      );
      expect(result.ok).toBe(true);
      expect(result.slots).toEqual([
        {
          raven_body_name: 'Velora Lantern A 1',
          orbital_slots: null,
          surface_slots: null,
        },
      ]);
      expect(result.warnings).toHaveLength(1);
      expect(result.warnings[0]?.code).toBe('invalid_slots');
    },
  );

  it('preserves valid slot bounds and a valid count beside an unknown one', () => {
    const result = parseRavenLayout(
      layout({
        bodies: [
          { num: 16, name: 'Lower' },
          { num: 17, name: 'Upper' },
        ],
        slots: { '16': [0, 64], '17': [-1, 6] },
      }),
    );
    expect(result.slots).toEqual([
      { raven_body_name: 'Lower', orbital_slots: 0, surface_slots: 64 },
      { raven_body_name: 'Upper', orbital_slots: null, surface_slots: 6 },
    ]);
    expect(result.warnings).toHaveLength(1);
  });

  it('keeps a site whose body is absent, and identifies the missing body', () => {
    const result = parseRavenLayout(
      layout({ sites: [site({ bodyNum: 999 })] }),
    );
    expect(result.ok).toBe(true);
    expect(result.sites[0]?.raven_body_name).toBeNull();
    expect(result.warnings).toHaveLength(1);
    expect(result.warnings[0]).toMatchObject({ code: 'unknown_body' });
    expect(result.warnings[0]?.detail).toContain('999');
  });

  it('skips slot entries for absent bodies with a warning', () => {
    const result = parseRavenLayout(layout({ slots: { '999': [3, 4] } }));
    expect(result.ok).toBe(true);
    expect(result.slots).toEqual([]);
    expect(result.warnings).toHaveLength(1);
    expect(result.warnings[0]?.code).toBe('unknown_slot_body');
    expect(result.warnings[0]?.detail).toContain('999');
  });

  it.each([null, undefined, [], 'layout', 6, new Date(0), new Map()])(
    'rejects a non-plain object %s without throwing',
    (input) => expectFatal(input),
  );

  it.each(['5', 5, '06', null, undefined])('rejects version %s', (v) => {
    expectFatal(layout({ v }));
  });

  it('accepts numeric version 6 and a safe numeric id64', () => {
    const result = parseRavenLayout(layout({ v: 6, id64: 123456789 }));
    expect(result.ok).toBe(true);
    expect(result.system?.id64).toBe('123456789');
  });

  it('accepts a plain record with a null prototype', () => {
    const input: Record<string, unknown> = Object.assign(
      Object.create(null),
      layout(),
    );
    expect(parseRavenLayout(input).ok).toBe(true);
  });

  it('accepts a numeric id64 with 19 digits as specified by the file contract', () => {
    const result = parseRavenLayout(
      layout({ id64: 1_000_000_000_000_000_000 }),
    );
    expect(result.ok).toBe(true);
    expect(result.system?.id64).toBe('1000000000000000000');
  });

  it.each([
    '',
    '1e10',
    '-1',
    '1.5',
    '12x',
    '12345678901234567890',
    null,
    undefined,
  ])('rejects invalid or missing id64 %s', (id64) =>
    expectFatal(layout({ id64 })),
  );

  it.each(['0', '1', '0000123', '9999999999999999999'])(
    'preserves valid id64 %s',
    (id64) => {
      expect(parseRavenLayout(layout({ id64 })).system?.id64).toBe(id64);
    },
  );

  it('rejects more than 1000 bodies or 300 sites', () => {
    expectFatal(
      layout({
        bodies: Array.from({ length: 1001 }, (_, num) => ({
          num,
          name: `Body ${num}`,
        })),
      }),
    );
    expectFatal(
      layout({
        sites: Array.from({ length: 301 }, (_, index) =>
          site({ id: `site-${index}` }),
        ),
      }),
    );
  });

  it('accepts the body and site count limits', () => {
    const result = parseRavenLayout(
      layout({
        bodies: Array.from({ length: 1000 }, (_, num) => ({
          num,
          name: `Body ${num}`,
        })),
        sites: Array.from({ length: 300 }, (_, index) =>
          site({ id: `site-${index}` }),
        ),
      }),
    );
    expect(result.ok).toBe(true);
    expect(result.sites).toHaveLength(300);
  });

  it('trims names and truncates system, body and site names to 64 characters', () => {
    const longName = 'L'.repeat(65);
    const result = parseRavenLayout(
      layout({
        name: ` ${longName} `,
        bodies: [{ num: 16, name: ` ${longName} ` }],
        sites: [site({ name: ` ${longName} ` })],
      }),
    );
    expect(result.ok).toBe(true);
    expect(result.system?.name).toBe('L'.repeat(64));
    expect(result.sites[0]?.name).toBe('L'.repeat(64));
    expect(result.sites[0]?.raven_body_name).toBe('L'.repeat(64));
    expect(result.slots[0]?.raven_body_name).toBe('L'.repeat(64));
    expect(result.warnings).toHaveLength(3);
    expect(
      result.warnings.every((entry) => entry.code === 'name_truncated'),
    ).toBe(true);
  });

  it('trims names without warnings when no truncation is necessary', () => {
    const result = parseRavenLayout(
      layout({
        name: ' Velora Lantern ',
        bodies: [{ num: 16, name: ' Velora Lantern A 1 ' }],
        sites: [site({ name: ' Copper Finch Dock ' })],
      }),
    );
    expect(result.system?.name).toBe('Velora Lantern');
    expect(result.sites[0]?.name).toBe('Copper Finch Dock');
    expect(result.sites[0]?.raven_body_name).toBe('Velora Lantern A 1');
    expect(result.warnings).toEqual([]);
  });

  it('does not split Unicode characters when truncating a name', () => {
    const result = parseRavenLayout(layout({ name: '🪐'.repeat(65) }));
    expect(result.system?.name).toBe('🪐'.repeat(64));
    expect(result.warnings[0]?.code).toBe('name_truncated');
  });

  it.each([
    layout({ name: 'x'.repeat(257) }),
    layout({ bodies: [{ num: 16, name: 'x'.repeat(257) }] }),
    layout({ sites: [site({ name: 'x'.repeat(257) })] }),
    layout({ sites: [site({ id: 'x'.repeat(257) })] }),
    layout({ sites: [site({ buildType: 'x'.repeat(257) })] }),
    layout({ sites: [site({ status: 'x'.repeat(257) })] }),
  ])('rejects consumed strings longer than 256 characters', (input) => {
    expectFatal(input, 'invalid_string');
  });

  it('ignores unknown fields, including long strings', () => {
    const result = parseRavenLayout(
      layout({
        extra: 'x'.repeat(300),
        bodies: [
          { num: 16, name: 'Velora Lantern A 1', features: ['x'.repeat(300)] },
        ],
        sites: [site({ extra: 'x'.repeat(300) })],
      }),
    );
    expect(result.ok).toBe(true);
    expect(result.warnings).toEqual([]);
  });

  it('allows omitted collections as an empty layout', () => {
    const result = parseRavenLayout({
      v: 6,
      id64: '123',
      name: 'Velora Lantern',
    });
    expect(result.ok).toBe(true);
    expect(result.sites).toEqual([]);
    expect(result.slots).toEqual([]);
  });

  it('skips malformed body and site entries without losing valid entries', () => {
    const result = parseRavenLayout(
      layout({
        bodies: [null, { num: 17 }, { num: 16, name: 'Velora Lantern A 1' }],
        sites: [null, {}, site()],
      }),
    );
    expect(result.ok).toBe(true);
    expect(result.sites).toHaveLength(1);
    expect(result.sites[0]?.raven_body_name).toBe('Velora Lantern A 1');
    expect(result.warnings).toHaveLength(4);
  });

  it.each([
    [null, null, null],
    [{}, null, null],
    [[1], 1, null],
    [[1, 2, 3], 1, 2],
  ])(
    'handles a malformed slot pair %s without throwing',
    (pair, orbital, surface) => {
      const result = parseRavenLayout(layout({ slots: { '16': pair } }));
      expect(result.ok).toBe(true);
      expect(result.slots).toEqual([
        {
          raven_body_name: 'Velora Lantern A 1',
          orbital_slots: orbital,
          surface_slots: surface,
        },
      ]);
      expect(result.warnings).toHaveLength(1);
      expect(result.warnings[0]?.code).toBe('invalid_slots');
    },
  );

  it('is deterministic and leaves the input unchanged', () => {
    const input = structuredClone(sample);
    const before = structuredClone(input);
    const first = parseRavenLayout(input);
    expect(parseRavenLayout(input)).toEqual(first);
    expect(input).toEqual(before);
  });

  it('returns a fatal error for content with a throwing accessor', () => {
    const input = Object.defineProperty(layout(), 'name', {
      get() {
        throw new Error('Not plain data');
      },
    });
    expectFatal(input);
  });
});

describe('matchRavenBodies', () => {
  it('matches exact names while retaining independent site and slot order', () => {
    const result = parseRavenLayout(sample);
    const matched = matchRavenBodies(result, [
      { body_id: 'body-32', name: 'Velora Lantern A 2' },
      { body_id: 'body-17', name: 'Velora Lantern A 1 a' },
      { body_id: 'body-0', name: 'Velora Lantern A' },
      { body_id: 'body-16', name: 'Velora Lantern A 1' },
    ]);
    expect(matched).toEqual({
      siteBodyRefs: ['body-16', 'body-17', 'body-0', 'body-32'],
      slotBodyRefs: ['body-16', 'body-17', 'body-32'],
      warnings: [],
    });
  });

  it('matches case-insensitively after trimming both names', () => {
    const result = parseRavenLayout(layout());
    result.sites[0].raven_body_name = ' VELORA LANTERN A 1 ';
    result.slots[0].raven_body_name = ' velora lantern a 1 ';
    expect(
      matchRavenBodies(result, [
        { body_id: 'body-16', name: ' Velora Lantern A 1 ' },
      ]),
    ).toEqual({
      siteBodyRefs: ['body-16'],
      slotBodyRefs: ['body-16'],
      warnings: [],
    });
  });

  it('returns null and warnings naming each unmatched body, without partial-name matching', () => {
    const matched = matchRavenBodies(parseRavenLayout(layout()), [
      { body_id: 'different-body', name: 'Velora Lantern A 1 a' },
    ]);
    expect(matched.siteBodyRefs).toEqual([null]);
    expect(matched.slotBodyRefs).toEqual([null]);
    expect(matched.warnings).toHaveLength(2);
    expect(
      matched.warnings.every((entry) =>
        entry.detail.includes('Velora Lantern A 1'),
      ),
    ).toBe(true);
  });

  it('preserves a missing Raven site body as null', () => {
    const result = parseRavenLayout(
      layout({ sites: [site({ bodyNum: 999 })], slots: {} }),
    );
    const matched = matchRavenBodies(result, []);
    expect(matched.siteBodyRefs).toEqual([null]);
    expect(matched.slotBodyRefs).toEqual([]);
  });

  it('does not assign ambiguous normalized names to an arbitrary body', () => {
    const matched = matchRavenBodies(parseRavenLayout(layout()), [
      { body_id: 'first', name: 'Velora Lantern A 1' },
      { body_id: 'second', name: ' VELORA LANTERN A 1 ' },
    ]);
    expect(matched.siteBodyRefs).toEqual([null]);
    expect(matched.slotBodyRefs).toEqual([null]);
    expect(matched.warnings).toHaveLength(2);
    expect(
      matched.warnings.every((entry) => entry.code === 'ambiguous_body'),
    ).toBe(true);
  });

  it('does not mutate the parsed result or the candidate bodies', () => {
    const result = parseRavenLayout(sample);
    const bodies = [{ body_id: 'body-16', name: ' Velora Lantern A 1 ' }];
    const before = structuredClone({ result, bodies });
    const matched = matchRavenBodies(result, bodies);
    expect(matchRavenBodies(result, bodies)).toEqual(matched);
    expect({ result, bodies }).toEqual(before);
  });
});
