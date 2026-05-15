/**
 * Pure helpers for the Stage 6D Validation panel.
 *
 * These helpers do NOT call the API. They produce stable cache keys for
 * the prediction (so the compare query refreshes when the preview
 * changes) and format compare-API values for display.
 */
import type {
  ObservedJsonValue,
  PredictionObservationComparison,
  SimulateBuildResponse,
} from '@/types/api';

/**
 * Stable fingerprint of a Simulation Preview result.
 *
 * The query key for the compare API includes this fingerprint so that:
 *   * two distinct preview runs against the same system+archetype with
 *     different placements produce different query keys (and therefore
 *     fresh compare calls);
 *   * an unchanged preview result reuses the cached compare response
 *     without a network call.
 *
 * We only include fields the backend comparison engine reads. The
 * fingerprint must be stable across re-renders, so we extract those
 * fields rather than hashing the whole response object.
 */
export function previewResultFingerprint(result: SimulateBuildResponse | null): string | null {
  if (!result) return null;
  return JSON.stringify({
    system_id64: result.system_id64,
    target_archetype: result.target_archetype,
    mechanics_version: result.mechanics_version,
    final_score: result.final_score,
    composition_score: result.composition_score,
    buildability_score: result.buildability_score,
    confidence: result.confidence,
    cp: result.cp,
    economy_order: result.economy_order,
    economy_composition: result.economy_composition,
    services: result.services
      ? Object.fromEntries(
          Object.entries(result.services).map(([key, value]) => [key, value?.status ?? null]),
        )
      : null,
    port_service_states: result.port_service_states,
    top_two_alignment: result.top_two_alignment,
  });
}

/**
 * Render an `observed_value` / `predicted_value` for display in the
 * Validation card. Mirrors the Stage 6B formatter but lives here so
 * the Validation panel does not depend on Observed Evidence internals.
 */
export function formatComparisonValue(value: ObservedJsonValue | null | undefined): string {
  if (value === undefined || value === null) return '—';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

/**
 * Filter comparison rows by status. An empty status filter returns the
 * full list. Unknown statuses are passed through verbatim so the UI
 * doesn't silently drop rows the backend introduces in a later stage.
 */
export function filterComparisonsByStatus(
  comparisons: PredictionObservationComparison[],
  statusFilter: string | null,
): PredictionObservationComparison[] {
  if (!statusFilter) return comparisons;
  return comparisons.filter((row) => row.status === statusFilter);
}
