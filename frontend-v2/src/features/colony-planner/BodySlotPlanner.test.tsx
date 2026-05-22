import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { BodySlotPrediction, SystemBody } from '@/types/api';
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
    expect(orbitSlot.textContent).toBe('1');
    expect(surfaceSlot.style.left).toContain('calc(50%');
    expect(surfaceSlot.style.left).toContain('px');
    expect(surfaceSlot.style.top).toContain('8.9rem');
    expect(surfaceSlot.style.left).not.toContain('92px');
    expect(surfaceSlot.textContent).toBe('1');
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
});
