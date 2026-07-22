import { useQuery } from '@tanstack/react-query';
import type { RegionLayerData } from './types';

export const AUTHORITATIVE_REGION_LAYER_PATH = 'stage26e/authoritative-regions.json';
export const AUTHORITATIVE_REGION_LABEL_COUNT = 42;
export const AUTHORITATIVE_REGION_BOUNDARY_LIMIT = 25_000;
export const AUTHORITATIVE_REGION_RESPONSE_BUDGET_BYTES = 4 * 1_048_576;

function isPoint(value: unknown): value is [number, number, number] {
  return Array.isArray(value)
    && value.length === 3
    && value.every((coordinate) => typeof coordinate === 'number' && Number.isFinite(coordinate));
}

export function validateAuthoritativeRegionLayer(value: unknown): RegionLayerData {
  if (!value || typeof value !== 'object') throw new Error('Authoritative region layer must be an object');
  const candidate = value as Partial<RegionLayerData>;
  if (!Array.isArray(candidate.labels) || candidate.labels.length !== AUTHORITATIVE_REGION_LABEL_COUNT) {
    throw new Error(`Authoritative region layer must contain ${AUTHORITATIVE_REGION_LABEL_COUNT} labels`);
  }
  if (!Array.isArray(candidate.boundaries) || candidate.boundaries.length > AUTHORITATIVE_REGION_BOUNDARY_LIMIT) {
    throw new Error(`Authoritative region layer exceeds ${AUTHORITATIVE_REGION_BOUNDARY_LIMIT} boundaries`);
  }
  const labelIds = new Set<number>();
  candidate.labels.forEach((label) => {
    if (!label || typeof label.id !== 'number' || !Number.isInteger(label.id)
      || typeof label.name !== 'string' || label.name.length === 0 || !isPoint(label.position)) {
      throw new Error('Authoritative region layer contains an invalid label');
    }
    labelIds.add(label.id);
  });
  if (labelIds.size !== AUTHORITATIVE_REGION_LABEL_COUNT) {
    throw new Error('Authoritative region layer label ids must be unique');
  }
  candidate.boundaries.forEach((boundary) => {
    if (!boundary || !isPoint(boundary.source) || !isPoint(boundary.target)) {
      throw new Error('Authoritative region layer contains an invalid boundary');
    }
  });
  return candidate as RegionLayerData;
}

export async function fetchAuthoritativeRegionLayer(): Promise<RegionLayerData> {
  const response = await fetch(`${import.meta.env.BASE_URL}${AUTHORITATIVE_REGION_LAYER_PATH}`, { cache: 'no-cache' });
  if (!response.ok) throw new Error(`Authoritative region layer request failed: ${response.status}`);
  const body = await response.text();
  if (new TextEncoder().encode(body).byteLength > AUTHORITATIVE_REGION_RESPONSE_BUDGET_BYTES) {
    throw new Error('Authoritative region layer exceeds its response budget');
  }
  return validateAuthoritativeRegionLayer(JSON.parse(body) as unknown);
}

export function useAuthoritativeRegionLayer(enabled = true) {
  return useQuery<RegionLayerData, Error>({
    queryKey: ['stage26e', 'authoritative-regions'],
    queryFn: fetchAuthoritativeRegionLayer,
    enabled,
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: Number.POSITIVE_INFINITY,
  });
}
