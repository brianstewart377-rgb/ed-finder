import type { PowerplaySystemState } from '@/lib/api';

const POWER_COLOURS: Record<string, string> = {
  'Aisling Duval': '#58a6ff',
  'A. Lavigny-Duval': '#d54a62',
  'Archon Delaine': '#f0b44d',
  'Denton Patreus': '#d96a45',
  'Edmund Mahon': '#58b86b',
  'Felicia Winters': '#77bdf2',
  'Jerome Archer': '#4268d5',
  'Li Yong-Rui': '#42c9c2',
  'Nakato Kaine': '#8cce68',
  'Pranav Antal': '#9f78d5',
  'Yuri Grom': '#b6854c',
  'Zemina Torval': '#a9554e',
};

export function powerColour(power: unknown): string {
  return typeof power === 'string' ? POWER_COLOURS[power] ?? '#aeb8c1' : '#68727b';
}

export function powerplayFreshness(uncertainty: PowerplaySystemState['uncertainty']): number {
  return uncertainty === 'low' ? 1 : uncertainty === 'medium' ? 0.62 : 0.34;
}

export function powerplayStateSize(state: unknown): number {
  if (state === 'Stronghold') return 16;
  if (state === 'Fortified') return 13;
  if (state === 'Exploited') return 10;
  if (state === 'Unoccupied') return 7;
  return 9;
}
