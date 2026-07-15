import type { ExpansionPlan } from '@/features/expansion-plans/expansionPlanStore';
import type { ColonyProject } from '@/features/colony-planner/colonyProjectStore';

export type ExpansionPlanStatus = 'Planning' | 'In Progress' | 'Established';

export function computeExpansionPlanStatus(
  plan: ExpansionPlan,
  projectsRecord: Record<string, ColonyProject>,
): ExpansionPlanStatus {
  if (plan.slots.length === 0) return 'Planning';

  let hasProjects = false;
  let allEstablished = true;

  for (const slot of plan.slots) {
    if (slot.colony_project_id) {
      const project = projectsRecord[slot.colony_project_id];
      if (project) {
        hasProjects = true;
        if (project.status !== 'established') {
          allEstablished = false;
        }
      }
    } else {
      allEstablished = false;
    }
  }

  if (!hasProjects) return 'Planning';
  if (!allEstablished) return 'In Progress';
  return 'Established';
}

export function expansionPlanStatusLabel(status: ExpansionPlanStatus): string {
  return status;
}
