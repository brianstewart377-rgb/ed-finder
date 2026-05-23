import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { FacilityTemplate, SystemBody } from '@/types/api';
import { CanvasStructurePicker } from './CanvasStructurePicker';

const landableBody = {
  id: 1,
  name: 'Body 1',
  body_type: 'Planet',
  subtype: 'Rocky body',
  is_landable: true,
} as SystemBody;

const waterWorld = {
  ...landableBody,
  id: 2,
  name: 'Water World',
  subtype: 'Water world',
  is_water_world: true,
  is_landable: false,
} as SystemBody;

const nonLandableBody = {
  ...landableBody,
  id: 3,
  name: 'High Metal Content Body',
  is_landable: false,
} as SystemBody;

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
    economy: 'Agriculture',
    is_port: false,
    is_support_facility: true,
    allowed_location: 'surface',
    pad_size: 'medium',
    confidence: 'confirmed',
    notes: null,
    yellow_cp_generated: 0,
    green_cp_generated: 1,
    yellow_cp_cost: 0,
    green_cp_cost: 0,
  },
];

describe('CanvasStructurePicker', () => {
  it('shows selected body, lane, compatible count, close control, and selectable templates', () => {
    const onClose = vi.fn();
    const onPickTemplate = vi.fn();

    render(
      <CanvasStructurePicker
        body={landableBody}
        lane="orbital"
        templates={templates}
        templatesLoading={false}
        onClose={onClose}
        onPickTemplate={onPickTemplate}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Body 1' })).toBeTruthy();
    expect(screen.getByText(/Add orbit structure/i)).toBeTruthy();
    expect(screen.getByText(/1 compatible option shown/i)).toBeTruthy();
    expect(screen.getByTestId('canvas-picker-compatibility-summary').textContent).toContain('1 incompatible hidden');
    expect(screen.getByTestId('body-structure-template-orbital_port')).toBeTruthy();
    expect(screen.queryByTestId('body-structure-template-surface_hub')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /Close structure picker/i }));
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: /Add Orbital Port to Body 1/i }));
    expect(onPickTemplate).toHaveBeenCalledWith('orbital_port');
  });

  it('shows a disabled reason for invalid surface lanes', () => {
    render(
      <CanvasStructurePicker
        body={waterWorld}
        lane="surface"
        templates={templates}
        templatesLoading={false}
        onClose={vi.fn()}
        onPickTemplate={vi.fn()}
      />,
    );

    expect(screen.getByText(/Add surface structure/i)).toBeTruthy();
    expect(screen.getByTestId('canvas-picker-disabled-reason').textContent).toContain('Surface limited: water world.');
    expect(screen.queryByTestId('body-structure-template-surface_hub')).toBeNull();
  });

  it('shows a disabled reason for non-landable surface lanes', () => {
    render(
      <CanvasStructurePicker
        body={nonLandableBody}
        lane="surface"
        templates={templates}
        templatesLoading={false}
        onClose={vi.fn()}
        onPickTemplate={vi.fn()}
      />,
    );

    expect(screen.getByTestId('canvas-picker-disabled-reason').textContent).toContain('Surface limited: non-landable body.');
    expect(screen.queryByTestId('body-structure-template-surface_hub')).toBeNull();
  });

  it('shows catalogue loading and disables template selection while templates load', () => {
    render(
      <CanvasStructurePicker
        body={landableBody}
        lane="orbital"
        templates={templates}
        templatesLoading
        onClose={vi.fn()}
        onPickTemplate={vi.fn()}
      />,
    );

    expect(screen.getByTestId('canvas-picker-loading').textContent).toContain('Facility catalogue loading.');
    expect((screen.getByTestId('body-structure-template-orbital_port') as HTMLButtonElement).disabled).toBe(true);
  });

  it('shows an empty state when no templates are compatible with the lane and body', () => {
    render(
      <CanvasStructurePicker
        body={landableBody}
        lane="orbital"
        templates={[templates[1]]}
        templatesLoading={false}
        onClose={vi.fn()}
        onPickTemplate={vi.fn()}
      />,
    );

    expect(screen.getByTestId('canvas-picker-empty-state').textContent).toContain('No compatible structures available for this lane/body.');
  });
});
