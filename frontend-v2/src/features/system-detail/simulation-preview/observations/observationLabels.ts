/**
 * User-facing labels for Observed Evidence (Stage 6B).
 *
 * The backend talks about "observed facts" because that maps to the persisted
 * data contract. The user-facing product talks about "Observed Evidence" so
 * the UI does not overclaim correctness — observations are recorded evidence,
 * not proof. These labels keep both vocabularies aligned without leaking
 * absolute wording ("verified", "proven", "rule update") into the UI.
 *
 * Stage 6B is intentionally passive: nothing here implies that an observation
 * changes Simulation Preview scoring, Suggested Builds, or generated plans.
 * Comparison comes in Stage 6C, validation display in Stage 6D.
 */
import type {
  ObservationSource,
  ObservedConfidence,
  ObservedFactType,
  ObservedStatus,
  ObservedSubjectType,
} from '@/types/api';

export const PASSIVE_EVIDENCE_COPY =
  'Later step: Observed Evidence records what you see in-game after planning. It does not change Simulation Preview scoring, Suggested Builds, or generated plans.';

export const PANEL_INTRO_COPY =
  'Observed Evidence is for later, after checking in-game. Record what you actually saw for this system or build; it does not change Simulation Preview scoring, Suggested Builds, or generated plans.';

export const EMPTY_STATE_TITLE = 'No observed evidence recorded yet.';
export const EMPTY_STATE_BODY =
  'Record what you actually saw in-game. Evidence is passive and will not change predictions until a later validation stage compares it.';

export const DELETE_CONFIRM_TITLE = 'Delete this observed evidence record?';
export const DELETE_CONFIRM_BODY =
  'This removes the manually recorded evidence only. It does not change predictions, builds, or in-game state.';

/**
 * Fact types offered to manual users. The backend enum also includes
 * `prediction_match` / `prediction_mismatch` which are reserved for Stage
 * 6C predicted-vs-observed comparison; Stage 6B does not let the user
 * manually create them because they would imply a comparison verdict that
 * the Stage 6B UI does not produce.
 */
export const CREATABLE_FACT_TYPES: readonly ObservedFactType[] = [
  'service_presence',
  'economy_presence',
  'facility_state',
  'cp_value',
  'build_outcome',
  'note',
];

export const FACT_TYPE_LABELS: Record<ObservedFactType, string> = {
  service_presence: 'Service presence',
  economy_presence: 'Economy presence',
  facility_state: 'Facility state',
  cp_value: 'CP value',
  build_outcome: 'Build outcome',
  prediction_match: 'Prediction match',
  prediction_mismatch: 'Prediction mismatch',
  note: 'Note',
};

export const SUBJECT_TYPE_LABELS: Record<ObservedSubjectType, string> = {
  system: 'System',
  body: 'Body',
  facility: 'Facility',
  service: 'Service',
  economy: 'Economy',
  build: 'Build',
  simulation: 'Simulation',
  cp: 'CP',
};

export const STATUS_LABELS: Record<ObservedStatus, string> = {
  observed_present: 'Observed present',
  observed_absent: 'Observed absent',
  confirmed: 'Confirmed',
  contradicted: 'Contradicted',
  unknown: 'Unknown',
  unverified: 'Unverified',
};

export const STATUSES: readonly ObservedStatus[] = [
  'observed_present',
  'observed_absent',
  'confirmed',
  'contradicted',
  'unknown',
  'unverified',
];

export const CONFIDENCE_LABELS: Record<ObservedConfidence, string> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
};

export const CONFIDENCES: readonly ObservedConfidence[] = ['low', 'medium', 'high'];

export const SOURCE_LABELS: Record<ObservationSource, string> = {
  manual: 'Manual',
  test_fixture: 'Test fixture',
  imported: 'Imported',
  inferred: 'Inferred',
};

/**
 * Default subject_type the form uses for each fact_type. The backend
 * doesn't strictly require these mappings (subject_id can be null for
 * free-form notes), but using sensible defaults keeps the create form
 * compact and matches how the panel cards describe each evidence row.
 */
export const DEFAULT_SUBJECT_TYPE_FOR_FACT_TYPE: Record<ObservedFactType, ObservedSubjectType> = {
  service_presence: 'service',
  economy_presence: 'economy',
  facility_state: 'facility',
  cp_value: 'cp',
  build_outcome: 'build',
  prediction_match: 'system',
  prediction_mismatch: 'system',
  note: 'system',
};

export function factTypeLabel(value: string): string {
  return (FACT_TYPE_LABELS as Record<string, string>)[value] ?? value;
}

export function statusLabel(value: string): string {
  return (STATUS_LABELS as Record<string, string>)[value] ?? value;
}

export function confidenceLabel(value: string): string {
  return (CONFIDENCE_LABELS as Record<string, string>)[value] ?? value;
}

export function subjectTypeLabel(value: string): string {
  return (SUBJECT_TYPE_LABELS as Record<string, string>)[value] ?? value;
}

export function sourceLabel(value: string): string {
  return (SOURCE_LABELS as Record<string, string>)[value] ?? value;
}
