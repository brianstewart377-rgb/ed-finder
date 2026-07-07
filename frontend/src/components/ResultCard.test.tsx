import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { SystemResult } from '@/types/api';
import { economyColor } from '@/features/colony-planner/economyVisuals';
import { ResultCard } from './ResultCard';

function hexToRgbString(hex: string): string {
  const value = hex.replace('#', '');
  const normalized = value.length === 3
    ? value.split('').map((char) => `${char}${char}`).join('')
    : value;
  const intValue = Number.parseInt(normalized, 16);
  const r = (intValue >> 16) & 255;
  const g = (intValue >> 8) & 255;
  const b = intValue & 255;
  return `rgb(${r}, ${g}, ${b})`;
}

const system = {
  id64: 42,
  name: 'Handoff',
  coords: { x: 1, y: 2, z: 3 },
  distance: 12.34,
  population: 0,
  is_colonised: false,
  primaryEconomy: 'Agriculture',
  primary_archetype: 'refinery_industrial',
  archetype_score: 91,
  archetype_tier: 'S',
  buildability_score: 77,
  purity_score: 69,
  est_total_slots: 12,
} as unknown as SystemResult;

describe('ResultCard actions', () => {
  it('offers Save for later and Inspect system without exposing a direct planner action', () => {
    const onOpenDetail = vi.fn();
    const onPin = vi.fn();
    const onCompare = vi.fn();
    const onToggleSavedForLater = vi.fn();
    const onShowOnMap = vi.fn();
    render(
      <ResultCard
        system={system}
        index={0}
        onPin={onPin}
        onCompare={onCompare}
        onToggleSavedForLater={onToggleSavedForLater}
        onShowOnMap={onShowOnMap}
        onOpenDetail={onOpenDetail}
      />,
    );

    fireEvent.click(screen.getByText('Handoff'));
    fireEvent.click(screen.getByRole('button', { name: /Inspect system/i }));
    fireEvent.click(screen.getByRole('button', { name: /Save for later/i }));
    fireEvent.click(screen.getByRole('button', { name: /Map/i }));
    fireEvent.click(screen.getByTestId('result-card-pin-42'));
    fireEvent.click(screen.getByTestId('result-card-compare-42'));

    expect(onOpenDetail).toHaveBeenCalledTimes(1);
    expect(onOpenDetail.mock.calls[0]).toEqual([42]);
    expect(onToggleSavedForLater).toHaveBeenCalledTimes(1);
    expect(onToggleSavedForLater).toHaveBeenCalledWith(42);
    expect(onShowOnMap).toHaveBeenCalledWith(42);
    expect(onPin).toHaveBeenCalledWith(42);
    expect(onCompare).toHaveBeenCalledWith(42);
    expect(screen.queryByRole('button', { name: /Evaluate in Colony Planner/i })).toBeNull();
    expect(screen.getByTestId('result-card-suggested-archetype').textContent).toContain('Refinery');
    expect(screen.getByTestId('result-card-suggested-archetype').textContent).toContain('Megacomplex');
    expect(screen.queryByLabelText('Development score: 91/100')).toBeNull();
    expect(screen.getByTestId('result-card-archetype-score').textContent).toContain('Score 91');
  });

  it('surfaces the archetype assessment in the expanded card', () => {
    render(<ResultCard system={system} index={0} />);

    fireEvent.click(screen.getByText('Handoff'));

    expect(screen.getByText('Primary archetype')).toBeTruthy();
    expect(screen.getByText('Development score')).toBeTruthy();
    expect(screen.getByText('Buildability')).toBeTruthy();
    expect(screen.getByText('Purity')).toBeTruthy();
    expect(screen.getByText('Est. slots')).toBeTruthy();
    expect(screen.getByTestId('result-card-suggested-archetype').getAttribute('aria-label')).toBe('Refinery / Industrial Megacomplex');
    expect(screen.getAllByText('Refinery / Industrial Megacomplex').length).toBeGreaterThanOrEqual(1);
  });

  it('renders split economy colours for paired archetype chips', () => {
    const pairedEconomies = {
      ...system,
      primaryEconomy: 'Refinery',
      secondaryEconomy: 'Industrial',
    } as unknown as SystemResult;

    render(<ResultCard system={pairedEconomies} index={0} />);

    const primaryLabel = screen.getByTestId('result-card-suggested-archetype-primary');
    const secondaryLabel = screen.getByTestId('result-card-suggested-archetype-secondary');
    expect(getComputedStyle(primaryLabel).color).toBe(hexToRgbString(economyColor('Refinery')));
    expect(getComputedStyle(secondaryLabel).color).toBe(hexToRgbString(economyColor('Industrial')));
    expect(primaryLabel.textContent).toBe('Refinery');
    expect(secondaryLabel.textContent).toBe('Industrial');
  });

  it('derives split economy colours from the visible archetype label when raw fields do not align', () => {
    render(<ResultCard system={system} index={0} />);

    const primaryLabel = screen.getByTestId('result-card-suggested-archetype-primary');
    const secondaryLabel = screen.getByTestId('result-card-suggested-archetype-secondary');
    expect(getComputedStyle(primaryLabel).color).toBe(hexToRgbString(economyColor('Refinery')));
    expect(getComputedStyle(secondaryLabel).color).toBe(hexToRgbString(economyColor('Industrial')));
    expect(primaryLabel.textContent).toBe('Refinery');
    expect(secondaryLabel.textContent).toBe('Industrial');
  });

  it('shows reversible saved state copy for save-for-later systems', () => {
    render(
      <ResultCard
        system={system}
        index={0}
        isSavedForLater
      />,
    );

    fireEvent.click(screen.getByText('Handoff'));
    expect(screen.getByText('Saved')).toBeTruthy();
    expect(screen.getByRole('button', { name: /Remove from saved/i })).toBeTruthy();
  });

  it('shows save and remove progress while preventing duplicate clicks', () => {
    const onToggleSavedForLater = vi.fn();
    const { rerender } = render(
      <ResultCard
        system={system}
        index={0}
        savedActionState="saving"
        onToggleSavedForLater={onToggleSavedForLater}
      />,
    );

    fireEvent.click(screen.getByText('Handoff'));
    const savingButton = screen.getByRole('button', { name: /Save for later/i }) as HTMLButtonElement;
    expect(screen.getByText('Saving…')).toBeTruthy();
    expect(savingButton.disabled).toBe(true);
    fireEvent.click(savingButton);
    expect(onToggleSavedForLater).not.toHaveBeenCalled();

    rerender(
      <ResultCard
        system={system}
        index={0}
        isSavedForLater
        savedActionState="removing"
        onToggleSavedForLater={onToggleSavedForLater}
      />,
    );

    expect(screen.getByText('Removing…')).toBeTruthy();
    expect((screen.getByRole('button', { name: /Remove from saved/i }) as HTMLButtonElement).disabled).toBe(true);
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
