import { describe, expect, it } from 'vitest';
import type { FacilityTemplate, SystemBody } from '@/types/api';
import {
  filterStructureTemplates,
  formatCpGives,
  formatCpNeeds,
  formatTemplateLocation,
  getStructurePickerBodyContext,
  getStructurePickerWarnings,
  locationMatchesFilter,
  templateLocationKind,
} from './structurePickerUtils';

const orbitalTemplate = template({
  id: 'orbital_port',
  name: 'Orbital Port',
  allowed_location: 'orbital',
});
const surfaceTemplate = template({
  id: 'surface_hub',
  name: 'Surface Hub',
  category: 'support',
  economy: 'Agriculture',
  allowed_location: 'surface',
  confidence: 'estimated',
  yellow_cp_generated: 2,
  green_cp_generated: 1,
  yellow_cp_cost: 3,
  green_cp_cost: 4,
});
const bothTemplate = template({
  id: 'dual_use',
  name: 'Dual Use Port',
  allowed_location: 'surface_or_orbit',
});

describe('structurePickerUtils', () => {
  it('normalises location labels and CP values from template fields', () => {
    expect(templateLocationKind(orbitalTemplate)).toBe('orbital');
    expect(templateLocationKind(surfaceTemplate)).toBe('surface');
    expect(templateLocationKind(bothTemplate)).toBe('both');
    expect(formatTemplateLocation(bothTemplate)).toBe('Both');
    expect(formatCpGives(surfaceTemplate)).toBe('Y+2 G+1');
    expect(formatCpNeeds(surfaceTemplate)).toBe('Y3 G4');
  });

  it('filters by location without hiding dual-use structures from location-specific filters', () => {
    expect(locationMatchesFilter(orbitalTemplate, 'orbital')).toBe(true);
    expect(locationMatchesFilter(surfaceTemplate, 'orbital')).toBe(false);
    expect(locationMatchesFilter(bothTemplate, 'orbital')).toBe(true);
    expect(locationMatchesFilter(bothTemplate, 'surface')).toBe(true);
    expect(locationMatchesFilter(bothTemplate, 'both')).toBe(true);
  });

  it('searches across structure name, id, economy, role, and location fields', () => {
    expect(filterStructureTemplates([orbitalTemplate, surfaceTemplate, bothTemplate], 'all', 'agriculture'))
      .toEqual([surfaceTemplate]);
    expect(filterStructureTemplates([orbitalTemplate, surfaceTemplate, bothTemplate], 'surface', 'dual'))
      .toEqual([bothTemplate]);
  });

  it('builds conservative body context and review warnings', () => {
    const waterWorld = { id: 1, name: 'A 1', body_type: 'Planet', is_water_world: true } as SystemBody;
    const nonLandable = { id: 2, name: 'A 2', body_type: 'Planet', is_landable: false } as SystemBody;
    const sparseBody = { id: 3 } as SystemBody;

    expect(getStructurePickerBodyContext([waterWorld], null).label).toBe('No body selected yet');
    expect(getStructurePickerBodyContext([waterWorld], 'missing').label).toBe('Unknown body');
    expect(getStructurePickerBodyContext([waterWorld], '1').label).toBe('A 1');

    expect(getStructurePickerWarnings(surfaceTemplate, getStructurePickerBodyContext([waterWorld], '1'))).toContain(
      'Check location: surface facility on water world may be invalid',
    );
    expect(getStructurePickerWarnings(surfaceTemplate, getStructurePickerBodyContext([nonLandable], '2'))).toContain(
      'Check location: surface facility needs suitable landable body',
    );
    expect(getStructurePickerWarnings(orbitalTemplate, getStructurePickerBodyContext([sparseBody], '3'))).toEqual([
      'Body metadata incomplete',
      'Orbital suitability unclear',
    ]);
    expect(getStructurePickerWarnings(surfaceTemplate, getStructurePickerBodyContext([], null))).toContain(
      'Needs body: body-specific checks need a body',
    );
    expect(getStructurePickerWarnings(surfaceTemplate, getStructurePickerBodyContext([], '404'))).toContain(
      'Unknown body: body-specific validity cannot be trusted',
    );
    expect(getStructurePickerWarnings(surfaceTemplate, getStructurePickerBodyContext([waterWorld], '1'))).toContain(
      'Template uses estimated data',
    );
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
