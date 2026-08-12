import { describe, expect, it } from 'vitest';
import { powerColour, powerplayFreshness, powerplayStateSize } from './powerplayPresentation';

describe('PowerplayPointLayer presentation', () => {
  it('covers every March 2025 community-schema power with a distinct power colour', () => {
    const powers = [
      'Aisling Duval', 'A. Lavigny-Duval', 'Archon Delaine', 'Denton Patreus',
      'Edmund Mahon', 'Felicia Winters', 'Jerome Archer', 'Li Yong-Rui',
      'Nakato Kaine', 'Pranav Antal', 'Yuri Grom', 'Zemina Torval',
    ];
    expect(new Set(powers.map(powerColour)).size).toBe(powers.length);
  });

  it('uses marker size for control tier and brightness for freshness', () => {
    expect(powerplayStateSize('Stronghold')).toBeGreaterThan(powerplayStateSize('Fortified'));
    expect(powerplayStateSize('Fortified')).toBeGreaterThan(powerplayStateSize('Exploited'));
    expect(powerplayFreshness('low')).toBeGreaterThan(powerplayFreshness('medium'));
    expect(powerplayFreshness('medium')).toBeGreaterThan(powerplayFreshness('high'));
  });
});
