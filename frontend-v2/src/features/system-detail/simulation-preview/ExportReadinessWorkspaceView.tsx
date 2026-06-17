import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getProvenanceCockpit, listObservedFacts } from '@/lib/api';
import type {
  FacilityTemplate,
  SimulateBuildPlacement,
  SimulateBuildResponse,
  SystemBody,
  SystemDetail,
} from '@/types/api';
import type { RoleReviewResult } from '@/features/colony-planner/colonyRoleReview';
import { buildExportArtifacts } from './exportArtifacts';


export function ExportReadinessWorkspaceView({
  system,
  targetArchetype,
  placements,
  templates,
  bodies,
  previewResult,
  previewResultStale,
  roleReview,
}: {
  system: SystemDetail;
  targetArchetype: string;
  placements: SimulateBuildPlacement[];
  templates: FacilityTemplate[];
  bodies: SystemBody[];
  previewResult: SimulateBuildResponse | null;
  previewResultStale: boolean;
  roleReview?: RoleReviewResult;
}) {
  const provenanceQuery = useQuery({
    queryKey: ['provenance-cockpit', system.id64],
    queryFn: () => getProvenanceCockpit(system.id64),
    retry: 1,
    staleTime: 60_000,
  });
  const observedQuery = useQuery({
    queryKey: ['observed-facts-export', system.id64, targetArchetype],
    queryFn: () => listObservedFacts({ system_id64: system.id64, target_archetype: targetArchetype, limit: 100 }),
    retry: 1,
    staleTime: 60_000,
  });

  const artifacts = useMemo(
    () =>
      buildExportArtifacts({
        system,
        targetArchetype,
        placements,
        templates,
        bodies,
        previewResult,
        previewResultStale,
        roleReview,
        observedFacts: observedQuery.data?.facts ?? [],
        provenance: provenanceQuery.data,
      }),
    [bodies, observedQuery.data?.facts, placements, previewResult, previewResultStale, provenanceQuery.data, roleReview, system, targetArchetype, templates],
  );

  return (
    <div className="space-y-3" data-testid="export-readiness-workspace-view">
      <section className="rounded-chunk-lg border border-cyan/25 bg-cyan/5 px-3 py-2 font-mono text-[11px] leading-snug text-silver-dk">
        <span className="font-bold text-cyan">Export mode</span>
        <span className="ml-2">
          Reviewable planning packs are assembled here from read-only planner, provenance, and observed-evidence data.
          Exports keep planned, projected, observed, inferred, and warehouse sections separate.
        </span>
      </section>

      <section className="rounded-chunk-lg border border-border/70 bg-bg2/50 p-3" aria-label="Closeout readiness">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="font-display tracking-[0.14em] text-cyan text-xs">Closeout readiness</span>
          <span className={`rounded border px-2 py-1 text-[10px] uppercase tracking-[0.12em] ${artifacts.readiness.closeout_ready ? 'border-green/40 bg-green/10 text-green' : 'border-gold/40 bg-gold/10 text-gold'}`}>
            {artifacts.readiness.closeout_ready ? 'Ready' : 'Needs review'}
          </span>
          {(provenanceQuery.isLoading || observedQuery.isLoading) && (
            <span className="text-text-dim">Refreshing export inputs…</span>
          )}
        </div>
        {artifacts.readiness.reasons.length > 0 ? (
          <ul className="space-y-1 text-gold" aria-label="Closeout blockers">
            {artifacts.readiness.reasons.map((reason) => <li key={reason}>{reason}</li>)}
          </ul>
        ) : (
          <p className="text-green">No Stage 20 export blockers detected in the current planner state.</p>
        )}
      </section>

      <ArtifactBlock
        title="Markdown operator pack"
        testId="export-markdown"
        description="Review-ready Markdown pack with separate planned, projected, observed, inferred, warehouse, and guardrail sections."
        value={artifacts.markdown}
      />
      <ArtifactBlock
        title="JSON snapshot"
        testId="export-json"
        description="Structured snapshot for automation, handoff, or diff review."
        value={artifacts.json}
      />
      <ArtifactBlock
        title="CSV planned placements"
        testId="export-csv"
        description="Compact CSV export of the explicit planned build sequence only."
        value={artifacts.csv}
      />
    </div>
  );
}

function ArtifactBlock({
  title,
  description,
  value,
  testId,
}: {
  title: string;
  description: string;
  value: string;
  testId: string;
}) {
  return (
    <section className="rounded-chunk-lg border border-border/70 bg-bg2/50 p-3">
      <div className="mb-2">
        <div className="font-display tracking-[0.14em] text-xs text-cyan">{title}</div>
        <p className="mt-1 font-mono text-[11px] leading-snug text-silver-dk">{description}</p>
      </div>
      <textarea
        readOnly
        data-testid={testId}
        value={value}
        className="min-h-[180px] w-full rounded border border-border bg-bg1/80 p-3 font-mono text-[10px] leading-snug text-silver"
      />
    </section>
  );
}
