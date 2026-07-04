import type { ComponentType } from 'react';
import { useHashRoute } from '@/hooks/useHashRoute';
import { useColonyProjectStore } from '@/features/colony-planner/colonyProjectStore';
import { PlannerRouteGuard } from '@/features/colony-planner/PlannerRouteGuard';
import { SelectedSystemRouteBar } from './SelectedSystemRouteBar';

export function Stage25cV2RouteRoot({ App }: { App: ComponentType }) {
  const route = useHashRoute();
  const projects = useColonyProjectStore((state) => state.projects);
  const isPlanner = route.route === 'colony-planner';
  const id64 = route.contextSystemId;
  const projectId = route.plannerProjectId;
  const project = projectId ? projects[projectId] ?? null : null;
  const projectMismatch = Boolean(projectId && (!project || project.system_id64 !== id64 || project.archived_at));
  const directPlannerDraftGate = Boolean(isPlanner && id64 != null && (!projectId || projectMismatch));

  if (directPlannerDraftGate) {
    return <PlannerRouteGuard />;
  }

  return (
    <>
      <App />
      <SelectedSystemRouteBar />
    </>
  );
}
