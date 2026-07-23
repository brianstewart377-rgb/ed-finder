// Representative local mock data for the UI concept gallery.
//
// NOTE: This is illustrative design data only. It is not wired to any API,
// store, dataset, or ranking logic and must never be treated as production
// truth. Numbers are hand-authored to exercise the layouts.

export interface MockSystem {
  id64: number;
  name: string;
  distanceLy: number;
  coords: { x: number; y: number; z: number };
  primaryEconomy: string;
  developmentScore: number;
  tier: 'S' | 'A' | 'B' | 'C' | 'D';
  buildability: number;
  purity: number;
  population: number;
  allegiance: string;
  security: string;
  status: 'Uncolonised' | 'Colonising' | 'Colonised';
}

export const finderSystems: MockSystem[] = [
  { id64: 10001, name: 'HIP 21991', distanceLy: 42.6, coords: { x: -18.4, y: -32.1, z: 44.7 }, primaryEconomy: 'Refinery', developmentScore: 91, tier: 'S', buildability: 88, purity: 74, population: 0, allegiance: 'Independent', security: 'Low', status: 'Uncolonised' },
  { id64: 10002, name: 'Wolf 1301', distanceLy: 58.2, coords: { x: 24.9, y: 6.5, z: -12.3 }, primaryEconomy: 'Industrial', developmentScore: 83, tier: 'A', buildability: 79, purity: 66, population: 0, allegiance: 'Independent', security: 'Anarchy', status: 'Uncolonised' },
  { id64: 10003, name: 'Col 285 Sector KV-Q', distanceLy: 73.9, coords: { x: 61.2, y: -18.8, z: 90.4 }, primaryEconomy: 'HighTech', developmentScore: 77, tier: 'A', buildability: 71, purity: 81, population: 0, allegiance: 'Independent', security: 'Low', status: 'Uncolonised' },
  { id64: 10004, name: 'LTT 4961', distanceLy: 88.1, coords: { x: -44.0, y: 12.9, z: 33.2 }, primaryEconomy: 'Agriculture', developmentScore: 64, tier: 'B', buildability: 62, purity: 58, population: 0, allegiance: 'Independent', security: 'Medium', status: 'Uncolonised' },
  { id64: 10005, name: 'Synuefe EN-H', distanceLy: 104.5, coords: { x: 102.4, y: -8.1, z: 51.9 }, primaryEconomy: 'Extraction', developmentScore: 58, tier: 'B', buildability: 55, purity: 49, population: 0, allegiance: 'Independent', security: 'Low', status: 'Colonising' },
  { id64: 10006, name: 'Hyades Sector DB-X', distanceLy: 129.7, coords: { x: -70.2, y: 41.3, z: 8.6 }, primaryEconomy: 'Tourism', developmentScore: 45, tier: 'C', buildability: 44, purity: 63, population: 0, allegiance: 'Independent', security: 'Medium', status: 'Uncolonised' },
];

export interface FilterCategory {
  id: string;
  label: string;
  summary: string;
  active: boolean;
}

export const finderFilterCategories: FilterCategory[] = [
  { id: 'reference', label: 'Reference', summary: 'Sol · 0.00, 0.00, 0.00', active: true },
  { id: 'radius', label: 'Radius', summary: '0 – 200 LY · 50/page', active: true },
  { id: 'bodies', label: 'Body types', summary: 'ELW ≥ 1 · Rings ≥ 2', active: true },
  { id: 'economy', label: 'Economy', summary: 'Any economy', active: false },
  { id: 'development', label: 'Development', summary: 'Score ≥ 40', active: true },
  { id: 'sort', label: 'Sort', summary: 'Development first', active: false },
];

export interface CompareMetric {
  key: string;
  label: string;
  group: string;
  values: (number | string | null)[]; // one per compare column
  higherIsBetter?: boolean;
  unit?: string;
}

export const compareColumns: MockSystem[] = finderSystems.slice(0, 4);

export const compareMetrics: CompareMetric[] = [
  { key: 'development', label: 'Development score', group: 'Potential', values: [91, 83, 77, 64], higherIsBetter: true, unit: '/100' },
  { key: 'buildability', label: 'Buildability', group: 'Potential', values: [88, 79, 71, 62], higherIsBetter: true, unit: '/100' },
  { key: 'purity', label: 'Ring purity', group: 'Potential', values: [74, 66, 81, 58], higherIsBetter: true, unit: '/100' },
  { key: 'distance', label: 'Distance from Sol', group: 'Logistics', values: [42.6, 58.2, 73.9, 88.1], higherIsBetter: false, unit: ' LY' },
  { key: 'economy', label: 'Primary economy', group: 'Profile', values: ['Refinery', 'Industrial', 'HighTech', 'Agriculture'] },
  { key: 'security', label: 'Security', group: 'Profile', values: ['Low', 'Anarchy', 'Low', 'Medium'] },
  { key: 'population', label: 'Population', group: 'Profile', values: [0, 0, null, 0] },
];

// Winner (best value) index per numeric metric — precomputed for display only.
export function bestIndex(metric: CompareMetric): number | null {
  const nums = metric.values.map((v) => (typeof v === 'number' ? v : null));
  if (nums.every((n) => n === null)) return null;
  let best: number | null = null;
  let bestVal = metric.higherIsBetter ? -Infinity : Infinity;
  nums.forEach((n, i) => {
    if (n === null) return;
    if (metric.higherIsBetter ? n > bestVal : n < bestVal) { bestVal = n; best = i; }
  });
  return best;
}

// ---- My Work -------------------------------------------------------------
export const myWork = {
  continue: { title: 'Colony Cockpit — HIP 21991', detail: 'Build plan draft · 3 of 7 slots placed', updated: '2h ago' },
  savedSystems: [
    { name: 'HIP 21991', note: 'Prime refinery candidate', tier: 'S' as const },
    { name: 'Col 285 Sector KV-Q', note: 'High-tech backup', tier: 'A' as const },
    { name: 'LTT 4961', note: 'Agriculture ring world', tier: 'B' as const },
  ],
  plans: [
    { name: 'Refinery corridor — Pleiades', status: 'Draft', systems: 4 },
    { name: 'Expansion — Wolf 1301', status: 'In review', systems: 2 },
  ],
  colonies: [
    { name: 'Aegis Station', system: 'HIP 21991', state: 'Constructing' },
  ],
  telemetry: {
    recent: [
      { system: 'Wolf 1301', when: '18m ago', events: 'FSD, Scan×4, Docked' },
      { system: 'Sol', when: '2h ago', events: 'Docked, Market' },
      { system: 'HIP 21991', when: '1d ago', events: 'Scan×11, Mapped×3' },
    ],
    freshness: 'Journal imported 18 minutes ago',
  },
};

// ---- Roadmap concepts ----------------------------------------------------
export const corridor = {
  start: 'Sol',
  target: 'Pleiades Sector',
  maxJumpLy: 34,
  waypoints: [
    { name: 'Sol', hop: 0 },
    { name: 'LHS 3006', hop: 1 },
    { name: 'Wolf 1301', hop: 2 },
    { name: 'HIP 21991', hop: 3 },
    { name: 'Merope', hop: 4 },
  ],
};

export const telemetryConcept = {
  visited: [
    { system: 'Wolf 1301', freshness: 'Fresh', events: 42 },
    { system: 'Col 285 Sector KV-Q', freshness: 'Stale (6d)', events: 11 },
    { system: 'Merope', freshness: 'Fresh', events: 27 },
  ],
};

export const nebulaLayers = [
  { id: 'nebula', label: 'Nebula fields', enabled: true },
  { id: 'poi', label: 'Community POIs', enabled: false },
];

export const syncCandidates = [
  { id: 'saved', label: 'Saved systems', note: '3 items' },
  { id: 'plans', label: 'Plans & expansion plans', note: '2 items' },
  { id: 'colonies', label: 'My colonies', note: '1 item' },
  { id: 'telemetry', label: 'Personal telemetry', note: 'Journal-derived' },
];
