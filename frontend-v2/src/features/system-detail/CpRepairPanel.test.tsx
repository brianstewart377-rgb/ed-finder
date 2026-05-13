import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { CpRepairPanel } from './SimulationPreview';
import type { SimulateBuildResponse } from '@/types/api';

describe('CpRepairPanel', () => {
  it('renders a high-priority CP repair suggestion without raw JSON', () => {
    const suggestions: SimulateBuildResponse['cp_repair_suggestions'] = [{
      type: 'move_cp_generator_earlier',
      severity: 'high',
      summary: 'Move Refinery Hub before Ocellus Starport',
      reason: 'Yellow CP goes negative at step 3.',
      affected_steps: [3, 5],
      expected_effect: 'Generating CP before the expensive port should reduce the temporary deficit.',
      action: 'Move Refinery Hub from step 5 to step 2.',
      confidence: 'inferred',
      caveats: ['This is a local repair suggestion, not a full optimiser result.'],
    }];

    render(<CpRepairPanel suggestions={suggestions} />);

    expect(screen.getByText('CP Repair Suggestions')).toBeTruthy();
    expect(screen.getByText('Move Refinery Hub before Ocellus Starport')).toBeTruthy();
    expect(screen.getByText('High priority')).toBeTruthy();
    expect(screen.getByText(/Yellow CP goes negative/)).toBeTruthy();
    expect(screen.queryByText(/"type"/)).toBeNull();
  });

  it('renders nothing for an empty suggestion list', () => {
    const { container } = render(<CpRepairPanel suggestions={[]} />);
    expect(container.textContent).toBe('');
  });
});
