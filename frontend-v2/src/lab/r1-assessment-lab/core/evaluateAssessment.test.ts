import { describe, expect, it } from 'vitest';

import { R1_ASSESSMENT_FIXTURES, R1_ASSESSMENT_TEMPLATE } from '@/lab/r1-assessment-lab/core/fixtures';
import { evaluateAssessment, normalizeAssessmentResult } from '@/lab/r1-assessment-lab/core/evaluateAssessment';
import type { AssessmentEvaluationInput } from '@/lab/r1-assessment-lab/core/types';

function buildInput(
  fixtureId: keyof typeof R1_ASSESSMENT_FIXTURES,
  overrides: Partial<AssessmentEvaluationInput> = {},
): AssessmentEvaluationInput {
  return {
    fixture: R1_ASSESSMENT_FIXTURES[fixtureId],
    template: R1_ASSESSMENT_TEMPLATE,
    lens: { kind: 'role', roleId: 'expedition-lead' },
    carrierMode: 'no_carrier',
    ...overrides,
  };
}

function collectForbiddenKeys(value: unknown, found = new Set<string>()): Set<string> {
  if (!value || typeof value !== 'object') return found;
  if (Array.isArray(value)) {
    for (const item of value) collectForbiddenKeys(item, found);
    return found;
  }
  for (const [key, nested] of Object.entries(value)) {
    if (['score', 'rank', 'best', 'plan_fit'].includes(key)) {
      found.add(key);
    }
    collectForbiddenKeys(nested, found);
  }
  return found;
}

describe('evaluateAssessment', () => {
  it('returns supported for the compact sufficient case', () => {
    const result = evaluateAssessment(buildInput('compact_sufficient_case'));
    expect(result.scenarioResults).toHaveLength(1);
    expect(result.scenarioResults[0].state).toBe('supported');
  });

  it('returns not_assessable with explicit missing evidence for the incomplete evidence case', () => {
    const result = evaluateAssessment(buildInput('incomplete_evidence_case'));
    expect(result.scenarioResults[0].state).toBe('not_assessable');
    expect(result.scenarioResults[0].requirementResults.find((item) => item.requirementId === 'foundation_evidence')?.missingEvidenceIds)
      .toEqual(['incomplete-foundation']);
  });

  it('returns not_assessable with explicit contradictory evidence for the contradictory allocation case', () => {
    const result = evaluateAssessment(buildInput('contradictory_allocation_case'));
    expect(result.scenarioResults[0].state).toBe('not_assessable');
    expect(result.scenarioResults[0].requirementResults.find((item) => item.requirementId === 'allocation_consistency')?.contradictoryEvidenceIds)
      .toEqual(['contradictory-allocation']);
  });

  it('returns not_supported for the fake flexibility case', () => {
    const result = evaluateAssessment(buildInput('fake_flexibility_case'));
    expect(result.scenarioResults[0].state).toBe('not_supported');
  });

  it('returns conditionally_supported for the remote materials case without a carrier', () => {
    const result = evaluateAssessment(buildInput('remote_materials_carrier_case', { carrierMode: 'no_carrier' }));
    expect(result.scenarioResults[0].state).toBe('conditionally_supported');
  });

  it('returns supported for the remote materials case with a carrier available', () => {
    const result = evaluateAssessment(buildInput('remote_materials_carrier_case', { carrierMode: 'carrier_available' }));
    expect(result.scenarioResults[0].state).toBe('supported');
  });

  it('does not expose a universal score, rank, best marker, or plan fit', () => {
    const result = evaluateAssessment(buildInput('compact_sufficient_case'));
    expect([...collectForbiddenKeys(result)]).toEqual([]);
  });

  it('requires an explicit assessment lens', () => {
    expect(() =>
      evaluateAssessment(buildInput('compact_sufficient_case', { lens: undefined as never })),
    ).toThrow('Assessment evaluation requires a valid assessment lens.');
  });

  it('is deterministic for identical input and stable JSON normalization', () => {
    const input = buildInput('remote_materials_carrier_case', { carrierMode: 'compare_both' });
    const resultA = evaluateAssessment(input);
    const resultB = evaluateAssessment(input);
    expect(resultA).toEqual(resultB);
    expect(normalizeAssessmentResult(resultA)).toBe(normalizeAssessmentResult(resultB));
  });

  it('does not mutate fixture input or template input', () => {
    const input = buildInput('remote_materials_carrier_case', { carrierMode: 'compare_both' });
    const before = JSON.stringify(input);
    evaluateAssessment(input);
    expect(JSON.stringify(input)).toBe(before);
  });

  it('returns exactly one scenario result for no_carrier and carrier_available', () => {
    expect(evaluateAssessment(buildInput('compact_sufficient_case', { carrierMode: 'no_carrier' })).scenarioResults)
      .toHaveLength(1);
    expect(evaluateAssessment(buildInput('compact_sufficient_case', { carrierMode: 'carrier_available' })).scenarioResults)
      .toHaveLength(1);
  });

  it('returns compare_both scenarios in the required order', () => {
    const result = evaluateAssessment(buildInput('remote_materials_carrier_case', { carrierMode: 'compare_both' }));
    expect(result.scenarioResults.map((scenario) => scenario.carrierMode)).toEqual([
      'no_carrier',
      'carrier_available',
    ]);
  });

  it('keeps frozen evidence and provenance identical across carrier scenarios while changing only logistics-sensitive outcomes', () => {
    const result = evaluateAssessment(buildInput('remote_materials_carrier_case', { carrierMode: 'compare_both' }));
    expect(result.scenarioResults).toHaveLength(2);
    const [noCarrier, carrierAvailable] = result.scenarioResults;

    expect(noCarrier.frozenEvidence).toEqual(carrierAvailable.frozenEvidence);

    const changedRequirementIds = noCarrier.requirementResults
      .filter((result, index) => JSON.stringify(result) !== JSON.stringify(carrierAvailable.requirementResults[index]))
      .map((result) => result.requirementId);
    expect(changedRequirementIds).toEqual(['remote_logistics']);
    expect(noCarrier.requirementResults.find((result) => result.requirementId === 'remote_logistics')?.carrierLogisticsAffected)
      .toBe(true);
    expect(carrierAvailable.requirementResults.find((result) => result.requirementId === 'remote_logistics')?.carrierLogisticsAffected)
      .toBe(true);
  });
});
