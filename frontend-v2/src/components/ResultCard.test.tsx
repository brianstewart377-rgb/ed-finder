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
  it('opens normal detail and focused Colony Planner without double-calling or collapsing the card', () => {
    const onOpenDetail = vi.fn();
    const onPin = vi.fn();
    const onCompare = vi.fn();
    const onWatch = vi.fn();
    const onShowOnMap = vi.fn();
    render(
      <ResultCard
        system={system}
        index={0}
        onPin={onPin}
        onCompare={onCompare}
        onWatch={onWatch}
        onShowOnMap={onShowOnMap}
        onOpenDetail={onOpenDetail}
      />,
    );

    fireEvent.click(screen.getByText('Handoff'));
    fireEvent.click(screen.getByRole('button', { name: /Details/i }));
    fireEvent.click(screen.getByRole('button', { name: /Evaluate in Colony Planner/i }));
    fireEvent.click(screen.getByRole('button', { name: /Watch/i }));
    fireEvent.click(screen.getByRole('button', { name: /Map/i }));
    fireEvent.click(screen.getByTestId('result-card-pin-42'));
    fireEvent.click(screen.getByTestId('result-card-compare-42'));

    expect(onOpenDetail).toHaveBeenCalledTimes(2);
    expect(onOpenDetail.mock.calls[0]).toEqual([42]);
    expect(onOpenDetail.mock.calls[1]).toEqual([42, { focus: 'colony-planner' }]);
    expect(onWatch).toHaveBeenCalledWith(42);
    expect(onShowOnMap).toHaveBeenCalledWith(42);
    expect(onPin).toHaveBeenCalledWith(42);
    expect(onCompare).toHaveBeenCalledWith(42);
    expect(screen.getByRole('button', { name: /Evaluate in Colony Planner/i })).toBeTruthy();
  });
});
