import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { WorkspaceHeader } from './WorkspaceHeader';
import type { SystemDetail } from '@/types/api';

describe('WorkspaceHeader data trust display', () => {
  it('renders unknown coords and population for non-Sol origin records', () => {
    const system = {
      id64: 2008132031194,
      name: 'Exioce',
      x: 0,
      y: 0,
      z: 0,
      population: null,
      is_colonised: true,
      primary_economy: null,
    } as unknown as SystemDetail;

    render(
      <WorkspaceHeader
        system={system}
        onBackToFinder={vi.fn()}
        onOpenSystemDetail={vi.fn()}
      />,
    );

    expect(screen.getByText('Colonised')).toBeTruthy();
    expect(screen.getAllByText('Unknown').length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText('0.00, 0.00, 0.00')).toBeNull();
    expect(screen.queryByText('Uninhabited')).toBeNull();
  });
});
