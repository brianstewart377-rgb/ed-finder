/**
 * Renderer-neutral stellar icon families for the Galaxy map.
 *
 * The catalogue values remain the truth. These descriptors only control the
 * non-factual marker shape, colour and relative display size.
 */
export type StellarGlyph =
  | 'ttauri-herbig'
  | 'brown-dwarf-y-t'
  | 'brown-dwarf-l'
  | 'main-sequence-m'
  | 'main-sequence-k'
  | 'main-sequence-g'
  | 'main-sequence-f'
  | 'main-sequence-a'
  | 'main-sequence-b'
  | 'main-sequence-o'
  | 'giant-warm'
  | 'giant-yellow'
  | 'giant-white'
  | 'giant-blue'
  | 'wolf-rayet'
  | 'hypergiant'
  | 'carbon'
  | 'white-dwarf'
  | 'neutron'
  | 'black-hole'
  | 'supermassive-black-hole'
  | 'unknown';

export type StellarPresentation = Readonly<{
  glyph: StellarGlyph;
  label: string;
  coreRgb: readonly [number, number, number];
  haloRgb: readonly [number, number, number];
  relativeScale: number;
  darkCore: boolean;
  ring: boolean;
}>;

type StellarPresentationInput = Readonly<{
  type?: string | null;
  subtype?: string | null;
}>;

const presentations = {
  'ttauri-herbig': [
    'T Tauri / AeBe Herbig',
    [1, 0.09, 0.13],
    [1, 0.16, 0.1],
    0.92,
    false,
    false,
  ],
  'brown-dwarf-y-t': [
    'Y / T brown dwarf',
    [0.78, 0.035, 0.08],
    [0.98, 0.06, 0.12],
    0.72,
    false,
    false,
  ],
  'brown-dwarf-l': [
    'L brown dwarf',
    [1, 0.16, 0.035],
    [1, 0.25, 0.06],
    0.8,
    false,
    false,
  ],
  'main-sequence-m': [
    'M class star',
    [1, 0.2, 0.06],
    [1, 0.26, 0.08],
    0.9,
    false,
    false,
  ],
  'main-sequence-k': [
    'K class star',
    [1, 0.47, 0.19],
    [1, 0.36, 0.11],
    0.96,
    false,
    false,
  ],
  'main-sequence-g': [
    'G class star',
    [1, 0.98, 0.66],
    [1, 0.92, 0.38],
    1,
    false,
    false,
  ],
  'main-sequence-f': [
    'F class star',
    [0.92, 0.94, 1],
    [0.72, 0.76, 1],
    1.04,
    false,
    false,
  ],
  'main-sequence-a': [
    'A class star',
    [0.62, 0.55, 1],
    [0.42, 0.28, 1],
    1.12,
    false,
    false,
  ],
  'main-sequence-b': [
    'B class star',
    [0.29, 0.34, 1],
    [0.09, 0.16, 1],
    1.2,
    false,
    false,
  ],
  'main-sequence-o': [
    'O class star',
    [0.18, 0.27, 1],
    [0.04, 0.12, 1],
    1.3,
    false,
    false,
  ],
  'giant-warm': [
    'M / K giant or supergiant',
    [1, 0.34, 0.12],
    [1, 0.18, 0.04],
    1.72,
    false,
    false,
  ],
  'giant-yellow': [
    'G giant or supergiant',
    [1, 1, 0.62],
    [0.95, 0.9, 0.32],
    1.62,
    false,
    false,
  ],
  'giant-white': [
    'F giant or supergiant',
    [0.9, 0.92, 1],
    [0.65, 0.67, 1],
    1.66,
    false,
    false,
  ],
  'giant-blue': [
    'O / B / A giant or supergiant',
    [0.46, 0.38, 1],
    [0.12, 0.16, 1],
    1.84,
    false,
    false,
  ],
  'wolf-rayet': [
    'Wolf-Rayet star',
    [1, 1, 1],
    [0.7, 0.78, 1],
    1.38,
    false,
    false,
  ],
  hypergiant: [
    'Hypergiant',
    [0.75, 0.8, 1],
    [0.46, 0.52, 1],
    2.1,
    false,
    false,
  ],
  carbon: [
    'Carbon star',
    [0.92, 0.93, 0.42],
    [0.78, 0.63, 0.18],
    1.36,
    false,
    false,
  ],
  'white-dwarf': [
    'White dwarf',
    [0.86, 0.91, 1],
    [0.45, 0.58, 1],
    0.66,
    false,
    false,
  ],
  neutron: ['Neutron star', [1, 1, 1], [0.58, 0.72, 1], 0.52, false, false],
  'black-hole': [
    'Black hole',
    [0.005, 0.007, 0.012],
    [0.56, 0.43, 0.34],
    0.92,
    true,
    true,
  ],
  'supermassive-black-hole': [
    'Supermassive black hole',
    [0, 0, 0],
    [0.55, 0.43, 0.36],
    1.48,
    true,
    true,
  ],
  unknown: [
    'Unknown star class',
    [0.47, 0.78, 0.88],
    [0.25, 0.64, 0.76],
    0.9,
    false,
    false,
  ],
} as const satisfies Record<
  StellarGlyph,
  readonly [
    label: string,
    coreRgb: readonly [number, number, number],
    haloRgb: readonly [number, number, number],
    relativeScale: number,
    darkCore: boolean,
    ring: boolean,
  ]
>;

function descriptor(glyph: StellarGlyph): StellarPresentation {
  const [label, coreRgb, haloRgb, relativeScale, darkCore, ring] =
    presentations[glyph];
  return { glyph, label, coreRgb, haloRgb, relativeScale, darkCore, ring };
}

function normalise(input: StellarPresentationInput): string {
  return `${input.type ?? ''} ${input.subtype ?? ''}`
    .trim()
    .toLocaleLowerCase()
    .replace(/[()/_-]+/gu, ' ')
    .replace(/\s+/gu, ' ');
}

function leadingClass(input: StellarPresentationInput): string {
  for (const value of [input.type, input.subtype]) {
    const match = (value ?? '')
      .trim()
      .toUpperCase()
      .match(/^([OBAFGKMLTY])(?:\s|$|\()/u);
    if (match?.[1]) return match[1];
  }
  return '';
}

export function stellarPresentation(
  input: StellarPresentationInput = {},
): StellarPresentation {
  const value = normalise(input);
  if (/supermassive|sagittarius\s*a\*|sgr\s*a\*/u.test(value))
    return descriptor('supermassive-black-hole');
  if (/black\s*hole/u.test(value) || /^h(?:\s|$)/u.test(value))
    return descriptor('black-hole');
  if (/neutron/u.test(value) || /^n(?:\s|$)/u.test(value))
    return descriptor('neutron');
  if (/hypergiant/u.test(value)) return descriptor('hypergiant');
  if (/white\s*dwarf/u.test(value) || /^d[abcoqvxz]?(?:\s|$)/u.test(value))
    return descriptor('white-dwarf');
  if (/wolf\s*rayet|wolf-rayet|^w(?:c|n|o)(?:\s|$)/u.test(value))
    return descriptor('wolf-rayet');
  if (/t\s*tauri|herbig|aebe/u.test(value)) return descriptor('ttauri-herbig');
  if (/carbon|^c(?:\s|$)|^s(?:\s|$)|^ms(?:\s|$)/u.test(value))
    return descriptor('carbon');
  const spectralClass = leadingClass(input);
  const giant = /(?:^|\s)(?:i|ii|iii|iv)(?:\s|$)|giant/u.test(value);
  if (giant) {
    if (spectralClass === 'M' || spectralClass === 'K')
      return descriptor('giant-warm');
    if (spectralClass === 'G') return descriptor('giant-yellow');
    if (spectralClass === 'F') return descriptor('giant-white');
    if (['O', 'B', 'A'].includes(spectralClass))
      return descriptor('giant-blue');
  }

  if (spectralClass === 'Y' || spectralClass === 'T')
    return descriptor('brown-dwarf-y-t');
  if (spectralClass === 'L') return descriptor('brown-dwarf-l');
  if (spectralClass === 'M') return descriptor('main-sequence-m');
  if (spectralClass === 'K') return descriptor('main-sequence-k');
  if (spectralClass === 'G') return descriptor('main-sequence-g');
  if (spectralClass === 'F') return descriptor('main-sequence-f');
  if (spectralClass === 'A') return descriptor('main-sequence-a');
  if (spectralClass === 'B') return descriptor('main-sequence-b');
  if (spectralClass === 'O') return descriptor('main-sequence-o');
  return descriptor('unknown');
}
