import type {
  AssessmentCondition,
  AssessmentEvaluationInput,
  AssessmentEvaluationResult,
  AssessmentLens,
  AssessmentState,
  CarrierMode,
  CarrierScenarioMode,
  FixtureRequirementEvaluation,
  RequirementAssessment,
  ScenarioAssessment,
} from '@/lab/r1-assessment-lab/core/types';

const SCENARIO_ORDER: CarrierScenarioMode[] = ['no_carrier', 'carrier_available'];

function assertValidLens(lens: AssessmentLens): asserts lens is AssessmentLens {
  if (!lens || typeof lens !== 'object' || !('kind' in lens)) {
    throw new Error('Assessment evaluation requires a valid assessment lens.');
  }
  if (lens.kind === 'role') {
    if (typeof lens.roleId !== 'string' || lens.roleId.trim() === '') {
      throw new Error('Role lens requires a non-empty roleId.');
    }
    return;
  }
  if (lens.kind === 'question') {
    if (typeof lens.questionId !== 'string' || lens.questionId.trim() === '') {
      throw new Error('Question lens requires a non-empty questionId.');
    }
    return;
  }
  throw new Error('Assessment lens must be a role lens or a question lens.');
}

function scenarioModesFor(carrierMode: CarrierMode): CarrierScenarioMode[] {
  if (carrierMode === 'compare_both') return [...SCENARIO_ORDER];
  return [carrierMode];
}

function evaluateRequirement(
  fixtureRequirement: FixtureRequirementEvaluation,
  scenarioMode: CarrierScenarioMode,
): RequirementAssessment {
  const outcome = fixtureRequirement.outcomeByCarrier?.[scenarioMode] ?? fixtureRequirement.baseOutcome;
  return {
    requirementId: fixtureRequirement.requirementId,
    outcome,
    matchedEvidenceIds: [...fixtureRequirement.matchedEvidenceIds].sort(),
    missingEvidenceIds: [...fixtureRequirement.missingEvidenceIds].sort(),
    contradictoryEvidenceIds: [...fixtureRequirement.contradictoryEvidenceIds].sort(),
    carrierLogisticsAffected: Boolean(fixtureRequirement.outcomeByCarrier),
  };
}

function conditionFor(
  fixtureRequirement: FixtureRequirementEvaluation,
  requirementResult: RequirementAssessment,
): AssessmentCondition | null {
  const source = fixtureRequirement.condition;
  if (!source) return null;
  if (requirementResult.outcome === 'met') return null;
  return {
    id: source.id,
    kind: source.kind,
    summary: source.summary,
    blocking: source.blocking,
    requirementIds: [fixtureRequirement.requirementId],
    evidenceIds: [
      ...requirementResult.matchedEvidenceIds,
      ...requirementResult.missingEvidenceIds,
      ...requirementResult.contradictoryEvidenceIds,
    ].sort(),
  };
}

function resolveScenarioState(
  requirementResults: RequirementAssessment[],
  conditions: AssessmentCondition[],
  mandatoryRequirementIds: Set<string>,
): AssessmentState {
  const hasUnknownOrContradiction = requirementResults.some((result) =>
    result.outcome === 'unknown' || result.outcome === 'contradictory',
  );
  const hasBlockingMissingOrContradictoryEvidence = requirementResults.some((result) =>
    result.missingEvidenceIds.length > 0 || result.contradictoryEvidenceIds.length > 0,
  );
  if (hasUnknownOrContradiction || hasBlockingMissingOrContradictoryEvidence) {
    return 'not_assessable';
  }

  const hasMandatoryUnmet = requirementResults.some((result) =>
    mandatoryRequirementIds.has(result.requirementId) && result.outcome === 'unmet',
  );
  if (hasMandatoryUnmet) {
    return 'not_supported';
  }

  const hasConditional = requirementResults.some((result) => result.outcome === 'conditional');
  if (hasConditional || conditions.length > 0) {
    return 'conditionally_supported';
  }

  return 'supported';
}

function sortScenarioAssessment(value: ScenarioAssessment): ScenarioAssessment {
  return {
    ...value,
    conditions: [...value.conditions].sort((a, b) => a.id.localeCompare(b.id)),
    requirementResults: [...value.requirementResults].sort((a, b) => a.requirementId.localeCompare(b.requirementId)),
    frozenEvidence: [...value.frozenEvidence].sort((a, b) => a.id.localeCompare(b.id)),
  };
}

export function evaluateAssessment(input: AssessmentEvaluationInput): AssessmentEvaluationResult {
  assertValidLens(input.lens);

  const templateRequirements = new Map(
    input.template.requirements.map((requirement) => [requirement.id, requirement]),
  );
  const mandatoryRequirementIds = new Set(
    input.template.requirements.filter((requirement) => requirement.mandatory).map((requirement) => requirement.id),
  );

  for (const fixtureRequirement of input.fixture.requirementEvaluations) {
    const templateRequirement = templateRequirements.get(fixtureRequirement.requirementId);
    if (!templateRequirement) {
      throw new Error(`Fixture requirement ${fixtureRequirement.requirementId} is not present in the selected template.`);
    }
    if (fixtureRequirement.outcomeByCarrier && !templateRequirement.carrierSensitive) {
      throw new Error(`Requirement ${fixtureRequirement.requirementId} cannot vary by carrier mode.`);
    }
  }

  const scenarioResults = scenarioModesFor(input.carrierMode).map((scenarioMode) => {
    const requirementResults = input.fixture.requirementEvaluations.map((fixtureRequirement) =>
      evaluateRequirement(fixtureRequirement, scenarioMode),
    );
    const conditions = input.fixture.requirementEvaluations
      .map((fixtureRequirement, index) => conditionFor(fixtureRequirement, requirementResults[index]))
      .filter((value): value is AssessmentCondition => value !== null);

    const scenario = sortScenarioAssessment({
      carrierMode: scenarioMode,
      state: resolveScenarioState(requirementResults, conditions, mandatoryRequirementIds),
      conditions,
      requirementResults,
      frozenEvidence: input.fixture.evidence.map((evidence) => ({
        ...evidence,
        provenance: { ...evidence.provenance },
      })),
    });

    return scenario;
  });

  return {
    context: {
      programmeId: input.template.programmeId,
      templateId: input.template.templateId,
      templateRevision: input.template.revision,
      lens: input.lens.kind === 'role'
        ? { kind: 'role', roleId: input.lens.roleId }
        : { kind: 'question', questionId: input.lens.questionId },
      carrierMode: input.carrierMode,
    },
    scenarioResults,
  };
}

export function normalizeAssessmentResult(result: AssessmentEvaluationResult): string {
  return JSON.stringify(result);
}
