import { ArrowLeft, Rocket } from 'lucide-react';

export function NoActiveDraftNotice({
  systemName,
  onCreateDraft,
}: {
  systemName: string;
  onCreateDraft: () => void;
}) {
  return (
    <section data-testid="planner-no-active-draft" className="panel border-orange/35 bg-orange/5 p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-2xl">
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-orange">Selected system</p>
          <h2 className="mt-1 font-display text-lg tracking-[0.1em] text-orange-lt">No active draft for this system</h2>
          <p className="mt-2 text-sm leading-relaxed text-silver">
            {systemName} is selected for planning, but no local draft has been created. Draft creation is explicit and does not change the selected system.
          </p>
        </div>
        <button
          type="button"
          onClick={onCreateDraft}
          data-testid="planner-create-draft"
          className="inline-flex items-center gap-2 rounded-chunk-sm border border-orange/45 bg-orange/10 px-3 py-2 text-xs font-mono font-bold text-orange hover:bg-orange/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/80"
        >
          <Rocket size={14} aria-hidden />
          Create draft
        </button>
      </div>
    </section>
  );
}

export function PlannerProjectRouteError({
  onViewWithoutDraft,
  onBackToFinder,
}: {
  onViewWithoutDraft: () => void;
  onBackToFinder: () => void;
}) {
  return (
    <section role="alert" data-testid="planner-project-route-error" className="panel border-red/45 bg-red/10 p-5 font-mono text-sm text-red">
      <div className="font-bold">Requested draft could not be opened.</div>
      <p className="mt-1 text-xs leading-relaxed text-red/85">
        This draft is missing, archived, or belongs to a different system. Another local draft was not opened instead.
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onViewWithoutDraft}
          className="rounded-chunk-sm border border-red/50 bg-red/10 px-3 py-2 text-xs font-bold text-red hover:bg-red/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red/80"
        >
          View system without a draft
        </button>
        <button
          type="button"
          onClick={onBackToFinder}
          className="inline-flex items-center gap-2 rounded-chunk-sm border border-border bg-bg4 px-3 py-2 text-xs font-bold text-text-dim hover:text-orange focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/80"
        >
          <ArrowLeft size={14} aria-hidden />
          Back to Finder
        </button>
      </div>
    </section>
  );
}
