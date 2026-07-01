import { describe, expect, it } from 'vitest';

import { R1_ASSESSMENT_FIXTURES, R1_ASSESSMENT_TEMPLATE } from '@/lab/r1-assessment-lab/core/fixtures';
import { evaluateAssessment, normalizeAssessmentResult } from '@/lab/r1-assessment-lab/core/evaluateAssessment';
import type { AssessmentEvaluationInput, ProgrammeTemplate } from '@/lab/r1-assessment-lab/core/types';

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

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
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

  it('rejects invalid exclusive assessment lens runtime shapes', () => {
    expect(() =>
      evaluateAssessment(buildInput('compact_sufficient_case', { lens: 'role' as never })),
    ).toThrow('Assessment evaluation requires a valid assessment lens.');

    expect(() =>
      evaluateAssessment(buildInput('compact_sufficient_case', { lens: { kind: 'unknown' } as never })),
    ).toThrow('Assessment lens must be a role lens or a question lens.');

    expect(() =>
      evaluateAssessment(buildInput('compact_sufficient_case', { lens: { kind: 'role', roleId: '   ' } as never })),
    ).toThrow('Role lens requires a non-empty roleId.');

    expect(() =>
      evaluateAssessment(buildInput('compact_sufficient_case', { lens: { kind: 'question', questionId: '   ' } as never })),
    ).toThrow('Question lens requires a non-empty questionId.');

    expect(() =>
      evaluateAssessment(buildInput('compact_sufficient_case', {
        lens: { kind: 'role', roleId: 'expedition-lead', questionId: 'q1' } as never,
      })),
    ).toThrow('Role lens must not contain questionId.');

    expect(() =>
      evaluateAssessment(buildInput('compact_sufficient_case', {
        lens: { kind: 'question', questionId: 'q1', roleId: 'expedition-lead' } as never,
      })),
    ).toThrow('Question lens must not contain roleId.');
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

  it('rejects invalid runtime carrier modes', () => {
    expect(() =>
      evaluateAssessment(buildInput('compact_sufficient_case', { carrierMode: 'fleet_train' as never })),
    ).toThrow('Unsupported carrier mode: fleet_train');
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

  it('rejects carrier-varying capacity requirements', () => {
    const template = clone(R1_ASSESSMENT_TEMPLATE);
    const fixture = clone(R1_ASSESSMENT_FIXTURES.remote_materials_carrier_case);
    const capacityRequirement = fixture.requirementEvaluations.find((item) => item.requirementId === 'capacity_floor');
    if (!capacityRequirement) throw new Error('capacity fixture requirement missing in test setup');
    capacityRequirement.outcomeByCarrier = {
      no_carrier: 'conditional',
      carrier_available: 'met',
    };

    expect(() =>
      evaluateAssessment(buildInput('remote_materials_carrier_case', { template, fixture, carrierMode: 'compare_both' })),
    ).toThrow(
      'Requirement capacity_floor may vary by carrier only when it is carrier-sensitive logistics and not a shared constraint.',
    );
  });

  it('rejects carrier-varying shared constraints', () => {
    const template: ProgrammeTemplate = clone(R1_ASSESSMENT_TEMPLATE);
    const logisticsRequirement = template.requirements.find((item) => item.id === 'remote_logistics');
    if (!logisticsRequirement) throw new Error('logistics template requirement missing in test setup');
    logisticsRequirement.sharedConstraint = true;

    expect(() =>
      evaluateAssessment(buildInput('remote_materials_carrier_case', { template, carrierMode: 'compare_both' })),
    ).toThrow(
      'Requirement remote_logistics may vary by carrier only when it is carrier-sensitive logistics and not a shared constraint.',
    );
  });

  it('rejects a selected template with a missing fixture requirement evaluation', () => {
    const fixture = clone(R1_ASSESSMENT_FIXTURES.compact_sufficient_case);
    fixture.requirementEvaluations = fixture.requirementEvaluations.filter((item) => item.requirementId !== 'capacity_floor');

    expect(() =>
      evaluateAssessment(buildInput('compact_sufficient_case', { fixture })),
    ).toThrow('Template requirement capacity_floor is missing fixture evaluation.');
  });

  it('rejects duplicate fixture requirement evaluations', () => {
    const fixture = clone(R1_ASSESSMENT_FIXTURES.compact_sufficient_case);
    fixture.requirementEvaluations.push(clone(fixture.requirementEvaluations[0]));

    expect(() =>
      evaluateAssessment(buildInput('compact_sufficient_case', { fixture })),
    ).toThrow('Duplicate fixture evaluation found for requirement foundation_evidence.');
  });

  it('rejects duplicate selected template requirement ids', () => {
    const template = clone(R1_ASSESSMENT_TEMPLATE);
    template.requirements.push(clone(template.requirements[0]));

    expect(() =>
      evaluateAssessment(buildInput('compact_sufficient_case', { template })),
    ).toThrow('Duplicate template requirement id: foundation_evidence');
  });

  it('rejects a blank selected programmeId at runtime', () => {
    const template = clone(R1_ASSESSMENT_TEMPLATE);
    template.programmeId = '   ';

    expect(() =>
      evaluateAssessment(buildInput('compact_sufficient_case', { template })),
    ).toThrow('Selected template requires a non-empty programmeId.');
  });

  it('rejects a blank selected templateId at runtime', () => {
    const template = clone(R1_ASSESSMENT_TEMPLATE);
    template.templateId = '   ';

    expect(() =>
      evaluateAssessment(buildInput('compact_sufficient_case', { template })),
    ).toThrow('Selected template requires a non-empty templateId.');
  });

  it('rejects a blank selected revision at runtime', () => {
    const template = clone(R1_ASSESSMENT_TEMPLATE);
    template.revision = '   ';

    expect(() =>
      evaluateAssessment(buildInput('compact_sufficient_case', { template: template as ProgrammeTemplate })),
    ).toThrow('Selected template requires a non-empty revision.');
  });
});
