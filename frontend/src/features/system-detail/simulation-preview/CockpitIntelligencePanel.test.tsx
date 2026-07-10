import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { FacilityTemplate, SimulateBuildPlacement, SystemBody } from '@/types/api';
import { CockpitIntelligencePanel } from './CockpitIntelligencePanel';

const templates: FacilityTemplate[] = [
  {
    id: 'generic_port_alpha',
    name: 'Generic Port Alpha',
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
    yellow_cp_cost: 12,
    green_cp_cost: 20,
  },
  {
    id: 'agri_support_a',
    name: 'Agriculture Support A',
    category: 'support',
    tier: 1,
    economy: 'Agriculture',
    is_port: false,
    is_support_facility: true,
    allowed_location: 'surface',
    pad_size: null,
    confidence: 'observed',
    notes: null,
    yellow_cp_generated: 2,
    green_cp_generated: 0,
    yellow_cp_cost: 0,
    green_cp_cost: 0,
  },
];

const bodies: SystemBody[] = [
  { id: 1, name: 'A 1', body_type: 'Planet', subtype: 'Rocky body', is_landable: true },
  { id: 2, name: 'A 2', body_type: 'Planet', subtype: 'Water world', is_water_world: true },
];

const placements: SimulateBuildPlacement[] = [
  { facility_template_id: 'generic_port_alpha', local_body_id: '1', is_primary_port: true, build_order: 1 },
  { facility_template_id: 'agri_support_a', local_body_id: '2', is_primary_port: false, build_order: 2 },
];

describe('CockpitIntelligencePanel', () => {
  it('summarises facility signals and next actions for an in-progress plan', () => {
    render(
      <CockpitIntelligencePanel
        placements={placements}
        templates={templates}
        bodies={bodies}
        previewStatus="not_run"
        observedFactsCount={0}
      />,
    );

    expect(screen.getByTestId('cockpit-intelligence-panel').textContent).toMatch(/Facility intelligence/);
    expect(screen.getByTestId('cockpit-intelligence-posture').textContent).toMatch(/needs an explicit preview result/i);
    expect(screen.getByTestId('cockpit-intelligence-role-anchors').textContent).toMatch(/Main station candidates: A 1/);
    expect(screen.getByTestId('cockpit-intelligence-role-anchors').textContent).toMatch(/Support bodies: A 2/);
    expect(screen.getByTestId('cockpit-intelligence-facility-pressure').textContent).toMatch(/Agriculture x1/);
    expect(screen.getByTestId('cockpit-intelligence-next-actions').textContent).toMatch(/Run Preview/);
  });

  it('switches to review-oriented next actions once preview and evidence are in place', () => {
    render(
      <CockpitIntelligencePanel
        placements={placements}
        templates={templates}
        bodies={bodies}
        previewStatus="current"
        observedFactsCount={2}
      />,
    );

    expect(screen.getByTestId('cockpit-intelligence-posture').textContent).toMatch(/aligned enough for validation and hand-off/i);
    expect(screen.getByTestId('cockpit-intelligence-next-actions').textContent).toMatch(/Move through Validation and Export/);
  });
});
