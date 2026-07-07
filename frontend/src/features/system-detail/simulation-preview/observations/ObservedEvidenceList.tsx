import type { ObservedFact, ObservedFactUpdateRequest } from '@/types/api';
import { ObservedEvidenceCard } from './ObservedEvidenceCard';
import { EMPTY_STATE_BODY, EMPTY_STATE_TITLE } from './observationLabels';

interface ObservedEvidenceListProps {
  facts: ObservedFact[];
  savingId: string | null;
  deletingId: string | null;
  saveErrorById: Record<string, string | null>;
  deleteErrorById: Record<string, string | null>;
  onSave: (observationId: string, update: ObservedFactUpdateRequest) => Promise<void> | void;
  onDelete: (observationId: string) => Promise<void> | void;
  onClearErrors: (observationId: string) => void;
}

/**
 * Renders the list of Observed Evidence cards (Stage 6B).
 *
 * The list itself is a passive display: it never calls the simulation
 * or optimiser, never alters predictions, and only reads the observation
 * shelf returned by the backend list endpoint. Empty/error/loading states
 * live in the parent panel.
 */
export function ObservedEvidenceList({
  facts,
  savingId,
  deletingId,
  saveErrorById,
  deleteErrorById,
  onSave,
  onDelete,
  onClearErrors,
}: ObservedEvidenceListProps) {
  if (facts.length === 0) {
    return (
      <div className="rounded-chunk-lg border border-border/60 bg-bg3/25 p-4 font-mono text-[11px] text-silver-dk">
        <div className="font-bold text-silver">{EMPTY_STATE_TITLE}</div>
        <p className="mt-1 leading-snug">{EMPTY_STATE_BODY}</p>
      </div>
    );
  }

  return (
    <ul className="space-y-2" aria-label="Observed evidence list" role="list">
      {facts.map((fact) => (
        <ObservedEvidenceCard
          key={fact.observation_id}
          fact={fact}
          saving={savingId === fact.observation_id}
          deleting={deletingId === fact.observation_id}
          saveError={saveErrorById[fact.observation_id] ?? null}
          deleteError={deleteErrorById[fact.observation_id] ?? null}
          onSave={(update) => onSave(fact.observation_id, update)}
          onDelete={() => onDelete(fact.observation_id)}
          onClearErrors={() => onClearErrors(fact.observation_id)}
        />
      ))}
    </ul>
  );
}
