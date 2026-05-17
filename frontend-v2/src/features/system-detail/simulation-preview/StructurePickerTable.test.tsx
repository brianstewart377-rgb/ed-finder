import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { FacilityTemplate, SystemBody } from '@/types/api';
import { StructurePickerTable } from './StructurePickerTable';

const templates: FacilityTemplate[] = [
  {
    id: 'orbital_port',
    name: 'Orbital Port',
    category: 'port',
    tier: 3,
    economy: 'Industrial',
    is_port: true,
    is_support_facility: false,
    allowed_location: 'orbital',
    pad_size: 'large',
    confidence: 'observed',
    notes: null,
    yellow_cp_generated: 0,
    green_cp_generated: 0,
    yellow_cp_cost: 20,
    green_cp_cost: 40,
  },
  {
    id: 'surface_hub',
    name: 'Surface Hub',
    category: 'support',
    tier: 2,
    economy: 'Extraction',
    is_port: false,
    is_support_facility: true,
    allowed_location: 'surface',
    pad_size: null,
    confidence: 'estimated',
    notes: null,
    yellow_cp_generated: 8,
    green_cp_generated: 2,
    yellow_cp_cost: 0,
    green_cp_cost: 0,
  },
];

const bodies = [
  { id: 1, name: 'A 1', is_landable: true },
  { id: 2, name: 'A 2', is_water_world: true, is_landable: true },
] as SystemBody[];

function renderPicker(overrides: Partial<Parameters<typeof StructurePickerTable>[0]> = {}) {
  const onSelectTemplate = vi.fn();
  render(
    <StructurePickerTable
      templates={templates}
      bodies={bodies}
      selectedBodyId="1"
      selectedTemplateId="orbital_port"
      onSelectTemplate={onSelectTemplate}
      {...overrides}
    />,
  );
  return { onSelectTemplate };
}

describe('StructurePickerTable', () => {
  it('renders template rows with planning fields and selection control', () => {
    renderPicker();

    const panel = screen.getByTestId('structure-picker');
    expect(within(panel).getByText('Compare structures')).toBeTruthy();
    expect(within(panel).getByText('Evaluating against: A 1')).toBeTruthy();
    expect(screen.getByTestId('structure-picker-row-orbital_port')).toBeTruthy();
    expect(screen.getByTestId('structure-picker-row-surface_hub')).toBeTruthy();
    expect(screen.getAllByText('Orbital Port').length).toBeGreaterThan(0);
    expect(screen.getAllByText('surface').length).toBeGreaterThan(0);
    expect(screen.getAllByText('CP gives').length).toBeGreaterThan(0);
    expect(screen.getAllByText('CP needs').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: 'Select structure Surface Hub' })).toBeTruthy();
  });

  it('filters by search and location', () => {
    renderPicker();

    fireEvent.change(screen.getByRole('searchbox', { name: 'Search structures' }), { target: { value: 'Surface' } });
    expect(screen.queryByTestId('structure-picker-row-orbital_port')).toBeNull();
    expect(screen.getByTestId('structure-picker-row-surface_hub')).toBeTruthy();

    fireEvent.change(screen.getByRole('searchbox', { name: 'Search structures' }), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Orbital' }));
    expect(screen.getByTestId('structure-picker-row-orbital_port')).toBeTruthy();
    expect(screen.queryByTestId('structure-picker-row-surface_hub')).toBeNull();
  });

  it('renders conservative warnings for body suitability and confidence', () => {
    renderPicker({ selectedBodyId: '2' });

    expect(screen.getByText('May be invalid: surface facility on water world')).toBeTruthy();
    expect(screen.getByText('Needs review: template uses estimated data')).toBeTruthy();
    expect(screen.getByText('Check location')).toBeTruthy();
  });

  it('handles no-body and unknown-body context labels', () => {
    renderPicker({ selectedBodyId: null });
    expect(screen.getByText('No body selected yet')).toBeTruthy();
    expect(screen.getAllByText('Needs body').length).toBeGreaterThan(0);

    renderPicker({ selectedBodyId: '404' });
    expect(screen.getByText('Unknown body: 404')).toBeTruthy();
    expect(screen.getAllByText('Unknown body').length).toBeGreaterThan(0);
  });

  it('invokes onSelectTemplate only when user explicitly selects a row', () => {
    const { onSelectTemplate } = renderPicker();
    expect(onSelectTemplate).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Select structure Surface Hub' }));
    expect(onSelectTemplate).toHaveBeenCalledTimes(1);
    expect(onSelectTemplate).toHaveBeenCalledWith('surface_hub');
  });

  it('shows empty catalogue and empty-filter states', () => {
    const emptyRender = render(
      <StructurePickerTable
        templates={[]}
        bodies={bodies}
        selectedBodyId="1"
        selectedTemplateId="orbital_port"
        onSelectTemplate={vi.fn()}
      />,
    );
    expect(screen.getByText('No structures available yet.')).toBeTruthy();
    emptyRender.unmount();

    renderPicker();
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search structures' }), { target: { value: 'zzzz' } });
    expect(screen.getByText('No structures match the current filters.')).toBeTruthy();
  });
});
