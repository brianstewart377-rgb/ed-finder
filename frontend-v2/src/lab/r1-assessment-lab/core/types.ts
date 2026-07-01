export type AssessmentState =
  | 'not_assessable'
  | 'not_supported'
  | 'conditionally_supported'
  | 'supported';

export type CarrierMode =
  | 'no_carrier'
  | 'carrier_available'
  | 'compare_both';

export type CarrierScenarioMode = Exclude<CarrierMode, 'compare_both'>;

export type AssessmentLens =
  | { kind: 'role'; roleId: string }
  | { kind: 'question'; questionId: string };

export type RequirementKind =
  | 'eligibility'
  | 'capacity'
  | 'logistics'
  | 'constraint';

export type ConditionKind =
  | 'missing_evidence'
  | 'contradictory_evidence'
  | 'logistics_dependency'
  | 'requirement_gap'
  | 'bounded_support';

export type EvidenceAvailability =
  | 'known'
  | 'missing'
  | 'contradictory'
  | 'not_applicable';

export type RequirementOutcome =
  | 'met'
  | 'unmet'
  | 'conditional'
  | 'unknown'
  | 'contradictory';

export interface EvidenceProvenance {
  sourceKind: 'fixture';
  fixtureId: string;
  fixtureRevision: string;
}

export interface EvidenceFact {
  id: string;
  factKey: string;
  value: string | number | boolean | null | Record<string, unknown>;
  availability: EvidenceAvailability;
  provenance: EvidenceProvenance;
}

export interface ProgrammeRequirement {
  id: string;
  label: string;
  kind: RequirementKind;
  mandatory: boolean;
  sharedConstraint: boolean;
  carrierSensitive: boolean;
  evidenceKeys: string[];
}

export interface ProgrammeTemplate {
  programmeId: string;
  templateId: string;
  revision: string;
  requirements: ProgrammeRequirement[];
}

export interface AssessmentCondition {
  id: string;
  kind: ConditionKind;
  summary: string;
  blocking: boolean;
  requirementIds: string[];
  evidenceIds: string[];
}

export interface RequirementAssessment {
  requirementId: string;
  outcome: RequirementOutcome;
  matchedEvidenceIds: string[];
  missingEvidenceIds: string[];
  contradictoryEvidenceIds: string[];
  carrierLogisticsAffected: boolean;
}

export interface ScenarioAssessment {
  carrierMode: CarrierScenarioMode;
  state: AssessmentState;
  conditions: AssessmentCondition[];
  requirementResults: RequirementAssessment[];
  frozenEvidence: EvidenceFact[];
}

export interface AssessmentEvaluationResult {
  context: {
    programmeId: string;
    templateId: string;
    templateRevision: string;
    lens: AssessmentLens;
    carrierMode: CarrierMode;
  };
  scenarioResults: ScenarioAssessment[];
}

export interface FixtureRequirementEvaluation {
  requirementId: string;
  matchedEvidenceIds: string[];
  missingEvidenceIds: string[];
  contradictoryEvidenceIds: string[];
  baseOutcome: RequirementOutcome;
  outcomeByCarrier?: Partial<Record<CarrierScenarioMode, RequirementOutcome>>;
  condition?: {
    id: string;
    kind: ConditionKind;
    summary: string;
    blocking: boolean;
  };
}

export interface FixtureAssessmentScenario {
  fixtureId: string;
  fixtureRevision: string;
  evidence: EvidenceFact[];
  requirementEvaluations: FixtureRequirementEvaluation[];
}

export interface AssessmentEvaluationInput {
  fixture: FixtureAssessmentScenario;
  template: ProgrammeTemplate;
  lens: AssessmentLens;
  carrierMode: CarrierMode;
}
