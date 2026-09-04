import type {
  OptimiserCandidatePlacement,
  SimulateBuildPlacement,
} from './types';

/**
 * Normalise an optimiser candidate into the deterministic placement form used
 * by planner previews and comparisons.
 */
export function candidatePlacementsToPreviewPlacements(
  placements: OptimiserCandidatePlacement[],
): SimulateBuildPlacement[] {
  let primaryPortAssigned = false;
  return [...placements]
    .sort((a, b) => a.build_order - b.build_order)
    .map((placement, index) => {
      const isPrimaryPort = Boolean(
        placement.is_primary_port && !primaryPortAssigned,
      );
      if (isPrimaryPort) {
        primaryPortAssigned = true;
      }
      return {
        facility_template_id: placement.facility_template_id,
        local_body_id: placement.local_body_id ?? null,
        is_primary_port: isPrimaryPort,
        build_order: index + 1,
      };
    });
}
