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
});
