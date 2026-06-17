import { GitBranch, Play } from 'lucide-react';
import type { FacilityTemplate, SimulateBuildPlacement, SimulateBuildResponse, SystemBody } from '@/types/api';
import { CpRepairPanel } from './panels/CpRepairPanel';
import { CpSummary } from './panels/CpSummary';
import { CpTimelinePanel } from './panels/CpTimelinePanel';


export function SequenceCockpitWorkspaceView({
  placements,
  templates,
  bodies,
  result,
  isResultStale,
  canRun,
  running,
  onRunPreview,
}: {
  placements: SimulateBuildPlacement[];
  templates: FacilityTemplate[];
  bodies: SystemBody[];
  result: SimulateBuildResponse | null;
  isResultStale: boolean;
  canRun: boolean;
  running: boolean;
  onRunPreview: () => void;
}) {
  const sequenceRows = buildSequenceRows(placements, templates, bodies);

  return (
    <div className="space-y-3" data-testid="sequence-cockpit-workspace-view">
      <section className="rounded-chunk-lg border border-orange/25 bg-orange/5 px-3 py-2">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="font-mono">
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.16em] text-orange">
              <GitBranch size={12} />
              Planner sequence cockpit
            </div>
            <p className="mt-0.5 text-[11px] leading-snug text-silver-dk">
              Build order and CP tradeoffs are explicit here. Preview remains manual, and this cockpit does not mutate the
              plan unless you edit Build Plan directly.
            </p>
          </div>
          <button
            type="button"
            onClick={onRunPreview}
            disabled={!canRun}
            className="inline-flex items-center gap-2 rounded-chunk-sm border border-orange/50 bg-orange/15 px-3 py-2 text-xs font-mono font-bold text-orange hover:bg-orange/25 disabled:cursor-not-allowed disabled:opacity-45"
          >
            <Play size={14} />
            {running ? 'Running' : 'Run Preview'}
          </button>
        </div>
      </section>

      <section className="rounded-chunk-lg border border-border/70 bg-bg2/50 p-3" aria-label="Sequence order">
        <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">Build sequence</div>
        {sequenceRows.length > 0 ? (
          <div className="space-y-2">
            {sequenceRows.map((row) => (
              <div
                key={`${row.step}-${row.templateName}-${row.bodyLabel}`}
                className="rounded border border-border/60 bg-bg3/45 px-3 py-2"
              >
                <div className="flex flex-wrap items-center justify-between gap-2 font-mono text-[11px] text-silver">
                  <span>{row.step}. {row.templateName}</span>
                  <span className="text-silver-dk">{row.bodyLabel}</span>
                </div>
                <div className="mt-1 flex flex-wrap gap-2 text-[10px] text-silver-dk">
                  {row.primaryPort && (
                    <span className="rounded border border-cyan/35 bg-cyan/10 px-1.5 py-0.5 text-cyan">
                      Primary port
                    </span>
                  )}
                  <span className="rounded border border-border/70 bg-bg1/60 px-1.5 py-0.5">
                    Template {row.templateId}
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded border border-border/60 bg-bg3/35 px-3 py-3 font-mono text-[11px] text-silver-dk">
            No placements yet. Build sequence will appear here once the plan contains at least one explicit placement.
          </div>
        )}
      </section>

      {result ? (
        <>
          {isResultStale && (
            <section className="rounded-chunk-lg border border-gold/35 bg-gold/5 px-3 py-2 font-mono text-[11px] leading-snug text-gold">
              Preview-derived CP metrics are stale because the Build Plan changed. Run Preview again to refresh the sequence
              tradeoffs.
            </section>
          )}
          <CpSummary cp={result.cp} />
          <CpTimelinePanel timeline={result.cp_timeline} />
          <CpRepairPanel suggestions={result.cp_repair_suggestions} />
        </>
      ) : (
        <section className="rounded-chunk-lg border border-border/70 bg-bg2/40 px-3 py-3 font-mono text-[11px] leading-snug text-silver-dk">
          CP curve, timeline, and repair suggestions appear after an explicit Preview run. This cockpit never auto-runs preview.
        </section>
      )}
    </div>
  );
}

function buildSequenceRows(
  placements: SimulateBuildPlacement[],
  templates: FacilityTemplate[],
  bodies: SystemBody[],
) {
  const templatesById = new Map(templates.map((template) => [template.id, template]));
  const bodiesById = new Map(bodies.map((body) => [String(body.id), body]));

  return [...placements]
    .sort((a, b) => (a.build_order ?? 0) - (b.build_order ?? 0))
    .map((placement, index) => {
      const template = templatesById.get(placement.facility_template_id);
      const body = placement.local_body_id ? bodiesById.get(String(placement.local_body_id)) : null;
      return {
        step: placement.build_order ?? index + 1,
        templateId: placement.facility_template_id,
        templateName: template?.name ?? placement.facility_template_id,
        bodyLabel: body?.name ?? (placement.is_primary_port ? 'Primary orbital context' : 'Unassigned body'),
        primaryPort: Boolean(placement.is_primary_port),
      };
    });
}
