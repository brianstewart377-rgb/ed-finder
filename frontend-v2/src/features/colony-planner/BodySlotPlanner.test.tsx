import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { BodySlotPrediction, SystemBody } from '@/types/api';
import type { ExistingStructure } from './existingInfrastructure';
import { BodySlotPlanner } from './BodySlotPlanner';

const body = {
  id: 2,
  name: 'Band Test A 1',
  body_type: 'Planet',
  subtype: 'High metal content world',
  is_landable: true,
} as SystemBody;

const slotPrediction: BodySlotPrediction = {
  system_address: 123,
  body_id: 2,
  body_name: 'Band Test A 1',
  predicted_orbital_slots: 4,
  predicted_ground_slots: 5,
  prediction_status: 'predicted',
  reasons: [],
};

const existingOrbital: ExistingStructure[] = [
  {
    source: 'existing',
    id: 'existing-orbit-1',
    market_id: 11,
    name: 'Jameson Orbital',
    station_type: 'Coriolis',
    body_id: '2',
    body_name: 'Band Test A 1',
    body_match_confidence: 'exact',
    body_match_reason: 'Matched by body id.',
    lane: 'orbital',
    association_status: 'confirmed',
    association_confidence: 'exact',
    association_source: 'body_id',
    economy: 'Industrial',
    secondary_economy: null,
    pad_size: 'L',
    distance_from_star: 1234,
    unresolved_reason: null,
    transient: false,
    transient_reason: null,
    raw: {
      station_id: 11,
      body_name: 'Band Test A 1',
      station_type: 'Coriolis',
    },
  },
];

const existingSurface: ExistingStructure[] = [
  {
    source: 'existing',
    id: 'existing-surface-1',
    market_id: 12,
    name: 'Miller Port',
    station_type: 'PlanetaryPort',
    body_id: '2',
    body_name: 'Band Test A 1',
    body_match_confidence: 'inferred',
    body_match_reason: 'Matched by body name.',
    lane: 'surface',
    association_status: 'inferred',
    association_confidence: 'strong_inference',
    association_source: 'body_name',
    economy: 'Agriculture',
    secondary_economy: null,
    pad_size: 'M',
    distance_from_star: 4321,
    unresolved_reason: null,
    transient: false,
    transient_reason: null,
    raw: {
      station_id: 12,
      body_name: 'Band Test A 1',
      station_type: 'PlanetaryPort',
    },
  },
];

describe('BodySlotPlanner', () => {
  it('renders vivid orbit/surface bands with one token per calculated slot', () => {
    const { container } = render(
      <BodySlotPlanner
        body={body}
        slotPrediction={slotPrediction}
        placements={[]}
        projectedPlacements={[]}
        selectedPlacementIndex={null}
        selectedProjectedPlacementIndex={null}
        hasTemplates
        onSelectPlacement={vi.fn()}
        onSelectProjectedPlacement={vi.fn()}
        onAddLaneStructure={vi.fn()}
      />,
    );

    const orbitBand = container.querySelector('circle[stroke="#00c8ff"]');
    const surfaceBand = container.querySelector('circle[stroke="#ff9f1a"]');
    expect(orbitBand?.getAttribute('stroke-width')).toBe('40');
    expect(orbitBand?.getAttribute('stroke-opacity')).toBe('0.46');
    expect(surfaceBand?.getAttribute('stroke-width')).toBe('40');
    expect(surfaceBand?.getAttribute('stroke-opacity')).toBe('0.48');

    expect(screen.getAllByTestId(/^ring-orbital-slot-/)).toHaveLength(4);
    expect(screen.getAllByTestId(/^ring-surface-slot-/)).toHaveLength(5);
    const orbitSlot = screen.getByTestId('ring-orbital-slot-0') as HTMLElement;
    const surfaceSlot = screen.getByTestId('ring-surface-slot-0') as HTMLElement;
    expect(orbitSlot.style.left).toContain('calc(50%');
    expect(orbitSlot.style.left).toContain('px');
    expect(orbitSlot.style.top).toContain('8.9rem');
    expect(orbitSlot.style.left).not.toContain('130px');
    expect(orbitSlot.textContent).toBe('+');
    expect(surfaceSlot.style.left).toContain('calc(50%');
    expect(surfaceSlot.style.left).toContain('px');
    expect(surfaceSlot.style.top).toContain('8.9rem');
    expect(surfaceSlot.style.left).not.toContain('92px');
    expect(surfaceSlot.textContent).toBe('+');
    expect(screen.getByTestId('ring-orbital-slot-3')).toBeTruthy();
    expect(screen.getByTestId('ring-surface-slot-4')).toBeTruthy();
  });

  it('keeps both bands visible but draws no slot icons when calculated counts are zero', () => {
    const { container } = render(
      <BodySlotPlanner
        body={body}
        slotPrediction={{
          ...slotPrediction,
          predicted_orbital_slots: 0,
          predicted_ground_slots: 0,
        }}
        placements={[]}
        projectedPlacements={[]}
        selectedPlacementIndex={null}
        selectedProjectedPlacementIndex={null}
        hasTemplates
        onSelectPlacement={vi.fn()}
        onSelectProjectedPlacement={vi.fn()}
        onAddLaneStructure={vi.fn()}
      />,
    );

    expect(container.querySelector('circle[stroke="#00c8ff"]')).toBeTruthy();
    expect(container.querySelector('circle[stroke="#ff9f1a"]')).toBeTruthy();
    expect(screen.queryByTestId('ring-orbital-slot-0')).toBeNull();
    expect(screen.queryByTestId('ring-surface-slot-0')).toBeNull();
  });

  it('shows existing infrastructure as occupied capacity with explicit confirm and verify labels', () => {
    render(
      <BodySlotPlanner
        body={body}
        slotPrediction={slotPrediction}
        placements={[]}
        projectedPlacements={[]}
        existingOrbital={existingOrbital}
        existingSurface={existingSurface}
        selectedPlacementIndex={null}
        selectedProjectedPlacementIndex={null}
        hasTemplates
        onSelectPlacement={vi.fn()}
        onSelectProjectedPlacement={vi.fn()}
        onAddLaneStructure={vi.fn()}
      />,
    );

    expect(screen.getByTestId('body-slot-trust-summary').textContent).toContain('Existing infrastructure already consumes predicted lane capacity');
    expect(screen.getByText('1 existing orbit')).toBeTruthy();
    expect(screen.getByText('1 existing surface')).toBeTruthy();
    expect(screen.getByTestId('existing-lane-orbital')).toBeTruthy();
    expect(screen.getByTestId('existing-lane-surface')).toBeTruthy();
    expect(screen.getByText('Jameson Orbital / Coriolis / Confirmed')).toBeTruthy();
    expect(screen.getByTitle(/Miller Port.*Verify body match/)).toBeTruthy();
    expect(screen.getAllByTitle('Existing: Jameson Orbital').length).toBeGreaterThan(0);
    expect(screen.getAllByTitle('Existing: Miller Port').length).toBeGreaterThan(0);
    expect(screen.getByText('1/4 occupied (1 existing, 0 planned)')).toBeTruthy();
    expect(screen.getByText('1/5 occupied (1 existing, 0 planned)')).toBeTruthy();
  });
});
