import type { Route } from '@/hooks/useHashRoute';
import manifest from './hostedReviewAvailability.manifest.json';

export type HostedReviewAvailabilityState = 'supported' | 'intentionally_unavailable' | 'excluded';

export interface HostedReviewFeatureAvailability {
  key: string;
  label: string;
  state: HostedReviewAvailabilityState;
  rationale: string;
  routes: string[];
}

interface HostedReviewAvailabilityManifest {
  features: HostedReviewFeatureAvailability[];
}

const ALLOWED_STATES = new Set<HostedReviewAvailabilityState>([
  'supported',
  'intentionally_unavailable',
  'excluded',
]);

const HASH_ROUTE_TO_ROUTE = new Map<string, Route>([
  ['#finder', 'finder'],
  ['#my-work', 'my-work'],
  ['#watchlist', 'watchlist'],
  ['#pinned', 'pinned'],
  ['#map', 'map'],
  ['#search-tuning', 'search-tuning'],
  ['#optimizer', 'search-tuning'],
  ['#admin', 'admin'],
  ['#operator', 'operator'],
  ['#colony-planner', 'colony-planner'],
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function readRequiredString(row: Record<string, unknown>, key: string, index: number): string {
  const value = row[key];
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`Hosted-review availability manifest row ${index} requires a non-empty ${key}.`);
  }
  return value;
}

export function validateHostedReviewAvailabilityManifest(candidate: unknown): HostedReviewAvailabilityManifest {
  if (!isRecord(candidate) || !Array.isArray(candidate.features)) {
    throw new Error('Hosted-review availability manifest must expose a features array.');
  }

  const featureKeys = new Set<string>();
  const routeOwners = new Map<string, string>();
  const features = candidate.features.map((row, index) => {
    if (!isRecord(row)) {
      throw new Error(`Hosted-review availability manifest row ${index} must be an object.`);
    }

    const key = readRequiredString(row, 'key', index);
    const label = readRequiredString(row, 'label', index);
    const state = readRequiredString(row, 'state', index);
    const rationale = readRequiredString(row, 'rationale', index);
    const routesValue = row.routes ?? [];

    if (!ALLOWED_STATES.has(state as HostedReviewAvailabilityState)) {
      throw new Error(`Hosted-review availability manifest row ${index} has invalid state ${state}.`);
    }
    if (featureKeys.has(key)) {
      throw new Error(`Hosted-review availability manifest duplicates feature key ${key}.`);
    }
    featureKeys.add(key);
    if (!Array.isArray(routesValue) || !routesValue.every((route) => typeof route === 'string' && route.trim() !== '' && route.startsWith('#'))) {
      throw new Error(`Hosted-review availability manifest row ${index} routes must be non-empty hash route strings.`);
    }

    const routes = routesValue as string[];
    for (const route of routes) {
      if (!HASH_ROUTE_TO_ROUTE.has(route)) {
        throw new Error(`Hosted-review availability manifest route ${route} is not a known hosted-review hash route.`);
      }
      const owner = routeOwners.get(route);
      if (owner) {
        throw new Error(`Hosted-review availability manifest route ${route} is owned by both ${owner} and ${key}.`);
      }
      routeOwners.set(route, key);
    }

    return {
      key,
      label,
      state: state as HostedReviewAvailabilityState,
      rationale,
      routes,
    };
  });

  return { features };
}

const HOSTED_REVIEW_AVAILABILITY_MANIFEST = validateHostedReviewAvailabilityManifest(manifest);

export const HOSTED_REVIEW_FEATURE_AVAILABILITY: HostedReviewFeatureAvailability[] = HOSTED_REVIEW_AVAILABILITY_MANIFEST.features;

const ROUTE_AVAILABILITY = new Map<Route, HostedReviewFeatureAvailability>();
for (const feature of HOSTED_REVIEW_FEATURE_AVAILABILITY) {
  for (const hashRoute of feature.routes) {
    const route = HASH_ROUTE_TO_ROUTE.get(hashRoute);
    if (!route) {
      throw new Error(`Hosted-review availability manifest route ${hashRoute} is not a known hosted-review hash route.`);
    }
    ROUTE_AVAILABILITY.set(route, feature);
  }
}

export function hostedReviewAvailabilityForRoute(route: Route): HostedReviewFeatureAvailability | null {
  return ROUTE_AVAILABILITY.get(route) ?? null;
}

export function isHostedReviewRouteSupported(route: Route): boolean {
  const availability = hostedReviewAvailabilityForRoute(route);
  return availability?.state !== 'intentionally_unavailable' && availability?.state !== 'excluded';
}

export function detectHostedReviewSurface(hostname: string, reviewSurface?: string | boolean | null): boolean {
  if (reviewSurface === true || reviewSurface === 'hosted') return true;
  return hostname === 'review.ed-finder.app';
}

export function isHostedReviewSurface(): boolean {
  if (typeof window === 'undefined') return false;
  return detectHostedReviewSurface(
    window.location.hostname,
    import.meta.env.VITE_REVIEW_SURFACE as string | undefined,
  );
}
