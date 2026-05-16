import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { FacilityTemplate, SimulateBuildPlacement, SystemBody } from '@/types/api';
import { BuildPlanEditor } from './BuildPlanEditor';

const templates: FacilityTemplate[] = [
  {
    id: 'known_port',
    name: 'Known Port',
    category: 'port',
    tier: 1,
    economy: 'Industrial',
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
  },
  {
    id: 'surface_lab',
    name: 'Surface Lab',
    category: 'support',
    tier: 2,
    economy: 'HighTech',
    is_port: false,
    is_support_facility: true,
    allowed_location: 'surface',
    pad_size: 'small',
    confidence: 'estimated',
    notes: null,
    yellow_cp_generated: 4,
    green_cp_generated: 1,
    yellow_cp_cost: 0,
    green_cp_cost: 0,
  },
];

const bodies = [
  { id: 'body1', name: 'Known Body', body_type: 'Planet', is_landable: true },
] as unknown as SystemBody[];

describe('BuildPlanEditor', () => {
  it('shows missing facility template ids in List view without crashing', () => {
    const onUpdate = vi.fn();
    const placements: SimulateBuildPlacement[] = [
      { facility_template_id: 'missing_template', local_body_id: 'body1', build_order: 1, is_primary_port: true },
    ];

    render(
      <BuildPlanEditor
        placements={placements}
        templates={templates}
        bodies={bodies}
        onUpdate={onUpdate}
        onRemove={vi.fn()}
        onMove={vi.fn()}
      />,
    );

    expect(screen.getByText('Needs review: facility template missing. Missing template: missing_template')).toBeTruthy();
    expect(screen.getByRole('option', { name: 'Missing template: missing_template' })).toBeTruthy();
    expect(screen.getByRole('option', { name: 'T1 - Known Port - Industrial' })).toBeTruthy();

    fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: 'known_port' } });

    expect(onUpdate).toHaveBeenCalledWith(0, {
      facility_template_id: 'known_port',
      is_primary_port: true,
    });
  });

  it('keeps the dropdown editor and lets the structure picker update through the existing callback', () => {
    const onUpdate = vi.fn();
    const placements: SimulateBuildPlacement[] = [
      { facility_template_id: 'known_port', local_body_id: 'body1', build_order: 1, is_primary_port: true },
    ];

    render(
      <BuildPlanEditor
        placements={placements}
        templates={templates}
        bodies={bodies}
        onUpdate={onUpdate}
        onRemove={vi.fn()}
        onMove={vi.fn()}
      />,
    );

    expect(screen.getByDisplayValue('T1 - Known Port - Industrial')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Browse structures/i }));

    expect(screen.getByRole('region', { name: 'Structure picker' })).toBeTruthy();
    expect(screen.getByText('Evaluating against: Known Body')).toBeTruthy();
    expect(screen.getByText('Surface Lab')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Select structure' }));

    expect(onUpdate).toHaveBeenCalledWith(0, {
      facility_template_id: 'surface_lab',
      is_primary_port: false,
    });
  });

  it('does not mutate placement state when filtering or searching the structure picker', () => {
    const onUpdate = vi.fn();
    const placements: SimulateBuildPlacement[] = [
      { facility_template_id: 'known_port', local_body_id: 'body1', build_order: 1, is_primary_port: true },
    ];

    render(
      <BuildPlanEditor
        placements={placements}
        templates={templates}
        bodies={bodies}
        onUpdate={onUpdate}
        onRemove={vi.fn()}
        onMove={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Browse structures/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Surface' }));
    fireEvent.change(screen.getByLabelText('Search structures'), { target: { value: 'Lab' } });

    expect(screen.getByText('Surface Lab')).toBeTruthy();
    expect(onUpdate).not.toHaveBeenCalled();
  });
});
