import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { FacilityTemplate, SimulateBuildPlacement, SimulateBuildResponse, SystemBody } from '@/types/api';
import {
  bodyDisplayName,
  bodyTags,
  getPlanSummary,
  groupPlacementsByBody,
} from './buildPlanLayoutUtils';
import { BuildPlanBodyView } from './BuildPlanBodyView';

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
  {
    id: 'surface_hab',
    name: 'Surface Hab',
    category: 'support',
    tier: 1,
    economy: 'Colony',
    is_port: false,
    is_support_facility: true,
    allowed_location: 'surface',
    pad_size: 'small',
    confidence: 'observed',
    notes: null,
    yellow_cp_generated: 1,
    green_cp_generated: 0,
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
  {
    id: 3,
    name: 'A 3',
    body_type: 'Planet',
    subtype: 'Rocky body',
    is_landable: false,
  },
] as SystemBody[];

const placements: SimulateBuildPlacement[] = [
  { facility_template_id: 'dodec_starport', local_body_id: '1', is_primary_port: true, build_order: 1 },
  { facility_template_id: 'extraction_hub', local_body_id: '2', is_primary_port: false, build_order: 2 },
  { facility_template_id: 'missing_template', local_body_id: null, is_primary_port: false, build_order: 3 },
];

function renderLayout(overrides: Partial<Parameters<typeof BuildPlanBodyView>[0]> = {}) {
  return render(
    <BuildPlanBodyView
      systemName="Test System"
      targetArchetype="refinery_industrial"
      placements={placements}
      templates={templates}
      bodies={bodies}
      previewResult={null}
      isPreviewResultStale={false}
      runningPreview={false}
      {...overrides}
    />,
  );
}

describe('BuildPlanBodyView', () => {
  it('groups placements by assigned body and leaves unassigned placements visible', () => {
    renderLayout();

    const summary = screen.getByRole('region', { name: 'Layout plan summary' });
    expect(within(summary).getByText('Test System')).toBeTruthy();
    expect(within(summary).getByText('3 total')).toBeTruthy();
    expect(within(summary).getByText('2 assigned')).toBeTruthy();
    expect(within(summary).getByText('1 unassigned')).toBeTruthy();
    expect(within(summary).getByText('2 bodies used')).toBeTruthy();
    expect(within(summary).getByText('Primary port set')).toBeTruthy();
    expect(within(summary).getByText('Preview: not run')).toBeTruthy();

    const firstBody = screen.getByTestId('layout-body-group-1');
    expect(within(firstBody).getByText('Dodec Starport')).toBeTruthy();
    expect(screen.getByTestId('layout-body-select-1')).toBeTruthy();
    expect(within(firstBody).getByText('Primary port')).toBeTruthy();
    expect(within(firstBody).getByText('Primary port body')).toBeTruthy();
    expect(within(firstBody).getByText('orbital')).toBeTruthy();
    expect(within(firstBody).getByText('Tier 3')).toBeTruthy();
    expect(within(firstBody).getByText('Economy: Industrial')).toBeTruthy();
    expect(within(firstBody).getAllByText('CP: Y+0 G+0').length).toBeGreaterThan(0);
    expect(within(firstBody).getAllByText('Needs: Y20 G40').length).toBeGreaterThan(0);
    expect(within(firstBody).getByText('Landable')).toBeTruthy();
    expect(within(firstBody).getByText('Terraformable')).toBeTruthy();

    const secondBody = screen.getByTestId('layout-body-group-2');
    expect(within(secondBody).getByText('Extraction Hub')).toBeTruthy();
    expect(screen.getByTestId('layout-body-select-2')).toBeTruthy();
    expect(within(secondBody).getByText('surface')).toBeTruthy();
    expect(within(secondBody).getByText('Confidence: estimated')).toBeTruthy();
    expect(within(secondBody).getByText('Needs review: template uses estimated data')).toBeTruthy();
    expect(within(secondBody).getAllByText('May be invalid: surface facility on water world').length).toBeGreaterThan(0);
    expect(within(secondBody).getAllByText('Surface structure may be invalid on this body.').length).toBeGreaterThan(0);
    expect(within(secondBody).getAllByText('Estimated template data: review before relying on the plan.').length).toBeGreaterThan(0);

    const unassigned = screen.getByTestId('layout-body-group-unassigned');
    expect(within(unassigned).getAllByText('Unassigned / needs body').length).toBeGreaterThan(0);
    expect(screen.getByTestId('layout-body-select-unassigned')).toBeTruthy();
    expect(within(unassigned).getByText('missing_template')).toBeTruthy();
    expect(within(unassigned).getByText('Needs review: facility template missing')).toBeTruthy();
    expect(within(unassigned).getByText('Needs review: placement has no body')).toBeTruthy();
  });

  it('reports primary port states for none, one, and multiple primary ports', () => {
    expect(planSummary([{ facility_template_id: 'surface_hab', local_body_id: '1', build_order: 1 }]).primaryPortStatus).toBe('none');
    expect(planSummary(placements).primaryPortStatus).toBe('one');
    expect(planSummary([
      ...placements,
      { facility_template_id: 'surface_hab', local_body_id: '3', is_primary_port: true, build_order: 4 },
    ]).primaryPortStatus).toBe('multiple');
  });

  it('shows unknown body, non-landable surface, sparse metadata, and stale preview warnings', () => {
    renderLayout({
      placements: [
        { facility_template_id: 'surface_hab', local_body_id: '404', build_order: 1 },
        { facility_template_id: 'surface_hab', local_body_id: '3', build_order: 2 },
        { facility_template_id: 'dodec_starport', local_body_id: '9', is_primary_port: true, build_order: 3 },
      ],
      bodies: [...bodies, { id: 9 } as SystemBody],
      previewResult: {} as SimulateBuildResponse,
      isPreviewResultStale: true,
    });

    expect(screen.getByText('Preview is stale')).toBeTruthy();
    expect(screen.getByText((content) => content.includes('Unknown body 404'))).toBeTruthy();
    expect(screen.getByText('Check placement: body ID does not match known body')).toBeTruthy();
    expect(screen.getAllByText('May be invalid: surface facility on non-landable body').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: 'Select body Body 9' })).toBeTruthy();
    expect(screen.getAllByText('Data incomplete: body metadata is sparse').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Data incomplete: orbital suitability unclear').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Sparse body metadata: confirm in game before relying on this placement.').length).toBeGreaterThan(0);
  });

  it('handles helper fallbacks and sparse body metadata without crashing', () => {
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

  it('shows a default summary detail panel with counts, preview status, and next action', () => {
    renderLayout();

    const panel = screen.getByTestId('layout-detail-panel');
    expect(within(panel).getByText('Select a body or placement')).toBeTruthy();
    expect(within(panel).getByText(/Pick a body group or placement card/)).toBeTruthy();
    expect(within(panel).getByText('Total placements')).toBeTruthy();
    expect(within(panel).getByText('3')).toBeTruthy();
    expect(within(panel).getByText('Primary port')).toBeTruthy();
    expect(within(panel).getByText('Primary port set')).toBeTruthy();
    expect(within(panel).getByText('Preview')).toBeTruthy();
    expect(within(panel).getByText('not run')).toBeTruthy();
    expect(within(panel).getByText('Assign bodies in List view before relying on Preview.')).toBeTruthy();
  });

  it('selects a body group and shows body details, tags, warnings, and placement list', () => {
    renderLayout();

    const body = screen.getByRole('button', { name: 'Select body A 2' });
    fireEvent.click(body);

    expect(body.getAttribute('aria-pressed')).toBe('true');
    const panel = screen.getByTestId('layout-detail-panel');
    expect(within(panel).getAllByText('A 2').length).toBeGreaterThan(0);
    expect(within(panel).getByText('Water world')).toBeTruthy();
    expect(within(panel).getByText('Surface structure may be invalid on this body.')).toBeTruthy();
    expect(within(panel).getByText('Placements')).toBeTruthy();
    expect(within(panel).getByText('1')).toBeTruthy();
    expect(within(panel).getByText('Primary port here')).toBeTruthy();
    expect(within(panel).getByText('No')).toBeTruthy();
    expect(within(panel).getByText((content) => content.includes('#2') && content.includes('Extraction Hub'))).toBeTruthy();
    expect(within(panel).getByText('May be invalid: surface facility on water world')).toBeTruthy();
  });

  it('selects a placement and shows read-only placement details', () => {
    renderLayout();

    const placement = screen.getByRole('button', { name: 'Placement 1: Dodec Starport' });
    fireEvent.click(placement);

    expect(placement.getAttribute('aria-pressed')).toBe('true');
    const panel = screen.getByTestId('layout-detail-panel');
    expect(within(panel).getAllByText('Dodec Starport').length).toBeGreaterThan(0);
    expect(within(panel).getByText('Build order')).toBeTruthy();
    expect(within(panel).getByText('A 1')).toBeTruthy();
    expect(within(panel).getByText('planned')).toBeTruthy();
    expect(within(panel).getByText('Yes')).toBeTruthy();
    expect(within(panel).getByText('orbital')).toBeTruthy();
    expect(within(panel).getByText('Industrial')).toBeTruthy();
    expect(within(panel).getByText('port')).toBeTruthy();
    expect(within(panel).getByText('Y+0/20 G+0/40')).toBeTruthy();
    expect(within(panel).getByText('observed')).toBeTruthy();
    expect(within(panel).getByText('Use List view to edit this placement.')).toBeTruthy();
    expect(within(panel).getByText('Architect survey: not observed')).toBeTruthy();
    expect(within(panel).getByText('Primary-port flag: unknown')).toBeTruthy();
    expect(within(panel).getByText('Primary-port location is placement guidance, not a Build Point source.')).toBeTruthy();
    expect(within(panel).getByText('Architect primary-port location should be checked before final major station placement.')).toBeTruthy();
    expect(within(panel).queryByRole('button', { name: /make primary/i })).toBeNull();
    expect(within(panel).queryByRole('button', { name: /remove primary/i })).toBeNull();
  });

  it('handles missing templates, unassigned placements, and summary reset safely', () => {
    renderLayout();

    const placement = screen.getByRole('button', { name: 'Placement 3: missing_template' });
    fireEvent.click(placement);

    const panel = screen.getByTestId('layout-detail-panel');
    expect(within(panel).getAllByText('missing_template').length).toBeGreaterThan(0);
    expect(within(panel).getByText('Unassigned')).toBeTruthy();
    expect(within(panel).getByText('missing template')).toBeTruthy();
    expect(within(panel).getAllByText('Unknown').length).toBeGreaterThan(0);
    expect(within(panel).getByText('Needs review: facility template missing')).toBeTruthy();
    expect(within(panel).getByText('Needs review: placement has no body')).toBeTruthy();
    expect(within(panel).getByText('Assign bodies in List view before relying on Preview.')).toBeTruthy();

    fireEvent.click(within(panel).getByRole('button', { name: /Summary/i }));
    expect(within(panel).getByText('Select a body or placement')).toBeTruthy();
  });

  it('shows unknown body placement fallback and stale preview guidance', () => {
    renderLayout({
      placements: [
        { facility_template_id: 'surface_hab', local_body_id: '404', build_order: 1 },
        { facility_template_id: 'dodec_starport', local_body_id: '1', is_primary_port: true, build_order: 2 },
      ],
      previewResult: {} as SimulateBuildResponse,
      isPreviewResultStale: true,
    });

    const placement = screen.getByRole('button', { name: 'Placement 1: Surface Hab' });
    fireEvent.click(placement);

    const panel = screen.getByTestId('layout-detail-panel');
    expect(within(panel).getByText('Unknown body 404')).toBeTruthy();
    expect(within(panel).getByText('Check placement: body ID does not match known body')).toBeTruthy();
    expect(within(panel).getByText('Build Plan changed. Run Preview again before relying on this result.')).toBeTruthy();
  });

  it('supports keyboard selection for body and placement cards', () => {
    renderLayout();

    const body = screen.getByRole('button', { name: 'Select body A 1' });
    const placement = screen.getByRole('button', { name: 'Placement 2: Extraction Hub' });
    const bodySelect = screen.getByTestId('layout-body-select-2');

    fireEvent.keyDown(body, { key: 'Enter' });
    expect(body.getAttribute('aria-pressed')).toBe('true');

    fireEvent.click(placement);
    expect(placement.getAttribute('aria-pressed')).toBe('true');
    expect(bodySelect.getAttribute('aria-pressed')).toBe('false');

    fireEvent.keyDown(placement, { key: ' ' });
    expect(placement.getAttribute('aria-pressed')).toBe('true');
    expect(bodySelect.getAttribute('aria-pressed')).toBe('false');
  });

  it('handles zero placements in the detail panel without crashing', () => {
    renderLayout({ placements: [] });

    const panel = screen.getByTestId('layout-detail-panel');
    expect(within(panel).getByText('Select a body or placement')).toBeTruthy();
    expect(within(panel).getByText('Copy a Suggested Build or add facilities in List view.')).toBeTruthy();
  });
});

function planSummary(customPlacements: SimulateBuildPlacement[]) {
  return getPlanSummary({
    systemName: 'Test System',
    targetArchetype: 'refinery_industrial',
    placements: customPlacements,
    templates,
    bodies,
    previewResult: null,
    isPreviewResultStale: false,
    runningPreview: false,
  });
}
