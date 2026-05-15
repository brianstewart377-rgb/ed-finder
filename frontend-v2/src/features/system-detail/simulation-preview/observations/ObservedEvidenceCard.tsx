import { useState } from 'react';
import type { ObservedFact, ObservedFactUpdateRequest } from '@/types/api';
import {
  CONFIDENCES,
  DELETE_CONFIRM_BODY,
  DELETE_CONFIRM_TITLE,
  STATUSES,
  confidenceLabel,
  factTypeLabel,
  sourceLabel,
  statusLabel,
  subjectTypeLabel,
} from './observationLabels';
import {
  defaultEditFormState,
  formatObservedValue,
  parseObservedValue,
  parseTagsInput,
} from './observationUtils';

interface ObservedEvidenceCardProps {
  fact: ObservedFact;
  saving: boolean;
  deleting: boolean;
  saveError: string | null;
  deleteError: string | null;
  onSave: (update: ObservedFactUpdateRequest) => Promise<void> | void;
  onDelete: () => Promise<void> | void;
  onClearErrors: () => void;
}

/**
 * Single Observed Evidence row, with inline edit + confirm-delete behaviour.
 *
 * The card is intentionally compact so a system-detail user can scan many
 * evidence rows without reading a wall of JSON. Detailed structured fields
 * (facility ids, service ids, fingerprints) are still rendered so a user
 * can verify they recorded the right thing, but they live below the
 * primary status / confidence / fact-type chip row.
 */
export function ObservedEvidenceCard({
  fact,
  saving,
  deleting,
  saveError,
  deleteError,
  onSave,
  onDelete,
  onClearErrors,
}: ObservedEvidenceCardProps) {
  const [mode, setMode] = useState<'view' | 'edit' | 'confirm-delete'>('view');
  const [editState, setEditState] = useState(() => defaultEditFormState(fact));

  function startEdit() {
    onClearErrors();
    setEditState(defaultEditFormState(fact));
    setMode('edit');
  }

  function cancelEdit() {
    onClearErrors();
    setEditState(defaultEditFormState(fact));
    setMode('view');
  }

  async function submitEdit() {
    const update: ObservedFactUpdateRequest = {
      status: editState.status,
      confidence: editState.confidence,
      notes: editState.notes.trim() === '' ? null : editState.notes.trim(),
      tags: parseTagsInput(editState.tags_input),
    };
    const observed = parseObservedValue(editState.observed_value_raw);
    if (observed !== undefined) update.observed_value = observed;
    const expected = parseObservedValue(editState.expected_value_raw);
    if (expected !== undefined) update.expected_value = expected;
    await onSave(update);
    // Stay in view mode if the save succeeded — the caller will refetch
    // and re-render with the updated fact. If it failed, the panel keeps
    // saveError visible and we stay in edit mode so the user can retry.
    if (!saveError) {
      setMode('view');
    }
  }

  async function confirmDelete() {
    await onDelete();
    // If delete succeeded the card unmounts. If it failed, deleteError is
    // shown and the user can cancel or retry from the confirmation panel.
  }

  const tagList = fact.tags && fact.tags.length > 0 ? fact.tags : null;

  return (
    <li
      className="rounded-chunk-lg border border-border/60 bg-bg2/40 p-3 font-mono text-[11px] text-silver-dk"
      role="listitem"
      aria-label="Observed evidence record"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-[0.14em]">
            <span className="rounded border border-orange/40 bg-orange/10 px-2 py-0.5 text-orange">
              {factTypeLabel(fact.fact_type)}
            </span>
            <span className="rounded border border-cyan/35 bg-cyan/10 px-2 py-0.5 text-cyan">
              {statusLabel(fact.status)}
            </span>
            <span className="rounded border border-border bg-bg3 px-2 py-0.5 text-silver">
              {confidenceLabel(fact.confidence)} confidence
            </span>
            <span className="rounded border border-border bg-bg3/60 px-2 py-0.5 text-silver-dk">
              {sourceLabel(fact.source)}
            </span>
          </div>
          <div className="mt-1 text-[11px] text-silver">
            {subjectTypeLabel(fact.subject_type)}
            {fact.subject_id ? <span className="text-silver-dk"> · {fact.subject_id}</span> : null}
          </div>
        </div>
        {mode === 'view' && (
          <div className="flex gap-2">
            <button
              type="button"
              onClick={startEdit}
              className="rounded-chunk-sm border border-border bg-bg2 px-2 py-1 text-[10px] uppercase tracking-[0.14em] text-silver hover:border-orange/40 hover:text-orange"
            >
              Edit
            </button>
            <button
              type="button"
              onClick={() => {
                onClearErrors();
                setMode('confirm-delete');
              }}
              className="rounded-chunk-sm border border-red/40 bg-red/10 px-2 py-1 text-[10px] uppercase tracking-[0.14em] text-red hover:bg-red/20"
            >
              Delete
            </button>
          </div>
        )}
      </div>

      {mode === 'view' && (
        <div className="mt-3 space-y-2">
          {fact.notes && (
            <p className="whitespace-pre-wrap text-[11px] text-silver">{fact.notes}</p>
          )}
          <dl className="grid grid-cols-1 gap-1 sm:grid-cols-2 text-[10px] text-silver-dk">
            {fact.service_id && (
              <KeyValue label="Service" value={fact.service_id} />
            )}
            {fact.economy && (
              <KeyValue label="Economy" value={fact.economy} />
            )}
            {fact.facility_template_id && (
              <KeyValue label="Facility template" value={fact.facility_template_id} />
            )}
            {fact.local_body_id && (
              <KeyValue label="Local body" value={fact.local_body_id} />
            )}
            {fact.target_archetype && (
              <KeyValue label="Target archetype" value={fact.target_archetype} />
            )}
            {fact.observed_value !== undefined && fact.observed_value !== null && (
              <KeyValue label="Observed value" value={formatObservedValue(fact.observed_value)} />
            )}
            {fact.expected_value !== undefined && fact.expected_value !== null && (
              <KeyValue label="Expected value" value={formatObservedValue(fact.expected_value)} />
            )}
          </dl>
          {tagList && (
            <div className="flex flex-wrap gap-1">
              {tagList.map((tag) => (
                <span key={tag} className="rounded border border-border bg-bg3/40 px-1.5 py-0.5 text-[10px] text-silver-dk">
                  #{tag}
                </span>
              ))}
            </div>
          )}
          <div className="text-[10px] text-silver-dk">
            Recorded {fact.created_at}
            {fact.updated_at ? <span> · Updated {fact.updated_at}</span> : null}
            {' · ID '}
            <span className="text-silver">{fact.observation_id}</span>
          </div>
        </div>
      )}

      {mode === 'edit' && (
        <form
          className="mt-3 space-y-2"
          onSubmit={(event) => {
            event.preventDefault();
            void submitEdit();
          }}
          aria-label="Edit observed evidence"
        >
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <label className="block text-[10px] uppercase tracking-[0.14em] text-silver-dk">
              Status
              <select
                value={editState.status}
                onChange={(event) => setEditState({ ...editState, status: event.target.value as typeof editState.status })}
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
                value={editState.confidence}
                onChange={(event) => setEditState({ ...editState, confidence: event.target.value as typeof editState.confidence })}
                className="mt-1 block w-full rounded border border-border bg-bg2 px-2 py-1 text-[11px] text-silver"
              >
                {CONFIDENCES.map((value) => (
                  <option key={value} value={value}>{confidenceLabel(value)}</option>
                ))}
              </select>
            </label>
          </div>
          <label className="block text-[10px] uppercase tracking-[0.14em] text-silver-dk">
            Notes
            <textarea
              value={editState.notes}
              onChange={(event) => setEditState({ ...editState, notes: event.target.value })}
              rows={3}
              className="mt-1 block w-full rounded border border-border bg-bg2 px-2 py-1 text-[11px] text-silver"
            />
          </label>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <label className="block text-[10px] uppercase tracking-[0.14em] text-silver-dk">
              Observed value
              <input
                type="text"
                value={editState.observed_value_raw}
                onChange={(event) => setEditState({ ...editState, observed_value_raw: event.target.value })}
                className="mt-1 block w-full rounded border border-border bg-bg2 px-2 py-1 text-[11px] text-silver"
              />
            </label>
            <label className="block text-[10px] uppercase tracking-[0.14em] text-silver-dk">
              Expected value
              <input
                type="text"
                value={editState.expected_value_raw}
                onChange={(event) => setEditState({ ...editState, expected_value_raw: event.target.value })}
                className="mt-1 block w-full rounded border border-border bg-bg2 px-2 py-1 text-[11px] text-silver"
              />
            </label>
          </div>
          <label className="block text-[10px] uppercase tracking-[0.14em] text-silver-dk">
            Tags (comma separated)
            <input
              type="text"
              value={editState.tags_input}
              onChange={(event) => setEditState({ ...editState, tags_input: event.target.value })}
              className="mt-1 block w-full rounded border border-border bg-bg2 px-2 py-1 text-[11px] text-silver"
            />
          </label>
          {saveError && (
            <div role="alert" className="rounded border border-red/40 bg-red/10 px-2 py-1 text-[11px] text-red">
              {saveError}
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <button
              type="submit"
              disabled={saving}
              className="rounded-chunk-sm border border-orange/50 bg-orange/15 px-3 py-1 text-[11px] font-bold text-orange hover:bg-orange/25 disabled:opacity-45"
            >
              {saving ? 'Saving' : 'Save changes'}
            </button>
            <button
              type="button"
              onClick={cancelEdit}
              className="rounded-chunk-sm border border-border bg-bg2 px-3 py-1 text-[11px] text-silver hover:border-orange/40 hover:text-orange"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {mode === 'confirm-delete' && (
        <div className="mt-3 rounded border border-red/40 bg-red/10 px-3 py-2" role="alertdialog" aria-label="Confirm delete observed evidence">
          <div className="font-bold text-red">{DELETE_CONFIRM_TITLE}</div>
          <p className="mt-1 text-[11px] leading-snug text-silver">{DELETE_CONFIRM_BODY}</p>
          {deleteError && (
            <div role="alert" className="mt-2 rounded border border-red/50 bg-red/15 px-2 py-1 text-[11px] text-red">
              {deleteError}
            </div>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void confirmDelete()}
              disabled={deleting}
              className="rounded-chunk-sm border border-red/60 bg-red/20 px-3 py-1 text-[11px] font-bold text-red hover:bg-red/30 disabled:opacity-45"
            >
              {deleting ? 'Deleting' : 'Confirm delete'}
            </button>
            <button
              type="button"
              onClick={() => {
                onClearErrors();
                setMode('view');
              }}
              className="rounded-chunk-sm border border-border bg-bg2 px-3 py-1 text-[11px] text-silver hover:border-orange/40 hover:text-orange"
            >
              Keep evidence
            </button>
          </div>
        </div>
      )}
    </li>
  );
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <dt className="shrink-0 text-silver-dk">{label}:</dt>
      <dd className="min-w-0 break-words text-silver">{value}</dd>
    </div>
  );
}
