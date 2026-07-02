import { describe, expect, it } from 'vitest';

import { R1_ASSESSMENT_FIXTURES, R1_ASSESSMENT_TEMPLATE } from '@/lab/r1-assessment-lab/core/fixtures';
import { evaluateAssessment } from '@/lab/r1-assessment-lab/core/evaluateAssessment';
import { evaluatePlanFit } from '@/lab/r1-assessment-lab/core/evaluatePlanFit';
import type {
  PlanFitEvaluationResult,
  PlanFitScenarioResult,
} from '@/lab/r1-assessment-lab/core/planFitTypes';
import { FIXED_STRATEGY_FIXTURES, validateStrategyFixtures } from '@/lab/r1-assessment-lab/core/strategyFixtures';
import type {
  AssessmentEvaluationInput,
  AssessmentEvaluationResult,
  CarrierMode,
} from '@/lab/r1-assessment-lab/core/types';

function buildAssessmentInput(
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

function buildAcceptedAssessmentResult(
  fixtureId: keyof typeof R1_ASSESSMENT_FIXTURES,
  carrierMode: CarrierMode = 'no_carrier',
  overrides: Partial<AssessmentEvaluationInput> = {},
): AssessmentEvaluationResult {
  return evaluateAssessment(buildAssessmentInput(fixtureId, { carrierMode, ...overrides }));
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function scenario(result: PlanFitEvaluationResult, carrierMode: 'no_carrier' | 'carrier_available'): PlanFitScenarioResult {
  const match = result.scenarioResults.find((item) => item.carrierMode === carrierMode);
  if (!match) {
    throw new Error(`Scenario ${carrierMode} missing in test setup`);
  }
  return match;
}

function collectForbiddenKeys(value: unknown, found = new Set<string>()): Set<string> {
  if (!value || typeof value !== 'object') return found;
  if (Array.isArray(value)) {
    for (const item of value) collectForbiddenKeys(item, found);
    return found;
  }
  for (const [key, nested] of Object.entries(value)) {
    if (['score', 'rank', 'best', 'recommend', 'recommendation', 'preference', 'winner', 'desirability'].includes(key)) {
      found.add(key);
    }
    collectForbiddenKeys(nested, found);
  }
  return found;
}

function assertDeepFrozen(value: unknown) {
  if (!value || typeof value !== 'object') return;
  expect(Object.isFrozen(value)).toBe(true);
  if (Array.isArray(value)) {
    for (const item of value) assertDeepFrozen(item);
    return;
  }
  for (const nested of Object.values(value)) {
    assertDeepFrozen(nested);
  }
}

describe('strategyFixtures', () => {
  it('contains exactly the two approved fixed strategy records with exact fields', () => {
    expect(FIXED_STRATEGY_FIXTURES).toEqual([
      {
        fixtureKey: 'baseline_local_strategy',
        strategyId: 'baseline_local_strategy',
        strategyRevision: 'v1',
        label: 'Baseline local strategy',
        compatibility: {
          programmeId: 'r1_assessment_programme',
          templateId: 'core_assessment_template',
          templateRevision: 'r1-contract-v1',
        },
        provenance: {
          sourceKind: 'fixture',
          fixtureId: 'baseline_local_strategy',
          fixtureRevision: 'v1',
        },
        requiredAssessmentRequirementIds: [
          'foundation_evidence',
          'allocation_consistency',
          'capacity_floor',
        ],
        logisticsSensitiveRequirementIds: [],
      },
      {
        fixtureKey: 'remote_logistics_strategy',
        strategyId: 'remote_logistics_strategy',
        strategyRevision: 'v1',
        label: 'Remote logistics strategy',
        compatibility: {
          programmeId: 'r1_assessment_programme',
          templateId: 'core_assessment_template',
          templateRevision: 'r1-contract-v1',
        },
        provenance: {
          sourceKind: 'fixture',
          fixtureId: 'remote_logistics_strategy',
          fixtureRevision: 'v1',
        },
        requiredAssessmentRequirementIds: [
          'foundation_evidence',
          'allocation_consistency',
          'capacity_floor',
          'remote_logistics',
        ],
        logisticsSensitiveRequirementIds: [
          'remote_logistics',
        ],
      },
    ]);
    assertDeepFrozen(FIXED_STRATEGY_FIXTURES);
  });

  it('rejects duplicate strategy ids', () => {
    const fixtures = clone(FIXED_STRATEGY_FIXTURES);
    fixtures[1].strategyId = fixtures[0].strategyId;
    expect(() => validateStrategyFixtures(fixtures)).toThrow('Duplicate strategy id: baseline_local_strategy');
  });

  it('rejects duplicate fixture keys', () => {
    const fixtures = clone(FIXED_STRATEGY_FIXTURES);
    fixtures[1].fixtureKey = fixtures[0].fixtureKey;
    fixtures[1].strategyId = 'remote_logistics_strategy_variant';
    expect(() => validateStrategyFixtures(fixtures)).toThrow('Duplicate strategy fixture key: baseline_local_strategy');
  });

  it('rejects invalid compatibility tuples before output', () => {
    const fixtures = clone(FIXED_STRATEGY_FIXTURES);
    fixtures[0].compatibility.templateRevision = 'wrong-revision';
    expect(() => validateStrategyFixtures(fixtures)).toThrow(
      'Strategy baseline_local_strategy compatibility tuple does not match the accepted template.',
    );
  });

  it('rejects unknown required requirement ids', () => {
    const fixtures = clone(FIXED_STRATEGY_FIXTURES);
    fixtures[0].requiredAssessmentRequirementIds.push('unknown_requirement');
    expect(() => validateStrategyFixtures(fixtures)).toThrow(
      'Strategy baseline_local_strategy references unknown required assessment requirement id: unknown_requirement',
    );
  });

  it('rejects invalid logistics-sensitive declarations for capacity, non-logistics, carrier-insensitive, and shared requirements', () => {
    for (const invalidRequirementId of ['capacity_floor', 'foundation_evidence', 'allocation_consistency']) {
      const fixtures = clone(FIXED_STRATEGY_FIXTURES);
      fixtures[0].logisticsSensitiveRequirementIds = [invalidRequirementId];
      expect(() => validateStrategyFixtures(fixtures)).toThrow(
        `Strategy baseline_local_strategy declares invalid logistics-sensitive requirement ${invalidRequirementId}.`,
      );
    }
  });
});

describe('evaluatePlanFit', () => {
  it('rejects a raw fixture-shaped object instead of an accepted assessment result', () => {
    expect(() =>
      evaluatePlanFit(R1_ASSESSMENT_FIXTURES.compact_sufficient_case as unknown as AssessmentEvaluationResult, 'baseline_local_strategy'),
    ).toThrow('Plan Fit evaluation requires an AssessmentEvaluationResult input.');
  });

  it('rejects missing or unknown selected strategy ids', () => {
    const assessmentResult = buildAcceptedAssessmentResult('compact_sufficient_case');

    expect(() => evaluatePlanFit(assessmentResult, '')).toThrow('Plan Fit evaluation requires a non-empty selectedStrategyId.');
    expect(() => evaluatePlanFit(assessmentResult, 'unknown_strategy')).toThrow('Unknown selected strategy id: unknown_strategy');
  });

  it('rejects malformed context, invalid lens, invalid carrier mode, invalid scenario ordering/count, duplicate scenarios, and malformed requirement structures', () => {
    const assessmentResult = buildAcceptedAssessmentResult('compact_sufficient_case', 'compare_both');

    const malformedProgramme = clone(assessmentResult);
    malformedProgramme.context.programmeId = ' ';
    expect(() => evaluatePlanFit(malformedProgramme, 'baseline_local_strategy')).toThrow(
      'Plan Fit evaluation requires a non-empty programmeId.',
    );

    const malformedLens = clone(assessmentResult);
    malformedLens.context.lens = { kind: 'role', roleId: 'expedition-lead', questionId: 'q1' } as never;
    expect(() => evaluatePlanFit(malformedLens, 'baseline_local_strategy')).toThrow(
      'Plan Fit role lens must not contain questionId.',
    );

    const malformedCarrierMode = clone(assessmentResult);
    malformedCarrierMode.context.carrierMode = 'fleet_train' as CarrierMode;
    expect(() => evaluatePlanFit(malformedCarrierMode, 'baseline_local_strategy')).toThrow(
      'Unsupported Plan Fit carrier mode: fleet_train',
    );

    const malformedScenarioOrder = clone(assessmentResult);
    malformedScenarioOrder.scenarioResults.reverse();
    expect(() => evaluatePlanFit(malformedScenarioOrder, 'baseline_local_strategy')).toThrow(
      'Plan Fit scenario order must match no_carrier, carrier_available.',
    );

    const duplicateScenario = clone(assessmentResult);
    duplicateScenario.scenarioResults[1].carrierMode = 'no_carrier';
    expect(() => evaluatePlanFit(duplicateScenario, 'baseline_local_strategy')).toThrow(
      'Duplicate scenario carrier mode no_carrier in Plan Fit input.',
    );

    const missingRequirement = clone(assessmentResult);
    missingRequirement.scenarioResults[0].requirementResults = missingRequirement.scenarioResults[0].requirementResults.filter(
      (item) => item.requirementId !== 'capacity_floor',
    );
    expect(() => evaluatePlanFit(missingRequirement, 'baseline_local_strategy')).toThrow(
      'Scenario no_carrier must contain every accepted template requirement exactly once.',
    );

    const duplicateRequirement = clone(assessmentResult);
    duplicateRequirement.scenarioResults[0].requirementResults.push(clone(duplicateRequirement.scenarioResults[0].requirementResults[0]));
    expect(() => evaluatePlanFit(duplicateRequirement, 'baseline_local_strategy')).toThrow(
      /Duplicate requirement result id .* in scenario no_carrier\./,
    );

    const unknownRequirement = clone(assessmentResult);
    unknownRequirement.scenarioResults[0].requirementResults[0].requirementId = 'unknown_requirement';
    expect(() => evaluatePlanFit(unknownRequirement, 'baseline_local_strategy')).toThrow(
      'Unknown requirement result id unknown_requirement in scenario no_carrier.',
    );

    const nonBooleanCarrierFlag = clone(assessmentResult);
    nonBooleanCarrierFlag.scenarioResults[0].requirementResults[0].carrierLogisticsAffected = 'true' as never;
    expect(() => evaluatePlanFit(nonBooleanCarrierFlag, 'baseline_local_strategy')).toThrow(
      /Requirement .* in scenario no_carrier requires boolean carrierLogisticsAffected\./,
    );
  });

  it('rejects non-not_assessable scenarios containing unknown or contradictory requirement outcomes', () => {
    const supportedWithUnknown = clone(buildAcceptedAssessmentResult('compact_sufficient_case'));
    supportedWithUnknown.scenarioResults[0].requirementResults[0].outcome = 'unknown';
    expect(() => evaluatePlanFit(supportedWithUnknown, 'baseline_local_strategy')).toThrow(
      'Scenario no_carrier is structurally inconsistent: non-not_assessable state cannot contain unknown or contradictory requirement outcomes.',
    );

    const supportedWithContradiction = clone(buildAcceptedAssessmentResult('compact_sufficient_case'));
    supportedWithContradiction.scenarioResults[0].requirementResults[0].outcome = 'contradictory';
    expect(() => evaluatePlanFit(supportedWithContradiction, 'baseline_local_strategy')).toThrow(
      'Scenario no_carrier is structurally inconsistent: non-not_assessable state cannot contain unknown or contradictory requirement outcomes.',
    );
  });

  it('returns supported compact baseline as provisional_plan_fit with no dependency reasons', () => {
    const result = evaluatePlanFit(buildAcceptedAssessmentResult('compact_sufficient_case'), 'baseline_local_strategy');
    expect(result.context).toEqual({
      programmeId: 'r1_assessment_programme',
      templateId: 'core_assessment_template',
      templateRevision: 'r1-contract-v1',
      lens: { kind: 'role', roleId: 'expedition-lead' },
      originalCarrierMode: 'no_carrier',
      selectedStrategyId: 'baseline_local_strategy',
      selectedStrategyRevision: 'v1',
    });
    expect(result.scenarioResults).toHaveLength(1);
    expect(result.scenarioResults[0]).toMatchObject({
      carrierMode: 'no_carrier',
      assessmentState: 'supported',
      planFitState: 'provisional_plan_fit',
      selectedStrategyId: 'baseline_local_strategy',
      selectedStrategyRevision: 'v1',
      selectedStrategyProvenance: {
        sourceKind: 'fixture',
        fixtureId: 'baseline_local_strategy',
        fixtureRevision: 'v1',
      },
    });
    expect(result.scenarioResults[0].reasons).toEqual([]);
  });

  it('returns not_assessable as no_plan_fit with exactly gate:not_assessable and no dependency reasons', () => {
    const result = evaluatePlanFit(buildAcceptedAssessmentResult('incomplete_evidence_case'), 'baseline_local_strategy');
    expect(result.scenarioResults[0].assessmentState).toBe('not_assessable');
    expect(result.scenarioResults[0].planFitState).toBe('no_plan_fit');
    expect(result.scenarioResults[0].reasons).toEqual([
      {
        id: 'gate:not_assessable',
        kind: 'assessment_state_gate',
        summary: 'Assessment state is not assessable.',
        blocking: true,
        relatedRequirementIds: [],
        relatedEvidenceIds: [],
      },
    ]);
  });

  it('returns not_supported as blocked_plan_fit with gate first and all applicable selected dependency reasons after it', () => {
    const result = evaluatePlanFit(buildAcceptedAssessmentResult('fake_flexibility_case'), 'baseline_local_strategy');
    expect(result.scenarioResults[0].assessmentState).toBe('not_supported');
    expect(result.scenarioResults[0].planFitState).toBe('blocked_plan_fit');
    expect(result.scenarioResults[0].reasons).toEqual([
      {
        id: 'gate:not_supported',
        kind: 'assessment_state_gate',
        summary: 'Assessment state is not supported.',
        blocking: true,
        relatedRequirementIds: [],
        relatedEvidenceIds: [],
      },
      {
        id: 'dependency:capacity_floor',
        kind: 'strategy_dependency',
        summary: 'Selected strategy dependency capacity_floor is unmet.',
        blocking: true,
        relatedRequirementIds: ['capacity_floor'],
        relatedEvidenceIds: ['flex-capacity'],
      },
    ]);
  });

  it('maps conditional logistics and non-logistics dependencies and unmet dependencies through the exact reason rules', () => {
    const logisticsResult = evaluatePlanFit(
      buildAcceptedAssessmentResult('remote_materials_carrier_case', 'no_carrier'),
      'remote_logistics_strategy',
    );
    expect(logisticsResult.scenarioResults[0].reasons).toEqual([
      {
        id: 'dependency:remote_logistics',
        kind: 'logistics_dependency',
        summary: 'Selected strategy dependency remote_logistics remains conditionally satisfied.',
        blocking: false,
        relatedRequirementIds: ['remote_logistics'],
        relatedEvidenceIds: ['remote-logistics-evidence'],
      },
    ]);

    const nonLogisticsAssessment = clone(buildAcceptedAssessmentResult('compact_sufficient_case'));
    nonLogisticsAssessment.scenarioResults[0].state = 'conditionally_supported';
    nonLogisticsAssessment.scenarioResults[0].requirementResults.find((item) => item.requirementId === 'capacity_floor')!.outcome = 'conditional';
    const nonLogisticsResult = evaluatePlanFit(nonLogisticsAssessment, 'baseline_local_strategy');
    expect(nonLogisticsResult.scenarioResults[0].reasons).toEqual([
      {
        id: 'dependency:capacity_floor',
        kind: 'strategy_dependency',
        summary: 'Selected strategy dependency capacity_floor remains unresolved.',
        blocking: false,
        relatedRequirementIds: ['capacity_floor'],
        relatedEvidenceIds: ['compact-capacity'],
      },
    ]);

    const unmetResult = evaluatePlanFit(buildAcceptedAssessmentResult('fake_flexibility_case'), 'baseline_local_strategy');
    expect(unmetResult.scenarioResults[0].reasons[1]).toEqual({
      id: 'dependency:capacity_floor',
      kind: 'strategy_dependency',
      summary: 'Selected strategy dependency capacity_floor is unmet.',
      blocking: true,
      relatedRequirementIds: ['capacity_floor'],
      relatedEvidenceIds: ['flex-capacity'],
    });
  });

  it('preserves the exact remote compare_both order, scenario states, Plan Fit states, and permitted reason difference', () => {
    const result = evaluatePlanFit(
      buildAcceptedAssessmentResult('remote_materials_carrier_case', 'compare_both'),
      'remote_logistics_strategy',
    );

    expect(result.scenarioResults.map((item) => item.carrierMode)).toEqual(['no_carrier', 'carrier_available']);
    expect(result.scenarioResults.map((item) => item.assessmentState)).toEqual(['conditionally_supported', 'supported']);
    expect(result.scenarioResults.map((item) => item.planFitState)).toEqual(['provisional_plan_fit', 'provisional_plan_fit']);
    expect(scenario(result, 'no_carrier').reasons.map((reason) => reason.id)).toEqual(['dependency:remote_logistics']);
    expect(scenario(result, 'carrier_available').reasons).toEqual([]);
  });

  it('returns both contradictory compare_both scenarios as no_plan_fit and carrier cannot repair contradiction', () => {
    const result = evaluatePlanFit(
      buildAcceptedAssessmentResult('contradictory_allocation_case', 'compare_both'),
      'baseline_local_strategy',
    );
    expect(result.scenarioResults).toHaveLength(2);
    expect(result.scenarioResults.map((item) => item.planFitState)).toEqual(['no_plan_fit', 'no_plan_fit']);
    expect(result.scenarioResults.every((item) => item.reasons.length === 1 && item.reasons[0].id === 'gate:not_assessable')).toBe(true);
  });

  it('preserves not_supported across compare_both and carrier cannot turn it provisional', () => {
    const result = evaluatePlanFit(
      buildAcceptedAssessmentResult('fake_flexibility_case', 'compare_both'),
      'baseline_local_strategy',
    );
    expect(result.scenarioResults.map((item) => item.assessmentState)).toEqual(['not_supported', 'not_supported']);
    expect(result.scenarioResults.map((item) => item.planFitState)).toEqual(['blocked_plan_fit', 'blocked_plan_fit']);
  });

  it('rejects compare_both when a selected dependency changes outcome without logistics-sensitive declaration', () => {
    const capacityVariance = clone(buildAcceptedAssessmentResult('compact_sufficient_case', 'compare_both'));
    capacityVariance.scenarioResults[1].state = 'conditionally_supported';
    capacityVariance.scenarioResults[1].requirementResults.find((item) => item.requirementId === 'capacity_floor')!.outcome = 'conditional';
    expect(() => evaluatePlanFit(capacityVariance, 'baseline_local_strategy')).toThrow(
      'Selected strategy dependency capacity_floor varies across compare_both without logistics-sensitive declaration.',
    );

    const sharedConstraintVariance = clone(buildAcceptedAssessmentResult('compact_sufficient_case', 'compare_both'));
    sharedConstraintVariance.scenarioResults[1].state = 'conditionally_supported';
    sharedConstraintVariance.scenarioResults[1].requirementResults.find((item) => item.requirementId === 'allocation_consistency')!.outcome = 'conditional';
    expect(() => evaluatePlanFit(sharedConstraintVariance, 'baseline_local_strategy')).toThrow(
      'Selected strategy dependency allocation_consistency varies across compare_both without logistics-sensitive declaration.',
    );
  });

  it('changes only the copied output context lens when only the assessment lens changes', () => {
    const roleAssessment = buildAcceptedAssessmentResult('remote_materials_carrier_case', 'compare_both');
    const questionAssessment = clone(roleAssessment);
    questionAssessment.context.lens = { kind: 'question', questionId: 'carrier-sensitivity-check' };

    const roleResult = evaluatePlanFit(roleAssessment, 'remote_logistics_strategy');
    const questionResult = evaluatePlanFit(questionAssessment, 'remote_logistics_strategy');

    expect(roleResult.context.lens).toEqual({ kind: 'role', roleId: 'expedition-lead' });
    expect(questionResult.context.lens).toEqual({ kind: 'question', questionId: 'carrier-sensitivity-check' });
    expect(roleResult.scenarioResults).toEqual(questionResult.scenarioResults);
  });

  it('is deterministic, deeply immutable, and does not mutate inputs, fixed strategy fixtures, or earlier outputs', () => {
    const assessmentResult = buildAcceptedAssessmentResult('remote_materials_carrier_case', 'compare_both');
    const beforeInput = JSON.stringify(assessmentResult);
    const beforeRegistry = JSON.stringify(FIXED_STRATEGY_FIXTURES);

    const first = evaluatePlanFit(assessmentResult, 'remote_logistics_strategy');
    const firstJson = JSON.stringify(first);
    const second = evaluatePlanFit(assessmentResult, 'remote_logistics_strategy');
    const secondJson = JSON.stringify(second);

    expect(first).toEqual(second);
    expect(firstJson).toBe(secondJson);
    expect(JSON.stringify(assessmentResult)).toBe(beforeInput);
    expect(JSON.stringify(FIXED_STRATEGY_FIXTURES)).toBe(beforeRegistry);
    expect(JSON.stringify(first)).toBe(firstJson);

    assertDeepFrozen(first);
    assertDeepFrozen(second);
    assertDeepFrozen(FIXED_STRATEGY_FIXTURES);
  });

  it('contains no forbidden output keys anywhere in the result shape', () => {
    const result = evaluatePlanFit(buildAcceptedAssessmentResult('remote_materials_carrier_case', 'compare_both'), 'remote_logistics_strategy');
    expect([...collectForbiddenKeys(result)]).toEqual([]);
  });
});
