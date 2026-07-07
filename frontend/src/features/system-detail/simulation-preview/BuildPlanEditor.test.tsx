import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { FacilityTemplate, SimulateBuildPlacement, SystemBody } from '@/types/api';
import { BuildPlanEditor } from './BuildPlanEditor';

const templates: FacilityTemplate[] = [
  {
    id: 'orbital_port',
    name: 'Orbital Port',
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
    id: 'surface_outpost',
    name: 'Surface Outpost',
    category: 'support',
    tier: 1,
    economy: 'Extraction',
    is_port: false,
    is_support_facility: true,
    allowed_location: 'surface',
    pad_size: 'small',
    confidence: 'estimated',
    notes: null,
    yellow_cp_generated: 8,
    green_cp_generated: 2,
    yellow_cp_cost: 0,
    green_cp_cost: 0,
  },
];

const bodies = [
  { id: 1, name: 'Body 1', body_type: 'Planet', is_landable: true },
] satisfies SystemBody[];

const placements: SimulateBuildPlacement[] = [
  { facility_template_id: 'orbital_port', local_body_id: '1', is_primary_port: true, build_order: 1 },
];

function renderEditor(customPlacements = placements) {
  const onUpdate = vi.fn();
  render(
    <BuildPlanEditor
      placements={customPlacements}
      templates={templates}
      bodies={bodies}
      onUpdate={onUpdate}
      onRemove={vi.fn()}
      onMove={vi.fn()}
    />,
  );
  return { onUpdate };
}

describe('BuildPlanEditor structure replacement review', () => {
  it('opens comparison instead of applying picker selection immediately', () => {
    const { onUpdate } = renderEditor();

    fireEvent.click(screen.getByRole('button', { name: /Browse structures/i }));
    fireEvent.click(screen.getByRole('button', { name: /Select structure Surface Outpost/i }));

    expect(onUpdate).not.toHaveBeenCalled();
    const comparison = screen.getByTestId('structure-replacement-comparison');
    expect(screen.getByTestId('structure-picker-row-surface_outpost').getAttribute('data-highlight')).toBe('proposed');
    expect(within(comparison).getByText('Review replacement')).toBeTruthy();
    expect(within(comparison).getAllByText('Current').length).toBeGreaterThan(0);
    expect(within(comparison).getAllByText('Proposed').length).toBeGreaterThan(0);
    expect(within(comparison).getAllByText('Orbital Port').length).toBeGreaterThan(0);
    expect(within(comparison).getAllByText('Surface Outpost').length).toBeGreaterThan(0);
    expect(within(comparison).getAllByText('CP gives').length).toBeGreaterThan(0);
    expect(within(comparison).getAllByText('CP needs').length).toBeGreaterThan(0);
    expect(within(comparison).getAllByText('Needs review: template uses estimated data').length).toBeGreaterThan(0);
    expect(within(comparison).getByText('Body context: Body 1')).toBeTruthy();
  });

  it('cancels replacement without updating placement', () => {
    const { onUpdate } = renderEditor();

    fireEvent.click(screen.getByRole('button', { name: /Browse structures/i }));
    fireEvent.click(screen.getByRole('button', { name: /Select structure Surface Outpost/i }));
    fireEvent.click(screen.getByRole('button', { name: /Cancel replacement/i }));

    expect(onUpdate).not.toHaveBeenCalled();
    expect(screen.queryByTestId('structure-replacement-comparison')).toBeNull();
    expect(screen.getByDisplayValue('T3 - Orbital Port - Industrial')).toBeTruthy();
  });

  it('applies replacement through existing update callback only after confirmation', () => {
    const { onUpdate } = renderEditor();

    fireEvent.click(screen.getByRole('button', { name: /Browse structures/i }));
    fireEvent.click(screen.getByRole('button', { name: /Select structure Surface Outpost/i }));
    fireEvent.click(screen.getByRole('button', { name: /Apply replacement/i }));

    expect(onUpdate).toHaveBeenCalledTimes(1);
    expect(onUpdate).toHaveBeenCalledWith(0, { facility_template_id: 'surface_outpost' });
  });

  it('shows read-only Architect primary-port context without primary controls', () => {
    renderEditor();

    expect(screen.getAllByText(/Check System Map > Architect Mode before final major station placement/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Primary-port location is placement guidance, not a Build Point source/).length).toBeGreaterThan(0);
    expect(screen.getByText('Architect survey: not observed')).toBeTruthy();
    expect(screen.getByText('Primary-port flag: unknown')).toBeTruthy();
    expect(screen.getAllByText(/If the flagged primary-port slot is inconvenient, consider an outpost there/).length).toBeGreaterThan(0);
    expect(screen.getByText('Architect primary-port location should be checked before final major station placement.')).toBeTruthy();
    expect(screen.getAllByText('If the flagged primary-port slot is inconvenient, consider an outpost there and place the main station elsewhere.').length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /make primary/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /remove primary/i })).toBeNull();
    expect(screen.queryByRole('checkbox', { name: /primary/i })).toBeNull();
    expect(screen.queryByText(/unsafe to invest/i)).toBeNull();
    expect(screen.queryByText(/system is poor/i)).toBeNull();
    expect(screen.queryByText(/do not build here/i)).toBeNull();
  });

  it('renders advisory guidance without changing apply or cancel behavior', () => {
    const { onUpdate } = renderEditor([
      { facility_template_id: 'surface_outpost', local_body_id: '1', is_primary_port: false, build_order: 1 },
    ]);

    fireEvent.click(screen.getByRole('button', { name: /Browse structures/i }));
    fireEvent.click(screen.getByRole('button', { name: /Select structure Orbital Port/i }));

    expect(screen.getAllByText('Estimated template data: review before relying on the plan.').length).toBeGreaterThan(0);
    expect(onUpdate).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /Cancel replacement/i }));
    expect(onUpdate).not.toHaveBeenCalled();
  });

  it('highlights placements related to the selected topology body without mutating the plan', () => {
    const onUpdate = vi.fn();
    render(
      <BuildPlanEditor
        placements={[
          { facility_template_id: 'orbital_port', local_body_id: '1', is_primary_port: true, build_order: 1 },
          { facility_template_id: 'surface_outpost', local_body_id: null, is_primary_port: false, build_order: 2 },
        ]}
        templates={templates}
        bodies={bodies}
        topologySelection={{ type: 'body', bodyId: '1' }}
        onUpdate={onUpdate}
        onRemove={vi.fn()}
        onMove={vi.fn()}
      />,
    );

    expect(screen.getByTestId('build-plan-placement-0').getAttribute('data-topology-highlight')).toBe('body');
    expect(screen.getByTestId('build-plan-placement-1').getAttribute('data-topology-highlight')).toBe('none');
    expect(onUpdate).not.toHaveBeenCalled();
  });

  it('highlights the selected topology placement and keeps editing in the central planner', () => {
    const onUpdate = vi.fn();
    render(
      <BuildPlanEditor
        placements={[
          { facility_template_id: 'orbital_port', local_body_id: '1', is_primary_port: true, build_order: 1 },
          { facility_template_id: 'surface_outpost', local_body_id: null, is_primary_port: false, build_order: 2 },
        ]}
        templates={templates}
        bodies={bodies}
        topologySelection={{ type: 'placement', placementIndex: 1 }}
        onUpdate={onUpdate}
        onRemove={vi.fn()}
        onMove={vi.fn()}
      />,
    );

    expect(screen.getByTestId('build-plan-placement-1').getAttribute('data-topology-highlight')).toBe('placement');
    expect(screen.getByText('Topology selected')).toBeTruthy();
    expect(onUpdate).not.toHaveBeenCalled();
  });
});
