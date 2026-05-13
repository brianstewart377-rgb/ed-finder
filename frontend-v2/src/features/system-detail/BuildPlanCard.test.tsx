import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BuildPlanCard } from './BuildPlanCard';
import type { RecommendedBuildPlan } from '@/types/api';

function plan(): RecommendedBuildPlan {
  return {
    id: 'balanced',
    label: 'Balanced',
    summary: 'A balanced plan.',
    complexity: 'moderate',
    confidence: 0.72,
    final_score: 84,
    composition_score: 82,
    buildability_score: 86,
    economy_result: { Refinery: 42, Industrial: 38, Extraction: 8 },
    port_economy_summary: ['Main port economy: Refinery / Industrial'],
    cp_result: {
      yellow_cp_final: 4,
      green_cp_final: 1,
      yellow_cp_generated: 8,
      green_cp_generated: 1,
      yellow_cp_spent: 4,
      green_cp_spent: 0,
      t2_ports: 1,
      t3_ports: 0,
      warnings: [],
    },
    build_order: [],
    strengths: ['Top-two economy stack is protected.'],
    warnings: ['Slot data is estimated.'],
    tradeoffs: ['Moderate CP pressure.'],
    next_actions: [],
    selected_body_id: '1',
    selected_body_name: 'Rocky Prime',
    body_selection_reason: 'Best local refinery body.',
    mechanics_basis: ['Mega Guide body economy inheritance.'],
    economy_caveats: [],
    assumptions: ['Slot prediction is estimated.'],
    regional_role: 'frontier_hub',
    nearest_colony_distance: 74.2,
    archetype_regional_fit: 91,
    regional_rationale: { summary: 'Excellent frontier placement.' },
    decision_explanation: {
      why_this_plan_won: ['This plan ranked highest after transparent penalties.'],
      sensitive_assumptions: ['Slot prediction is estimated.'],
      confidence_summary: 'Medium confidence.',
    },
    rank_breakdown: {
      simulation_score: 46.2,
      economy_stack_score: 20.5,
      buildability_score: 12.9,
      regional_fit_score: 6.4,
      service_score: 0,
      confidence_penalty: 0.3,
      complexity_penalty: 2,
      warning_penalty: 2,
      final_rank_score: 82,
    },
    simulation_request: {
      system_id64: 123,
      target_archetype: 'refinery_industrial',
      placements: [],
    },
    is_default: true,
  };
}

describe('BuildPlanCard explainability', () => {
  it('renders why-this-plan and score breakdown sections', () => {
    render(<BuildPlanCard plan={plan()} onPreview={vi.fn()} />);

    expect(screen.getByText('Why this plan won')).toBeTruthy();
    expect(screen.getByText('Score breakdown')).toBeTruthy();
    expect(screen.getAllByText(/This plan ranked highest/).length).toBeGreaterThan(0);
    expect(screen.getByText('Regional Fit Score')).toBeTruthy();
    expect(screen.queryByText('Service Score')).toBeNull();
    expect(screen.queryByText(/Service Score\s*0/i)).toBeNull();
    expect(screen.getByText(/Service unlocks are shown in Simulation Preview/)).toBeTruthy();
    expect(screen.getByText(/Regional fit is a light adjustment/)).toBeTruthy();
  });
});
