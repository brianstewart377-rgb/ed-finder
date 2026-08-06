import type {
  ListObservedFactsParams,
  ObservedFact,
  ObservedFactCreateRequest,
  ObservedFactDeleteResponse,
  ObservedFactListResponse,
  ObservedFactUpdateRequest,
  PredictionObservationCompareRequest,
  PredictionObservationCompareResponse,
  ValidationReviewRequest,
  ValidationReviewResponse,
} from '@/types/api';
import { jsonFetch, operatorMutationHeaders } from './core';

// ── Stage 6B Observed Evidence (Observed Facts) ────────────────────────
// Passive evidence: records what a user actually saw in-game for a system
// or build. These calls do NOT change Simulation Preview scoring, optimiser
// ranking, or generated candidates. They are also not consumed by the
// simulation/optimiser modules — see api-contracts.md "Stage 6A Observed
// Facts API" for the contract details.
export function listObservedFacts(params: ListObservedFactsParams): Promise<ObservedFactListResponse> {
  const usp = new URLSearchParams();
  usp.set('system_id64', String(params.system_id64));
  if (params.fact_type)              usp.set('fact_type',              params.fact_type);
  if (params.subject_type)           usp.set('subject_type',           params.subject_type);
  if (params.status)                 usp.set('status',                 params.status);
  if (params.target_archetype)       usp.set('target_archetype',       params.target_archetype);
  if (params.build_fingerprint)      usp.set('build_fingerprint',      params.build_fingerprint);
  if (params.simulation_fingerprint) usp.set('simulation_fingerprint', params.simulation_fingerprint);
  if (params.limit  !== undefined)   usp.set('limit',  String(params.limit));
  if (params.offset !== undefined)   usp.set('offset', String(params.offset));
  return jsonFetch(`/observations/facts?${usp.toString()}`);
}

export function createObservedFact(request: ObservedFactCreateRequest): Promise<ObservedFact> {
  return jsonFetch('/observations/facts', {
    method: 'POST',
    body:   JSON.stringify(request),
    headers: operatorMutationHeaders(),
  });
}

export function updateObservedFact(observationId: string, request: ObservedFactUpdateRequest): Promise<ObservedFact> {
  return jsonFetch(`/observations/facts/${encodeURIComponent(observationId)}`, {
    method: 'PATCH',
    body:   JSON.stringify(request),
    headers: operatorMutationHeaders(),
  });
}

export function deleteObservedFact(observationId: string): Promise<ObservedFactDeleteResponse> {
  return jsonFetch(`/observations/facts/${encodeURIComponent(observationId)}`, {
    method: 'DELETE',
    headers: operatorMutationHeaders(),
  });
}

// ── Stage 6C Predicted-vs-Observed Comparison ──────────────────────────
// Read-only comparison: takes a current prediction (a
// SimulateBuildResponse, in practice) and asks the backend to compare
// it against persisted observed evidence for the same system. Stage 6D
// renders the result inside Colony Planner. This call does NOT mutate
// any prediction, optimiser candidate, optimiser ranking, or persisted
// observation. The backend operates in Mode A by default (it loads
// persisted facts itself); Stage 6D never sends `observed_facts`.
export function comparePredictionToObservations(
  request: PredictionObservationCompareRequest,
): Promise<PredictionObservationCompareResponse> {
  return jsonFetch('/observations/compare', {
    method: 'POST',
    body:   JSON.stringify(request),
  });
}

// ── Stage 6E Validation Review Guidance ────────────────────────────────
// Read-only advisory guidance built from the Stage 6C comparison
// result. This helper only calls the review endpoint; it does not run
// Simulation Preview, optimiser candidate generation, or observation
// mutations.
export function reviewPredictionValidation(
  request: ValidationReviewRequest,
): Promise<ValidationReviewResponse> {
  return jsonFetch('/observations/review', {
    method: 'POST',
    body:   JSON.stringify(request),
  });
}
