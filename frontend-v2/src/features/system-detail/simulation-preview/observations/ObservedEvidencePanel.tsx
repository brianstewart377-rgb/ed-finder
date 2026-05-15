import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createObservedFact,
  deleteObservedFact,
  listObservedFacts,
  updateObservedFact,
} from '@/lib/api';
import type {
  ListObservedFactsParams,
  ObservedConfidence,
  ObservedFactCreateRequest,
  ObservedFactListResponse,
  ObservedFactType,
  ObservedFactUpdateRequest,
  ObservedStatus,
} from '@/types/api';
import { ObservedEvidenceForm } from './ObservedEvidenceForm';
import { ObservedEvidenceList } from './ObservedEvidenceList';
import {
  CONFIDENCES,
  CREATABLE_FACT_TYPES,
  PANEL_INTRO_COPY,
  PASSIVE_EVIDENCE_COPY,
  STATUSES,
  confidenceLabel,
  factTypeLabel,
  statusLabel,
} from './observationLabels';
import { describeApiError } from './observationUtils';

interface ObservedEvidencePanelProps {
  systemId64: number;
  suggestedArchetype?: string | null;
}

/**
 * Stage 6B Observed Evidence panel.
 *
 * Lists, creates, updates, and deletes manually recorded observed evidence
 * for the current system. The panel is passive: nothing here calls
 * `simulateBuild` or `fetchOptimiserCandidates`, and the data fetched here
 * is NOT plumbed back into Simulation Preview scoring or optimiser ranking.
 * Stage 6C/6D/6E compare and review evidence in separate read-only
 * validation queries; this panel remains the only Stage 6 surface that
 * mutates observed evidence.
 *
 * The query key includes the current filter set so changing a filter
 * triggers a fresh backend list call with the filter applied (the
 * backend list endpoint already returns `summary` over the full filtered
 * result set).
 */
export function ObservedEvidencePanel({ systemId64, suggestedArchetype }: ObservedEvidencePanelProps) {
  const queryClient = useQueryClient();

  const [factTypeFilter, setFactTypeFilter] = useState<ObservedFactType | ''>('');
  const [statusFilter, setStatusFilter] = useState<ObservedStatus | ''>('');
  const [confidenceFilter, setConfidenceFilter] = useState<ObservedConfidence | ''>('');

  const [createError, setCreateError] = useState<string | null>(null);
  const [createFormKey, setCreateFormKey] = useState(0);
  const [saveErrorById, setSaveErrorById] = useState<Record<string, string | null>>({});
  const [deleteErrorById, setDeleteErrorById] = useState<Record<string, string | null>>({});

  const listParams: ListObservedFactsParams = useMemo(() => {
    const params: ListObservedFactsParams = { system_id64: systemId64 };
    if (factTypeFilter) params.fact_type = factTypeFilter;
    if (statusFilter) params.status = statusFilter;
    return params;
  }, [systemId64, factTypeFilter, statusFilter]);

  const queryKey = useMemo(
    () => ['observed-facts', systemId64, factTypeFilter || null, statusFilter || null],
    [systemId64, factTypeFilter, statusFilter],
  );

  const listQuery = useQuery<ObservedFactListResponse, Error>({
    queryKey,
    queryFn: () => listObservedFacts(listParams),
    staleTime: 30 * 1000,
    // Keep retries to 1 in production, but tests pass retry:false through
    // the React Query client so failures surface immediately.
    retry: 1,
  });

  // Confidence filtering is applied locally because the Stage 6A list
  // endpoint accepts `fact_type` and `status` query params but does not
  // expose a `confidence` query param. As a result:
  //   - The backend list query reflects only the type/status filters.
  //   - The `summary` returned by the backend describes that backend
  //     result set (type/status filters applied), NOT the
  //     confidence-narrowed visible list below.
  //   - The confidence filter is a UI-only refinement that hides rows
  //     from view; it does not change the totals shown in summary.
  // The UI surfaces this distinction explicitly via a "Showing X of Y
  // records after confidence filter" line when the confidence filter is
  // active. Adding backend confidence filtering is deferred until the
  // backend list endpoint is extended in a later stage.
  const facts = useMemo(() => {
    const all = listQuery.data?.facts ?? [];
    if (!confidenceFilter) return all;
    return all.filter((fact) => fact.confidence === confidenceFilter);
  }, [listQuery.data, confidenceFilter]);

  const summary = listQuery.data?.summary;

  const createMutation = useMutation({
    mutationFn: (request: ObservedFactCreateRequest) => createObservedFact(request),
    onSuccess: () => {
      setCreateError(null);
      // Force form remount to reset state on success.
      setCreateFormKey((value) => value + 1);
      void queryClient.invalidateQueries({ queryKey: ['observed-facts', systemId64] });
      // Stage 6D: the Validation panel reads from the same persisted
      // evidence pool. Invalidate its compare query so the user can see
      // the new evidence reflected after recording it. The Validation
      // panel still does NOT auto-run Simulation Preview.
      void queryClient.invalidateQueries({ queryKey: ['observation-compare', systemId64] });
      void queryClient.invalidateQueries({ queryKey: ['observation-review', systemId64] });
    },
    onError: (error: unknown) => {
      setCreateError(describeApiError(error));
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ observationId, request }: { observationId: string; request: ObservedFactUpdateRequest }) =>
      updateObservedFact(observationId, request),
    onSuccess: (_data, variables) => {
      setSaveErrorById((prev) => {
        const next = { ...prev };
        delete next[variables.observationId];
        return next;
      });
      void queryClient.invalidateQueries({ queryKey: ['observed-facts', systemId64] });
      void queryClient.invalidateQueries({ queryKey: ['observation-compare', systemId64] });
      void queryClient.invalidateQueries({ queryKey: ['observation-review', systemId64] });
    },
    onError: (error: unknown, variables) => {
      setSaveErrorById((prev) => ({ ...prev, [variables.observationId]: describeApiError(error) }));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (observationId: string) => deleteObservedFact(observationId),
    onSuccess: (_data, observationId) => {
      setDeleteErrorById((prev) => {
        const next = { ...prev };
        delete next[observationId];
        return next;
      });
      void queryClient.invalidateQueries({ queryKey: ['observed-facts', systemId64] });
      void queryClient.invalidateQueries({ queryKey: ['observation-compare', systemId64] });
      void queryClient.invalidateQueries({ queryKey: ['observation-review', systemId64] });
    },
    onError: (error: unknown, observationId) => {
      setDeleteErrorById((prev) => ({ ...prev, [observationId]: describeApiError(error) }));
    },
  });

  function clearCardErrors(observationId: string) {
    setSaveErrorById((prev) => {
      if (!prev[observationId]) return prev;
      const next = { ...prev };
      delete next[observationId];
      return next;
    });
    setDeleteErrorById((prev) => {
      if (!prev[observationId]) return prev;
      const next = { ...prev };
      delete next[observationId];
      return next;
    });
  }

  const filtersActive = Boolean(factTypeFilter || statusFilter || confidenceFilter);
  const filteredCount = facts.length;

  return (
    <section
      aria-label="Observed Evidence"
      className="rounded-chunk-lg border border-orange/20 bg-bg1/55 p-4"
    >
      <header className="mb-3">
        <h3 className="text-orange text-sm font-bold tracking-[0.18em] uppercase">Observed Evidence</h3>
        <p className="mt-1 text-[11px] text-silver-dk font-mono leading-snug">{PANEL_INTRO_COPY}</p>
        <p
          className="mt-1 rounded border border-cyan/30 bg-cyan/5 px-2 py-1 text-[10px] text-cyan font-mono"
          role="note"
          aria-label="Observed Evidence passivity notice"
        >
          {PASSIVE_EVIDENCE_COPY}
        </p>
      </header>

      <div className="mb-4 rounded border border-border/60 bg-bg2/30 p-3">
        <div className="mb-2 text-[10px] uppercase tracking-[0.14em] text-silver-dk">Record manually observed evidence</div>
        <ObservedEvidenceForm
          // Remount on success so internal form state resets cleanly.
          key={createFormKey}
          systemId64={systemId64}
          suggestedArchetype={suggestedArchetype}
          submitting={createMutation.isPending}
          serverError={createError}
          onSubmit={async (request) => {
            await createMutation.mutateAsync(request);
          }}
          onClearError={() => setCreateError(null)}
        />
      </div>

      <div className="mb-3 grid gap-2 sm:grid-cols-[auto_auto_auto_auto] sm:items-end">
        <label className="block text-[10px] uppercase tracking-[0.14em] text-silver-dk">
          Filter by type
          <select
            value={factTypeFilter}
            onChange={(event) => setFactTypeFilter(event.target.value as ObservedFactType | '')}
            className="mt-1 block w-full rounded border border-border bg-bg2 px-2 py-1 text-[11px] text-silver"
          >
            <option value="">All types</option>
            {CREATABLE_FACT_TYPES.map((value) => (
              <option key={value} value={value}>{factTypeLabel(value)}</option>
            ))}
            <option value="prediction_match">{factTypeLabel('prediction_match')}</option>
            <option value="prediction_mismatch">{factTypeLabel('prediction_mismatch')}</option>
          </select>
        </label>
        <label className="block text-[10px] uppercase tracking-[0.14em] text-silver-dk">
          Filter by status
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as ObservedStatus | '')}
            className="mt-1 block w-full rounded border border-border bg-bg2 px-2 py-1 text-[11px] text-silver"
          >
            <option value="">All statuses</option>
            {STATUSES.map((value) => (
              <option key={value} value={value}>{statusLabel(value)}</option>
            ))}
          </select>
        </label>
        <label className="block text-[10px] uppercase tracking-[0.14em] text-silver-dk">
          Filter by confidence
          <select
            value={confidenceFilter}
            onChange={(event) => setConfidenceFilter(event.target.value as ObservedConfidence | '')}
            className="mt-1 block w-full rounded border border-border bg-bg2 px-2 py-1 text-[11px] text-silver"
          >
            <option value="">All confidences</option>
            {CONFIDENCES.map((value) => (
              <option key={value} value={value}>{confidenceLabel(value)}</option>
            ))}
          </select>
        </label>
        {filtersActive && (
          <button
            type="button"
            onClick={() => {
              setFactTypeFilter('');
              setStatusFilter('');
              setConfidenceFilter('');
            }}
            className="rounded-chunk-sm border border-border bg-bg2 px-3 py-1.5 text-[11px] text-silver hover:border-orange/40 hover:text-orange"
          >
            Clear filters
          </button>
        )}
      </div>

      {summary && (
        <div className="mb-3 rounded border border-border/60 bg-bg3/20 px-3 py-2 font-mono text-[10px] text-silver-dk">
          <div className="uppercase tracking-[0.16em] text-silver">
            Summary
            {(factTypeFilter || statusFilter) && (
              <span className="ml-2 text-cyan">(type / status filtered)</span>
            )}
          </div>
          <p className="mt-1 text-[10px] text-silver-dk">
            Totals reflect the type and status filters only. Confidence
            filtering is applied locally and narrows the visible list
            below without changing these totals.
          </p>
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
            <span>Total: <span className="text-silver">{summary.total_count}</span></span>
            {Object.entries(summary.by_fact_type ?? {}).map(([type, count]) => (
              <span key={`ft-${type}`}>
                {factTypeLabel(type)}: <span className="text-silver">{count}</span>
              </span>
            ))}
            {Object.entries(summary.by_status ?? {}).map(([status, count]) => (
              <span key={`st-${status}`}>
                {statusLabel(status)}: <span className="text-silver">{count}</span>
              </span>
            ))}
            {Object.entries(summary.by_confidence ?? {}).map(([confidence, count]) => (
              <span key={`cf-${confidence}`}>
                {confidenceLabel(confidence)}: <span className="text-silver">{count}</span>
              </span>
            ))}
          </div>
          {confidenceFilter && (
            <p className="mt-1 text-[10px] text-silver-dk">
              Showing {filteredCount} of {summary.total_count} records after local confidence filter.
            </p>
          )}
        </div>
      )}

      {listQuery.isLoading && (
        <div className="rounded border border-border/60 bg-bg3/30 px-3 py-3 font-mono text-xs text-silver-dk">
          Loading observed evidence&hellip;
        </div>
      )}

      {listQuery.isError && (
        <div
          role="alert"
          className="rounded border border-red/40 bg-red/10 px-3 py-2 font-mono text-[11px] text-red"
        >
          <div>Observed evidence failed to load: {describeApiError(listQuery.error)}</div>
          <button
            type="button"
            onClick={() => void listQuery.refetch()}
            className="mt-2 rounded-chunk-sm border border-red/50 bg-red/15 px-3 py-1 text-[11px] font-bold text-red hover:bg-red/25"
          >
            Retry
          </button>
        </div>
      )}

      {!listQuery.isLoading && !listQuery.isError && (
        <ObservedEvidenceList
          facts={facts}
          savingId={updateMutation.isPending ? updateMutation.variables?.observationId ?? null : null}
          deletingId={deleteMutation.isPending ? deleteMutation.variables ?? null : null}
          saveErrorById={saveErrorById}
          deleteErrorById={deleteErrorById}
          onSave={async (observationId, update) => {
            await updateMutation.mutateAsync({ observationId, request: update });
          }}
          onDelete={async (observationId) => {
            await deleteMutation.mutateAsync(observationId);
          }}
          onClearErrors={clearCardErrors}
        />
      )}
    </section>
  );
}
