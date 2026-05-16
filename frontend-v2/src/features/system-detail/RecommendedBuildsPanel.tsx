import { useQuery } from '@tanstack/react-query';
import { getRecommendedBuilds } from '@/lib/api';
import type { RecommendedBuildPlan, SystemDetail } from '@/types/api';
import { BuildPlanCard } from './BuildPlanCard';

export function RecommendedBuildsPanel({
  system,
  onPreviewBuild,
}: {
  system: SystemDetail;
  onPreviewBuild: (plan: RecommendedBuildPlan) => void;
}) {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['recommended-builds', system.id64],
    queryFn: () => getRecommendedBuilds(system.id64),
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  return (
    <section
      className="rounded-chunk-lg border border-border/70 bg-bg1/60 p-4"
      aria-label="Recommended builds"
    >
      <div className="mb-3 flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="text-orange text-sm font-bold tracking-[0.18em] uppercase">Recommended Builds</h3>
          <p className="mt-1 text-[11px] text-silver-dk font-mono">
            Choose a recommended plan, then open it in Colony Planner to review the editable Build Plan before committing in-game.
          </p>
        </div>
      </div>

      {isLoading && (
        <div className="rounded border border-border/60 bg-bg3/30 px-3 py-3 font-mono text-xs text-silver-dk">
          Building recommended plans...
        </div>
      )}

      {isError && (
        <div className="rounded border border-gold/40 bg-gold/10 px-3 py-2 font-mono text-xs text-gold">
          Recommended builds are unavailable: {error?.message}
          <button type="button" onClick={() => void refetch()} className="ml-2 underline hover:text-orange">retry</button>
        </div>
      )}

      {data && data.warnings.length > 0 && (
        <div className="mb-3 rounded border border-gold/35 bg-gold/5 px-3 py-2 font-mono text-[11px] text-gold">
          {data.warnings[0]}
        </div>
      )}

      {data && data.plans.length === 0 && (
        <div className="rounded-chunk-lg border border-dashed border-border bg-bg3/25 px-4 py-5 text-center">
          <div className="font-mono text-xs text-silver">No recommended builds yet.</div>
          <div className="mt-1 text-[11px] text-silver-dk">
            Start blank in Colony Planner, or scan more bodies to improve topology confidence.
          </div>
        </div>
      )}

      {data && data.plans.length > 0 && (
        <>
          <div className="mb-3 rounded-chunk-lg border border-cyan/25 bg-cyan/5 px-3 py-2 font-mono text-[11px] text-cyan">
            {data.recommended_next_action}
          </div>
          <div className="grid gap-3 xl:grid-cols-3">
            {data.plans.map((plan) => (
              <BuildPlanCard key={plan.id} plan={plan} onPreview={onPreviewBuild} />
            ))}
          </div>
        </>
      )}
    </section>
  );
}
