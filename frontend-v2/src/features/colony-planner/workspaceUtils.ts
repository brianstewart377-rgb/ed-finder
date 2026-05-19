import type { SimulateBuildPlacement, SystemDetail } from '@/types/api';
import { bodyDisplayName } from '@/features/system-detail/simulation-preview/buildPlanLayoutUtils';
import type { TopologyPlanSnapshot, TopologySelection, TopologySelectionContext } from './ColonyTopologyRail';
import type { ColonyProject } from './colonyProjectStore';

export type ReviewDrawer = 'evidence' | 'validation' | null;
export interface PlannerWorkspaceCommand {
  token: number;
  kind: 'add-structure' | 'review-structures';
  bodyId: string;
}

export interface PlanHealthSummary {
  placementCount: number;
  unassignedCount: number;
  warningCount: number;
  previewStatus: string;
  saveStatus: string;
}

export function humanizeArchetype(value?: string | null): string {
  if (!value) return 'Unknown Plan';
  const known: Record<string, string> = {
    refinery_industrial: 'Refinery / Industrial Plan',
    tourism_agriculture: 'Tourism / Agriculture Plan',
    agriculture_terraforming: 'Tourism / Agriculture Plan',
    military_security: 'Military / Security Plan',
  };
  if (known[value]) return known[value];
  return value
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
    .concat(' Plan');
}

export function deriveArchitectStatus(snapshot: TopologyPlanSnapshot): string {
  const hasPrimaryPlacement = snapshot.placements.some((placement) => placement.is_primary_port);
  if (hasPrimaryPlacement) {
    return 'Primary-port placement planned; Architect flag not recorded';
  }
  return 'Architect flag not recorded';
}

export function getPlanHealthSummary({
  snapshot,
  system,
  selectedContext,
  unsavedChanges,
}: {
  snapshot: TopologyPlanSnapshot;
  system: SystemDetail;
  selectedContext: TopologySelectionContext;
  unsavedChanges: boolean;
}): PlanHealthSummary {
  const bodyIds = new Set(
    (system.bodies ?? [])
      .filter((body) => body.id != null)
      .map((body) => String(body.id)),
  );
  const unassignedCount = snapshot.placements.filter((placement) => !placement.local_body_id).length;
  const unknownBodyCount = snapshot.placements.filter((placement) => {
    const bodyId = placement.local_body_id != null ? String(placement.local_body_id) : '';
    return Boolean(bodyId && !bodyIds.has(bodyId));
  }).length;
  return {
    placementCount: snapshot.placements.length,
    unassignedCount,
    warningCount: Math.max(selectedContext.warningCount, unassignedCount + unknownBodyCount),
    previewStatus: 'Preview explicit',
    saveStatus: unsavedChanges ? 'Unsaved changes' : 'Saved',
  };
}

export function getPlanningFocusLabel(selection: TopologySelection, system: SystemDetail): string | null {
  if (selection.type !== 'body') return null;
  const body = (system.bodies ?? []).find((candidate) => String(candidate.id) === selection.bodyId);
  return body ? bodyDisplayName(body) : 'Unknown body reference';
}

export function projectRequestFromProject(project: ColonyProject | null) {
  if (!project) return null;
  return {
    system_id64: project.system_id64,
    target_archetype: project.target_archetype,
    placements: project.build_plan_placements,
  };
}

export function countUnassignedPlacements(placements: SimulateBuildPlacement[]): number {
  return placements.filter((placement) => !placement.local_body_id).length;
}

export function formatProjectTimestamp(value?: string | null) {
  if (!value) return 'Not saved';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Unknown';
  return date.toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}
