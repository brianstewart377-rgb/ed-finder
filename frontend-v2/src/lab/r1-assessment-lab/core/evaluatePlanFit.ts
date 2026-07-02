import { R1_ASSESSMENT_TEMPLATE } from '@/lab/r1-assessment-lab/core/fixtures';
import type {
  AssessmentEvaluationResult,
  AssessmentLens,
  AssessmentState,
  CarrierMode,
  CarrierScenarioMode,
  RequirementAssessment,
  RequirementOutcome,
  ScenarioAssessment,
} from '@/lab/r1-assessment-lab/core/types';
import type {
  FixedStrategyFixture,
  PlanFitEvaluationResult,
  PlanFitReason,
  PlanFitReasonKind,
  PlanFitScenarioResult,
} from '@/lab/r1-assessment-lab/core/planFitTypes';
import { FIXED_STRATEGY_FIXTURES } from '@/lab/r1-assessment-lab/core/strategyFixtures';

const VALID_CARRIER_MODES: CarrierMode[] = ['no_carrier', 'carrier_available', 'compare_both'];
const VALID_SCENARIO_ORDER: Record<CarrierMode, CarrierScenarioMode[]> = {
  no_carrier: ['no_carrier'],
  carrier_available: ['carrier_available'],
  compare_both: ['no_carrier', 'carrier_available'],
};
const VALID_ASSESSMENT_STATES: AssessmentState[] = [
  'not_assessable',
  'not_supported',
  'conditionally_supported',
  'supported',
];
const VALID_REQUIREMENT_OUTCOMES: RequirementOutcome[] = [
  'met',
  'unmet',
  'conditional',
  'unknown',
  'contradictory',
];

function deepFreeze<T>(value: T): T {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.freeze(value);
    const nestedValues = Array.isArray(value) ? value : Object.values(value);
    for (const nested of nestedValues) {
      deepFreeze(nested);
    }
  }
  return value;
}

function assertNonEmptyString(value: unknown, message: string): asserts value is string {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(message);
  }
}

function assertValidLens(lens: AssessmentLens): asserts lens is AssessmentLens {
  if (!lens || typeof lens !== 'object' || !('kind' in lens)) {
    throw new Error('Plan Fit evaluation requires a valid assessment lens.');
  }
  if (lens.kind === 'role') {
    if ('questionId' in lens) {
      throw new Error('Plan Fit role lens must not contain questionId.');
    }
    if (typeof lens.roleId !== 'string' || lens.roleId.trim() === '') {
      throw new Error('Plan Fit role lens requires a non-empty roleId.');
    }
    return;
  }
  if (lens.kind === 'question') {
    if ('roleId' in lens) {
      throw new Error('Plan Fit question lens must not contain roleId.');
    }
    if (typeof lens.questionId !== 'string' || lens.questionId.trim() === '') {
      throw new Error('Plan Fit question lens requires a non-empty questionId.');
    }
    return;
  }
  throw new Error('Plan Fit lens must be a role lens or a question lens.');
}

function uniqueSorted(values: string[]): string[] {
  return [...new Set(values)].sort();
}

function cloneLens(lens: AssessmentLens): AssessmentLens {
  return lens.kind === 'role'
    ? { kind: 'role', roleId: lens.roleId }
    : { kind: 'question', questionId: lens.questionId };
}

function buildReason(
  id: string,
  kind: PlanFitReasonKind,
  summary: string,
  blocking: boolean,
  relatedRequirementIds: string[],
  relatedEvidenceIds: string[],
): PlanFitReason {
  return {
    id,
    kind,
    summary,
    blocking,
    relatedRequirementIds: uniqueSorted(relatedRequirementIds),
    relatedEvidenceIds: uniqueSorted(relatedEvidenceIds),
  };
}

function dependencyReasonFor(
  strategy: FixedStrategyFixture,
  requirement: RequirementAssessment,
): PlanFitReason | null {
  const evidenceIds = uniqueSorted([
    ...requirement.matchedEvidenceIds,
    ...requirement.missingEvidenceIds,
    ...requirement.contradictoryEvidenceIds,
  ]);
  const reasonId = `dependency:${requirement.requirementId}`;

  if (requirement.outcome === 'met') {
    return null;
  }

  if (requirement.outcome === 'conditional') {
    const isLogisticsSensitive = strategy.logisticsSensitiveRequirementIds.includes(requirement.requirementId);
    return buildReason(
      reasonId,
      isLogisticsSensitive ? 'logistics_dependency' : 'strategy_dependency',
      isLogisticsSensitive
        ? `Selected strategy dependency ${requirement.requirementId} remains conditionally satisfied.`
        : `Selected strategy dependency ${requirement.requirementId} remains unresolved.`,
      false,
      [requirement.requirementId],
      evidenceIds,
    );
  }

  if (requirement.outcome === 'unmet') {
    return buildReason(
      reasonId,
      'strategy_dependency',
      `Selected strategy dependency ${requirement.requirementId} is unmet.`,
      true,
      [requirement.requirementId],
      evidenceIds,
    );
  }

  throw new Error(
    `Plan Fit received unsupported requirement outcome ${requirement.outcome} for ${requirement.requirementId}.`,
  );
}

function validateScenarioRequirementResults(scenario: ScenarioAssessment) {
  const expectedRequirementIds = R1_ASSESSMENT_TEMPLATE.requirements.map((requirement) => requirement.id).sort();
  const seenRequirementIds = new Set<string>();

  for (const requirement of scenario.requirementResults) {
    if (seenRequirementIds.has(requirement.requirementId)) {
      throw new Error(`Duplicate requirement result id ${requirement.requirementId} in scenario ${scenario.carrierMode}.`);
    }
    seenRequirementIds.add(requirement.requirementId);

    if (!expectedRequirementIds.includes(requirement.requirementId)) {
      throw new Error(`Unknown requirement result id ${requirement.requirementId} in scenario ${scenario.carrierMode}.`);
    }
    if (!VALID_REQUIREMENT_OUTCOMES.includes(requirement.outcome)) {
      throw new Error(`Invalid requirement outcome ${String(requirement.outcome)} in scenario ${scenario.carrierMode}.`);
    }
    if (typeof requirement.carrierLogisticsAffected !== 'boolean') {
      throw new Error(`Requirement ${requirement.requirementId} in scenario ${scenario.carrierMode} requires boolean carrierLogisticsAffected.`);
    }
  }

  if (scenario.requirementResults.length !== expectedRequirementIds.length) {
    throw new Error(`Scenario ${scenario.carrierMode} must contain every accepted template requirement exactly once.`);
  }

  const scenarioRequirementIds = [...seenRequirementIds].sort();
  if (JSON.stringify(scenarioRequirementIds) !== JSON.stringify(expectedRequirementIds)) {
    throw new Error(`Scenario ${scenario.carrierMode} must contain every accepted template requirement exactly once.`);
  }

  const hasUnknownOrContradictoryOutcome = scenario.requirementResults.some((requirement) =>
    requirement.outcome === 'unknown' || requirement.outcome === 'contradictory',
  );
  if (scenario.state !== 'not_assessable' && hasUnknownOrContradictoryOutcome) {
    throw new Error(
      `Scenario ${scenario.carrierMode} is structurally inconsistent: non-not_assessable state cannot contain unknown or contradictory requirement outcomes.`,
    );
  }
}

function validateAssessmentResult(assessmentResult: AssessmentEvaluationResult) {
  if (!assessmentResult || typeof assessmentResult !== 'object' || !('context' in assessmentResult) || !('scenarioResults' in assessmentResult)) {
    throw new Error('Plan Fit evaluation requires an AssessmentEvaluationResult input.');
  }

  const { context, scenarioResults } = assessmentResult;
  assertNonEmptyString(context.programmeId, 'Plan Fit evaluation requires a non-empty programmeId.');
  assertNonEmptyString(context.templateId, 'Plan Fit evaluation requires a non-empty templateId.');
  assertNonEmptyString(context.templateRevision, 'Plan Fit evaluation requires a non-empty templateRevision.');

  if (
    context.programmeId !== R1_ASSESSMENT_TEMPLATE.programmeId
    || context.templateId !== R1_ASSESSMENT_TEMPLATE.templateId
    || context.templateRevision !== R1_ASSESSMENT_TEMPLATE.revision
  ) {
    throw new Error('Plan Fit evaluation requires the accepted fixed template context tuple.');
  }

  assertValidLens(context.lens);

  if (!VALID_CARRIER_MODES.includes(context.carrierMode)) {
    throw new Error(`Unsupported Plan Fit carrier mode: ${String(context.carrierMode)}`);
  }

  const expectedScenarioOrder = VALID_SCENARIO_ORDER[context.carrierMode];
  if (!Array.isArray(scenarioResults) || scenarioResults.length !== expectedScenarioOrder.length) {
    throw new Error(`Plan Fit evaluation requires scenario count matching carrier mode ${context.carrierMode}.`);
  }

  const seenScenarioModes = new Set<string>();
  scenarioResults.forEach((scenario, index) => {
    if (seenScenarioModes.has(scenario.carrierMode)) {
      throw new Error(`Duplicate scenario carrier mode ${scenario.carrierMode} in Plan Fit input.`);
    }
    seenScenarioModes.add(scenario.carrierMode);
    if (scenario.carrierMode !== expectedScenarioOrder[index]) {
      throw new Error(`Plan Fit scenario order must match ${expectedScenarioOrder.join(', ')}.`);
    }
    if (!VALID_ASSESSMENT_STATES.includes(scenario.state)) {
      throw new Error(`Invalid assessment state ${String(scenario.state)} in scenario ${scenario.carrierMode}.`);
    }
    validateScenarioRequirementResults(scenario);
  });
}

function resolveStrategy(selectedStrategyId: string): FixedStrategyFixture {
  assertNonEmptyString(selectedStrategyId, 'Plan Fit evaluation requires a non-empty selectedStrategyId.');
  const matches = FIXED_STRATEGY_FIXTURES.filter((strategy) => strategy.strategyId === selectedStrategyId);
  if (matches.length !== 1) {
    throw new Error(`Unknown selected strategy id: ${selectedStrategyId}`);
  }
  return matches[0];
}

function assertStrategyCompatibility(strategy: FixedStrategyFixture, assessmentResult: AssessmentEvaluationResult) {
  if (
    strategy.compatibility.programmeId !== assessmentResult.context.programmeId
    || strategy.compatibility.templateId !== assessmentResult.context.templateId
    || strategy.compatibility.templateRevision !== assessmentResult.context.templateRevision
  ) {
    throw new Error(`Selected strategy ${strategy.strategyId} is incompatible with the assessment context tuple.`);
  }
}

function validateSelectedDependencyVariance(
  strategy: FixedStrategyFixture,
  scenarioResults: ScenarioAssessment[],
) {
  if (scenarioResults.length !== 2) return;

  const [noCarrier, carrierAvailable] = scenarioResults;
  const noCarrierMap = new Map(noCarrier.requirementResults.map((requirement) => [requirement.requirementId, requirement]));
  const carrierAvailableMap = new Map(carrierAvailable.requirementResults.map((requirement) => [requirement.requirementId, requirement]));

  for (const requirementId of strategy.requiredAssessmentRequirementIds) {
    const noCarrierRequirement = noCarrierMap.get(requirementId);
    const carrierAvailableRequirement = carrierAvailableMap.get(requirementId);
    if (!noCarrierRequirement || !carrierAvailableRequirement) {
      throw new Error(`Selected strategy dependency ${requirementId} is missing from compare_both scenarios.`);
    }
    if (
      noCarrierRequirement.outcome !== carrierAvailableRequirement.outcome
      && !strategy.logisticsSensitiveRequirementIds.includes(requirementId)
    ) {
      throw new Error(
        `Selected strategy dependency ${requirementId} varies across compare_both without logistics-sensitive declaration.`,
      );
    }
  }
}

function evaluateScenario(strategy: FixedStrategyFixture, scenario: ScenarioAssessment): PlanFitScenarioResult {
  if (scenario.state === 'not_assessable') {
    return {
      carrierMode: scenario.carrierMode,
      assessmentState: scenario.state,
      planFitState: 'no_plan_fit',
      reasons: [
        buildReason(
          'gate:not_assessable',
          'assessment_state_gate',
          'Assessment state is not assessable.',
          true,
          [],
          [],
        ),
      ],
      selectedStrategyId: strategy.strategyId,
      selectedStrategyRevision: strategy.strategyRevision,
      selectedStrategyProvenance: { ...strategy.provenance },
    };
  }

  const requirementMap = new Map(scenario.requirementResults.map((requirement) => [requirement.requirementId, requirement]));
  const dependencyReasons = strategy.requiredAssessmentRequirementIds
    .map((requirementId) => {
      const requirement = requirementMap.get(requirementId);
      if (!requirement) {
        throw new Error(`Selected strategy dependency ${requirementId} is missing from scenario ${scenario.carrierMode}.`);
      }
      return dependencyReasonFor(strategy, requirement);
    })
    .filter((value): value is PlanFitReason => value !== null)
    .sort((a, b) => a.id.localeCompare(b.id));

  if (scenario.state === 'not_supported') {
    return {
      carrierMode: scenario.carrierMode,
      assessmentState: scenario.state,
      planFitState: 'blocked_plan_fit',
      reasons: [
        buildReason(
          'gate:not_supported',
          'assessment_state_gate',
          'Assessment state is not supported.',
          true,
          [],
          [],
        ),
        ...dependencyReasons,
      ],
      selectedStrategyId: strategy.strategyId,
      selectedStrategyRevision: strategy.strategyRevision,
      selectedStrategyProvenance: { ...strategy.provenance },
    };
  }

  const hasBlockingDependency = dependencyReasons.some((reason) => reason.blocking);
  return {
    carrierMode: scenario.carrierMode,
    assessmentState: scenario.state,
    planFitState: hasBlockingDependency ? 'blocked_plan_fit' : 'provisional_plan_fit',
    reasons: dependencyReasons,
    selectedStrategyId: strategy.strategyId,
    selectedStrategyRevision: strategy.strategyRevision,
    selectedStrategyProvenance: { ...strategy.provenance },
  };
}

export function evaluatePlanFit(
  assessmentResult: AssessmentEvaluationResult,
  selectedStrategyId: string,
): PlanFitEvaluationResult {
  validateAssessmentResult(assessmentResult);
  const strategy = resolveStrategy(selectedStrategyId);
  assertStrategyCompatibility(strategy, assessmentResult);
  validateSelectedDependencyVariance(strategy, assessmentResult.scenarioResults);

  const result: PlanFitEvaluationResult = {
    context: {
      programmeId: assessmentResult.context.programmeId,
      templateId: assessmentResult.context.templateId,
      templateRevision: assessmentResult.context.templateRevision,
      lens: cloneLens(assessmentResult.context.lens),
      originalCarrierMode: assessmentResult.context.carrierMode,
      selectedStrategyId: strategy.strategyId,
      selectedStrategyRevision: strategy.strategyRevision,
    },
    scenarioResults: assessmentResult.scenarioResults.map((scenario) => evaluateScenario(strategy, scenario)),
  };

  return deepFreeze(result);
}
