/**
 * Pure helper utilities for the Stage 6B Observed Evidence panel.
 *
 * These helpers do NOT call the API. They format / parse strings that the
 * manual-evidence form needs, and provide a small validator the form uses
 * before POSTing to the backend. The backend remains authoritative
 * for validation; this validator only catches the most obvious mistakes so
 * the user doesn't have to wait for a network round-trip to spot them.
 */
import type {
  ApiError,
} from '@/lib/api';
import type {
  ObservedConfidence,
  ObservedFact,
  ObservedFactCreateRequest,
  ObservedFactType,
  ObservedJsonValue,
  ObservedStatus,
  ObservedSubjectType,
} from '@/types/api';
import { DEFAULT_SUBJECT_TYPE_FOR_FACT_TYPE } from './observationLabels';

export function parseTagsInput(raw: string): string[] {
  if (!raw) return [];
  const seen = new Set<string>();
  const tags: string[] = [];
  for (const piece of raw.split(',')) {
    const value = piece.trim();
    if (!value || seen.has(value)) continue;
    seen.add(value);
    tags.push(value);
    if (tags.length >= 20) break;
  }
  return tags;
}

export function tagsToInputValue(tags: readonly string[] | undefined | null): string {
  if (!tags || tags.length === 0) return '';
  return tags.join(', ');
}

/**
 * Parse the small "observed_value" / "expected_value" free-text fields.
 *
 * The backend column is JSONB, so users could in theory type any JSON
 * value. We keep the UX small: blank → undefined, valid JSON → parsed,
 * otherwise the raw string. This matches "type a number, type a JSON
 * object, or just type a sentence" intuitions without forcing users to
 * remember strict JSON quoting.
 */
export function parseObservedValue(raw: string): ObservedJsonValue | undefined {
  if (raw == null) return undefined;
  const trimmed = String(raw).trim();
  if (trimmed === '') return undefined;
  try {
    return JSON.parse(trimmed) as ObservedJsonValue;
  } catch {
    return trimmed;
  }
}

export function formatObservedValue(value: ObservedJsonValue | undefined | null): string {
  if (value === undefined || value === null) return '';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

/**
 * Map a fact_type the user picked to the sensible default subject_type
 * the panel/form uses behind the scenes. The user can still leave the
 * structured subject blank for note-style entries.
 */
export function subjectTypeForFactType(factType: ObservedFactType): ObservedSubjectType {
  return DEFAULT_SUBJECT_TYPE_FOR_FACT_TYPE[factType] ?? 'system';
}

export interface CreateFormState {
  fact_type: ObservedFactType;
  status: ObservedStatus;
  confidence: ObservedConfidence;
  notes: string;
  service_id: string;
  economy: string;
  facility_template_id: string;
  local_body_id: string;
  observed_value_raw: string;
  expected_value_raw: string;
  target_archetype: string;
  tags_input: string;
}

export function defaultCreateFormState(suggestedArchetype?: string | null): CreateFormState {
  return {
    fact_type: 'note',
    status: 'observed_present',
    confidence: 'medium',
    notes: '',
    service_id: '',
    economy: '',
    facility_template_id: '',
    local_body_id: '',
    observed_value_raw: '',
    expected_value_raw: '',
    target_archetype: suggestedArchetype ?? '',
    tags_input: '',
  };
}

export interface ValidationResult {
  ok: boolean;
  errors: string[];
}

/**
 * Lightweight client-side validation. The Stage 6A backend still validates
 * authoritatively (and rejects e.g. `service_presence` without `service_id`),
 * but flagging the most common mistakes locally avoids a round-trip.
 */
export function validateCreateForm(state: CreateFormState): ValidationResult {
  const errors: string[] = [];
  if (state.fact_type === 'service_presence' && !state.service_id.trim()) {
    errors.push('Service ID is required for Service presence evidence.');
  }
  if (state.fact_type === 'economy_presence' && !state.economy.trim()) {
    errors.push('Economy is required for Economy presence evidence.');
  }
  if (state.fact_type === 'facility_state' && !state.facility_template_id.trim()) {
    errors.push('Facility template ID is required for Facility state evidence.');
  }
  return { ok: errors.length === 0, errors };
}

export function buildCreateRequest(
  state: CreateFormState,
  systemId64: number,
): ObservedFactCreateRequest {
  const subject_type = subjectTypeForFactType(state.fact_type);
  let subject_id: string | null = null;
  switch (state.fact_type) {
    case 'service_presence':
      subject_id = state.service_id.trim() || null;
      break;
    case 'economy_presence':
      subject_id = state.economy.trim() || null;
      break;
    case 'facility_state':
      subject_id = state.facility_template_id.trim() || null;
      break;
    case 'cp_value':
      subject_id = 'cp';
      break;
    case 'build_outcome':
      subject_id = null;
      break;
    case 'note':
    default:
      subject_id = null;
      break;
  }

  const request: ObservedFactCreateRequest = {
    system_id64: systemId64,
    source: 'manual',
    fact_type: state.fact_type,
    subject_type,
    subject_id,
    status: state.status,
    confidence: state.confidence,
  };

  const notes = state.notes.trim();
  if (notes) request.notes = notes;

  const observed = parseObservedValue(state.observed_value_raw);
  if (observed !== undefined) request.observed_value = observed;

  const expected = parseObservedValue(state.expected_value_raw);
  if (expected !== undefined) request.expected_value = expected;

  if (state.service_id.trim())          request.service_id          = state.service_id.trim();
  if (state.economy.trim())             request.economy             = state.economy.trim();
  if (state.facility_template_id.trim()) request.facility_template_id = state.facility_template_id.trim();
  if (state.local_body_id.trim())       request.local_body_id       = state.local_body_id.trim();
  if (state.target_archetype.trim())    request.target_archetype    = state.target_archetype.trim();

  const tags = parseTagsInput(state.tags_input);
  if (tags.length > 0) request.tags = tags;

  return request;
}

export interface EditFormState {
  status: ObservedStatus;
  confidence: ObservedConfidence;
  notes: string;
  tags_input: string;
  observed_value_raw: string;
  expected_value_raw: string;
}

export function defaultEditFormState(fact: ObservedFact): EditFormState {
  return {
    status: (fact.status as ObservedStatus) ?? 'observed_present',
    confidence: (fact.confidence as ObservedConfidence) ?? 'medium',
    notes: fact.notes ?? '',
    tags_input: tagsToInputValue(fact.tags),
    observed_value_raw: formatObservedValue(fact.observed_value),
    expected_value_raw: formatObservedValue(fact.expected_value),
  };
}

/**
 * Surface FastAPI / Problem-Details validation messages in a human form.
 *
 * The backend returns either a plain text message or a JSON body shaped
 * like `{ detail: [ { loc, msg, type } ] }` for 422 validation errors.
 * We try the JSON shape first so the user sees the real reason a request
 * was rejected, but fall back to the raw text rather than swallowing it.
 */
export function describeApiError(err: unknown): string {
  if (err instanceof Error) {
    const apiErr = err as unknown as ApiError;
    const body = (apiErr.body ?? '').trim();
    if (body.startsWith('{') || body.startsWith('[')) {
      try {
        const parsed = JSON.parse(body) as { detail?: unknown };
        const detail = parsed?.detail;
        if (Array.isArray(detail)) {
          const messages = detail
            .map((d) => {
              if (d && typeof d === 'object' && 'msg' in (d as Record<string, unknown>)) {
                return String((d as Record<string, unknown>).msg ?? '');
              }
              return '';
            })
            .filter((s) => s.length > 0);
          if (messages.length > 0) return messages.join('; ');
        }
        if (typeof detail === 'string') return detail;
      } catch {
        /* fall through to raw body */
      }
    }
    if (body) return body;
    return err.message;
  }
  return 'Unexpected error';
}
