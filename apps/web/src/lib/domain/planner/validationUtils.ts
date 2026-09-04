/**
 * Pure helpers for planner validation.
 *
 * They make no API calls. The compare request and its cache fingerprint must
 * use the same projection so no backend-relevant prediction change is hidden
 * behind an unchanged key.
 */
import type {
  ObservedJsonValue,
  PredictionObservationComparison,
  SimulateBuildResponse,
} from './types';

type ValidationPredictionSource = Pick<
  SimulateBuildResponse,
  | 'final_score'
  | 'confidence'
  | 'cp'
  | 'economy_composition'
  | 'economy_order'
  | 'services'
  | 'port_service_states'
>;

/**
 * The complete prediction input consumed by the comparison backend.
 *
 * Validation sends this projection to the compare endpoint and uses the same
 * value for its cache fingerprint.
 */
export function validationInputProjection(
  result: ValidationPredictionSource,
): Record<string, unknown> {
  return {
    final_score: result.final_score,
    confidence: result.confidence,
    cp: {
      yellow_cp_final: result.cp.yellow_cp_final,
      green_cp_final: result.cp.green_cp_final,
      yellow_cp_generated: result.cp.yellow_cp_generated,
      green_cp_generated: result.cp.green_cp_generated,
      yellow_cp_spent: result.cp.yellow_cp_spent,
      green_cp_spent: result.cp.green_cp_spent,
      t2_ports: result.cp.t2_ports,
      t3_ports: result.cp.t3_ports,
      warnings: [...result.cp.warnings],
    },
    economy_composition: sortedRecord(result.economy_composition),
    economy_order: [...result.economy_order],
    services: Object.fromEntries(
      Object.entries(result.services)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([serviceId, service]) => [serviceId, service?.status ?? null]),
    ),
    port_service_states: normalisePortServiceStates(result.port_service_states),
  };
}

/** Stable fingerprint of the exact validation prediction projection. */
export function previewResultFingerprint(
  result: ValidationPredictionSource | null,
): string | null {
  if (!result) return null;
  return JSON.stringify(validationInputProjection(result));
}

function sortedRecord<T>(record: Record<string, T>): Record<string, T> {
  return Object.fromEntries(
    Object.entries(record).sort(([left], [right]) => left.localeCompare(right)),
  );
}

function normalisePortServiceStates(
  states: SimulateBuildResponse['port_service_states'],
): Array<Record<string, Record<string, true>>> {
  if (states.length === 0) return [];

  const active = new Set<string>();
  const locked = new Set<string>();
  const unknown = new Set<string>();

  for (const state of states) {
    Object.keys(state.active_services).forEach((serviceId) =>
      active.add(serviceId),
    );
    Object.keys(state.locked_services).forEach((serviceId) =>
      locked.add(serviceId),
    );
    Object.keys(state.unknown_services).forEach((serviceId) =>
      unknown.add(serviceId),
    );
  }

  // Match backend precedence: active > locked > unknown > top-level service.
  active.forEach((serviceId) => {
    locked.delete(serviceId);
    unknown.delete(serviceId);
  });
  locked.forEach((serviceId) => unknown.delete(serviceId));

  return [
    {
      active_services: setRecord(active),
      locked_services: setRecord(locked),
      unknown_services: setRecord(unknown),
    },
  ];
}

function setRecord(values: Set<string>): Record<string, true> {
  return Object.fromEntries(
    [...values]
      .sort((left, right) => left.localeCompare(right))
      .map((value) => [value, true]),
  );
}

/** Render a predicted/observed comparison value for display. */
export function formatComparisonValue(
  value: ObservedJsonValue | null | undefined,
): string {
  if (value === undefined || value === null) return '—';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

/**
 * Filter comparison rows by exact status. An empty filter returns every row,
 * including statuses introduced by newer backends.
 */
export function filterComparisonsByStatus(
  comparisons: PredictionObservationComparison[],
  statusFilter: string | null,
): PredictionObservationComparison[] {
  if (!statusFilter) return comparisons;
  return comparisons.filter((row) => row.status === statusFilter);
}
