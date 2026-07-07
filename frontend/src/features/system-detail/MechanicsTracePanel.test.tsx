import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MechanicsTracePanel } from './SimulationPreview';
import type { SimulateBuildResponse } from '@/types/api';

describe('MechanicsTracePanel', () => {
  it('renders collapsed trace categories without raw JSON', () => {
    const trace: SimulateBuildResponse['mechanics_trace'] = {
      strong_link_effects: [{
        category: 'strong_link_effects',
        label: 'Refinery Hub -> Ocellus',
        description: 'Adds Refinery influence through a strong link.',
        delta: 0.8,
        confidence: 'verified',
        source: 'Frontier strong/weak link rules',
      }],
      weak_link_effects: [],
      economy_sources: [],
      pass_through_effects: [],
      converted_port_effects: [],
      regional_effects: [],
      purity_effects: [],
      contamination_effects: [],
      cp_effects: [],
      service_unlock_effects: [],
      confidence_adjustments: [],
    };

    render(<MechanicsTracePanel trace={trace} />);

    expect(screen.getByTestId('mechanics-trace-accordion')).toBeTruthy();
    expect(screen.getByText('Mechanics Trace')).toBeTruthy();
    expect(screen.getByText('Strong Link Effects')).toBeTruthy();
    expect(screen.getByText(/Adds Refinery influence/)).toBeTruthy();
  });
});
