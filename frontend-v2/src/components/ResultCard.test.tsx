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
    const scoreBar = screen.getByLabelText('Rating score: 82/100');
    expect(scoreBar).toBeTruthy();
    expect(scoreBar.getAttribute('title')).toBe('Rating score: 82/100');
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

describe('ResultCard distance display (Stage 17N.2)', () => {
  it('shows valid distance with LY suffix', () => {
    render(<ResultCard system={system} index={0} />);
    expect(screen.getByText('12.34')).toBeTruthy();
    expect(screen.getByText('LY')).toBeTruthy();
  });

  it('shows dash for null distance instead of 0.00', () => {
    const nullDist = { ...system, distance: null } as unknown as SystemResult;
    render(<ResultCard system={nullDist} index={0} />);
    expect(screen.getByText('— LY')).toBeTruthy();
    expect(screen.queryByText('0.00')).toBeNull();
  });

  it('shows dash for undefined distance', () => {
    const noDist = { ...system, distance: undefined } as unknown as SystemResult;
    render(<ResultCard system={noDist} index={0} />);
    expect(screen.getByText('— LY')).toBeTruthy();
  });

  it('shows dash for zero distance (galaxy-wide fake zero)', () => {
    const zeroDist = { ...system, distance: 0 } as unknown as SystemResult;
    render(<ResultCard system={zeroDist} index={0} />);
    expect(screen.getByText('— LY')).toBeTruthy();
    expect(screen.queryByText('0.00')).toBeNull();
  });

  it('does not label colonised unknown-population systems as uninhabited', () => {
    const unknownPop = {
      ...system,
      population: null,
      is_colonised: true,
    } as unknown as SystemResult;

    render(<ResultCard system={unknownPop} index={0} />);

    expect(screen.getByText('COL')).toBeTruthy();
    expect(screen.getByText('Unknown')).toBeTruthy();
    expect(screen.queryByText('Uninhabited')).toBeNull();
  });
});
