import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { FacilityTemplate, SimulateBuildPlacement, SystemBody } from '@/types/api';
import { StructureReplacementComparison } from './StructureReplacementComparison';

const currentTemplate: FacilityTemplate = {
  id: 'surface_industrial',
  name: 'Surface Industrial',
  category: 'support',
  tier: 2,
  economy: 'Industrial',
  is_port: false,
  is_support_facility: true,
  allowed_location: 'surface',
  pad_size: 'medium',
  confidence: 'estimated',
  notes: null,
  yellow_cp_generated: 3,
  green_cp_generated: 1,
  yellow_cp_cost: 0,
  green_cp_cost: 0,
};

const proposedTemplate: FacilityTemplate = {
  ...currentTemplate,
  id: 'orbital_industrial',
  name: 'Orbital Industrial',
  allowed_location: 'orbital',
  yellow_cp_generated: 5,
  green_cp_generated: 2,
};

const placement: SimulateBuildPlacement = {
  facility_template_id: currentTemplate.id,
  local_body_id: '1',
  is_primary_port: true,
  build_order: 1,
};

const bodies = [
  { id: 1, name: 'Water Body', is_water_world: true, is_landable: true },
] as SystemBody[];

describe('StructureReplacementComparison', () => {
  it('marks changed fields while keeping unchanged fields subdued', () => {
    render(
      <StructureReplacementComparison
        placement={placement}
        currentTemplate={currentTemplate}
        proposedTemplate={proposedTemplate}
        bodies={bodies}
        onApply={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    expect(screen.getByTestId('structure-replacement-deltas')).toBeTruthy();
    expect(screen.getByTestId('structure-replacement-delta-tier').getAttribute('data-changed')).toBe('false');
    expect(screen.getByTestId('structure-replacement-delta-allowed-location').getAttribute('data-changed')).toBe('true');
    expect(screen.getByTestId('structure-replacement-delta-cp-gives').getAttribute('data-changed')).toBe('true');
    expect(screen.getByText('Surface Industrial')).toBeTruthy();
    expect(screen.getByText('Orbital Industrial')).toBeTruthy();
  });

  it('shows warning deltas for added, removed, and unchanged warnings', () => {
    render(
      <StructureReplacementComparison
        placement={placement}
        currentTemplate={currentTemplate}
        proposedTemplate={proposedTemplate}
        bodies={bodies}
        onApply={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    const warningDeltas = screen.getByTestId('structure-replacement-warning-deltas');
    expect(within(warningDeltas).getByText('Warnings added')).toBeTruthy();
    expect(within(warningDeltas).getByText('Data incomplete: orbital suitability unclear')).toBeTruthy();
    expect(within(warningDeltas).getByText('Warnings removed')).toBeTruthy();
    expect(within(warningDeltas).getByText('May be invalid: surface facility on water world')).toBeTruthy();
    expect(within(warningDeltas).getByText('Warnings unchanged')).toBeTruthy();
    expect(within(warningDeltas).getByText('Needs review: template uses estimated data')).toBeTruthy();
  });
});
