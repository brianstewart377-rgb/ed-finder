import { useQuery } from '@tanstack/react-query';
import type { RegionLayerData, RegionLookupData } from './types';

export const AUTHORITATIVE_REGION_LAYER_PATH = 'stage26e/authoritative-regions.json';
export const AUTHORITATIVE_REGION_LABEL_COUNT = 42;
export const AUTHORITATIVE_REGION_BOUNDARY_LIMIT = 25_000;
export const AUTHORITATIVE_REGION_RESPONSE_BUDGET_BYTES = 4 * 1_048_576;

function isPoint(value: unknown): value is [number, number, number] {
  return Array.isArray(value)
    && value.length === 3
    && value.every((coordinate) => typeof coordinate === 'number' && Number.isFinite(coordinate));
}

function validateRegionLookup(value: unknown): RegionLookupData {
  if (!value || typeof value !== 'object') {
    throw new Error('Authoritative region layer must include its lookup grid');
  }
  const candidate = value as Partial<RegionLookupData>;
  if (
    !candidate.origin
    || typeof candidate.origin.x !== 'number'
    || !Number.isFinite(candidate.origin.x)
    || typeof candidate.origin.z !== 'number'
    || !Number.isFinite(candidate.origin.z)
    || typeof candidate.pixel_scale !== 'number'
    || !Number.isFinite(candidate.pixel_scale)
    || candidate.pixel_scale <= 0
  ) {
    throw new Error('Authoritative region lookup has invalid coordinates');
  }
  if (
    !Array.isArray(candidate.regions)
    || candidate.regions.length !== AUTHORITATIVE_REGION_LABEL_COUNT + 1
    || candidate.regions[0] !== ''
    || candidate.regions.slice(1).some((name) => typeof name !== 'string' || name.length === 0)
  ) {
    throw new Error('Authoritative region lookup has invalid region names');
  }
  if (
    !Array.isArray(candidate.regionmap)
    || candidate.regionmap.length === 0
    || candidate.regionmap.some((row) => (
      !Array.isArray(row)
      || row.length === 0
      || row.some((run) => (
        !Array.isArray(run)
        || run.length !== 2
        || !Number.isInteger(run[0])
        || run[0] <= 0
        || !Number.isInteger(run[1])
        || run[1] < 0
        || run[1] > AUTHORITATIVE_REGION_LABEL_COUNT
      ))
    ))
  ) {
    throw new Error('Authoritative region lookup has an invalid RLE grid');
  }
  const rowWidths = candidate.regionmap.map(
    (row) => row.reduce((width, [runLength]) => width + runLength, 0),
  );
  if (rowWidths.some((width) => width !== rowWidths[0])) {
    throw new Error('Authoritative region lookup rows must share one width');
  }
  return candidate as RegionLookupData;
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
  candidate.lookup = validateRegionLookup(candidate.lookup);
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
