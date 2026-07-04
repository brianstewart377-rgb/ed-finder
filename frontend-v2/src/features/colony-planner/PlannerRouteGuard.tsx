import { useEffect, useState } from 'react';
import { Rocket, RotateCcw } from 'lucide-react';
import { api } from '@/lib/api';
import type { SystemDetail } from '@/types/api';
import { useHashRoute } from '@/hooks/useHashRoute';
import { useColonyProjectStore } from './colonyProjectStore';
import { defaultDraftProjectName } from './plannerDraftContext';
import { archetypeFromEconomy } from '@/features/system-detail/simulation-preview/utils/placementHelpers';

export function PlannerRouteGuard() {
  const route = useHashRoute();
  const projects = useColonyProjectStore((state) => state.projects);
  const saveProject = useColonyProjectStore((state) => state.saveProject);
  const [system, setSystem] = useState<SystemDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const id64 = route.route === 'colony-planner' ? route.contextSystemId : null;
  const projectId = route.route === 'colony-planner' ? route.plannerProjectId : null;

  useEffect(() => {
    if (id64 == null || projectId) {
      setSystem(null);
      setError(null);
      setLoading(false);
      return;
    }
    let active = true;
    setSystem(null);
    setError(null);
    setLoading(true);
    void api.system(id64)
      .then((data) => { if (active) setSystem(data); })
      .catch((cause: unknown) => { if (active) setError(cause instanceof Error ? cause.message : 'The selected system is unavailable.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id64, projectId]);

  if (id64 == null) return null;
  const requested = projectId ? projects[projectId] ?? null : null;
  const mismatch = Boolean(projectId && (!requested || requested.system_id64 !== id64 || requested.archived_at));
  const direct = !projectId && !loading && system;
  const unavailable = !projectId && !loading && !system && error;

  if (!mismatch && !direct && !unavailable) {
    return <RouteSurface title="Loading selected system" detail="Resolving the requested Planner system without selecting or creating a local draft." busy />;
  }

  const createDraft = () => {
    if (!system) return;
    const objective = 'decide_later' as const;
    const project = saveProject(null, {
      system_id64: system.id64,
      system_name: system.name || 'Unknown system',
      project_name: defaultDraftProjectName(system.name || 'Unknown system', objective),
      build_plan_placements: [],
      target_archetype: archetypeFromEconomy(system.economy_suggestion ?? system.primary_economy) ?? 'refinery_industrial',
      notes: '', status: 'draft', objective, start_approach: 'manual', created_from: 'system_detail',
    });
    window.location.hash = `#colony-planner/system/${system.id64}/project/${encodeURIComponent(project.id)}`;
  };

  if (mismatch) {
    return <RouteSurface title="Requested draft could not be opened" detail="This draft is missing, archived, or belongs to a different system. A different local draft has not been opened instead." primary="View system without a draft" onPrimary={() => { window.location.hash = `#colony-planner/system/${id64}`; }} testId="planner-project-route-error" />;
  }
  if (unavailable) {
    return <RouteSurface title="Requested system could not be opened" detail={error} testId="planner-system-route-error" />;
  }
  return <RouteSurface title="No active draft for this system" detail={`${system?.name || 'This system'} is selected, but this direct Planner route has not chosen or created a local draft.`} primary="Create draft" onPrimary={createDraft} create testId="planner-no-active-draft-route" />;
}

function RouteSurface({ title, detail, primary, onPrimary, create, busy, testId }: { title: string; detail: string; primary?: string; onPrimary?: () => void; create?: boolean; busy?: boolean; testId?: string }) {
  return (
    <section role="dialog" aria-modal="true" aria-label={title} data-testid={testId ?? 'planner-route-loading'} className="fixed inset-0 z-[60] grid place-items-center bg-bg0/95 p-4 backdrop-blur-sm">
      <div className="panel w-full max-w-2xl border-orange/35 p-6 sm:p-8">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-orange">Planner route</p>
        <h1 className="mt-2 font-display text-xl tracking-[0.12em] text-orange-lt">{title}</h1>
        <p className="mt-3 text-sm leading-relaxed text-silver">{detail}</p>
        {!busy ? <div className="mt-5 flex flex-wrap gap-2">
          {primary && onPrimary ? <button type="button" onClick={onPrimary} data-testid={create ? 'planner-create-draft' : undefined} className="inline-flex items-center gap-2 rounded-chunk-sm border border-orange/45 bg-orange/10 px-3 py-2 text-xs font-mono font-bold text-orange hover:bg-orange/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/80">{create ? <Rocket size={14} aria-hidden /> : null}{primary}</button> : null}
          <button type="button" onClick={() => { window.location.hash = '#finder'; }} className="inline-flex items-center gap-2 rounded-chunk-sm border border-border bg-bg4 px-3 py-2 text-xs font-mono font-bold text-silver hover:text-orange focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/80"><RotateCcw size={14} aria-hidden />Back to Finder</button>
        </div> : null}
      </div>
    </section>
  );
}
