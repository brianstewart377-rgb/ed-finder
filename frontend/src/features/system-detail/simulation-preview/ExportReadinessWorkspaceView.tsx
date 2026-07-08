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
import { SelectedSystemReviewContext } from './SelectedSystemReviewContext';


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
      <SelectedSystemReviewContext
        system={system}
        targetArchetype={targetArchetype}
        modeLabel="Export mode"
        tone="report_only"
        summary={`${system.name ?? 'This system'} remains the active selected-system context while review-ready packs are assembled. Planned, projected, observed, inferred, and warehouse sections stay explicitly separate.`}
      />
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

      <section className="rounded-chunk-lg border border-border/70 bg-bg2/50 p-3" aria-label="Operator review and audit">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className="font-display tracking-[0.14em] text-cyan text-xs">Operator review and audit</span>
          <span className={`rounded border px-2 py-1 text-[10px] uppercase tracking-[0.12em] ${artifacts.operatorReview.ready ? 'border-green/40 bg-green/10 text-green' : 'border-gold/40 bg-gold/10 text-gold'}`}>
            {artifacts.operatorReview.ready ? 'Review ready' : 'Needs operator review'}
          </span>
        </div>

        <div className="grid gap-3 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="space-y-3">
            <div>
              <div className="mb-1 font-display tracking-[0.12em] text-[11px] text-cyan">Review focus</div>
              <ul className="space-y-1 text-[11px] text-silver-dk" data-testid="operator-review-focus">
                {artifacts.operatorReview.focus_items.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </div>

            <div>
              <div className="mb-1 font-display tracking-[0.12em] text-[11px] text-cyan">Safeguards</div>
              <ul className="space-y-1 text-[11px] text-silver-dk" data-testid="operator-review-safeguards">
                {artifacts.operatorReview.safeguards.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </div>
          </div>

          <div className="space-y-3">
            <div className="rounded border border-border/70 bg-bg1/50 p-2">
              <div className="mb-2 font-display tracking-[0.12em] text-[11px] text-cyan">Sanitized references</div>
              <dl className="grid gap-1 text-[11px] text-silver-dk" data-testid="operator-review-references">
                <ReferenceRow label="System" value={artifacts.operatorReview.references.system_name ?? `ID64 ${artifacts.operatorReview.references.system_id64}`} />
                <ReferenceRow label="Source run" value={artifacts.operatorReview.references.source_run_key ?? 'Unknown'} />
                <ReferenceRow label="Artifact" value={artifacts.operatorReview.references.artifact_name ?? 'Unknown'} />
                <ReferenceRow label="Warehouse state" value={artifacts.operatorReview.references.warehouse_state} />
              </dl>
            </div>

            <div className="rounded border border-border/70 bg-bg1/50 p-2">
              <div className="mb-2 font-display tracking-[0.12em] text-[11px] text-cyan">Section coverage</div>
              <div className="flex flex-wrap gap-2" data-testid="operator-review-sections">
                {Object.entries(artifacts.operatorReview.sections).map(([key, present]) => (
                  <span
                    key={key}
                    className={`rounded border px-2 py-1 text-[10px] uppercase tracking-[0.12em] ${present ? 'border-green/40 bg-green/10 text-green' : 'border-gold/40 bg-gold/10 text-gold'}`}
                  >
                    {key}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="rounded-chunk-lg border border-border/70 bg-bg2/50 p-3" aria-label="Documentation governance">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className="font-display tracking-[0.14em] text-cyan text-xs">Documentation governance</span>
          <span className="rounded border border-cyan/40 bg-cyan/10 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-cyan">
            Read-only policy
          </span>
        </div>

        <div className="grid gap-3 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="space-y-3">
            <div className="rounded border border-border/70 bg-bg1/50 p-2" data-testid="export-governance-scope">
              <div className="mb-1 font-display tracking-[0.12em] text-[11px] text-cyan">Authority scope</div>
              <p className="text-[11px] text-silver-dk">{artifacts.governance.authority_scope}</p>
            </div>

            <div>
              <div className="mb-1 font-display tracking-[0.12em] text-[11px] text-cyan">Exclusions</div>
              <ul className="space-y-1 text-[11px] text-silver-dk" data-testid="export-governance-exclusions">
                {artifacts.governance.exclusions.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </div>
          </div>

          <div className="space-y-3">
            <div className="rounded border border-border/70 bg-bg1/50 p-2" data-testid="export-governance-history">
              <div className="mb-1 font-display tracking-[0.12em] text-[11px] text-cyan">Historical status</div>
              <p className="text-[11px] text-silver-dk">{artifacts.governance.historical_status}</p>
            </div>

            <div>
              <div className="mb-1 font-display tracking-[0.12em] text-[11px] text-cyan">Reference docs</div>
              <ul className="space-y-1 text-[11px] text-silver-dk" data-testid="export-governance-references">
                {artifacts.governance.documentation_references.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </div>
          </div>
        </div>
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

function ReferenceRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[88px_1fr] gap-2">
      <dt className="text-text-dim">{label}</dt>
      <dd className="font-mono text-silver">{value}</dd>
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
