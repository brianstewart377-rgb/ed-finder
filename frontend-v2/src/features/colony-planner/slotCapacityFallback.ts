import type { BodySlotPrediction, SystemBody, SystemDetail } from '@/types/api';
import { bodyIdKey } from '@/features/system-detail/simulation-preview/bodyIdUtils';
import type { TopologyPlanSnapshot } from './ColonyTopologyRail';

export type SlotCapacityLane = 'orbital' | 'surface';

export interface ResolvedSlotCapacity {
  value: number | null;
  estimated: boolean;
}

export const ESTIMATED_SLOT_LAYOUT_DISCLAIMER = 'Slot layout estimated from body data (Not 100% verified).';

export function resolveSlotCapacity(
  body: SystemBody,
  prediction: BodySlotPrediction | null,
  lane: SlotCapacityLane,
): ResolvedSlotCapacity {
  const predicted = normaliseSlotCount(lane === 'orbital'
    ? prediction?.predicted_orbital_slots
    : prediction?.predicted_ground_slots);

  if (prediction?.prediction_status === 'observed') {
    return { value: predicted, estimated: false };
  }

  if (predicted != null && predicted > 0) {
    return { value: predicted, estimated: false };
  }

  const fallback = estimateBodySlots(body);
  const estimatedValue = lane === 'orbital' ? fallback?.orbital : fallback?.surface;
  if (estimatedValue != null && (predicted == null || estimatedValue > predicted)) {
    return { value: estimatedValue, estimated: true };
  }

  return { value: predicted, estimated: false };
}

export function hasEstimatedSlotFallback(system: SystemDetail, snapshot: TopologyPlanSnapshot): boolean {
  const predictionsByBodyId = new Map(
    (snapshot.slotPredictions?.predictions ?? []).map((prediction) => [bodyIdKey(prediction.body_id), prediction]),
  );

  return (system.bodies ?? []).some((body) => {
    if (body.id == null) return false;
    const prediction = predictionsByBodyId.get(bodyIdKey(body.id)) ?? null;
    return resolveSlotCapacity(body, prediction, 'orbital').estimated
      || resolveSlotCapacity(body, prediction, 'surface').estimated;
  });
}

function estimateBodySlots(body: SystemBody): { orbital: number; surface: number | null } | null {
  if (!isBuildableBodyCandidate(body)) return null;

  const radiusKm = readRadiusKm(body);
  if (radiusKm == null) return null;

  const orbitalBase = radiusBaseSlots(radiusKm);
  const orbital = clampSlotCount(orbitalBase + (readBoolean(body, 'is_ringed') ? 1 : 0), 1, 4);

  if (body.is_landable !== true || body.is_water_world === true) {
    return { orbital, surface: 0 };
  }

  const surfaceTemp = readNumber(body, 'surface_temp');
  if (surfaceTemp != null && surfaceTemp > 700) {
    return { orbital, surface: 0 };
  }

  const gravity = readNumber(body, 'gravity');
  if (gravity != null && gravity > 2.7) {
    return { orbital, surface: 0 };
  }

  let bonus = 0;
  const planetClass = String(body.subtype ?? '').trim().toLowerCase();
  if (planetClass === 'high metal content world' || planetClass === 'high metal content body') bonus += 1;
  if (body.is_terraformable === true) bonus += 1;
  if ((body.geo_signal_count ?? 0) > 0 || hasVolcanism(body)) bonus += 1;
  if ((body.bio_signal_count ?? 0) > 0) bonus += 1;
  bonus += atmosphereBonus(body);

  const surface = Math.min(radiusBaseSlots(radiusKm) + Math.min(bonus, 3), 7);
  return { orbital, surface };
}

function isBuildableBodyCandidate(body: SystemBody): boolean {
  const type = `${body.body_type ?? ''} ${body.subtype ?? ''}`.toLowerCase();
  return !type.includes('star') && !type.includes('barycentre');
}

function readRadiusKm(body: SystemBody): number | null {
  const radius = readNumber(body, 'radius');
  if (radius == null || radius <= 0) return null;
  return radius > 50_000 ? radius / 1000 : radius;
}

function radiusBaseSlots(radiusKm: number): number {
  if (radiusKm < 1500) return 1;
  if (radiusKm < 3750) return 2;
  if (radiusKm < 5500) return 3;
  return 4;
}

function atmosphereBonus(body: SystemBody): number {
  const atmosphere = readString(body, 'atmosphere') ?? readString(body, 'atmosphere_type');
  if (!atmosphere) return 0;
  const normalised = atmosphere.toLowerCase();
  if (normalised === 'no atmosphere') return 0;
  return normalised.includes('thin') ? 1 : 2;
}

function hasVolcanism(body: SystemBody): boolean {
  const volcanism = readString(body, 'volcanism');
  if (!volcanism) return false;
  const normalised = volcanism.toLowerCase();
  return normalised !== 'no volcanism' && normalised !== 'none';
}

function normaliseSlotCount(value: unknown): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return null;
  return Math.floor(value);
}

function readNumber(body: SystemBody, key: string): number | null {
  const value = (body as Record<string, unknown>)[key];
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function readBoolean(body: SystemBody, key: string): boolean {
  const value = (body as Record<string, unknown>)[key];
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value !== 0;
  if (typeof value === 'string') return ['true', 't', '1', 'yes', 'y'].includes(value.trim().toLowerCase());
  return false;
}

function readString(body: SystemBody, key: string): string | null {
  const value = (body as Record<string, unknown>)[key];
  if (value == null) return null;
  const text = String(value).trim();
  return text || null;
}

function clampSlotCount(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
