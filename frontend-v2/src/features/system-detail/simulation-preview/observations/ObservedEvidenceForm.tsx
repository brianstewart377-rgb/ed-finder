import { useState } from 'react';
import type { ObservedFactCreateRequest, ObservedFactType } from '@/types/api';
import {
  CONFIDENCES,
  CREATABLE_FACT_TYPES,
  STATUSES,
  confidenceLabel,
  factTypeLabel,
  statusLabel,
} from './observationLabels';
import {
  buildCreateRequest,
  defaultCreateFormState,
  validateCreateForm,
  type CreateFormState,
} from './observationUtils';

interface ObservedEvidenceFormProps {
  systemId64: number;
  suggestedArchetype?: string | null;
  submitting: boolean;
  serverError: string | null;
  onSubmit: (request: ObservedFactCreateRequest) => Promise<void> | void;
  onClearError: () => void;
}

/**
 * Manual create form for the Observed Evidence panel (Stage 6B).
 *
 * The form deliberately exposes only a compact subset of the Stage 6A
 * backend contract:
 *   - Evidence type, status, confidence, notes always visible.
 *   - Subject fields shown conditionally based on evidence type.
 *   - Optional structured advanced fields collapsed under a toggle so the
 *     common case stays small.
 *
 * The form only sends `source: 'manual'`. Imported / inferred sources are
 * reserved for later stages and are intentionally not exposed here.
 */
export function ObservedEvidenceForm({
  systemId64,
  suggestedArchetype,
  submitting,
  serverError,
  onSubmit,
  onClearError,
}: ObservedEvidenceFormProps) {
  const [state, setState] = useState<CreateFormState>(() => defaultCreateFormState(suggestedArchetype));
  const [localErrors, setLocalErrors] = useState<string[]>([]);
  const [advancedOpen, setAdvancedOpen] = useState(false);

  function update<K extends keyof CreateFormState>(key: K, value: CreateFormState[K]) {
    setState((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onClearError();
    const validation = validateCreateForm(state);
    if (!validation.ok) {
      setLocalErrors(validation.errors);
      return;
    }
    setLocalErrors([]);
    const request = buildCreateRequest(state, systemId64);
    try {
      await onSubmit(request);
    } catch {
      // The parent's mutation `onError` already captures the failure and
      // surfaces it via the `serverError` prop. We swallow the re-thrown
      // rejection here so React/jest don't see it as an unhandled
      // rejection. The user-visible error message remains controlled by
      // the panel's mutation state. We don't know here whether the
      // submit succeeded — the parent panel is the source of truth. If
      // it set serverError we keep the form so the user can fix and
      // retry; if it cleared serverError, ObservedEvidencePanel
      // remounts the form via a `key` change for a clean reset.
    }
  }

  function resetAfterSuccess() {
    setState(defaultCreateFormState(suggestedArchetype));
    setLocalErrors([]);
    setAdvancedOpen(false);
  }

  // The parent panel calls this via an imperative-ish pattern: it passes
  // a ref through `formInstance` if needed. To keep the API simple here
  // we expose resetAfterSuccess on the function itself via a side-channel:
  // we attach it to the form's onSubmit lifecycle by re-running the reset
  // when `submitting` flips from true to false and there is no server
  // error. That side-effect lives in the panel; the form's local form
  // state is reset there by remounting via `key` changes.
  void resetAfterSuccess;

  return (
    <form onSubmit={handleSubmit} aria-label="Record observed evidence" className="space-y-3">
      <div className="grid gap-2 sm:grid-cols-3">
        <label className="block text-[10px] uppercase tracking-[0.14em] text-silver-dk">
          Evidence type
          <select
            value={state.fact_type}
            onChange={(event) => {
              const next = event.target.value as ObservedFactType;
              update('fact_type', next);
              // Clear local validation when fact_type changes so the user
              // doesn't see a stale "service_id required" error after
              // switching to "Note".
              setLocalErrors([]);
            }}
            className="mt-1 block w-full rounded border border-border bg-bg2 px-2 py-1 text-[11px] text-silver"
          >
            {CREATABLE_FACT_TYPES.map((value) => (
              <option key={value} value={value}>{factTypeLabel(value)}</option>
            ))}
          </select>
        </label>
        <label className="block text-[10px] uppercase tracking-[0.14em] text-silver-dk">
          Status
          <select
            value={state.status}
            onChange={(event) => update('status', event.target.value as CreateFormState['status'])}
            className="mt-1 block w-full rounded border border-border bg-bg2 px-2 py-1 text-[11px] text-silver"
          >
            {STATUSES.map((value) => (
              <option key={value} value={value}>{statusLabel(value)}</option>
            ))}
          </select>
        </label>
        <label className="block text-[10px] uppercase tracking-[0.14em] text-silver-dk">
          Confidence
          <select
            value={state.confidence}
            onChange={(event) => update('confidence', event.target.value as CreateFormState['confidence'])}
            className="mt-1 block w-full rounded border border-border bg-bg2 px-2 py-1 text-[11px] text-silver"
          >
            {CONFIDENCES.map((value) => (
              <option key={value} value={value}>{confidenceLabel(value)}</option>
            ))}
          </select>
        </label>
      </div>

      {/* Conditional subject fields. Only render the structured input the
          chosen evidence type needs so the form does not look intimidating
          for a quick free-form note. */}
      {state.fact_type === 'service_presence' && (
        <label className="block text-[10px] uppercase tracking-[0.14em] text-silver-dk">
          Service ID
          <input
            type="text"
            value={state.service_id}
            onChange={(event) => update('service_id', event.target.value)}
            placeholder="e.g. market, refuel, repair"
            className="mt-1 block w-full rounded border border-border bg-bg2 px-2 py-1 text-[11px] text-silver"
          />
        </label>
      )}
      {state.fact_type === 'economy_presence' && (
        <label className="block text-[10px] uppercase tracking-[0.14em] text-silver-dk">
          Economy
          <input
            type="text"
            value={state.economy}
            onChange={(event) => update('economy', event.target.value)}
            placeholder="e.g. Agriculture, Refinery"
            className="mt-1 block w-full rounded border border-border bg-bg2 px-2 py-1 text-[11px] text-silver"
          />
        </label>
      )}
      {state.fact_type === 'facility_state' && (
        <label className="block text-[10px] uppercase tracking-[0.14em] text-silver-dk">
          Facility template ID
          <input
            type="text"
            value={state.facility_template_id}
            onChange={(event) => update('facility_template_id', event.target.value)}
            placeholder="e.g. agri_support_a"
            className="mt-1 block w-full rounded border border-border bg-bg2 px-2 py-1 text-[11px] text-silver"
          />
        </label>
      )}
      {(state.fact_type === 'cp_value' || state.fact_type === 'build_outcome') && (
        <label className="block text-[10px] uppercase tracking-[0.14em] text-silver-dk">
          Observed value
          <input
            type="text"
            value={state.observed_value_raw}
            onChange={(event) => update('observed_value_raw', event.target.value)}
            placeholder={state.fact_type === 'cp_value' ? 'e.g. 12 or {"yellow":4,"green":2}' : 'e.g. completed'}
            className="mt-1 block w-full rounded border border-border bg-bg2 px-2 py-1 text-[11px] text-silver"
          />
        </label>
      )}

      <label className="block text-[10px] uppercase tracking-[0.14em] text-silver-dk">
        Notes
        <textarea
          value={state.notes}
          onChange={(event) => update('notes', event.target.value)}
          rows={2}
          placeholder="What did you actually see in-game?"
          className="mt-1 block w-full rounded border border-border bg-bg2 px-2 py-1 text-[11px] text-silver"
        />
      </label>

      <div>
        <button
          type="button"
          onClick={() => setAdvancedOpen((v) => !v)}
          className="text-[10px] uppercase tracking-[0.14em] text-silver-dk hover:text-orange"
          aria-expanded={advancedOpen}
        >
          {advancedOpen ? 'Hide advanced details' : 'Show advanced details'}
        </button>
      </div>

      {advancedOpen && (
        <div className="space-y-2 rounded border border-border/60 bg-bg3/20 p-2">
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="block text-[10px] uppercase tracking-[0.14em] text-silver-dk">
              Local body ID
              <input
                type="text"
                value={state.local_body_id}
                onChange={(event) => update('local_body_id', event.target.value)}
                className="mt-1 block w-full rounded border border-border bg-bg2 px-2 py-1 text-[11px] text-silver"
              />
            </label>
            <label className="block text-[10px] uppercase tracking-[0.14em] text-silver-dk">
              Target archetype
              <input
                type="text"
                value={state.target_archetype}
                onChange={(event) => update('target_archetype', event.target.value)}
                placeholder={suggestedArchetype ?? ''}
                className="mt-1 block w-full rounded border border-border bg-bg2 px-2 py-1 text-[11px] text-silver"
              />
            </label>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="block text-[10px] uppercase tracking-[0.14em] text-silver-dk">
              Observed value
              <input
                type="text"
                value={state.observed_value_raw}
                onChange={(event) => update('observed_value_raw', event.target.value)}
                className="mt-1 block w-full rounded border border-border bg-bg2 px-2 py-1 text-[11px] text-silver"
              />
            </label>
            <label className="block text-[10px] uppercase tracking-[0.14em] text-silver-dk">
              Expected value
              <input
                type="text"
                value={state.expected_value_raw}
                onChange={(event) => update('expected_value_raw', event.target.value)}
                className="mt-1 block w-full rounded border border-border bg-bg2 px-2 py-1 text-[11px] text-silver"
              />
            </label>
          </div>
          <label className="block text-[10px] uppercase tracking-[0.14em] text-silver-dk">
            Tags (comma separated)
            <input
              type="text"
              value={state.tags_input}
              onChange={(event) => update('tags_input', event.target.value)}
              className="mt-1 block w-full rounded border border-border bg-bg2 px-2 py-1 text-[11px] text-silver"
            />
          </label>
          <p className="text-[10px] text-silver-dk leading-snug">
            These advanced fields are optional. Stage 6B records evidence only —
            it does not interpret or compare it. Imported and inferred sources
            are reserved for later stages and cannot be selected here.
          </p>
        </div>
      )}

      {localErrors.length > 0 && (
        <div role="alert" className="rounded border border-gold/45 bg-gold/10 px-2 py-1 text-[11px] text-gold">
          <ul className="list-disc space-y-1 pl-4">
            {localErrors.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        </div>
      )}
      {serverError && (
        <div role="alert" className="rounded border border-red/40 bg-red/10 px-2 py-1 text-[11px] text-red">
          {serverError}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="submit"
          disabled={submitting}
          className="rounded-chunk-sm border border-orange/50 bg-orange/15 px-3 py-1.5 text-[11px] font-bold text-orange hover:bg-orange/25 disabled:opacity-45"
        >
          {submitting ? 'Recording' : 'Record observed evidence'}
        </button>
        <span className="text-[10px] text-silver-dk">
          Stage 6B records evidence only. It does not change predictions, scoring, or generated candidates.
        </span>
      </div>
    </form>
  );
}
