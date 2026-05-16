import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { SystemResult } from '@/types/api';
import { ResultCard } from './ResultCard';

const system = {
  id64: 42,
  name: 'Handoff',
  coords: { x: 1, y: 2, z: 3 },
  distance: 12.34,
  population: 0,
  is_colonised: false,
  primaryEconomy: 'Agriculture',
  _rating: {
    score: 82,
    confidence: 0.7,
    rationale: 'Good fit',
  },
} as unknown as SystemResult;

describe('ResultCard Colony Planner action', () => {
  it('opens normal detail and focused Colony Planner without auto-running anything', () => {
    const onOpenDetail = vi.fn();
    render(
      <ResultCard
        system={system}
        index={0}
        onOpenDetail={onOpenDetail}
      />,
    );

    fireEvent.click(screen.getByText('Handoff'));
    fireEvent.click(screen.getByRole('button', { name: /Details/i }));
    fireEvent.click(screen.getByRole('button', { name: /Evaluate in Colony Planner/i }));

    expect(onOpenDetail).toHaveBeenCalledTimes(2);
    expect(onOpenDetail.mock.calls[0]).toEqual([42]);
    expect(onOpenDetail.mock.calls[1]).toEqual([42, { focus: 'colony-planner' }]);
  });
});
