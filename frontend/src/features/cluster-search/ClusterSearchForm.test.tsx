import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ClusterSearchFilters } from './useClusterSearch';
import { ClusterSearchForm } from './ClusterSearchForm';

vi.mock('@/features/search/RefSystemPicker', () => ({
  RefSystemPicker: ({ value }: { value: string }) => (
    <input aria-label="Reference system" value={value} readOnly />
  ),
}));

const FILTERS: ClusterSearchFilters = {
  slots: [{
    archetype_key: 'refinery_industrial',
    label: 'Refinery + Industrial',
    economies: [],
  }],
  refName: 'Sol',
  refCoords: { x: 0, y: 0, z: 0 },
  galaxyRegionId: null,
  limit: 50,
};

function renderForm(onChange = vi.fn()) {
  render(
    <ClusterSearchForm
      filters={FILTERS}
      onChange={onChange}
      onAddSlot={() => undefined}
      onRemoveSlot={() => undefined}
      onUpdateSlot={() => undefined}
      onSubmit={() => undefined}
      onReset={() => undefined}
    />,
  );
  return onChange;
}

describe('ClusterSearchForm region scope', () => {
  it('offers all 42 named galactic regions and an all-regions option', () => {
    renderForm();

    const regionSelect = screen.getByLabelText('Galactic region') as HTMLSelectElement;
    expect(regionSelect.options).toHaveLength(43);
    expect(regionSelect.options[0]?.text).toBe('All 42 named regions');
    expect(regionSelect.options[18]?.text).toBe('Inner Orion Spur');
    expect(regionSelect.options[42]?.text).toBe('The Void');
  });

  it('reports the chosen region ID and explains the separate result limit', () => {
    const onChange = renderForm();

    fireEvent.change(screen.getByLabelText('Galactic region'), {
      target: { value: '31' },
    });

    expect(onChange).toHaveBeenCalledWith({ galaxyRegionId: 31 });
    expect(screen.getByText('Maximum cluster matches')).toBeTruthy();
    expect(screen.getByText(/not the number of galactic regions/i)).toBeTruthy();
  });

  it('explains how the reference system is used without exposing raw coordinates', () => {
    renderForm();

    expect(screen.getByText('Results ranked by distance from Sol.')).toBeTruthy();
    expect(screen.queryByText(/0\.00, 0\.00, 0\.00/)).toBeNull();
  });

  it('describes additional slots as economy requirements', () => {
    renderForm();

    expect(screen.getByText('Economies Needed')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Add Economy Requirement' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Add World' })).toBeNull();
  });
});
