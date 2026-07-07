import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ObservedVsPredictedPanel } from './SimulationPreview';
import type { SimulateBuildResponse } from '@/types/api';

describe('ObservedVsPredictedPanel', () => {
  it('renders predicted-only state when no observations are attached', () => {
    const summary: SimulateBuildResponse['observation_summary'] = {
      status: 'predicted_only',
      observed_facts_count: 0,
      confirmed_count: 0,
      mismatch_count: 0,
      observed_only_count: 0,
      predicted_only_count: 0,
      unknown_count: 0,
      confidence_impact: 'none',
      summary: 'No observed player data is attached to this simulation yet. Results are predicted from current mechanics rules.',
    };

    render(<ObservedVsPredictedPanel summary={summary} diffs={[]} />);

    expect(screen.getByText('Observed vs Predicted')).toBeTruthy();
    expect(screen.getByText(/No observed player data/)).toBeTruthy();
    expect(screen.getAllByText(/Results are predicted from current mechanics rules/).length).toBeGreaterThan(0);
  });

  it('renders mismatch counts and top diffs when observations exist', () => {
    const summary: SimulateBuildResponse['observation_summary'] = {
      status: 'has_observations',
      observed_facts_count: 1,
      confirmed_count: 0,
      mismatch_count: 1,
      observed_only_count: 0,
      predicted_only_count: 0,
      unknown_count: 0,
      confidence_impact: 'review_required',
      summary: '1 prediction differs from observed data and should be reviewed.',
    };
    const diffs: SimulateBuildResponse['prediction_observation_diffs'] = [{
      area: 'slots',
      subject_id: 'orbital_slots',
      subject_type: 'system',
      predicted_value: 6,
      observed_value: 5,
      status: 'mismatch',
      severity: 'medium',
      confidence: 'observed',
      reason: 'Observed orbital slot count differs from predicted slot count.',
      recommended_action: 'Review slot prediction rules for this body type.',
      source_type: 'test_fixture',
    }];

    render(<ObservedVsPredictedPanel summary={summary} diffs={diffs} />);

    expect(screen.getByText('1 mismatch')).toBeTruthy();
    expect(screen.getByText(/Observed orbital slot count differs/)).toBeTruthy();
    expect(screen.getByText(/Review slot prediction rules/)).toBeTruthy();
  });
});
