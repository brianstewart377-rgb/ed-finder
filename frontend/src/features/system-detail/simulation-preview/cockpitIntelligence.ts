import type { FacilityTemplate, SimulateBuildPlacement, SystemBody } from '@/types/api';
import { groupPlacementsByBody } from './buildPlanLayoutUtils';
import { buildColonyRoleSummaryForGroup } from './colonyRoleHintUtils';
import type { ReviewPreviewStatus } from './ReviewWorkflowRail';

export interface CockpitIntelligenceAction {
  id: string;
  label: string;
  reason: string;
  tone: 'good' | 'warn' | 'neutral';
}

export interface CockpitIntelligenceSnapshot {
  postureLabel: string;
  postureDetail: string;
  mainStationCandidates: string[];
  supportBodies: string[];
  unresolvedGroups: number;
  confidentRoleBodies: number;
  conflictCount: number;
  warningCount: number;
  facilityPressure: string[];
  nextActions: CockpitIntelligenceAction[];
}

export function buildCockpitIntelligence({
  placements,
  templates,
  bodies,
  previewStatus,
  observedFactsCount,
  exportBlockerCount = 0,
}: {
  placements: SimulateBuildPlacement[];
  templates: FacilityTemplate[];
  bodies: SystemBody[];
  previewStatus: ReviewPreviewStatus;
  observedFactsCount: number;
  exportBlockerCount?: number;
}): CockpitIntelligenceSnapshot {
  const groups = groupPlacementsByBody(placements, templates, bodies).filter((group) => group.placements.length > 0);
  const resolvedGroups = groups.filter((group) => group.body);
  const roleSummaries = resolvedGroups.map((group) => ({
    group,
    summary: buildColonyRoleSummaryForGroup(group, resolvedGroups),
  }));
  const mainStationCandidates = roleSummaries
    .filter(({ summary }) => summary.hints.some((hint) => hint.id === 'main-station-body' || hint.id === 'colony-core-body'))
    .map(({ group }) => group.body?.name ?? 'Unknown body');
  const supportBodies = roleSummaries
    .filter(({ summary }) => summary.hints.some((hint) => hint.id === 'support-body'))
    .map(({ group }) => group.body?.name ?? 'Unknown body');
  const unresolvedGroups = groups.filter((group) => !group.body).length;
  const confidentRoleBodies = roleSummaries.filter(({ summary }) => summary.confidence === 'strong' || summary.confidence === 'likely').length;
  const conflictCount = roleSummaries.reduce((total, item) => total + item.summary.conflicts.length, 0);
  const warningCount = unresolvedGroups + roleSummaries.reduce((total, item) => total + item.summary.warnings.length, 0);
  const facilityPressure = summarizeFacilityPressure(placements, templates);
  const nextActions = buildNextActions({
    placements,
    unresolvedGroups,
    mainStationCandidateCount: mainStationCandidates.length,
    previewStatus,
    observedFactsCount,
    exportBlockerCount,
  });
  const posture = buildPosture({
    placements,
    unresolvedGroups,
    previewStatus,
    observedFactsCount,
    exportBlockerCount,
  });

  return {
    postureLabel: posture.label,
    postureDetail: posture.detail,
    mainStationCandidates,
    supportBodies,
    unresolvedGroups,
    confidentRoleBodies,
    conflictCount,
    warningCount,
    facilityPressure,
    nextActions,
  };
}

function summarizeFacilityPressure(
  placements: SimulateBuildPlacement[],
  templates: FacilityTemplate[],
): string[] {
  const templatesById = new Map(templates.map((template) => [template.id, template]));
  const counts = new Map<string, number>();
  for (const placement of placements) {
    const template = templatesById.get(placement.facility_template_id);
    const key = template?.economy ?? template?.category ?? template?.name ?? placement.facility_template_id;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }

  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 3)
    .map(([label, count]) => `${label} x${count}`);
}

function buildNextActions({
  placements,
  unresolvedGroups,
  mainStationCandidateCount,
  previewStatus,
  observedFactsCount,
  exportBlockerCount,
}: {
  placements: SimulateBuildPlacement[];
  unresolvedGroups: number;
  mainStationCandidateCount: number;
  previewStatus: ReviewPreviewStatus;
  observedFactsCount: number;
  exportBlockerCount: number;
}): CockpitIntelligenceAction[] {
  const actions: CockpitIntelligenceAction[] = [];

  if (placements.length === 0) {
    actions.push({
      id: 'seed-plan',
      label: 'Seed the Build Plan',
      reason: 'Add the first facility or copy a Suggested Build so the cockpit has enough structure to reason about.',
      tone: 'neutral',
    });
    return actions;
  }

  if (unresolvedGroups > 0) {
    actions.push({
      id: 'assign-bodies',
      label: 'Resolve body assignments',
      reason: `${unresolvedGroups} placement group${unresolvedGroups === 1 ? '' : 's'} still need known body context before the plan can be trusted.`,
      tone: 'warn',
    });
  }

  if (mainStationCandidateCount === 0) {
    actions.push({
      id: 'set-main-station',
      label: 'Establish a main station candidate',
      reason: 'The current facility mix does not yet show a clear colony anchor or primary-port body.',
      tone: 'warn',
    });
  } else if (mainStationCandidateCount > 1) {
    actions.push({
      id: 'narrow-main-station',
      label: 'Narrow the main station body',
      reason: `${mainStationCandidateCount} bodies currently look like colony anchors, which keeps the plan strategically fuzzy.`,
      tone: 'warn',
    });
  }

  if (previewStatus === 'not_run') {
    actions.push({
      id: 'run-preview',
      label: 'Run Preview',
      reason: 'The next meaningful cockpit read depends on an explicit prediction for the current Build Plan.',
      tone: 'neutral',
    });
  } else if (previewStatus === 'stale') {
    actions.push({
      id: 'refresh-preview',
      label: 'Refresh Preview',
      reason: 'Preview exists, but the current plan has changed since that result was produced.',
      tone: 'warn',
    });
  } else if (observedFactsCount === 0) {
    actions.push({
      id: 'record-evidence',
      label: 'Record observed evidence',
      reason: 'The plan now has a current prediction, so the next trust-building step is comparing it with what you actually see in-game.',
      tone: 'neutral',
    });
  } else if (exportBlockerCount > 0) {
    actions.push({
      id: 'closeout-export',
      label: 'Close out export blockers',
      reason: `${exportBlockerCount} export blocker${exportBlockerCount === 1 ? '' : 's'} remain before the review pack is share-ready.`,
      tone: 'warn',
    });
  } else {
    actions.push({
      id: 'validate-and-export',
      label: 'Move through Validation and Export',
      reason: 'The current plan has prediction and evidence context, so the cockpit can shift from shaping to review and hand-off.',
      tone: 'good',
    });
  }

  return actions.slice(0, 3);
}

function buildPosture({
  placements,
  unresolvedGroups,
  previewStatus,
  observedFactsCount,
  exportBlockerCount,
}: {
  placements: SimulateBuildPlacement[];
  unresolvedGroups: number;
  previewStatus: ReviewPreviewStatus;
  observedFactsCount: number;
  exportBlockerCount: number;
}) {
  if (placements.length === 0) {
    return {
      label: 'Needs plan shape',
      detail: 'No facilities are placed yet, so facility intelligence stays intentionally conservative.',
    };
  }
  if (unresolvedGroups > 0) {
    return {
      label: 'Needs assignment discipline',
      detail: 'Facility signals exist, but unresolved body context still weakens the strategic read.',
    };
  }
  if (previewStatus !== 'current') {
    return {
      label: 'Needs current preview',
      detail: previewStatus === 'stale'
        ? 'The plan structure is intelligible, but Preview needs refreshing before downstream review should be trusted.'
        : 'The cockpit has a shape, but it still needs an explicit preview result before the plan can mature.',
    };
  }
  if (observedFactsCount === 0) {
    return {
      label: 'Ready for evidence',
      detail: 'Facility and role signals are coherent enough to take into in-game checking and evidence capture.',
    };
  }
  if (exportBlockerCount > 0) {
    return {
      label: 'Needs closeout review',
      detail: 'The review story is in place, but export readiness still has explicit blockers to resolve.',
    };
  }
  return {
    label: 'Review-ready posture',
    detail: 'Plan shape, current preview, and observed evidence are aligned enough for validation and hand-off work.',
  };
}
