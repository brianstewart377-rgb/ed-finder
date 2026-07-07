import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { FacilityTemplate } from '@/types/api';
import { economyColor } from './economyVisuals';
import { BodyStructureSlot } from './BodyStructureSlot';
import { ProjectedStructureSlot } from './ProjectedStructureSlot';

const template = {
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
} as FacilityTemplate;

describe('structure economy bars', () => {
  it('renders planned structure bars with readable height, central colour, and direct CP tooltip', () => {
    render(
      <BodyStructureSlot
        item={{
          placement: { facility_template_id: 'surface_refinery', local_body_id: '2', build_order: 1 },
          index: 0,
          template,
          lane: 'surface',
        }}
        selected={false}
        onSelect={vi.fn()}
      />,
    );

    const bar = screen.getByTestId('body-structure-economy-micro-bar');
    expect(bar.className).toContain('h-2.5');
    expect(bar.getAttribute('data-economy-color')).toBe(economyColor('Refinery'));
    expect(bar.getAttribute('title')).toContain('Direct facility economy: Refinery');
    expect(bar.getAttribute('title')).toContain('CP generated +550');
  });

  it('renders projected structure bars with projected wording and the same economy colour', () => {
    render(
      <ProjectedStructureSlot
        item={{
          placement: { facility_template_id: 'surface_refinery', local_body_id: '2', build_order: 1 },
          index: 0,
          template,
          lane: 'surface',
        }}
      />,
    );

    const bar = screen.getByTestId('projected-structure-economy-micro-bar');
    expect(bar.className).toContain('h-2.5');
    expect(bar.getAttribute('data-economy-color')).toBe(economyColor('Refinery'));
    expect(bar.getAttribute('title')).toContain('Projected direct facility economy: Refinery');
    expect(bar.getAttribute('title')).toContain('CP generated +550');
  });
});
