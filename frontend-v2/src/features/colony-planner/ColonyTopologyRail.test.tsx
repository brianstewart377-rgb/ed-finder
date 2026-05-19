import { fireEvent, render, screen, within } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import type { FacilityTemplate, SimulateBuildPlacement, SystemDetail } from '@/types/api';
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
}: {
  customSystem?: SystemDetail;
  onSelectSpy?: (selection: TopologySelection) => void;
}) {
  const [selection, setSelection] = useState<TopologySelection>({ type: 'system' });
  return (
    <>
      <ColonyTopologyRail
        system={customSystem}
        snapshot={{ placements, templates, targetArchetype: 'refinery_industrial' }}
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
        }).label}
      </output>
    </>
  );
}

describe('ColonyTopologyRail', () => {
  it('renders body rows, moon indentation, and placement counts from the plan snapshot', () => {
    render(<RailHarness />);

    expect(screen.getByTestId('topology-root-row')).toBeTruthy();
    expect(screen.getByText('Tree System A')).toBeTruthy();
    expect(screen.getByText('Tree System A 1')).toBeTruthy();
    expect(screen.getByText('Tree System A 1 a')).toBeTruthy();

    const firstBody = screen.getByTestId('topology-body-1');
    expect(within(firstBody).getByText('1')).toBeTruthy();
    expect(within(firstBody).getByLabelText('Primary-port placement')).toBeTruthy();
    expect(within(firstBody).getAllByText('primary').length).toBeGreaterThan(0);

    const moonBody = screen.getByTestId('topology-body-2');
    expect(within(moonBody).getByText('1')).toBeTruthy();
    expect(within(moonBody).queryByText(/Inferred:/i)).toBeNull();
    expect(within(moonBody).queryByText('1 surface')).toBeNull();
    expect(within(moonBody).getByRole('button', { name: /Tree System A 1 a/i }).getAttribute('aria-pressed')).toBe('false');
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

    fireEvent.click(screen.getByText('Tree System A 1'));
    expect(onSelectSpy).toHaveBeenLastCalledWith({ type: 'body', bodyId: '1' });
    expect(screen.getByTestId('selected-context').textContent).toBe('Tree System A 1');
    expect(screen.getByRole('button', { name: /Tree System A 1 High metal content/i }).getAttribute('aria-pressed')).toBe('true');

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
});
