import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DataConfidencePanel } from './SimulationPreview';
import type { SimulateBuildResponse } from '@/types/api';

function result(): SimulateBuildResponse {
  return {
    system_id64: 123,
    mechanics_version: 'colonisation-engine-v2.1',
    target_archetype: 'refinery_industrial',
    final_score: 80,
    composition_score: 80,
    buildability_score: 80,
    build_complexity: 'moderate',
    confidence: 0.7,
    cp: {
      yellow_cp_final: 0,
      green_cp_final: 0,
      yellow_cp_generated: 0,
      green_cp_generated: 0,
      yellow_cp_spent: 0,
      green_cp_spent: 0,
      t2_ports: 0,
      t3_ports: 0,
      warnings: [],
    },
    cp_timeline: [],
    economy_composition: {},
    economy_order: [],
    economy_stack: {},
    port_economy_states: [],
    influence_ledger: [],
    inherited_economies: [],
    topology: {},
    services: {},
    port_service_states: [],
    service_unlock_ledger: [],
    data_quality: {
      slots: 'estimated',
      facility_catalogue: 'community_observed',
      topology: 'inferred',
    },
    confidence_signals: [{
      area: 'slots',
      level: 'estimated',
      reason: 'Slot data is estimated from body scan data.',
      impact: -0.08,
    }],
    mechanics_trace: {},
    top_two_alignment: 'none',
    contamination_risk: 'low',
    warnings: [],
    strengths: [],
    recommendations: [],
    mechanics_notes: [],
    links: { strong_links: [], weak_links: [] },
  };
}

describe('DataConfidencePanel', () => {
  it('renders standard confidence labels', () => {
    render(<DataConfidencePanel result={result()} />);

    expect(screen.getByText('Data Confidence')).toBeTruthy();
    expect(screen.getByText(/Slots: Estimated/)).toBeTruthy();
    expect(screen.getByText(/Facility Catalogue: Community observed/)).toBeTruthy();
    expect(screen.getByText(/Slot data is estimated/)).toBeTruthy();
  });
});
