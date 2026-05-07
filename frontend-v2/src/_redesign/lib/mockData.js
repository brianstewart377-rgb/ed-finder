// Mock galactic data — modeled after the real ed-finder backend response shapes.
// No network calls. No backend touched. Pure local data for the prototype.

export const REGIONS = [
  { id: 1, name: 'Inner Orion Spur', x: 0, z: 0, count: 412_000, avgScore: 47 },
  { id: 2, name: 'Pleiades Sector', x: -85, z: -340, count: 38_400, avgScore: 61 },
  { id: 3, name: 'Hawking\'s Gap', x: 220, z: 800, count: 91_300, avgScore: 53 },
  { id: 4, name: 'Colonia', x: -78, z: 220, count: 24_900, avgScore: 58 },
  { id: 5, name: 'Outer Arm', x: 380, z: 510, count: 18_500, avgScore: 42 },
];

export const CLUSTERS = [
  { id: 1, name: 'Wregoe Anchor',  x: -120, z: -45, radius: 95,  topEcon: 'HighTech',   topScore: 89 },
  { id: 2, name: 'HIP 22460 Bloc', x:  165, z: -32, radius: 70,  topEcon: 'Tourism',    topScore: 82 },
  { id: 3, name: 'NGC 1893 Reach', x:  -90, z:  180, radius: 120, topEcon: 'Refinery',   topScore: 76 },
  { id: 4, name: 'Synuefe Run',    x:   60, z:   90, radius: 50,  topEcon: 'Industrial', topScore: 71 },
  { id: 5, name: 'Hyades Frontier',x: -200, z:  -20, radius: 85,  topEcon: 'Agriculture',topScore: 68 },
];

// Heatmap voxels (200LY cubes carrying mean score). Hand-picked for visual.
export const HEATMAP = (() => {
  const cells = [];
  for (let i = 0; i < 60; i++) {
    cells.push({
      x: (Math.random() - 0.5) * 700,
      z: (Math.random() - 0.5) * 700,
      score: Math.floor(20 + Math.random() * 70),
    });
  }
  return cells;
})();

// Mock systems with full rating breakdown (matches backend ratings table)
export const SYSTEMS = [
  {
    id64: 1001,
    name: 'Wregoe XX-1 b48-2',
    x: -118, y: -2, z: -42,
    distance: 184.2,
    population: 0,
    is_colonised: false,
    primaryEconomy: 'High Tech',
    secondaryEconomy: 'Refinery',
    allegiance: 'Independent',
    security: 'Low',
    score: 89,
    confidence: 0.92,
    rationale: 'Exceptional terraforming potential, 2 ELWs, low orbital risk, dense biological signal yield.',
    breakdown: {
      Agriculture: 42, Refinery: 71, Industrial: 55,
      HighTech: 89,    Military: 38, Tourism: 64, Extraction: 58,
    },
    economySuggestion: 'High Tech',
    bodies: { elw: 2, ww: 1, ammonia: 0, terra: 4, gasGiant: 3, landable: 8 },
    signals: { bio: 28, geo: 14 },
    stars: { neutron: 0, blackHole: 0, whiteDwarf: 0 },
  },
  {
    id64: 1002,
    name: 'HIP 22460',
    x: 162, y: 8, z: -28,
    distance: 224.7,
    population: 14_300_000_000,
    is_colonised: true,
    primaryEconomy: 'Tourism',
    secondaryEconomy: 'High Tech',
    allegiance: 'Federation',
    security: 'High',
    score: 82,
    confidence: 0.88,
    rationale: 'Established Tourism hub, neutron cluster nearby, 3 mapped Earth-likes within 50LY.',
    breakdown: {
      Agriculture: 31, Refinery: 28, Industrial: 44,
      HighTech: 78, Military: 52, Tourism: 82, Extraction: 35,
    },
    economySuggestion: 'Tourism',
    bodies: { elw: 1, ww: 2, ammonia: 0, terra: 2, gasGiant: 4, landable: 11 },
    signals: { bio: 12, geo: 4 },
    stars: { neutron: 1, blackHole: 0, whiteDwarf: 0 },
  },
  {
    id64: 1003,
    name: 'Synuefe IB-S c19-12',
    x: 58, y: -12, z: 88,
    distance: 158.3,
    population: 0,
    is_colonised: false,
    primaryEconomy: 'Refinery',
    secondaryEconomy: 'Industrial',
    allegiance: 'Independent',
    security: 'Low',
    score: 76,
    confidence: 0.81,
    rationale: 'Metal-rich ring stack with 6 high-density rocky bodies, ideal Refinery/Industrial pairing.',
    breakdown: {
      Agriculture: 22, Refinery: 76, Industrial: 71,
      HighTech: 35, Military: 41, Tourism: 28, Extraction: 73,
    },
    economySuggestion: 'Refinery',
    bodies: { elw: 0, ww: 0, ammonia: 0, terra: 1, gasGiant: 2, landable: 14 },
    signals: { bio: 4, geo: 22 },
    stars: { neutron: 0, blackHole: 0, whiteDwarf: 0 },
  },
  {
    id64: 1004,
    name: 'Pleiades RX-K d8-22',
    x: -84, y: 4, z: -338,
    distance: 348.1,
    population: 0,
    is_colonised: false,
    primaryEconomy: 'Agriculture',
    secondaryEconomy: 'Tourism',
    allegiance: 'Independent',
    security: 'Anarchy',
    score: 71,
    confidence: 0.74,
    rationale: '1 Earth-like + 3 terraformables. Mid-confidence — body data partial.',
    breakdown: {
      Agriculture: 71, Refinery: 18, Industrial: 24,
      HighTech: 45, Military: 32, Tourism: 58, Extraction: 22,
    },
    economySuggestion: 'Agriculture',
    bodies: { elw: 1, ww: 0, ammonia: 0, terra: 3, gasGiant: 1, landable: 5 },
    signals: { bio: 18, geo: 6 },
    stars: { neutron: 0, blackHole: 0, whiteDwarf: 0 },
  },
  {
    id64: 1005,
    name: 'NGC 1893 Sector OD-T b3-7',
    x: -91, y: -14, z: 178,
    distance: 201.5,
    population: 0,
    is_colonised: false,
    primaryEconomy: 'Refinery',
    secondaryEconomy: 'Extraction',
    allegiance: 'Independent',
    security: 'Low',
    score: 68,
    confidence: 0.79,
    rationale: 'Solid Refinery slot capacity, single black hole increases orbital risk.',
    breakdown: {
      Agriculture: 18, Refinery: 68, Industrial: 54,
      HighTech: 31, Military: 47, Tourism: 22, Extraction: 65,
    },
    economySuggestion: 'Refinery',
    bodies: { elw: 0, ww: 0, ammonia: 1, terra: 0, gasGiant: 3, landable: 9 },
    signals: { bio: 2, geo: 11 },
    stars: { neutron: 0, blackHole: 1, whiteDwarf: 0 },
  },
  {
    id64: 1006,
    name: 'Col 285 Sector AA-Q d5-93',
    x: 102, y: 0, z: 14,
    distance: 102.9,
    population: 0,
    is_colonised: false,
    primaryEconomy: 'Industrial',
    secondaryEconomy: 'High Tech',
    allegiance: 'Independent',
    security: 'Medium',
    score: 64,
    confidence: 0.68,
    rationale: 'Dense rocky stack, viable Industrial. Lower confidence due to incomplete signal scan.',
    breakdown: {
      Agriculture: 21, Refinery: 48, Industrial: 64,
      HighTech: 52, Military: 38, Tourism: 24, Extraction: 51,
    },
    economySuggestion: 'Industrial',
    bodies: { elw: 0, ww: 0, ammonia: 0, terra: 1, gasGiant: 2, landable: 8 },
    signals: { bio: 8, geo: 5 },
    stars: { neutron: 0, blackHole: 0, whiteDwarf: 0 },
  },
];

export const EDDN_FEED = [
  { ago: '2 min', cmdr: 'SmurfTheBlue',   action: 'first-discovered', system: 'HIP 12345',         scoreDelta: '+73 (Tourism)' },
  { ago: '7 min', cmdr: 'KaelOrbital',    action: 'station-detected', system: 'Wregoe AB-Q b48-2', scoreDelta: '71 → 78' },
  { ago: '12 min',cmdr: 'Astra Voyager',  action: 'mapped',           system: 'Synuefe IB-S',      scoreDelta: '+1 ELW' },
  { ago: '23 min',cmdr: 'Frostbyte',      action: 'claimed',          system: 'Col 285 AA-Q',      scoreDelta: '64 (Industrial)' },
  { ago: '41 min',cmdr: 'NebulaPilot',    action: 'first-footfall',   system: 'Pleiades RX-K',     scoreDelta: '+8 bio signals' },
];

export const ECONOMIES = [
  'Agriculture', 'Refinery', 'Industrial', 'HighTech',
  'Military', 'Tourism', 'Extraction',
];

export const ECON_COLORS = {
  Agriculture: '#66bb6a',
  Refinery:    '#ff9133',
  Industrial:  '#ffaa33',
  HighTech:    '#42a5f5',
  Military:    '#ef5350',
  Tourism:     '#ec407a',
  Extraction:  '#90a4ae',
};

export function ratingTier(score) {
  if (score == null) return { label: 'N/A',       color: 'var(--steel-400)' };
  if (score >= 85)   return { label: 'JACKPOT',   color: 'var(--rate-jackpot)' };
  if (score >= 70)   return { label: 'EXCELLENT', color: 'var(--rate-good)' };
  if (score >= 55)   return { label: 'GOOD',      color: 'var(--ed-orange)' };
  if (score >= 40)   return { label: 'OK',        color: 'var(--rate-ok)' };
  return               { label: 'POOR',      color: 'var(--rate-poor)' };
}

export function fmtPop(n) {
  if (!n) return '—';
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(0)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
  return `${n}`;
}
