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
  it('renders vivid orbit/surface bands with slot tokens centered from polar coordinates', () => {
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
    expect(orbitBand?.getAttribute('stroke-width')).toBe('24');
    expect(orbitBand?.getAttribute('stroke-opacity')).toBe('0.46');
    expect(surfaceBand?.getAttribute('stroke-width')).toBe('16');
    expect(surfaceBand?.getAttribute('stroke-opacity')).toBe('0.48');

    const orbitSlot = screen.getByTestId('ring-orbital-slot-0') as HTMLElement;
    const surfaceSlot = screen.getByTestId('ring-surface-slot-0') as HTMLElement;
    expect(orbitSlot.style.left).toContain('calc(50%');
    expect(orbitSlot.style.left).toContain('px');
    expect(orbitSlot.style.top).toContain('8.9rem');
    expect(orbitSlot.style.top).toContain('px');
    expect(orbitSlot.style.left).not.toContain('130px');
    expect(surfaceSlot.style.left).toContain('calc(50%');
    expect(surfaceSlot.style.left).toContain('px');
    expect(surfaceSlot.style.top).toContain('8.9rem');
    expect(surfaceSlot.style.top).toContain('px');
    expect(surfaceSlot.style.left).not.toContain('92px');
    expect(screen.getByTestId('ring-orbital-slot-3')).toBeTruthy();
    expect(screen.getByTestId('ring-surface-slot-4')).toBeTruthy();
  });
});
