import { R1_ASSESSMENT_TEMPLATE } from '@/lab/r1-assessment-lab/core/fixtures';
import type { FixedStrategyFixture } from '@/lab/r1-assessment-lab/core/planFitTypes';

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

const STRATEGY_FIXTURE_LIST: FixedStrategyFixture[] = [
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
];

function assertNonEmptyString(value: unknown, message: string): asserts value is string {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(message);
  }
}

function assertUniqueStrings(values: string[], message: string) {
  if (new Set(values).size !== values.length) {
    throw new Error(message);
  }
}

export function validateStrategyFixtures(fixtures: FixedStrategyFixture[]): FixedStrategyFixture[] {
  const seenFixtureKeys = new Set<string>();
  const seenStrategyIds = new Set<string>();
  const templateRequirementMap = new Map(R1_ASSESSMENT_TEMPLATE.requirements.map((requirement) => [requirement.id, requirement]));

  for (const fixture of fixtures) {
    assertNonEmptyString(fixture.fixtureKey, 'Strategy fixture key must be non-empty.');
    assertNonEmptyString(fixture.strategyId, 'Strategy id must be non-empty.');
    assertNonEmptyString(fixture.strategyRevision, `Strategy ${fixture.strategyId || fixture.fixtureKey} requires a non-empty revision.`);
    assertNonEmptyString(fixture.label, `Strategy ${fixture.strategyId || fixture.fixtureKey} requires a non-empty label.`);
    assertNonEmptyString(fixture.compatibility.programmeId, `Strategy ${fixture.strategyId} requires a non-empty compatibility programmeId.`);
    assertNonEmptyString(fixture.compatibility.templateId, `Strategy ${fixture.strategyId} requires a non-empty compatibility templateId.`);
    assertNonEmptyString(fixture.compatibility.templateRevision, `Strategy ${fixture.strategyId} requires a non-empty compatibility templateRevision.`);
    assertNonEmptyString(fixture.provenance.sourceKind, `Strategy ${fixture.strategyId} requires a non-empty provenance sourceKind.`);
    if (fixture.provenance.sourceKind !== 'fixture') {
      throw new Error(`Strategy ${fixture.strategyId} provenance sourceKind must be fixture.`);
    }
    assertNonEmptyString(fixture.provenance.fixtureId, `Strategy ${fixture.strategyId} requires a non-empty provenance fixtureId.`);
    assertNonEmptyString(fixture.provenance.fixtureRevision, `Strategy ${fixture.strategyId} requires a non-empty provenance fixtureRevision.`);

    if (seenFixtureKeys.has(fixture.fixtureKey)) {
      throw new Error(`Duplicate strategy fixture key: ${fixture.fixtureKey}`);
    }
    seenFixtureKeys.add(fixture.fixtureKey);

    if (seenStrategyIds.has(fixture.strategyId)) {
      throw new Error(`Duplicate strategy id: ${fixture.strategyId}`);
    }
    seenStrategyIds.add(fixture.strategyId);

    if (
      fixture.compatibility.programmeId !== R1_ASSESSMENT_TEMPLATE.programmeId
      || fixture.compatibility.templateId !== R1_ASSESSMENT_TEMPLATE.templateId
      || fixture.compatibility.templateRevision !== R1_ASSESSMENT_TEMPLATE.revision
    ) {
      throw new Error(`Strategy ${fixture.strategyId} compatibility tuple does not match the accepted template.`);
    }

    if (fixture.requiredAssessmentRequirementIds.length === 0) {
      throw new Error(`Strategy ${fixture.strategyId} must declare at least one required assessment requirement id.`);
    }

    assertUniqueStrings(
      fixture.requiredAssessmentRequirementIds,
      `Strategy ${fixture.strategyId} has duplicate required assessment requirement ids.`,
    );
    assertUniqueStrings(
      fixture.logisticsSensitiveRequirementIds,
      `Strategy ${fixture.strategyId} has duplicate logistics-sensitive requirement ids.`,
    );

    for (const requirementId of fixture.requiredAssessmentRequirementIds) {
      assertNonEmptyString(
        requirementId,
        `Strategy ${fixture.strategyId} has an empty required assessment requirement id.`,
      );
      if (!templateRequirementMap.has(requirementId)) {
        throw new Error(`Strategy ${fixture.strategyId} references unknown required assessment requirement id: ${requirementId}`);
      }
    }

    for (const requirementId of fixture.logisticsSensitiveRequirementIds) {
      assertNonEmptyString(
        requirementId,
        `Strategy ${fixture.strategyId} has an empty logistics-sensitive requirement id.`,
      );
      if (!fixture.requiredAssessmentRequirementIds.includes(requirementId)) {
        throw new Error(
          `Strategy ${fixture.strategyId} declares logistics-sensitive requirement ${requirementId} outside required assessment requirement ids.`,
        );
      }
      const templateRequirement = templateRequirementMap.get(requirementId);
      if (!templateRequirement) {
        throw new Error(`Strategy ${fixture.strategyId} references unknown logistics-sensitive requirement id: ${requirementId}`);
      }
      if (
        templateRequirement.kind !== 'logistics'
        || !templateRequirement.carrierSensitive
        || templateRequirement.sharedConstraint
      ) {
        throw new Error(
          `Strategy ${fixture.strategyId} declares invalid logistics-sensitive requirement ${requirementId}.`,
        );
      }
    }
  }

  return fixtures.map((fixture) => deepFreeze({
    ...fixture,
    compatibility: { ...fixture.compatibility },
    provenance: { ...fixture.provenance },
    requiredAssessmentRequirementIds: [...fixture.requiredAssessmentRequirementIds],
    logisticsSensitiveRequirementIds: [...fixture.logisticsSensitiveRequirementIds],
  }));
}

export const FIXED_STRATEGY_FIXTURES = deepFreeze(validateStrategyFixtures(STRATEGY_FIXTURE_LIST));
