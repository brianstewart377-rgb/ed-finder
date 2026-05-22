import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { FacilityTemplate, SlotPredictionResponse, SystemDetail } from '@/types/api';
import type { TopologyPlanSnapshot, TopologySelectionContext } from './ColonyTopologyRail';
import { RavenPlannerTelemetryPanel, RavenStylePlannerCanvas, buildRavenPlannerRows } from './RavenStylePlannerCanvas';
import { buildPlanningEconomyLedger } from './planningEconomy';

const system = {
  id64: 123,
  name: 'Real Data System',
  population: 1250000,
  score: 72,
  bodies: [
    { id: 1, name: 'Real Data System A', body_type: 'Star', subtype: 'K' },
    { id: 2, name: 'Real Data System A 1', body_type: 'Planet', subtype: 'High metal content world', is_landable: true, parent_body_id: 1, distance_from_star: 220 },
    { id: 3, name: 'Real Data System A 2', body_type: 'Planet', subtype: 'Icy body', is_landable: false, parent_body_id: 1, distance_from_star: 330 },
  ],
} as unknown as SystemDetail;

const templates: FacilityTemplate[] = [
  {
    id: 'dodec_starport',
    display_name: 'Dodec Starport',
    name: 'Fallback Dodec',
    category: 'port',
    tier: 3,
    economy: 'Industrial',
    is_port: true,
    is_support_facility: false,
    allowed_location: 'orbital',
    pad_size: 'large',
    confidence: 'confirmed',
    notes: null,
    yellow_cp_generated: 480,
    green_cp_generated: 240,
    yellow_cp_cost: 0,
    green_cp_cost: 0,
  } as FacilityTemplate & { display_name: string },
  {
    id: 'surface_refinery',
    name: 'Surface Refinery Hub',
    category: 'support',
    tier: 1,
    economy: 'Refinery',
    is_port: false,
    is_support_facility: true,
    allowed_location: 'surface',
    pad_size: 'medium',
    confidence: 'confirmed',
    notes: null,
    yellow_cp_generated: 300,
    green_cp_generated: 250,
    yellow_cp_cost: 1,
    green_cp_cost: 0,
  },
  {
    id: 'no_metadata',
    name: 'No Metadata Facility',
    category: 'support',
    tier: 1,
    economy: null,
    is_port: false,
    is_support_facility: true,
    allowed_location: 'surface',
    pad_size: 'medium',
    confidence: 'estimated',
    notes: null,
    yellow_cp_generated: 0,
    green_cp_generated: 0,
    yellow_cp_cost: 0,
    green_cp_cost: 0,
  },
];

const slotPredictions: SlotPredictionResponse = {
  system_id64: 123,
  data_source: 'eddn',
  body_count: 2,
  predicted_orbital_slots_total: 2,
  predicted_ground_slots_total: 2,
  prediction_status: 'predicted',
  prediction_version: 'validated-slot-v1',
  confidence_label: 'validated',
  disclaimer: 'Predicted slots.',
  validation_note: 'Validated.',
  required_input_missing: [],
  predictions: [
    {
      system_address: 123,
      body_id: 2,
      body_name: 'Real Data System A 1',
      predicted_orbital_slots: 2,
      predicted_ground_slots: 2,
      prediction_status: 'predicted',
      reasons: [],
    },
  ],
};

const snapshot: TopologyPlanSnapshot = {
  placements: [
    { facility_template_id: 'dodec_starport', local_body_id: '2', is_primary_port: true, build_order: 1 },
    { facility_template_id: 'surface_refinery', local_body_id: '2', build_order: 2 },
    { facility_template_id: 'no_metadata', local_body_id: '3', build_order: 3 },
  ],
  templates,
  targetArchetype: 'refinery_industrial',
  slotPredictions,
  projection: {
    candidateId: 'candidate-1',
    label: 'Candidate 1',
    placements: [
      { facility_template_id: 'surface_refinery', local_body_id: '2', build_order: 4 },
    ],
  },
};

describe('RavenStylePlannerCanvas real data adapter', () => {
  it('maps real bodies, slot predictions, placements, projections, and economy metadata into rows', () => {
    const rows = buildRavenPlannerRows(system, snapshot);
    const body = rows.find((row) => row.id === '2');
    const missingPredictionBody = rows.find((row) => row.id === '3');

    expect(body?.displayName).toBe('Real Data System A 1');
    expect(body?.orbitalCapacity).toBe(2);
    expect(body?.groundCapacity).toBe(2);
    expect(body?.orbitalSlots[0].fullName).toBe('Dodec Starport');
    expect(body?.orbitalSlots[0].economySegments[0]).toEqual(expect.objectContaining({ economy: 'Industrial', strength: 720 }));
    expect(body?.groundSlots[0].fullName).toBe('Surface Refinery Hub');
    expect(body?.groundSlots[1].kind).toBe('projected');
    expect(missingPredictionBody?.orbitalSlots[0].kind).toBe('unknown');
    expect(missingPredictionBody?.groundSlots[1].title).toContain('No economy metadata');
  });

  it('renders real planner lanes without static mock bodies or attached-structure column', () => {
    render(<RavenStylePlannerCanvas system={system} snapshot={snapshot} selection={{ type: 'system' }} onSelect={vi.fn()} />);

    expect(screen.getByTestId('raven-real-planner-canvas')).toBeTruthy();
    expect(screen.getByTestId('raven-real-body-row-2')).toBeTruthy();
    expect(screen.getByText('Dodec')).toBeTruthy();
    expect(screen.getByText('Refinery Hub')).toBeTruthy();
    expect(screen.getByText('Ghost Refinery Hub')).toBeTruthy();
    expect(screen.getAllByTestId('raven-structure-economy-micro-bar').length).toBeGreaterThan(0);
    expect(screen.getByTitle(/Dodec Starport.*Industrial 100% share.*\+720 CP strength/)).toBeTruthy();
    expect(screen.queryByText('Praea Eug WV-W b2-2')).toBeNull();
    expect(screen.queryByText('Attached Structures')).toBeNull();
    expect(screen.queryByText('Facilities and economy')).toBeNull();
  });

  it('renders telemetry with positive and negative zero-centered bars from live planner state', () => {
    const ledger = buildPlanningEconomyLedger({
      placements: snapshot.placements,
      projectedPlacements: snapshot.projection?.placements ?? [],
      templates,
    });
    const selectedContext: TopologySelectionContext = {
      label: 'Real Data System A 1',
      kind: 'Planet',
      placementCount: 2,
      warningCount: 1,
      architectStatus: 'not recorded',
      detail: 'Body selected for planning.',
    };

    render(
      <RavenPlannerTelemetryPanel
        system={system}
        snapshot={snapshot}
        economyLedger={ledger}
        selectedContext={selectedContext}
      />,
    );

    expect(screen.getByTestId('raven-real-telemetry-panel')).toBeTruthy();
    expect(screen.getByTestId('raven-stat-planned-builds-positive').dataset.tone).toBe('positive-green');
    expect(screen.getByTestId('raven-stat-missing-economy-negative').dataset.tone).toBe('negative-red');
    expect(screen.getByTestId('raven-stat-missing-economy-negative').style.width).not.toBe('0%');
    expect(within(screen.getByTestId('raven-telemetry-economy-ledger')).getByText(/Ind/i)).toBeTruthy();
  });
});
