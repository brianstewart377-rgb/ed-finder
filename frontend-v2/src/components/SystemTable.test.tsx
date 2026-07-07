import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SystemTable, type SystemRow } from './SystemTable';

describe('SystemTable data trust display', () => {
  it('does not render missing coordinates or distance as zero', () => {
    const rows = [{
      id64: 2008132031194,
      name: 'Exioce',
      x: 0,
      y: 0,
      z: 0,
      population: null,
      is_colonised: false,
      score: null,
      economy: null,
      timestamp: null,
      distance: null,
    }] as unknown as SystemRow[];

    render(<SystemTable rows={rows} columns={['system', 'coords', 'distanceRef', 'population']} />);

    expect(screen.getAllByText('Unknown')).toHaveLength(2);
    expect(screen.getByText('Exioce')).toBeTruthy();
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
    expect(screen.queryByText(/0\.00/)).toBeNull();
    expect(screen.queryByText(/0\.0 LY from Sol/)).toBeNull();
  });

  it('renders development score and archetype context when provided', () => {
    const rows = [{
      id64: 42,
      name: 'Handoff',
      x: 1,
      y: 2,
      z: 3,
      population: 1000,
      is_colonised: false,
      score: 91,
      economy: 'Refinery',
      archetype: 'refinery_industrial',
      secondaryArchetype: 'trade_logistics',
      timestamp: '2026-07-05T00:00:00Z',
      distance: 12.5,
    }] as SystemRow[];

    render(<SystemTable rows={rows} columns={['system', 'score', 'economy']} />);

    expect(screen.getByText('Score 91')).toBeTruthy();
    expect(screen.getByText('Refinery / Industrial Megacomplex')).toBeTruthy();
    expect(screen.getByText('Trade / Logistics Hub')).toBeTruthy();
  });
});
