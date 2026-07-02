import type {
  AssessmentEvaluationResult,
  AssessmentLens,
  AssessmentState,
  CarrierMode,
  CarrierScenarioMode,
} from '@/lab/r1-assessment-lab/core/types';

export type PlanFitState =
  | 'no_plan_fit'
  | 'blocked_plan_fit'
  | 'provisional_plan_fit';

export type PlanFitReasonKind =
  | 'assessment_state_gate'
  | 'strategy_dependency'
  | 'logistics_dependency';

export interface StrategyCompatibilityTuple {
  programmeId: string;
  templateId: string;
  templateRevision: string;
}

export interface StrategyFixtureProvenance {
  sourceKind: 'fixture';
  fixtureId: string;
  fixtureRevision: string;
}

export interface FixedStrategyFixture {
  fixtureKey: string;
  strategyId: string;
  strategyRevision: string;
  label: string;
  compatibility: StrategyCompatibilityTuple;
  provenance: StrategyFixtureProvenance;
  requiredAssessmentRequirementIds: string[];
  logisticsSensitiveRequirementIds: string[];
}

export interface PlanFitReason {
  id: string;
  kind: PlanFitReasonKind;
  summary: string;
  blocking: boolean;
  relatedRequirementIds: string[];
  relatedEvidenceIds: string[];
}

export interface PlanFitScenarioResult {
  carrierMode: CarrierScenarioMode;
  assessmentState: AssessmentState;
  planFitState: PlanFitState;
  reasons: PlanFitReason[];
  selectedStrategyId: string;
  selectedStrategyRevision: string;
  selectedStrategyProvenance: StrategyFixtureProvenance;
}

export interface PlanFitEvaluationResult {
  context: {
    programmeId: string;
    templateId: string;
    templateRevision: string;
    lens: AssessmentLens;
    originalCarrierMode: CarrierMode;
    selectedStrategyId: string;
    selectedStrategyRevision: string;
  };
  scenarioResults: PlanFitScenarioResult[];
}

export type AcceptedAssessmentResult = AssessmentEvaluationResult;
