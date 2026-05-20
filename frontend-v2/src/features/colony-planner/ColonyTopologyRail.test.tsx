import { fireEvent, render, screen, within } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import type { FacilityTemplate, SimulateBuildPlacement, SlotPredictionResponse, SystemDetail } from '@/types/api';
import {
  ColonyTopologyRail,
  describeTopologySelection,
  type TopologySelection,
} from './ColonyTopologyRail';

const templates: FacilityTemplate[] = [
  {
    id: 'orbital_port',
    name: 'Orbital Port',
    category: 'port',
    tier: 3,
    economy: null,
    is_port: true,
    is_support_facility: false,
    allowed_location: 'orbital',
    pad_size: 'large',
    confidence: 'confirmed',
    notes: null,
    yellow_cp_generated: 1,
    green_cp_generated: 1,
    yellow_cp_cost: 0,
    green_cp_cost: 0,
  },
  {
    id: 'surface_hub',
    name: 'Surface Hub',
    category: 'support',
    tier: 1,
    economy: 'Extraction',
    is_port: false,
    is_support_facility: true,
    allowed_location: 'surface',
    pad_size: 'medium',
    confidence: 'confirmed',
    notes: null,
    yellow_cp_generated: 0,
    green_cp_generated: 0,
    yellow_cp_cost: 1,
    green_cp_cost: 0,
  },
];

const placements: SimulateBuildPlacement[] = [
  { facility_template_id: 'orbital_port', local_body_id: '1', is_primary_port: true, build_order: 1 },
  { facility_template_id: 'surface_hub', local_body_id: '2', build_order: 2 },
  { facility_template_id: 'surface_hub', local_body_id: '404', build_order: 3 },
  { facility_template_id: 'surface_hub', local_body_id: null, build_order: 4 },
];

const slotPredictions: SlotPredictionResponse = {
  system_id64: 123,
  data_source: 'eddn',
  body_count: 2,
  predicted_orbital_slots_total: 4,
  predicted_ground_slots_total: 5,
  prediction_status: 'predicted',
  prediction_version: 'validated-slot-v1',
  confidence_label: 'validated_high_accuracy',
  disclaimer: 'Predicted slots — high-accuracy algorithm, not guaranteed. Verify in Architect Mode.',
  validation_note: 'Validated against the supplied evidence set with only 2 true mismatches after data-entry corrections.',
  required_input_missing: [],
  predictions: [
    {
      system_address: 123,
      body_id: 1,
      body_name: 'Tree System A 1',
      planet_class: 'High metal content world',
      predicted_orbital_slots: 4,
      predicted_ground_slots: 5,
      prediction_status: 'predicted',
      reasons: [],
    },
    {
      system_address: 123,
      body_id: 2,
      body_name: 'Tree System A 1 a',
      planet_class: 'Rocky body',
      predicted_orbital_slots: null,
      predicted_ground_slots: null,
      prediction_status: 'unknown',
      required_input_missing: ['atmosphere'],
      reasons: [],
    },
  ],
};

const system = {
  id64: 123,
  name: 'Tree System',
  bodies: [
    { id: 0, name: 'Tree System A', body_type: 'Star', subtype: 'K' },
    { id: 1, name: 'Tree System A 1', body_type: 'Planet', subtype: 'High metal content world', distance_from_star: 100 },
    { id: 2, name: 'Tree System A 1 a', body_type: 'Planet', subtype: 'Rocky body', parent_body_id: 1, is_landable: true },
  ],
} as unknown as SystemDetail;

function RailHarness({
  customSystem = system,
  onSelectSpy,
  projection = null,
}: {
  customSystem?: SystemDetail;
  onSelectSpy?: (selection: TopologySelection) => void;
  projection?: {
    candidateId: string;
    label: string;
    placements: SimulateBuildPlacement[];
  } | null;
}) {
  const [selection, setSelection] = useState<TopologySelection>({ type: 'system' });
  return (
    <>
      <ColonyTopologyRail
        system={customSystem}
        snapshot={{ placements, templates, targetArchetype: 'refinery_industrial', slotPredictions, projection }}
        selection={selection}
        onSelect={(next) => {
          onSelectSpy?.(next);
          setSelection(next);
        }}
      />
      <output data-testid="selected-context">
        {describeTopologySelection(selection, customSystem, {
          placements,
          templates,
          targetArchetype: 'refinery_industrial',
          slotPredictions,
        }).label}
      </output>
    </>
  );
}

describe('ColonyTopologyRail', () => {
  it('renders body rows, moon indentation, and placement counts from the plan snapshot', () => {
    render(<RailHarness />);

    expect(screen.getByTestId('topology-root-row')).toBeTruthy();
    expect(screen.getByText('A')).toBeTruthy();
    expect(screen.getByText('A 1')).toBeTruthy();
    expect(screen.getByText('A 1 a')).toBeTruthy();
    expect(screen.getByTitle('Tree System A')).toBeTruthy();
    expect(screen.getByTitle('Tree System A 1')).toBeTruthy();
    expect(screen.getByTitle('Tree System A 1 a')).toBeTruthy();

    const firstBody = screen.getByTestId('topology-body-1');
    expect(within(firstBody).getByText('1')).toBeTruthy();
    expect(within(firstBody).getByText('Planned')).toBeTruthy();
    expect(within(firstBody).getByLabelText('Primary-port placement')).toBeTruthy();
    expect(within(firstBody).getAllByText('primary').length).toBeGreaterThan(0);

    const moonBody = screen.getByTestId('topology-body-2');
    expect(within(moonBody).getByText('1')).toBeTruthy();
    expect(within(moonBody).queryByText(/Inferred:/i)).toBeNull();
    expect(within(moonBody).queryByText('1 surface')).toBeNull();
    expect(screen.getByTestId('topology-body-button-2').getAttribute('aria-pressed')).toBe('false');
  });

  it('renders unknown and unassigned placement groups without exposing raw IDs by default', () => {
    render(<RailHarness />);

    expect(screen.getByText('Unknown / unmatched body')).toBeTruthy();
    expect(screen.getByText('1 unmatched placement reference')).toBeTruthy();
    expect(screen.getByText('Unassigned placements')).toBeTruthy();
    expect(screen.getByText('1 placement needs a body')).toBeTruthy();
    expect(screen.queryByText('404')).toBeNull();
  });

  it('selects body and placement context without mutating the plan', () => {
    const onSelectSpy = vi.fn();
    render(<RailHarness onSelectSpy={onSelectSpy} />);

    fireEvent.click(screen.getByTestId('topology-body-button-1'));
    expect(onSelectSpy).toHaveBeenLastCalledWith({ type: 'body', bodyId: '1' });
    expect(screen.getByTestId('selected-context').textContent).toBe('Tree System A 1');
    expect(screen.getByTestId('topology-body-button-1').getAttribute('aria-pressed')).toBe('true');

    fireEvent.click(screen.getByTestId('topology-placement-0'));
    expect(onSelectSpy).toHaveBeenLastCalledWith({ type: 'placement', placementIndex: 0 });
    expect(screen.getByTestId('selected-context').textContent).toBe('Orbital Port');
  });

  it('renders the friendly empty body layout state', () => {
    render(<RailHarness customSystem={{ ...system, bodies: [] } as unknown as SystemDetail} />);

    expect(
      screen.getByText(/No body layout imported yet\. Use the planner tools to import\/refresh layout when available/i),
    ).toBeTruthy();
  });

  it('shows projected suggested-build placements under matching bodies before loading', () => {
    render(
      <RailHarness
        projection={{
          candidateId: 'candidate-expansion',
          label: 'Expansion candidate',
          placements: [
            { facility_template_id: 'surface_hub', local_body_id: '2', is_primary_port: false, build_order: 5 },
          ],
        }}
      />,
    );

    expect(screen.getByTestId('topology-projected-bodies')).toBeTruthy();
    expect(screen.getByTestId('topology-projected-group-2')).toBeTruthy();
    expect(within(screen.getByTestId('topology-projected-group-2')).getByText('Projected')).toBeTruthy();
    expect(screen.getByTestId('topology-projected-placement-0')).toBeTruthy();
  });

  it('renders canonical slot lane counts and occupancy for a 4 orbital / 5 ground body', () => {
    render(<RailHarness />);

    expect(screen.getByText(/Predicted slots — high-accuracy algorithm, not guaranteed. Verify in Architect Mode./)).toBeTruthy();
    expect(screen.getByTestId('1-orbital-slot-3')).toBeTruthy();
    expect(screen.getByTestId('1-ground-slot-4')).toBeTruthy();

    const firstBody = screen.getByTestId('topology-body-1');
    expect(within(firstBody).getByTestId('1-orbital-slot-0').textContent?.trim().length).toBeGreaterThan(0);
  });

  it('shows unknown slot lane when canonical prediction is unknown', () => {
    render(<RailHarness />);
    expect(screen.getByTestId('slot-lane-unknown-2-orbital')).toBeTruthy();
    expect(screen.getByTestId('slot-lane-unknown-2-ground')).toBeTruthy();
  });

  it('shows overflow when structures exceed predicted capacity', () => {
    render(
      <RailHarness
        projection={{
          candidateId: 'candidate-overflow',
          label: 'Overflow candidate',
          placements: [
            { facility_template_id: 'orbital_port', local_body_id: '1', is_primary_port: false, build_order: 5 },
            { facility_template_id: 'orbital_port', local_body_id: '1', is_primary_port: false, build_order: 6 },
            { facility_template_id: 'orbital_port', local_body_id: '1', is_primary_port: false, build_order: 7 },
            { facility_template_id: 'orbital_port', local_body_id: '1', is_primary_port: false, build_order: 8 },
            { facility_template_id: 'orbital_port', local_body_id: '1', is_primary_port: false, build_order: 9 },
          ],
        }}
      />,
    );
    expect(screen.getByTestId('topology-overflow-1').textContent).toContain('overflow / unconfirmed');
  });
});
