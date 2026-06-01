import type {
  FacilityTemplate,
  OptimiserCandidate,
  OptimiserCandidatePlacement,
  SimulateBuildPlacement,
  SlotPredictionResponse,
  SystemBody,
  SystemDetail,
} from '@/types/api';
import type { BodyPlannerLane } from '@/features/colony-planner/BodySlotPlanner';
import { roleCompactLabel, type DeclaredColonyRole } from '@/features/colony-planner/colonyRoles';
import { resolveExistingInfrastructure } from '@/features/colony-planner/existingInfrastructure';
import { compactEconomyLabel, normalisePlanningEconomy } from '@/features/colony-planner/planningEconomy';
import { buildBodyDataSlotEstimateMap, resolveSlotCapacity, systemBodyData } from '@/features/colony-planner/slotCapacityFallback';
import { placementLaneForTemplate } from '@/features/colony-planner/structurePlanningRules';
import { bodyDisplayName, bodyTags } from '../buildPlanLayoutUtils';
import { bodyIdKey } from '../bodyIdUtils';

export interface SuggestedBuildStrategyAdvisor {
  cardLine: string;
  bodyChoice: string;
  existingInfrastructure: string;
  slotPressure: string;
  economyIntent: string;
  roleContext: string;
  uncertainty: string;
  projectionEffect: string;
  manualBoundary: string;
}

interface AdvisorInput {
  candidate: OptimiserCandidate;
  system?: SystemDetail | null;
  templates?: FacilityTemplate[];
  bodyLabelsById?: Record<string, string>;
  currentPreviewPlacements?: SimulateBuildPlacement[];
  declaredRoles?: DeclaredColonyRole[];
  slotPredictions?: SlotPredictionResponse | null;
}

type PlacementLike = Pick<SimulateBuildPlacement | OptimiserCandidatePlacement, 'facility_template_id' | 'local_body_id'>;

interface LaneCounts {
  orbital: number;
  surface: number;
}

interface PlacementLaneSummary {
  byBodyId: Map<string, LaneCounts>;
  unassignedBody: number;
  unknownBody: number;
  unknownLane: number;
  missingTemplate: number;
}

export function buildSuggestedBuildStrategyAdvisor({
  candidate,
  system,
  templates = [],
  bodyLabelsById = {},
  currentPreviewPlacements = [],
  declaredRoles = [],
  slotPredictions = null,
}: AdvisorInput): SuggestedBuildStrategyAdvisor {
  const templatesById = new Map(templates.map((template) => [template.id, template]));
  const bodies = system ? systemBodyData(system) : [];
  const bodiesById = new Map(
    bodies
      .filter((body) => body.id != null)
      .map((body) => [bodyIdKey(body.id), body]),
  );
  const usedBodyIds = candidateBodyIds(candidate);
  const mainBodyId = bodyIdKey(
    candidate.placements.find((placement) => placement.is_primary_port)?.local_body_id
      ?? usedBodyIds[0]
      ?? null,
  ) || null;
  const labelForBody = (bodyId: string) => (
    bodyLabelsById[bodyId] ?? bodyLabelsById[bodyIdKey(bodyId)] ?? (bodiesById.get(bodyId) ? bodyDisplayName(bodiesById.get(bodyId)!) : `Body ${bodyId}`)
  );

  const currentLaneSummary = summarizePlacementLanes(currentPreviewPlacements, templatesById, bodiesById);
  const projectedLaneSummary = summarizePlacementLanes(candidate.placements, templatesById, bodiesById);
  const existingResolution = system ? resolveExistingInfrastructure(system) : null;

  const bodyChoice = describeBodyChoice({
    mainBodyId,
    usedBodyIds,
    bodiesById,
    labelForBody,
    projectedLaneSummary,
  });
  const roleContext = describeDeclaredRoles(usedBodyIds, declaredRoles, labelForBody);
  const existingInfrastructure = describeExistingInfrastructure({
    usedBodyIds,
    existingResolution,
  });
  const slotPressure = describeSlotPressure({
    system,
    bodiesById,
    labelForBody,
    currentLaneSummary,
    projectedLaneSummary,
    slotPredictions,
    existingResolution,
  });
  const economyIntent = describeEconomyIntent(candidate, templatesById);
  const uncertainty = describeUncertainty({
    candidate,
    system,
    bodies,
    projectedLaneSummary,
    slotPredictions,
  });
  const projectionEffect = describeProjectionEffect(candidate, usedBodyIds, projectedLaneSummary);
  const manualBoundary = 'Manual boundary: select projects read-only ghosts, Load explicitly copies this candidate into the editable Build Plan, and Run Preview remains explicit.';

  return {
    cardLine: cardLineFor({ slotPressure, existingInfrastructure, uncertainty }),
    bodyChoice,
    existingInfrastructure,
    slotPressure,
    economyIntent,
    roleContext,
    uncertainty,
    projectionEffect,
    manualBoundary,
  };
}

function describeBodyChoice({
  mainBodyId,
  usedBodyIds,
  bodiesById,
  labelForBody,
  projectedLaneSummary,
}: {
  mainBodyId: string | null;
  usedBodyIds: string[];
  bodiesById: Map<string, SystemBody>;
  labelForBody: (bodyId: string) => string;
  projectedLaneSummary: PlacementLaneSummary;
}) {
  if (!mainBodyId && usedBodyIds.length === 0) {
    return 'Body choice: system-level candidate with no explicit body assignments yet; body and lane selection need manual review.';
  }
  if (!mainBodyId) {
    return `Body choice: ${usedBodyIds.map(labelForBody).join(', ')}. No primary-port body is declared by this candidate.`;
  }

  const mainBody = bodiesById.get(mainBodyId);
  const tags = mainBody ? bodyTags(mainBody).slice(0, 3).join(', ') : null;
  const supportBodies = usedBodyIds.filter((bodyId) => bodyId !== mainBodyId).map(labelForBody);
  const unresolved = projectedLaneSummary.unknownBody > 0
    ? ` ${projectedLaneSummary.unknownBody} placement(s) reference bodies not present in current body data.`
    : '';
  const support = supportBodies.length > 0 ? ` Support bodies: ${supportBodies.join(', ')}.` : '';

  return `Body choice: main body is ${labelForBody(mainBodyId)}${tags ? ` (${tags})` : ''}.${support}${unresolved}`;
}

function describeDeclaredRoles(
  usedBodyIds: string[],
  declaredRoles: DeclaredColonyRole[],
  labelForBody: (bodyId: string) => string,
) {
  if (declaredRoles.length === 0) return 'Declared roles: none available for candidate context.';
  const used = new Set(usedBodyIds);
  const rolesByBody = new Map<string, string[]>();
  declaredRoles.forEach((role) => {
    const key = bodyIdKey(role.body_id);
    if (!used.has(key)) return;
    const labels = rolesByBody.get(key) ?? [];
    labels.push(roleCompactLabel(role.role_id));
    rolesByBody.set(key, labels);
  });

  if (rolesByBody.size === 0) {
    return 'Declared roles: roles exist elsewhere, but none are on the projected candidate bodies.';
  }

  const parts = Array.from(rolesByBody.entries()).map(([bodyId, labels]) => (
    `${labelForBody(bodyId)}: ${Array.from(new Set(labels)).join(', ')}`
  ));
  return `Declared roles: ${parts.join('; ')}. Advisory only; no role mechanics are applied.`;
}

function describeExistingInfrastructure({
  usedBodyIds,
  existingResolution,
}: {
  usedBodyIds: string[];
  existingResolution: ReturnType<typeof resolveExistingInfrastructure> | null;
}) {
  if (!existingResolution) {
    return 'Existing infrastructure: system context is unavailable in this view.';
  }
  const permanent = existingResolution.structures.filter((structure) => !structure.transient);
  if (permanent.length === 0) {
    return 'Existing infrastructure: none visible in the current system data.';
  }

  const used = new Set(usedBodyIds);
  const onCandidateBodies = existingResolution.mapped.filter((structure) => used.has(bodyIdKey(structure.body_id)));
  const confirmed = onCandidateBodies.filter((structure) => structure.association_status === 'confirmed').length;
  const inferred = onCandidateBodies.filter((structure) => structure.association_status === 'inferred').length;
  const unresolved = existingResolution.unresolved.length;
  const unknownLane = existingResolution.unresolved.filter((structure) => structure.lane === 'unknown').length;
  const candidateLine = onCandidateBodies.length > 0
    ? `${onCandidateBodies.length} existing slot occupant(s) on projected candidate bodies (${confirmed} confirmed, ${inferred} verify/inferred).`
    : `${existingResolution.mapped.length} mapped existing slot occupant(s) are visible, but none are on projected candidate bodies.`;
  const unresolvedLine = unresolved > 0
    ? ` ${unresolved} unresolved${unknownLane > 0 ? ` / ${unknownLane} unknown-lane` : ''} infrastructure item(s) stay visible but are not forced into a lane.`
    : '';

  return `Existing infrastructure: ${candidateLine} Existing items remain Existing and are not Build Plan placements.${unresolvedLine}`;
}

function describeSlotPressure({
  system,
  bodiesById,
  labelForBody,
  currentLaneSummary,
  projectedLaneSummary,
  slotPredictions,
  existingResolution,
}: {
  system?: SystemDetail | null;
  bodiesById: Map<string, SystemBody>;
  labelForBody: (bodyId: string) => string;
  currentLaneSummary: PlacementLaneSummary;
  projectedLaneSummary: PlacementLaneSummary;
  slotPredictions: SlotPredictionResponse | null;
  existingResolution: ReturnType<typeof resolveExistingInfrastructure> | null;
}) {
  const unresolvedProjection = projectedLaneSummary.unassignedBody
    + projectedLaneSummary.unknownBody
    + projectedLaneSummary.unknownLane
    + projectedLaneSummary.missingTemplate;
  const projectedLaneEntries = Array.from(projectedLaneSummary.byBodyId.entries())
    .flatMap(([bodyId, counts]) => ([
      { bodyId, lane: 'orbital' as BodyPlannerLane, projected: counts.orbital },
      { bodyId, lane: 'surface' as BodyPlannerLane, projected: counts.surface },
    ]))
    .filter((entry) => entry.projected > 0);

  if (!system || projectedLaneEntries.length === 0) {
    if (unresolvedProjection > 0) {
      return `Slot pressure: ${unresolvedProjection} projected placement(s) need body/lane/template resolution before lane capacity can be checked; they remain ghost-only.`;
    }
    return 'Slot pressure: no lane-specific projected occupancy is available for this candidate.';
  }

  const predictionByBodyId = new Map(
    (slotPredictions?.predictions ?? []).map((prediction) => [bodyIdKey(prediction.body_id), prediction]),
  );
  const estimateMap = buildBodyDataSlotEstimateMap(system, slotPredictions?.predictions);
  const entries = projectedLaneEntries.map((entry) => {
    const body = bodiesById.get(entry.bodyId);
    const current = currentLaneSummary.byBodyId.get(entry.bodyId)?.[entry.lane] ?? 0;
    const existing = existingResolution?.byBodyId.get(entry.bodyId)?.[entry.lane].length ?? 0;
    const capacity = body
      ? resolveSlotCapacity(body, predictionByBodyId.get(entry.bodyId) ?? null, entry.lane, estimateMap.get(entry.bodyId))
      : { value: null, estimated: false };
    const remainingBeforeProjection = capacity.value == null ? null : capacity.value - existing - current;
    const remainingAfterProjection = capacity.value == null ? null : capacity.value - existing - current - entry.projected;
    return {
      ...entry,
      body,
      current,
      existing,
      capacity,
      remainingBeforeProjection,
      remainingAfterProjection,
    };
  }).sort((left, right) => {
    const leftOver = (left.remainingAfterProjection ?? 0) < 0 ? 1 : 0;
    const rightOver = (right.remainingAfterProjection ?? 0) < 0 ? 1 : 0;
    if (leftOver !== rightOver) return rightOver - leftOver;
    return right.projected - left.projected;
  });

  const entry = entries[0];
  const laneLabel = entry.lane === 'orbital' ? 'Orbit' : 'Surface';
  const capacityLabel = entry.capacity.value == null
    ? 'capacity unknown'
    : `${entry.capacity.estimated ? 'estimated' : 'predicted'} capacity ${entry.capacity.value}`;
  const prefix = `${labelForBody(entry.bodyId)} ${laneLabel}: ${capacityLabel}, existing ${entry.existing}, planned ${entry.current}, projected ghost ${entry.projected}`;
  if (entry.remainingAfterProjection != null && entry.remainingAfterProjection < 0) {
    return `Slot pressure: ${prefix}; projection would exceed visible capacity by ${Math.abs(entry.remainingAfterProjection)}.`;
  }
  if (entry.remainingBeforeProjection != null && entry.remainingAfterProjection != null) {
    return `Slot pressure: ${prefix}; ${entry.remainingBeforeProjection} remaining before projection (${entry.remainingAfterProjection} after projection).`;
  }
  return `Slot pressure: ${prefix}; unknown capacity remains unknown until verified in the Raven canvas.`;
}

function describeEconomyIntent(
  candidate: OptimiserCandidate,
  templatesById: Map<string, FacilityTemplate>,
) {
  const counts = new Map<ReturnType<typeof normalisePlanningEconomy>, number>();
  let contextualPorts = 0;
  let unknown = 0;
  candidate.placements.forEach((placement) => {
    const template = templatesById.get(placement.facility_template_id);
    const economy = normalisePlanningEconomy(template?.economy);
    if (economy) {
      counts.set(economy, (counts.get(economy) ?? 0) + 1);
    } else if (template?.is_port) {
      contextualPorts += 1;
    } else {
      unknown += 1;
    }
  });

  const economies = Array.from(counts.entries())
    .filter((entry): entry is [NonNullable<ReturnType<typeof normalisePlanningEconomy>>, number] => Boolean(entry[0]))
    .sort((left, right) => right[1] - left[1])
    .slice(0, 3)
    .map(([economy, count]) => `${compactEconomyLabel(economy)} x${count}`);
  const economyLine = economies.length > 0
    ? `Economy intent: ${economies.join(', ')}.`
    : 'Economy intent: contextual or unknown from available templates.';
  const portLine = contextualPorts > 0
    ? ` ${contextualPorts} port placement(s) need Preview to validate inherited economy.`
    : '';
  const unknownLine = unknown > 0
    ? ` ${unknown} placement(s) have unknown economy metadata.`
    : '';
  return `${economyLine}${portLine}${unknownLine}`;
}

function describeUncertainty({
  candidate,
  system,
  bodies,
  projectedLaneSummary,
  slotPredictions,
}: {
  candidate: OptimiserCandidate;
  system?: SystemDetail | null;
  bodies: SystemBody[];
  projectedLaneSummary: PlacementLaneSummary;
  slotPredictions: SlotPredictionResponse | null;
}) {
  const signals = new Set<string>();
  const warningText = [...candidate.warnings, ...candidate.assumptions].join(' ').toLowerCase();
  if (/\b(sparse|estimated|inferred|no body|no matching|limited|unavailable|preview failed)\b/.test(warningText)) {
    signals.add('candidate warnings or assumptions use sparse, estimated, or incomplete data');
  }
  if (!system) signals.add('system context is unavailable');
  if (system && bodies.length === 0) signals.add('body catalogue is unavailable');
  if (slotPredictions?.prediction_status === 'unknown' || slotPredictions?.data_source === 'none') {
    signals.add('slot prediction status is unknown');
  }
  if (projectedLaneSummary.unassignedBody > 0) signals.add('some projected placements have no body assignment');
  if (projectedLaneSummary.unknownBody > 0) signals.add('some projected bodies are not in current body data');
  if (projectedLaneSummary.unknownLane > 0) signals.add('some projected lanes cannot be inferred from template/body data');
  if (projectedLaneSummary.missingTemplate > 0) signals.add('some facility templates are missing from the loaded catalogue');
  if (!candidate.preview_summary) {
    signals.add('lightweight preview summary is unavailable');
  } else if (candidate.preview_summary.confidence != null && candidate.preview_summary.confidence < 0.5) {
    signals.add('lightweight preview confidence is low');
  }

  if (signals.size === 0) {
    return 'Uncertainty: no additional data-quality signal beyond the candidate warnings; verify before loading or previewing.';
  }
  return `Uncertainty: ${Array.from(signals).join('; ')}.`;
}

function describeProjectionEffect(
  candidate: OptimiserCandidate,
  usedBodyIds: string[],
  projectedLaneSummary: PlacementLaneSummary,
) {
  const unresolvedProjection = projectedLaneSummary.unassignedBody
    + projectedLaneSummary.unknownBody
    + projectedLaneSummary.unknownLane
    + projectedLaneSummary.missingTemplate;
  const bodyCount = usedBodyIds.length || 1;
  const unresolvedLine = unresolvedProjection > 0
    ? ` ${unresolvedProjection} placement(s) need manual body/lane/template review before capacity is reliable.`
    : '';
  return `Projection effect: selecting this candidate shows ${candidate.placements.length} ghost structure(s) across ${bodyCount} body/bodies on the Raven canvas; ghosts do not count as planned placements.${unresolvedLine}`;
}

function cardLineFor({
  slotPressure,
  existingInfrastructure,
  uncertainty,
}: {
  slotPressure: string;
  existingInfrastructure: string;
  uncertainty: string;
}) {
  if (/exceed visible capacity/i.test(slotPressure)) return 'Slot pressure needs review before loading.';
  if (/unresolved|unknown-lane/i.test(existingInfrastructure)) return 'Existing or unresolved infrastructure is called out in details.';
  if (/sparse|estimated|unknown|unavailable|missing/i.test(uncertainty)) return 'Sparse or estimated data is called out in details.';
  return 'Projection stays ghost-only until explicit load.';
}

function candidateBodyIds(candidate: OptimiserCandidate): string[] {
  return Array.from(new Set(
    candidate.placements
      .map((placement) => bodyIdKey(placement.local_body_id))
      .filter((bodyId) => Boolean(bodyId)),
  ));
}

function summarizePlacementLanes(
  placements: PlacementLike[],
  templatesById: Map<string, FacilityTemplate>,
  bodiesById: Map<string, SystemBody>,
): PlacementLaneSummary {
  const byBodyId = new Map<string, LaneCounts>();
  const summary: PlacementLaneSummary = {
    byBodyId,
    unassignedBody: 0,
    unknownBody: 0,
    unknownLane: 0,
    missingTemplate: 0,
  };

  placements.forEach((placement) => {
    const bodyId = bodyIdKey(placement.local_body_id);
    if (!bodyId) {
      summary.unassignedBody += 1;
      return;
    }
    const body = bodiesById.get(bodyId);
    if (!body) {
      summary.unknownBody += 1;
      return;
    }
    const template = templatesById.get(placement.facility_template_id);
    if (!template) {
      summary.missingTemplate += 1;
      return;
    }
    const lane = placementLaneForTemplate(template, body);
    if (lane !== 'orbital' && lane !== 'surface') {
      summary.unknownLane += 1;
      return;
    }
    const counts = byBodyId.get(bodyId) ?? { orbital: 0, surface: 0 };
    counts[lane] += 1;
    byBodyId.set(bodyId, counts);
  });

  return summary;
}
