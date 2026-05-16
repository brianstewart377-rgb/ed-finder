import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { FacilityTemplate, SystemBody } from '@/types/api';
import { StructurePickerTable } from './StructurePickerTable';

const templates: FacilityTemplate[] = [
  template({
    id: 'orbital_port',
    name: 'Orbital Port',
    category: 'port',
    economy: 'Industrial',
    allowed_location: 'orbital',
    pad_size: 'large',
    confidence: 'observed',
    yellow_cp_generated: 1,
    green_cp_generated: 2,
    yellow_cp_cost: 3,
    green_cp_cost: 4,
  }),
  template({
    id: 'surface_farm',
    name: 'Surface Farm',
    category: 'support',
    economy: 'Agriculture',
    is_port: false,
    is_support_facility: true,
    allowed_location: 'surface',
    pad_size: 'small',
    confidence: 'estimated',
    yellow_cp_generated: 5,
    green_cp_generated: 0,
    yellow_cp_cost: 0,
    green_cp_cost: 1,
  }),
  template({
    id: 'dual_lab',
    name: 'Dual Use Lab',
    category: 'research',
    economy: 'HighTech',
    allowed_location: 'surface_or_orbit',
    confidence: 'inferred',
  }),
];

const bodies = [
  { id: 1, name: 'Candidate Body', body_type: 'Planet', is_landable: true },
  { id: 2, name: 'Water Body', body_type: 'Planet', is_water_world: true },
  { id: 3, name: 'Rock Body', body_type: 'Planet', is_landable: false },
] as SystemBody[];

function renderPicker(overrides: Partial<Parameters<typeof StructurePickerTable>[0]> = {}) {
  const onSelectTemplate = vi.fn();
  const view = render(
    <StructurePickerTable
      templates={templates}
      bodies={bodies}
      selectedBodyId="1"
      selectedTemplateId="orbital_port"
      onSelectTemplate={onSelectTemplate}
      {...overrides}
    />,
  );
  return { onSelectTemplate, ...view };
}

describe('StructurePickerTable', () => {
  it('renders template rows with known picker fields and conservative validity copy', () => {
    renderPicker();

    expect(screen.getByRole('region', { name: 'Structure picker' })).toBeTruthy();
    expect(screen.getByText('Uses current facility catalogue. Validity hints are planning checks; run Preview for full prediction.')).toBeTruthy();
    expect(screen.getByText('Evaluating against: Candidate Body')).toBeTruthy();

    const row = screen.getByText('Orbital Port').closest('tr');
    expect(row).toBeTruthy();
    expect(within(row as HTMLTableRowElement).getByText('Orbital')).toBeTruthy();
    expect(within(row as HTMLTableRowElement).getByText('Tier 1')).toBeTruthy();
    expect(within(row as HTMLTableRowElement).getByText('large')).toBeTruthy();
    expect(within(row as HTMLTableRowElement).getByText('Industrial')).toBeTruthy();
    expect(within(row as HTMLTableRowElement).getByText('port')).toBeTruthy();
    expect(within(row as HTMLTableRowElement).getByText('Port')).toBeTruthy();
    expect(within(row as HTMLTableRowElement).getByText('Y+1 G+2')).toBeTruthy();
    expect(within(row as HTMLTableRowElement).getByText('Y3 G4')).toBeTruthy();
    expect(within(row as HTMLTableRowElement).getByText('observed')).toBeTruthy();
  });

  it('filters by location and searches by structure text without selecting anything', () => {
    const { onSelectTemplate } = renderPicker();

    fireEvent.click(screen.getByRole('button', { name: 'Surface' }));
    expect(screen.queryByText('Orbital Port')).toBeNull();
    expect(screen.getByText('Surface Farm')).toBeTruthy();
    expect(screen.getByText('Dual Use Lab')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Both' }));
    expect(screen.queryByText('Surface Farm')).toBeNull();
    expect(screen.getByText('Dual Use Lab')).toBeTruthy();

    fireEvent.change(screen.getByLabelText('Search structures'), { target: { value: 'nope' } });
    expect(screen.getByText('No structures match the current filters.')).toBeTruthy();
    expect(onSelectTemplate).not.toHaveBeenCalled();
  });

  it('searches by name and explicitly selects a structure row', () => {
    const { onSelectTemplate } = renderPicker();

    fireEvent.change(screen.getByLabelText('Search structures'), { target: { value: 'Farm' } });
    expect(screen.getByText('Surface Farm')).toBeTruthy();
    expect(screen.queryByText('Orbital Port')).toBeNull();
    expect(onSelectTemplate).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Select structure' }));
    expect(onSelectTemplate).toHaveBeenCalledWith('surface_farm');
  });

  it('shows no-body and unknown-body context without crashing', () => {
    const { unmount } = render(
      <StructurePickerTable
        templates={templates}
        bodies={bodies}
        selectedBodyId={null}
        selectedTemplateId={null}
        onSelectTemplate={vi.fn()}
      />,
    );
    expect(screen.getByText('No body selected yet')).toBeTruthy();
    expect(screen.getAllByText('Needs body: body-specific checks need a body').length).toBeGreaterThan(0);
    unmount();

    renderPicker({ selectedBodyId: 'missing' });
    expect(screen.getByText('Unknown body')).toBeTruthy();
    expect(screen.getAllByText('Unknown body: body-specific validity cannot be trusted').length).toBeGreaterThan(0);
  });

  it('shows conservative water-world and non-landable body warnings when data supports them', () => {
    const { unmount } = renderPicker({ selectedBodyId: '2' });
    expect(screen.getAllByText('Check location: surface facility on water world may be invalid').length).toBeGreaterThan(0);
    unmount();

    renderPicker({ selectedBodyId: '3' });
    expect(screen.getAllByText('Check location: surface facility needs suitable landable body').length).toBeGreaterThan(0);
  });

  it('handles empty catalogues and missing template fields safely', () => {
    const sparseTemplate = template({
      id: 'sparse',
      name: '',
      category: '',
      economy: null,
      allowed_location: 'unknown',
      pad_size: null,
      confidence: null,
    });
    const { unmount } = renderPicker({ templates: [] });
    expect(screen.getByText('No structures available yet.')).toBeTruthy();
    unmount();

    renderPicker({ templates: [sparseTemplate], selectedTemplateId: null });
    expect(screen.getAllByText('sparse').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Unknown').length).toBeGreaterThan(0);
    expect(screen.getByText('missing')).toBeTruthy();
  });
});

function template(overrides: Partial<FacilityTemplate>): FacilityTemplate {
  return {
    id: 'template',
    name: 'Template',
    category: 'port',
    tier: 1,
    economy: null,
    is_port: true,
    is_support_facility: false,
    allowed_location: 'surface_or_orbit',
    pad_size: 'large',
    confidence: 'observed',
    notes: null,
    yellow_cp_generated: 0,
    green_cp_generated: 0,
    yellow_cp_cost: 0,
    green_cp_cost: 0,
    ...overrides,
  };
}
