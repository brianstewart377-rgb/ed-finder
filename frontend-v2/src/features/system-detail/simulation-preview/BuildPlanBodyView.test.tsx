import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { FacilityTemplate, SimulateBuildPlacement, SystemBody } from '@/types/api';
import { BuildPlanBodyView, bodyDisplayName, bodyTags, groupPlacementsByBody } from './BuildPlanBodyView';

const templates: FacilityTemplate[] = [
  {
    id: 'dodec_starport',
    name: 'Dodec Starport',
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
    id: 'extraction_hub',
    name: 'Extraction Hub',
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
  {
    id: 1,
    name: 'A 1',
    body_type: 'Planet',
    subtype: 'High metal content world',
    is_landable: true,
    is_terraformable: true,
  },
  {
    id: 2,
    name: 'A 2',
    body_type: 'Planet',
    subtype: 'Water world',
    is_water_world: true,
  },
] as SystemBody[];

const placements: SimulateBuildPlacement[] = [
  { facility_template_id: 'dodec_starport', local_body_id: '1', is_primary_port: true, build_order: 1 },
  { facility_template_id: 'extraction_hub', local_body_id: '2', is_primary_port: false, build_order: 2 },
  { facility_template_id: 'missing_template', local_body_id: null, is_primary_port: false, build_order: 3 },
];

describe('BuildPlanBodyView', () => {
  it('groups placements by assigned body and leaves unassigned placements visible', () => {
    render(
      <BuildPlanBodyView
        placements={placements}
        templates={templates}
        bodies={bodies}
        onMove={vi.fn()}
        onRemove={vi.fn()}
      />,
    );

    const firstBody = screen.getByRole('region', { name: 'Body group A 1' });
    expect(within(firstBody).getByText('Dodec Starport')).toBeTruthy();
    expect(within(firstBody).getByText('Primary port')).toBeTruthy();
    expect(within(firstBody).getByText('orbital')).toBeTruthy();
    expect(within(firstBody).getByText('Tier 3')).toBeTruthy();
    expect(within(firstBody).getByText('Economy: Industrial')).toBeTruthy();
    expect(within(firstBody).getByText('CP: Y+0 G+0')).toBeTruthy();
    expect(within(firstBody).getByText('Needs: Y20 G40')).toBeTruthy();
    expect(within(firstBody).getByText('Landable')).toBeTruthy();
    expect(within(firstBody).getByText('Terraformable')).toBeTruthy();

    const secondBody = screen.getByRole('region', { name: 'Body group A 2' });
    expect(within(secondBody).getByText('Extraction Hub')).toBeTruthy();
    expect(within(secondBody).getByText('surface')).toBeTruthy();
    expect(within(secondBody).getByText('Estimated data')).toBeTruthy();
    expect(within(secondBody).getByText('Water world')).toBeTruthy();

    const unassigned = screen.getByRole('region', { name: 'Unassigned / needs body' });
    expect(within(unassigned).getAllByText('Unassigned / needs body').length).toBeGreaterThan(0);
    expect(within(unassigned).getByText('missing_template')).toBeTruthy();
    expect(within(unassigned).getByText('Missing template')).toBeTruthy();
    expect(within(unassigned).getByText('No body')).toBeTruthy();
    expect(within(unassigned).getByText(/Assign these placements to bodies before trusting Preview/)).toBeTruthy();
  });

  it('keeps actions wired to original placement indexes', () => {
    const onMove = vi.fn();
    const onRemove = vi.fn();
    render(
      <BuildPlanBodyView
        placements={placements}
        templates={templates}
        bodies={bodies}
        onMove={onMove}
        onRemove={onRemove}
      />,
    );

    const secondBody = screen.getByRole('region', { name: 'Body group A 2' });
    fireEvent.click(within(secondBody).getByRole('button', { name: 'Move up' }));
    fireEvent.click(within(secondBody).getByRole('button', { name: 'Remove' }));

    expect(onMove).toHaveBeenCalledWith(1, -1);
    expect(onRemove).toHaveBeenCalledWith(1);
  });

  it('handles unknown bodies and sparse body metadata without crashing', () => {
    const sparseBody = { id: 9 } as SystemBody;
    const groups = groupPlacementsByBody(
      [{ facility_template_id: 'dodec_starport', local_body_id: '404', build_order: 1 }],
      templates,
      [sparseBody],
    );

    expect(groups).toHaveLength(1);
    expect(groups[0].key).toBe('unassigned');
    expect(bodyDisplayName(sparseBody)).toBe('Body 9');
    expect(bodyTags({} as SystemBody)).toEqual(['Unknown body data']);
  });
});
