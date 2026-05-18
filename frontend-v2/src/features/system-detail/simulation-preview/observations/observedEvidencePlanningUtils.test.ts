import { describe, expect, it } from 'vitest';
import type { ObservedFact } from '@/types/api';
import {
  categorizeObservedEvidence,
  summarizeObservedEvidenceCategories,
} from './observedEvidencePlanningUtils';

function fact(overrides: Partial<ObservedFact> = {}): ObservedFact {
  return {
    observation_id: 'obs_a',
    system_id64: 123,
    created_at: '2026-05-14T13:00:00+00:00',
    updated_at: null,
    source: 'manual',
    fact_type: 'note',
    subject_type: 'system',
    subject_id: null,
    status: 'observed_present',
    observed_value: undefined,
    expected_value: undefined,
    confidence: 'medium',
    notes: null,
    build_fingerprint: null,
    simulation_fingerprint: null,
    target_archetype: null,
    facility_template_id: null,
    local_body_id: null,
    service_id: null,
    economy: null,
    tags: [],
    metadata: {},
    ...overrides,
  };
}

describe('observedEvidencePlanningUtils', () => {
  it('categorizes Architect and primary-port notes without a backend taxonomy', () => {
    expect(
      categorizeObservedEvidence(
        fact({ notes: 'Architect Mode shows the primary-port flag on the inner orbital slot.' }),
      ),
    ).toBe('architect_primary_port');
  });

  it('categorizes existing observed fact types into planning categories', () => {
    expect(categorizeObservedEvidence(fact({ fact_type: 'facility_state', facility_template_id: 'orbital_port_a' }))).toBe('structure_built');
    expect(categorizeObservedEvidence(fact({ fact_type: 'build_outcome', observed_value: 'completed' }))).toBe('structure_built');
    expect(categorizeObservedEvidence(fact({ fact_type: 'economy_presence', economy: 'Agriculture' }))).toBe('economy');
    expect(categorizeObservedEvidence(fact({ fact_type: 'service_presence', service_id: 'market' }))).toBe('service_population_security');
    expect(categorizeObservedEvidence(fact({ subject_type: 'body', local_body_id: 'A 2' }))).toBe('body_slot');
  });

  it('summarizes category counts while keeping zero-count categories visible', () => {
    const summary = summarizeObservedEvidenceCategories([
      fact({ notes: 'Primary port flag observed in Architect Mode.' }),
      fact({ fact_type: 'facility_state', facility_template_id: 'tourism_support_a' }),
      fact({ fact_type: 'economy_presence', economy: 'Tourism' }),
    ]);

    expect(summary.find((item) => item.id === 'architect_primary_port')?.count).toBe(1);
    expect(summary.find((item) => item.id === 'structure_built')?.count).toBe(1);
    expect(summary.find((item) => item.id === 'economy')?.count).toBe(1);
    expect(summary.find((item) => item.id === 'service_population_security')?.count).toBe(0);
  });
});
