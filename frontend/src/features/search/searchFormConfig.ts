import { BODY_SLIDERS, type BodySliderKey, type SearchFilters } from './useSearch';

export const SLIDER_GROUPS = [
  {
    id: 'high-value',
    label: 'Valuable worlds',
    shortLabel: 'Valuable worlds',
    description: 'Look for systems containing Earth-like, water or ammonia worlds.',
    summary: 'Earth-like, water and ammonia worlds',
    keys: ['elw', 'ww', 'ammonia'],
  },
  {
    id: 'stars',
    label: 'Stellar objects',
    shortLabel: 'Stellar objects',
    description: 'Look for systems containing black holes, neutron stars, white dwarfs or other stars.',
    summary: 'Black holes, neutron stars and more',
    keys: ['blackHole', 'neutron', 'whiteDwarf', 'otherStar'],
  },
  {
    id: 'landable',
    label: 'Accessible surfaces',
    shortLabel: 'Accessible surfaces',
    description: 'Look for systems with landable bodies or bodies that can be explored on foot.',
    summary: 'Landable and walkable bodies',
    keys: ['landable', 'walkable'],
  },
  {
    id: 'planetary',
    label: 'Planet classes',
    shortLabel: 'Planet classes',
    description: 'Look for specific planet types, from gas giants to rocky, icy and metal-rich worlds.',
    summary: 'Rocky, icy, metal-rich and gas worlds',
    keys: ['gasGiant', 'hmc', 'metalRich', 'rockyIce', 'rocky', 'icy'],
  },
  {
    id: 'signals',
    label: 'Rings & signals',
    shortLabel: 'Rings & signals',
    description: 'Look for systems with rings, geological activity or biological signals.',
    summary: 'Rings, geological and biological signals',
    keys: ['rings', 'geoSignals', 'bioSignals'],
  },
] as const satisfies readonly {
  id: string;
  label: string;
  shortLabel: string;
  description: string;
  summary: string;
  keys: readonly BodySliderKey[];
}[];

export type SliderGroupId = (typeof SLIDER_GROUPS)[number]['id'];
export type FilterSectionId = 'reference' | 'presets' | 'distance' | 'system' | SliderGroupId | 'sort';

export const ECONOMY_OPTIONS: { value: string; label: string }[] = [
  { value: 'any', label: 'Any' },
  { value: 'Agriculture', label: 'Agriculture' },
  { value: 'Refinery', label: 'Refinery' },
  { value: 'Industrial', label: 'Industrial' },
  { value: 'HighTech', label: 'High Tech' },
  { value: 'Military', label: 'Military' },
  { value: 'Tourism', label: 'Tourism' },
  { value: 'Extraction', label: 'Extraction' },
];

export function distanceSummary(filters: SearchFilters) {
  if (filters.galaxyWide) return `Across the galaxy · show up to ${filters.size}`;
  const range = filters.minDistance > 0
    ? `${filters.minDistance}–${filters.maxDistance} LY from origin`
    : `Within ${filters.maxDistance} LY`;
  return `${range} · show up to ${filters.size}`;
}

export function rangeGroupSummary(
  filters: SearchFilters,
  keys: readonly BodySliderKey[],
  defaultSummary: string,
) {
  const constraints: string[] = [];
  for (const key of keys) {
    const definition = BODY_SLIDERS.find((slider) => slider.key === key);
    const range = filters.bodyRanges[key];
    if (!definition || !range || (range.min === 0 && range.max === definition.max)) continue;
    if (range.min > 0 && range.max < definition.max) {
      constraints.push(`${definition.label} ${range.min}–${range.max}`);
    } else if (range.min > 0) {
      constraints.push(`${definition.label} ≥ ${range.min}`);
    } else {
      constraints.push(`${definition.label} ≤ ${range.max}`);
    }
  }
  if (constraints.length === 0) return defaultSummary;
  const visible = constraints.slice(0, 2).join(' · ');
  return constraints.length > 2 ? `${visible} · +${constraints.length - 2} more` : visible;
}

export function systemProfileSummary(filters: SearchFilters) {
  const status = filters.populated === 'uninhabited'
    ? 'Non-colonised'
    : filters.populated === 'populated'
      ? 'Inhabited'
      : 'Any status';
  const economy = filters.economy === 'any' ? 'any economy' : economyLabel(filters.economy);
  return `${status} · ${economy}`;
}

function economyLabel(economy: string) {
  return ECONOMY_OPTIONS.find((option) => option.value === economy)?.label ?? economy;
}

export function sortLabel(sortBy: SearchFilters['sortBy']) {
  if (sortBy === 'distance') return 'Nearest first';
  if (sortBy === 'population') return 'Highest population';
  return 'Best development potential first';
}
