import { describe, expect, it } from 'vitest';

import { stellarPresentation } from './stellar-presentation';

describe('stellar presentation', () => {
  it.each([
    ['T Tauri Star', null, 'ttauri-herbig'],
    ['Herbig Ae/Be Star', null, 'ttauri-herbig'],
    ['Y', 'Brown dwarf', 'brown-dwarf-y-t'],
    ['L', null, 'brown-dwarf-l'],
    ['M', '5 V', 'main-sequence-m'],
    ['K', '4 V', 'main-sequence-k'],
    ['G', '2 V', 'main-sequence-g'],
    ['Star', 'G (White-Yellow) Star', 'main-sequence-g'],
    ['F', null, 'main-sequence-f'],
    ['A', null, 'main-sequence-a'],
    ['B', null, 'main-sequence-b'],
    ['O', null, 'main-sequence-o'],
    ['M', 'III', 'giant-warm'],
    ['G', 'Supergiant', 'giant-yellow'],
    ['F', 'Giant', 'giant-white'],
    ['B', 'Ia Supergiant', 'giant-blue'],
    ['Wolf-Rayet N Star', null, 'wolf-rayet'],
    ['D Hypergiant', null, 'hypergiant'],
    ['Carbon Star', null, 'carbon'],
    ['White Dwarf (DA) Star', null, 'white-dwarf'],
    ['D', 'A7', 'white-dwarf'],
    ['Neutron Star', null, 'neutron'],
    ['Black Hole', null, 'black-hole'],
    ['Supermassive Black Hole', null, 'supermassive-black-hole'],
  ] as const)('maps %s %s to the %s icon family', (type, subtype, glyph) => {
    expect(stellarPresentation({ type, subtype }).glyph).toBe(glyph);
  });

  it('uses an explicit unknown icon instead of guessing a physical class', () => {
    expect(stellarPresentation({ type: 'mystery' })).toMatchObject({
      glyph: 'unknown',
      label: 'Unknown star class',
    });
  });
});
