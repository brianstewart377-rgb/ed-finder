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
  it('opens normal detail and dedicated Colony Planner without double-calling or collapsing the card', () => {
    const onOpenDetail = vi.fn();
    const onOpenColonyPlanner = vi.fn();
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
        onOpenColonyPlanner={onOpenColonyPlanner}
      />,
    );

    fireEvent.click(screen.getByText('Handoff'));
    fireEvent.click(screen.getByRole('button', { name: /Details/i }));
    fireEvent.click(screen.getByRole('button', { name: /Evaluate in Colony Planner/i }));
    fireEvent.click(screen.getByRole('button', { name: /Watch/i }));
    fireEvent.click(screen.getByRole('button', { name: /Map/i }));
    fireEvent.click(screen.getByTestId('result-card-pin-42'));
    fireEvent.click(screen.getByTestId('result-card-compare-42'));

    expect(onOpenDetail).toHaveBeenCalledTimes(1);
    expect(onOpenDetail.mock.calls[0]).toEqual([42]);
    expect(onOpenColonyPlanner).toHaveBeenCalledTimes(1);
    expect(onOpenColonyPlanner).toHaveBeenCalledWith(42);
    expect(onWatch).toHaveBeenCalledWith(42);
    expect(onShowOnMap).toHaveBeenCalledWith(42);
    expect(onPin).toHaveBeenCalledWith(42);
    expect(onCompare).toHaveBeenCalledWith(42);
    expect(screen.getByRole('button', { name: /Evaluate in Colony Planner/i })).toBeTruthy();
  });

  it('falls back to focused detail handoff when no Colony Planner workspace callback is provided', () => {
    const onOpenDetail = vi.fn();

    render(
      <ResultCard
        system={system}
        index={0}
        onOpenDetail={onOpenDetail}
      />,
    );

    fireEvent.click(screen.getByText('Handoff'));
    fireEvent.click(screen.getByRole('button', { name: /Evaluate in Colony Planner/i }));

    expect(onOpenDetail).toHaveBeenCalledTimes(1);
    expect(onOpenDetail).toHaveBeenCalledWith(42, { focus: 'colony-planner' });
  });

  it('copies the system name without toggling the expanded card', () => {
    const writeText = vi.fn();
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    });

    render(<ResultCard system={system} index={0} />);

    fireEvent.click(screen.getByText('Handoff'));
    fireEvent.click(screen.getByRole('button', { name: /Copy name/i }));

    expect(writeText).toHaveBeenCalledWith('Handoff');
    expect(screen.getByRole('button', { name: /Copy name/i })).toBeTruthy();
  });
});
