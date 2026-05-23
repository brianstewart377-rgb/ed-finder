import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { FacilityTemplate, SlotPredictionResponse, SystemDetail } from '@/types/api';
import type { TopologyPlanSnapshot, TopologySelectionContext } from './ColonyTopologyRail';
import { RavenPlannerTelemetryPanel, RavenStylePlannerCanvas, buildProjectionComparison, buildRavenPlannerRows } from './RavenStylePlannerCanvas';
import { buildPlanningEconomyLedger } from './planningEconomy';

const system = {
  id64: 123,
  name: 'Real Data System',
  population: 1250000,
  score: 72,
  score_agriculture: 38,
  score_refinery: 83,
  score_industrial: 71,
  score_hightech: 44,
  score_military: 52,
  score_tourism: 29,
  score_extraction: 68,
  economy_suggestion: 'Refinery',
  terraforming_potential: 23,
  body_diversity: 18,
  confidence: 0.82,
  rationale: 'Strong Refinery; dense HMC and rocky body stack with solid slot capacity.',
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
    stat_effects: {
      population: 72,
      max_population: 10,
      security: -20.9,
      tech_level: 18.6,
      wealth: 20.25,
      standard_of_living: 30.4,
      development_level: 27.6,
    },
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

  it('excludes Barycentre and Null entries from the real system tree rows', () => {
    const rows = buildRavenPlannerRows({
      ...system,
      bodies: [
        ...(system.bodies ?? []),
        { id: 90, name: 'Real Data System Barycentre', body_type: 'Barycentre', subtype: 'Barycentre' },
        { id: 91, name: 'Null Body', body_type: 'Planet', subtype: 'Null' },
      ],
    } as unknown as SystemDetail, {
      ...snapshot,
      placements: [],
      projection: null,
      slotPredictions: null,
    });

    expect(rows.find((row) => row.id === '90')).toBeUndefined();
    expect(rows.find((row) => row.id === '91')).toBeUndefined();
    expect(rows.map((row) => row.displayName).join(' ')).not.toMatch(/Barycentre|Null Body/i);
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

  it('expands selected bodies inline and supports projected structure selection', () => {
    render(
      <RavenStylePlannerCanvas
        system={system}
        snapshot={snapshot}
        selection={{ type: 'body', bodyId: '2' }}
        expandedBodyDetail={<div data-testid="inline-body-test-detail">Inline body detail</div>}
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByTestId('raven-real-body-row-2').getAttribute('data-expanded')).toBe('true');
    expect(within(screen.getByTestId('raven-real-planner-canvas')).getByTestId('raven-inline-body-expansion-2')).toBeTruthy();
    expect(screen.getByTestId('inline-body-test-detail')).toBeTruthy();
  });

  it('selects planned and projected structures from the main canvas', () => {
    const onSelect = vi.fn();
    render(<RavenStylePlannerCanvas system={system} snapshot={snapshot} selection={{ type: 'system' }} onSelect={onSelect} />);

    fireEvent.click(screen.getByTestId('2-orbital-slot-0'));
    expect(onSelect).toHaveBeenCalledWith({ type: 'placement', placementIndex: 0 });

    fireEvent.click(screen.getByTestId('2-ground-slot-1'));
    expect(onSelect).toHaveBeenCalledWith({ type: 'projected-placement', placementIndex: 0 });
  });

  it('matches projected structures to large numeric system body ids', () => {
    const exactBodyId = '1044927859400806427';
    const roundedBodyId = String(Number(exactBodyId));
    const largeSystem = {
      ...system,
      bodies: [
        { id: Number(exactBodyId), name: 'Real Data System A 1 a', body_type: 'Planet', subtype: 'Rocky body', is_landable: true, distance_from_star: 440 },
      ],
    } as unknown as SystemDetail;
    const largeSnapshot: TopologyPlanSnapshot = {
      ...snapshot,
      placements: [],
      slotPredictions: {
        ...slotPredictions,
        predictions: [
          {
            ...slotPredictions.predictions[0],
            body_id: Number(exactBodyId),
            body_name: 'Real Data System A 1 a',
            predicted_orbital_slots: 1,
            predicted_ground_slots: 2,
          },
        ],
      },
      projection: {
        candidateId: 'large-id-candidate',
        label: 'Large id candidate',
        placements: [
          { facility_template_id: 'surface_refinery', local_body_id: exactBodyId, build_order: 1 },
        ],
      },
    };

    const rows = buildRavenPlannerRows(largeSystem, largeSnapshot);
    const row = rows.find((candidate) => candidate.id === roundedBodyId);

    expect(row?.projected).toBe(true);
    expect(row?.groundSlots[0]).toEqual(expect.objectContaining({ kind: 'projected', projectionIndex: 0 }));

    render(<RavenStylePlannerCanvas system={largeSystem} snapshot={largeSnapshot} selection={{ type: 'system' }} onSelect={vi.fn()} />);

    expect(screen.getByTestId(`raven-real-body-row-${roundedBodyId}`).getAttribute('data-projected')).toBe('true');
    expect(screen.getByText('Ghost Refinery Hub')).toBeTruthy();
  });

  it('summarises selected projection comparison against the current Build Plan', () => {
    const ledger = buildPlanningEconomyLedger({
      placements: snapshot.placements,
      projectedPlacements: snapshot.projection?.placements ?? [],
      templates,
    });
    const comparison = buildProjectionComparison(system, snapshot, ledger);

    expect(comparison.hasProjection).toBe(true);
    expect(comparison.plannedBodyCount).toBe(2);
    expect(comparison.projectedBodyCount).toBe(1);
    expect(comparison.sharedBodyCount).toBe(1);
    expect(comparison.projectedGroundCount).toBe(1);
    expect(comparison.economyDeltas.find((entry) => entry.economy === 'Refinery')).toEqual(expect.objectContaining({ planned: 1, projected: 1 }));
  });

  it('renders exact BGS telemetry deltas with positive and negative zero-centered bars from live planner state', () => {
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
        selection={{ type: 'body', bodyId: '2' }}
      />,
    );

    expect(screen.getByTestId('raven-real-telemetry-panel')).toBeTruthy();
    expect(screen.getByText('Max population')).toBeTruthy();
    expect(screen.getByText('Standard of living')).toBeTruthy();
    expect(screen.getByText('Development level')).toBeTruthy();
    expect(screen.getByTestId('raven-stat-population-positive').dataset.tone).toBe('positive-green');
    expect(screen.getByTestId('raven-stat-security-negative').dataset.tone).toBe('negative-red');
    expect(screen.getByTestId('raven-stat-security-negative').style.width).not.toBe('0%');
    expect(screen.getByText('+72')).toBeTruthy();
    expect(screen.getByText('-20.9')).toBeTruthy();
    expect(screen.getByTestId('raven-rating-profile-card')).toBeTruthy();
    expect(screen.getByTestId('raven-rating-overall-score').textContent).toContain('72');
    expect(screen.getByTestId('raven-rating-economy-breakdown')).toBeTruthy();
    expect(screen.getByTestId('raven-rating-axis-refinery').textContent).toContain('83');
    expect(screen.getByText(/High 82%/)).toBeTruthy();
    expect(screen.getByTestId('raven-rating-rationale').textContent).toContain('Strong Refinery');
    expect(within(screen.getByTestId('raven-telemetry-economy-ledger')).getByText(/Ind/i)).toBeTruthy();
    expect(screen.getByTestId('raven-projection-comparison')).toBeTruthy();
    expect(screen.getByTestId('projection-comparison-bodies')).toBeTruthy();
    fireEvent.click(screen.getByTestId('projection-comparison-economy-toggle'));
    expect(screen.getByTestId('projection-comparison-economy')).toBeTruthy();
    fireEvent.click(screen.getByTestId('projection-comparison-slots-toggle'));
    expect(screen.getByTestId('projection-comparison-slots')).toBeTruthy();
  });
});
