/**
 * Application API facade.
 *
 * V3 boundary (issue #579, docs/development/v3-application-stack-decision.md):
 *   FastAPI/OpenAPI
 *     -> generated Hey API SDK operations   (authoritative transport for ordinary ops)
 *       -> this handwritten facade          (application normalization)
 *         -> Svelte components               (import ONLY this facade)
 *
 * Ordinary API operations delegate to the generated Hey API SDK. The generated
 * `client` is configured here (once) so every operation carries the application
 * normalization the raw SDK does not:
 *   - same-origin `credentials: 'include'`;
 *   - bounded session-only `X-Admin-Token` injected only for require_admin routes;
 *   - lossless Id64 preservation BEFORE the SDK's `JSON.parse` can round a token;
 *   - structured `ApiError` on any non-2xx / transport failure.
 * Application-shaped concerns (system-envelope unwrapping, profile-sync
 * helpers) stay here in the facade.
 *
 * Components never import generated modules directly
 * (tests/test_svelte_generated_client_boundary.py).
 */
import {
  ADMIN_TOKEN_SESSION_KEY,
  ApiError,
  LEGACY_ADMIN_ENDPOINTS,
  adminEndpointClass,
  apiRequest,
  canonicalApiPath,
} from '@ed-finder/api-client/core';
import { parseLosslessJson } from '@ed-finder/api-client/lossless-json';
import { parseId64, type Id64 } from '@ed-finder/api-client/id64';
import {
  isArchetypeKey,
  isTier,
  type ArchetypeKey,
  type MinimumScore,
  type Tier,
} from '$lib/features/explore/archetypes';
import { client } from './generated/client.gen';
import {
  addWatchlistApiV2WatchlistSyncKeyId64Post,
  authLogoutApiV1AuthLogoutPost,
  authSessionApiV1AuthSessionGet,
  autocompleteApiLocalAutocompleteGet,
  claimOwnerApiV1AuthOwnerClaimPost,
  frontierLinkApiV1AuthFrontierLinkPost,
  getArchetypeRankingsApiArchetypesRankingsGet,
  getProfileSyncApiProfileSyncSyncKeyGet,
  getV3CurrentGeneration,
  getV3JournalTravelHeatmap,
  getV3System,
  getWatchlistApiV2WatchlistSyncKeyGet,
  healthApiHealthGet,
  listIdentitiesApiV1AuthIdentitiesGet,
  listV3SystemBodies,
  listV3SystemRings,
  listV3SystemStations,
  listVerifiedCommanders,
  createVerifiedJournalImport,
  offerJournalGalaxyFacts,
  listJournalGalaxyContributions,
  getJournalGalaxyImpact,
  withdrawJournalGalaxyContribution,
  localSearchEndpointApiLocalSearchPost,
  mapHeatmapApiMapHeatmapGet,
  mapSystemsApiMapSystemsGet,
  putProfileSyncApiProfileSyncSyncKeyPut,
  removeWatchlistApiV2WatchlistSyncKeyId64Delete,
  unlinkIdentityApiV1AuthIdentitiesExternalIdentityIdDelete,
} from './generated/sdk.gen';
import type {
  ArchetypeRankingRow,
  ArchetypeRankingsResponse,
  AuthSessionResponse,
  AutocompleteHit,
  AutocompleteResponse,
  ExternalIdentityResponse,
  HealthResponse,
  LocalSearchRequest,
  BodyV1,
  MapViewportResponse,
  RankingIdentity,
  RingV1,
  SearchResponse,
  StationV1,
  SystemRow,
  SystemV1,
  V3JournalImportRequest,
  V3TravelHeatmapResponse,
} from './generated';

export type {
  BodyV1,
  RingV1,
  StationV1,
  SystemV1,
  VerifiedCommanderResponse,
  V3JournalImportRequest,
  V3VerifiedImportReceipt,
  ContributionRow,
  GalaxyImpactSummary,
} from './generated';

export const getVerifiedCommanders = async (signal?: AbortSignal) =>
  (await listVerifiedCommanders({ throwOnError: true, signal })).data;

export const getGalaxyImpact = async (signal?: AbortSignal) =>
  (await getJournalGalaxyImpact({ throwOnError: true, signal })).data;

export const importVerifiedJournals = async (
  body: V3JournalImportRequest,
  signal?: AbortSignal,
) =>
  (await createVerifiedJournalImport({ body, throwOnError: true, signal }))
    .data;

export const offerGalaxyFacts = async (
  importId: string,
  fileSha256: string[],
  signal?: AbortSignal,
) =>
  (
    await offerJournalGalaxyFacts({
      path: { import_id: importId },
      body: {
        policy_version: 'journal-galaxy-physical-v1',
        share_on_site_and_api: true,
        file_sha256: fileSha256,
      },
      throwOnError: true,
      signal,
    })
  ).data;

export const getGalaxyContributions = async (
  offset = 0,
  signal?: AbortSignal,
) =>
  (
    await listJournalGalaxyContributions({
      query: { offset, limit: 50 },
      throwOnError: true,
      signal,
    })
  ).data;

export const withdrawGalaxyContribution = async (
  id: string,
  signal?: AbortSignal,
) =>
  (
    await withdrawJournalGalaxyContribution({
      path: { contribution_id: id },
      throwOnError: true,
      signal,
    })
  ).data;

export {
  ADMIN_TOKEN_SESSION_KEY,
  ApiError,
  LEGACY_ADMIN_ENDPOINTS,
  adminEndpointClass,
  apiRequest,
  canonicalApiPath,
};

function sessionAdminToken(): string {
  if (typeof window === 'undefined') return '';
  try {
    return window.sessionStorage.getItem(ADMIN_TOKEN_SESSION_KEY)?.trim() ?? '';
  } catch {
    return '';
  }
}

function requestPathname(url: string): string {
  try {
    return new URL(url, 'https://ed-finder.invalid').pathname;
  } catch {
    return url;
  }
}

// Configure the generated client once with the application transport contract.
// The app is served same-origin (nginx proxies `/api`); we pin an absolute
// same-origin base because the generated client builds `new Request(url)`
// before dispatch, and the platform URL parser rejects a bare relative path
// outside a document base (undici in Node, and any non-browser runtime).
// In the browser this resolves to the current origin — identical to the
// relative path — so cookies stay first-party under `credentials: 'include'`.
client.setConfig({
  baseUrl: typeof window === 'undefined' ? '' : window.location.origin,
  credentials: 'include',
});

// Bounded session-only admin token: injected only for require_admin routes,
// and never carried in from a caller (a one-time owner secret must not become
// a reusable header).
client.interceptors.request.use((request) => {
  request.headers.delete('X-Admin-Token');
  if (adminEndpointClass(requestPathname(request.url), request.method)) {
    const token = sessionAdminToken();
    if (token) request.headers.set('X-Admin-Token', token);
  }
  return request;
});

// Lossless Id64 lane: re-serialise the JSON body with identifier fields already
// projected to decimal strings, BEFORE the SDK's `JSON.parse` can round an
// id64 token past Number.MAX_SAFE_INTEGER.
client.interceptors.response.use(async (response) => {
  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.toLowerCase().includes('json')) return response;
  const text = await response.text();
  if (!text) return response;
  let body: string;
  try {
    body = JSON.stringify(parseLosslessJson(text));
  } catch {
    body = text;
  }
  const headers = new Headers(response.headers);
  headers.delete('content-length');
  return new Response(body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
});

// Structured, uniform application errors.
client.interceptors.error.use((error, response, request) => {
  if (error instanceof ApiError) return error;
  const status = response?.status ?? 0;
  const path = request ? requestPathname(request.url) : '';
  return new ApiError(status, path, error);
});

export const getHealth = async (
  signal?: AbortSignal,
): Promise<HealthResponse> =>
  (await healthApiHealthGet({ throwOnError: true, signal })).data;

export type AuthIdentity = ExternalIdentityResponse;

export const getAuthSession = async (
  signal?: AbortSignal,
): Promise<AuthSessionResponse> =>
  (await authSessionApiV1AuthSessionGet({ throwOnError: true, signal })).data;

export const getAuthIdentities = async (
  signal?: AbortSignal,
): Promise<readonly AuthIdentity[]> =>
  (await listIdentitiesApiV1AuthIdentitiesGet({ throwOnError: true, signal }))
    .data;

export const startFrontierLink = async (returnTo: string): Promise<string> => {
  const { data } = await frontierLinkApiV1AuthFrontierLinkPost({
    throwOnError: true,
    query: { return_to: returnTo },
  });
  return data.authorization_url;
};

export const unlinkAuthIdentity = async (
  externalIdentityId: string,
): Promise<AuthSessionResponse> =>
  (
    await unlinkIdentityApiV1AuthIdentitiesExternalIdentityIdDelete({
      throwOnError: true,
      path: { external_identity_id: externalIdentityId },
    })
  ).data;

export type AutocompleteSystem = Readonly<
  Pick<
    AutocompleteHit,
    'name' | 'x' | 'y' | 'z' | 'population' | 'primaryEconomy'
  > & { id64: Id64 }
>;

/**
 * Sol's lossless id64 (`apps/api/src/helpers.py` `SOL_ID64`), mirrored so an
 * Any search anchored at Sol normalizes to the same `sol` distance reference
 * the selected-archetype ranking measures from.
 */
export const SOL_ID64: Id64 = parseId64('10477373803');
export const SOL_NAME = 'Sol';

/** The committed anchor's identity, held by the caller alongside the request. */
export type DistanceAnchor = Readonly<{ id64: Id64; name: string }>;

/** Which origin a row's `distance` was measured from. */
export type DistanceReference = Readonly<{
  kind: 'anchor' | 'sol';
  id64: Id64;
  name: string;
}>;

/**
 * The seven provenance fields copied from a ranked response envelope onto
 * every normalized row, so a saved snapshot can be compared like with like
 * (ranking profile and archetype model identities) and the generation that
 * produced it can be shown.
 */
export type RankingProvenance = Readonly<{
  ranking_version: string;
  ranking_sha256: string;
  derived_generation_id: string;
  publication_sequence: number;
  archetype_version: string;
  archetype_manifest_sha256: string;
  archetype_model_sha256: string;
}>;

/**
 * `unknown` is only the decoder's result for a pre-F4 snapshot carrying the
 * ambiguous generic `archetype_score`; the facade never produces it.
 */
export type ScoreKind = 'overall_potential' | 'selected_fit' | 'unknown';

export type RankingIdentityFields = Readonly<{
  ranking_score: number | null;
  /** API-owned tier of `ranking_score`; carried with `score_kind`. */
  ranking_tier: Tier | null;
  score_kind: ScoreKind;
  selected_archetype: ArchetypeKey | null;
  distance_reference: DistanceReference | null;
  ranking_provenance: RankingProvenance | null;
}>;

export type ExploreSystem = Readonly<
  Pick<
    SystemRow,
    | 'name'
    | 'coords'
    | 'distance'
    | 'population'
    | 'primaryEconomy'
    | 'secondaryEconomy'
    | 'security'
    | 'allegiance'
    | 'government'
    | 'is_colonised'
    | 'is_being_colonised'
    | 'main_star_type'
    | 'main_star_subtype'
    | 'archetype_score'
    | 'archetype_tier'
    | 'primary_archetype'
    | 'secondary_archetype'
    | 'archetype_confidence'
    | 'overall_development_potential'
    | 'buildability_score'
    | 'purity_score'
    | 'build_complexity'
    | 'est_total_slots'
    | 'tags'
    | 'elw_count'
    | 'ww_count'
    | 'ammonia_count'
    | 'landable_count'
    | 'terraformable_count'
    | 'bio_signal_total'
    | 'geo_signal_total'
    | 'confidence'
    | 'completeness'
  > & { id64: Id64 } & Partial<RankingIdentityFields>
>;

/** Exclusive offset ceiling and navigable window applied to every mode. */
export const FINDER_NAVIGATION_LIMIT = 10_000;
export const FINDER_PAGE_SIZE_MIN = 1;
export const FINDER_PAGE_SIZE_MAX = 50;
export const FINDER_PAGE_SIZE_DEFAULT = 50;

export type FinderPageTruncation =
  | Readonly<{
      source: 'local-search';
      /** Sentinel-backed: true only when a 10,001st matching row existed. */
      total_is_capped: boolean;
    }>
  | Readonly<{
      source: 'rankings';
      /** API-owned: a 10,001st qualifying row existed in canonical order. */
      is_truncated: boolean;
    }>;

/** One normalized page envelope; navigation copy derives only from this. */
export type FinderPageEnvelope = Readonly<{
  page_size: number;
  count: number;
  /** Raw response total (never above 10,000 from either route). */
  total: number;
  /** `min(total, navigation_limit)`. */
  navigable_total: number;
  offset: number;
  navigation_limit: number;
  truncation: FinderPageTruncation;
}>;

export type ArchetypeRankingsRequest = Readonly<{
  archetype: ArchetypeKey;
  min_score: MinimumScore;
  /** Facade page size 1..50, mapped to the endpoint's wire `limit`. */
  page_size: number;
  offset: number;
}>;

export type ArchetypeRankingsPage = Readonly<{
  archetype: ArchetypeKey;
  archetype_label: string;
  results: readonly ExploreSystem[];
  page: FinderPageEnvelope;
  ranking: RankingProvenance;
  source?: string | null;
  query_ms?: number | null;
}>;

/** One catalogued ring or belt of a body (V3 canonical generation). */
export type SystemDetailRing = Readonly<{
  /** Canonical V3 ring key (lossless decimal). */
  ringKey: string;
  name: string;
  kind: 'RING' | 'BELT';
  ringType: string | null;
  innerRadiusKm: number | null;
  outerRadiusKm: number | null;
}>;

/** One catalogued body as Inspect renders it (V3 canonical generation). */
export type SystemDetailBody = Readonly<{
  /**
   * Frontier in-system BodyID: the 3D map / selection reference. Null when the
   * catalogue has none (or it is not a unique safe integer); such a body is
   * counted but cannot be selected in the system map.
   */
  id: number | null;
  /** Canonical V3 body key (lossless decimal). */
  bodyKey: string;
  name: string;
  /** V3 public body-type code: `star`, `planet`, `barycentre`, `belt_cluster`. */
  bodyType: string | null;
  isMainStar: boolean | null;
  spectralClass: string | null;
  luminosityClass: string | null;
  isLandable: boolean | null;
  radiusKm: number | null;
  distanceFromArrivalLs: number | null;
  rings: readonly SystemDetailRing[];
  signals: readonly Readonly<{ signalType: string; count: number }>[];
}>;

export type SystemDetailStation = Readonly<{
  /** Canonical V3 station key (lossless decimal). */
  stationKey: string;
  name: string;
  stationType: string | null;
  distanceFromArrivalLs: number | null;
}>;

/**
 * Inspect's system detail, read from the published V3 canonical generation
 * (`/api/v1/systems/{id}` + `/bodies`, `/rings`, `/stations`). Only ACTIVE
 * bodies, rings and stations are current catalogue objects; rows the
 * generation retains as MISSING_CANDIDATE or RETIRED are omitted. Population,
 * economy, security, allegiance, government and development fit are not part
 * of the V3 canonical catalogue, so they are deliberately absent here.
 */
export type SystemDetail = Readonly<{
  id64: Id64;
  name: string;
  /** The system's own catalogue lifecycle: ACTIVE, MISSING_CANDIDATE, RETIRED. */
  lifecycleState: string;
  x: number;
  y: number;
  z: number;
  sourceBodyCount: number | null;
  loadedBodyCount: number;
  sourceUpdatedAt: string | null;
  bodies: readonly SystemDetailBody[];
  stations: readonly SystemDetailStation[];
}>;

export type AutocompleteSystemsResponse = Omit<
  AutocompleteResponse,
  'results'
> & {
  readonly results: readonly AutocompleteSystem[];
};

export type ExploreSearchResponse = Omit<SearchResponse, 'results'> & {
  readonly results: readonly ExploreSystem[];
  readonly page: FinderPageEnvelope;
};

export type ExploreSearchRequest = LocalSearchRequest;

export type CatalogueViewportRequest = Readonly<{
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  minZ: number;
  maxZ: number;
  limit: number;
}>;

export type CatalogueViewportResponse = Readonly<{
  systems: readonly Readonly<{
    id64: Id64;
    name: string;
    x: number;
    y: number;
    z: number;
    mainStarClass?: string | null;
    populated: boolean;
  }>[];
  truncated: boolean;
}>;

export interface MapHeatmapPyramidCell {
  origin_x_ly: number;
  origin_y_ly: number;
  origin_z_ly: number;
  centroid_x_ly: number;
  centroid_y_ly: number;
  centroid_z_ly: number;
  system_count: number;
}

export interface MapHeatmapPyramidResponse {
  source: 'pyramid';
  generation_id: string;
  spatial_generation_id: string;
  spatial_pyramid_version: string;
  source_system_count: number;
  coverage_at: string | null;
  level: number;
  cell_size_ly: number;
  voxel_size: number;
  bounds: {
    min_x: number | null;
    max_x: number | null;
    min_y: number | null;
    max_y: number | null;
    min_z: number | null;
    max_z: number | null;
  };
  cells: MapHeatmapPyramidCell[];
  count: number;
  max_cells: number;
  truncated: boolean;
}

export type MapHeatmapResponse =
  | MapHeatmapPyramidResponse
  | { source: 'legacy-fallback'; [k: string]: unknown };

export type CommanderTravelHeatmapResponse = Readonly<{
  mode: 'markers' | 'density';
  visits: readonly Readonly<{
    kind: 'marker' | 'density';
    systemId64?: Id64 | null;
    systemName?: string | null;
    x: number;
    y: number;
    z: number;
    visitCount: number;
    firstVisitedAt: string;
    lastVisitedAt: string;
    cellSizeLy?: number | null;
  }>[];
  count: number;
  truncated: boolean;
}>;

function losslessId64(value: unknown): Id64 {
  if (typeof value !== 'string') {
    throw new TypeError('API id64 did not pass through the lossless JSON lane');
  }
  return parseId64(value);
}

export async function autocompleteSystems(
  query: string,
  signal?: AbortSignal,
): Promise<AutocompleteSystemsResponse> {
  const { data } = await autocompleteApiLocalAutocompleteGet({
    throwOnError: true,
    query: { q: query, limit: 10 },
    signal,
  });
  return {
    ...data,
    results: data.results.map((hit) => ({
      ...hit,
      id64: losslessId64(hit.id64),
    })),
  };
}

const finiteNumber = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value);

const nonNegativeInteger = (value: unknown): value is number =>
  Number.isInteger(value) && (value as number) >= 0;

/**
 * Copy the seven provenance fields from a response envelope. An envelope that
 * does not carry all seven yields `null`: a row without provenance is listed
 * but never enters a score comparison, which is the honest fallback.
 */
export function normalizeRankingProvenance(
  ranking: Partial<RankingIdentity> | null | undefined,
): RankingProvenance | null {
  if (!ranking || typeof ranking !== 'object') return null;
  const {
    ranking_version,
    ranking_sha256,
    derived_generation_id,
    publication_sequence,
    archetype_version,
    archetype_manifest_sha256,
    archetype_model_sha256,
  } = ranking;
  if (
    typeof ranking_version !== 'string' ||
    typeof ranking_sha256 !== 'string' ||
    typeof derived_generation_id !== 'string' ||
    !nonNegativeInteger(publication_sequence) ||
    typeof archetype_version !== 'string' ||
    typeof archetype_manifest_sha256 !== 'string' ||
    typeof archetype_model_sha256 !== 'string'
  )
    return null;
  return {
    ranking_version,
    ranking_sha256,
    derived_generation_id,
    publication_sequence,
    archetype_version,
    archetype_manifest_sha256,
    archetype_model_sha256,
  };
}

/** An Any search anchored at Sol measures from the same origin as rankings. */
export function distanceReferenceForAnchor(
  anchor: DistanceAnchor | null | undefined,
): DistanceReference | null {
  if (!anchor) return null;
  return anchor.id64 === SOL_ID64
    ? { kind: 'sol', id64: SOL_ID64, name: anchor.name || SOL_NAME }
    : { kind: 'anchor', id64: anchor.id64, name: anchor.name };
}

const SOL_REFERENCE: DistanceReference = {
  kind: 'sol',
  id64: SOL_ID64,
  name: SOL_NAME,
};

function finderPageSize(value: number | undefined, fallback: number): number {
  return Number.isInteger(value) ? (value as number) : fallback;
}

function pageEnvelope(
  pageSize: number,
  offset: number,
  count: number,
  total: number | undefined,
  truncation: FinderPageTruncation,
): FinderPageEnvelope {
  const rawTotal = nonNegativeInteger(total) ? total : count;
  return {
    page_size: pageSize,
    count,
    total: rawTotal,
    navigable_total: Math.min(rawTotal, FINDER_NAVIGATION_LIMIT),
    offset,
    navigation_limit: FINDER_NAVIGATION_LIMIT,
    truncation,
  };
}

/**
 * Normalize one `/api/local/search` (Any) row. The overall score is carried as
 * `ranking_score` with `score_kind: 'overall_potential'`; the distance
 * reference is the committed anchor's identity (which the wire request does
 * not carry, so the caller supplies it), and only when a distance was measured.
 */
export function normalizeAnySearchRow(
  system: SystemRow,
  reference: DistanceReference | null,
  provenance: RankingProvenance | null,
): ExploreSystem {
  const tier = system.archetype_tier;
  // The Any ranking score is the overall potential only: never fall back to a
  // semantically different value under `score_kind: 'overall_potential'`.
  const overall = finiteNumber(system.overall_development_potential)
    ? system.overall_development_potential
    : null;
  // `archetype_tier` is the API's tier of `archetype_score`; it travels with
  // the overall score only when it was derived from that same value.
  const tierOfOverall =
    overall !== null && system.archetype_score === overall && isTier(tier)
      ? tier
      : null;
  return {
    ...system,
    id64: losslessId64(system.id64),
    ranking_score: overall,
    ranking_tier: tierOfOverall,
    score_kind: 'overall_potential',
    selected_archetype: null,
    distance_reference: finiteNumber(system.distance) ? reference : null,
    ranking_provenance: provenance,
  };
}

/**
 * The facade/URL page size of an Any request. It is distinct from the wire
 * `size`, which is clamped to `min(page_size, 10000 - offset)` near the
 * navigation ceiling: Previous/Next must keep stepping by the facade page
 * size, exactly as the rankings path does. Without an explicit value (the
 * live default-off request) the wire size is the page size.
 */
function anyFacadePageSize(
  request: ExploreSearchRequest,
  pageSize: number | undefined,
): number {
  if (pageSize === undefined)
    return finderPageSize(request.size, FINDER_PAGE_SIZE_DEFAULT);
  if (
    !Number.isInteger(pageSize) ||
    pageSize < FINDER_PAGE_SIZE_MIN ||
    pageSize > FINDER_PAGE_SIZE_MAX
  )
    throw new RangeError(
      `page_size must be an integer from ${FINDER_PAGE_SIZE_MIN} to ${FINDER_PAGE_SIZE_MAX}`,
    );
  return pageSize;
}

/**
 * Normalize an Any (`/api/local/search`) response into the lossless page
 * envelope. `reference` is the committed anchor's `{ id64, name }` when the
 * request is anchored (F4 design section 6); pass `null` for galaxy-wide.
 * `pageSize` is the facade/URL page size when it differs from the clamped
 * wire `size`.
 */
export function normalizeAnySearchResponse(
  data: SearchResponse,
  request: ExploreSearchRequest,
  reference: DistanceAnchor | null = null,
  pageSize?: number,
): ExploreSearchResponse {
  const facadePageSize = anyFacadePageSize(request, pageSize);
  const provenance = normalizeRankingProvenance(data.ranking);
  const distanceReference = request.reference_coords
    ? distanceReferenceForAnchor(reference)
    : null;
  const results = data.results.map((system) =>
    normalizeAnySearchRow(system, distanceReference, provenance),
  );
  return {
    ...data,
    results,
    page: pageEnvelope(
      facadePageSize,
      finderPageSize(request.from, 0),
      results.length,
      data.total,
      {
        source: 'local-search',
        total_is_capped: data.total_is_capped === true,
      },
    ),
  };
}

export async function searchExploreSystems(
  request: ExploreSearchRequest,
  signal?: AbortSignal,
  reference: DistanceAnchor | null = null,
  pageSize?: number,
): Promise<ExploreSearchResponse> {
  // Validate before dispatch so a bad page size never reaches the API.
  const facadePageSize = anyFacadePageSize(request, pageSize);
  const { data } = await localSearchEndpointApiLocalSearchPost({
    throwOnError: true,
    body: request,
    signal,
  });
  return normalizeAnySearchResponse(data, request, reference, facadePageSize);
}

/**
 * Normalize one `/api/archetypes/rankings` row onto the Explore shape. The
 * selected fit is carried as `ranking_score`/`ranking_tier` with
 * `score_kind: 'selected_fit'` and never enters generic `archetype_score`;
 * `distance` is the endpoint's Sol distance with a `sol` reference.
 */
export function normalizeRankingRow(
  row: ArchetypeRankingRow,
  archetype: ArchetypeKey,
  provenance: RankingProvenance | null,
): ExploreSystem {
  if (!finiteNumber(row.score) || !isTier(row.tier))
    throw new TypeError('The archetype ranking row has no valid score/tier');
  const distance = finiteNumber(row.distance_to_sol)
    ? row.distance_to_sol
    : null;
  return {
    id64: losslessId64(row.id64),
    name: row.name,
    coords: row.coords ?? null,
    distance,
    primary_archetype: row.primary_archetype ?? null,
    secondary_archetype: row.secondary_archetype ?? null,
    archetype_confidence: row.archetype_confidence ?? null,
    overall_development_potential: row.overall_development_potential ?? null,
    buildability_score: row.buildability_score ?? null,
    purity_score: row.purity_score ?? null,
    build_complexity: row.build_complexity ?? null,
    est_total_slots: row.est_total_slots ?? null,
    tags: row.tags,
    elw_count: row.elw_count ?? null,
    landable_count: row.landable_count ?? null,
    confidence: row.confidence ?? null,
    completeness: row.completeness ?? null,
    archetype_score: null,
    archetype_tier: null,
    ranking_score: row.score,
    ranking_tier: row.tier,
    score_kind: 'selected_fit',
    selected_archetype: archetype,
    distance_reference: distance === null ? null : SOL_REFERENCE,
    ranking_provenance: provenance,
  };
}

function validateRankingsRequest(request: ArchetypeRankingsRequest): {
  archetype: ArchetypeKey;
  limit: number;
  offset: number;
} {
  if (!isArchetypeKey(request.archetype))
    throw new RangeError(`Unsupported archetype key: ${request.archetype}`);
  if (
    !Number.isInteger(request.page_size) ||
    request.page_size < FINDER_PAGE_SIZE_MIN ||
    request.page_size > FINDER_PAGE_SIZE_MAX
  )
    throw new RangeError(
      `page_size must be an integer from ${FINDER_PAGE_SIZE_MIN} to ${FINDER_PAGE_SIZE_MAX}`,
    );
  if (
    !nonNegativeInteger(request.offset) ||
    request.offset >= FINDER_NAVIGATION_LIMIT
  )
    throw new RangeError(
      `offset must be an integer from 0 below ${FINDER_NAVIGATION_LIMIT}`,
    );
  return {
    archetype: request.archetype,
    // One navigation ceiling for every mode: the wire page never crosses it.
    limit: Math.min(
      request.page_size,
      FINDER_NAVIGATION_LIMIT - request.offset,
    ),
    offset: request.offset,
  };
}

export function normalizeRankingsResponse(
  data: ArchetypeRankingsResponse,
  request: ArchetypeRankingsRequest,
): ArchetypeRankingsPage {
  const { archetype, offset } = validateRankingsRequest(request);
  const provenance = normalizeRankingProvenance(data.ranking);
  if (!provenance)
    throw new TypeError(
      'The archetype ranking response has no ranking identity',
    );
  const results = data.results.map((row) =>
    normalizeRankingRow(row, archetype, provenance),
  );
  const total = nonNegativeInteger(data.total) ? data.total : results.length;
  if (data.is_truncated === true && total === 0)
    throw new TypeError(
      'The archetype ranking response is truncated with no qualifying rows',
    );
  return {
    archetype,
    archetype_label: data.archetype_label,
    results,
    page: pageEnvelope(request.page_size, offset, results.length, total, {
      source: 'rankings',
      is_truncated: data.is_truncated === true,
    }),
    ranking: provenance,
    source: data.source,
    query_ms: data.query_ms,
  };
}

/**
 * Selected-archetype ranking (`GET /api/archetypes/rankings`). The facade
 * exposes `page_size` 1..50 and maps it to the endpoint's wire `limit`; it
 * accepts no hard filter, so a picked request can never carry one.
 */
export async function getArchetypeRankings(
  request: ArchetypeRankingsRequest,
  signal?: AbortSignal,
): Promise<ArchetypeRankingsPage> {
  const { archetype, limit, offset } = validateRankingsRequest(request);
  const { data } = await getArchetypeRankingsApiArchetypesRankingsGet({
    throwOnError: true,
    query: { archetype, min_score: request.min_score, limit, offset },
    signal,
  });
  return normalizeRankingsResponse(data, request);
}

export async function getCatalogueViewportSystems(
  request: CatalogueViewportRequest,
  signal?: AbortSignal,
): Promise<CatalogueViewportResponse> {
  const { data } = await mapSystemsApiMapSystemsGet({
    throwOnError: true,
    query: {
      min_x: request.minX,
      max_x: request.maxX,
      min_y: request.minY,
      max_y: request.maxY,
      min_z: request.minZ,
      max_z: request.maxZ,
      limit: request.limit,
    },
    signal,
  });
  const response = data as MapViewportResponse;
  return {
    systems: response.systems.map((system) => ({
      id64: losslessId64(system.id64),
      name: system.name,
      x: system.x,
      y: system.y,
      z: system.z,
      mainStarClass: system.main_star_class,
      populated: system.populated,
    })),
    truncated: response.truncated ?? false,
  };
}

export const getMapHeatmap = async (
  query: { voxel_size?: number; min_systems?: number; max_cells?: number },
  signal?: AbortSignal,
): Promise<MapHeatmapResponse> =>
  (await mapHeatmapApiMapHeatmapGet({ query, throwOnError: true, signal }))
    .data as MapHeatmapResponse;

/**
 * The signed-in account's imported journal travel (V3 journal store) inside
 * one viewport box, aggregated server-side. Rejects with a 401 ApiError when
 * signed out.
 */
export async function getCommanderTravelHeatmap(
  request: CatalogueViewportRequest,
  cameraDistanceLy: number,
  signal?: AbortSignal,
): Promise<CommanderTravelHeatmapResponse> {
  const { data } = await getV3JournalTravelHeatmap({
    throwOnError: true,
    query: {
      min_x: request.minX,
      max_x: request.maxX,
      min_y: request.minY,
      max_y: request.maxY,
      min_z: request.minZ,
      max_z: request.maxZ,
      zoom: Math.min(5_000, Math.max(0.001, cameraDistanceLy)),
      limit: Math.min(20_000, request.limit),
    },
    signal,
  });
  const response = data as V3TravelHeatmapResponse;
  return {
    mode: response.mode,
    visits: response.points.map((point) => ({
      kind: point.kind,
      systemId64:
        point.system_id64 == null ? null : parseId64(point.system_id64),
      systemName: point.system_name,
      x: point.x,
      y: point.y,
      z: point.z,
      visitCount: point.visit_count,
      firstVisitedAt: point.first_visited_at,
      lastVisitedAt: point.last_visited_at,
      cellSizeLy: response.cell_size_ly,
    })),
    count: response.count,
    truncated: response.truncated,
  };
}

const SAFE_DECIMAL = /^(0|[1-9][0-9]{0,15})$/;
const ACTIVE = 'ACTIVE';

/** Unique, safe Frontier BodyIDs keyed by canonical body key. */
function frontierBodyIds(bodies: readonly BodyV1[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const body of bodies) {
    const raw = body.frontier_body_id;
    if (raw != null) counts.set(raw, (counts.get(raw) ?? 0) + 1);
  }
  const ids = new Map<string, number>();
  for (const body of bodies) {
    const raw = body.frontier_body_id;
    if (raw == null || counts.get(raw) !== 1 || !SAFE_DECIMAL.test(raw))
      continue;
    const value = Number(raw);
    if (Number.isSafeInteger(value)) ids.set(body.body_id, value);
  }
  return ids;
}

/** Main star first, then by arrival distance (unknown last), then name. */
function bodyOrder(left: SystemDetailBody, right: SystemDetailBody): number {
  const main =
    Number(right.isMainStar === true) - Number(left.isMainStar === true);
  if (main !== 0) return main;
  const leftDistance = left.distanceFromArrivalLs ?? Number.POSITIVE_INFINITY;
  const rightDistance = right.distanceFromArrivalLs ?? Number.POSITIVE_INFINITY;
  if (leftDistance !== rightDistance)
    return leftDistance < rightDistance ? -1 : 1;
  return left.name.localeCompare(right.name);
}

/** Pure V3 canonical → Inspect mapping; exported for tests. */
export function systemDetailFromV3(
  system: SystemV1,
  bodies: readonly BodyV1[],
  rings: readonly RingV1[],
  stations: readonly StationV1[],
): SystemDetail {
  const current = bodies.filter((body) => body.lifecycle_state === ACTIVE);
  const ids = frontierBodyIds(current);
  const ringsByBody = new Map<string, SystemDetailRing[]>();
  for (const ring of rings) {
    if (ring.lifecycle_state !== ACTIVE) continue;
    const list = ringsByBody.get(ring.body_id) ?? [];
    list.push({
      ringKey: ring.ring_id,
      name: ring.name,
      kind: ring.kind,
      ringType: ring.ring_type,
      innerRadiusKm: ring.inner_radius_km,
      outerRadiusKm: ring.outer_radius_km,
    });
    ringsByBody.set(ring.body_id, list);
  }
  return {
    id64: parseId64(system.id64),
    name: system.name,
    lifecycleState: system.lifecycle_state,
    x: system.x_ly,
    y: system.y_ly,
    z: system.z_ly,
    sourceBodyCount: system.source_body_count,
    loadedBodyCount: system.loaded_body_count,
    sourceUpdatedAt: system.source_updated_at,
    bodies: current
      .map((body): SystemDetailBody => ({
        id: ids.get(body.body_id) ?? null,
        bodyKey: body.body_id,
        name: body.name,
        bodyType: body.body_type,
        isMainStar: body.is_main_star,
        spectralClass: body.spectral_class,
        luminosityClass: body.luminosity_class,
        isLandable: body.is_landable,
        radiusKm: body.radius_km,
        distanceFromArrivalLs: body.distance_from_arrival_ls,
        rings: ringsByBody.get(body.body_id) ?? [],
        signals: body.signals.map((signal) => ({
          signalType: signal.signal_type,
          count: signal.count,
        })),
      }))
      .sort(bodyOrder),
    stations: stations
      .filter((station) => station.lifecycle_state === ACTIVE)
      .map((station) => ({
        stationKey: station.station_id,
        name: station.name,
        stationType: station.station_type,
        distanceFromArrivalLs: station.distance_from_arrival_ls,
      })),
  };
}

/** Attempts before a read that keeps straddling publications fails closed. */
const INSPECT_GENERATION_ATTEMPTS = 2;

/**
 * Inspect's system read: the generation-pinned V3 canonical routes, fetched in
 * parallel. Each route resolves the canonical pointer on its own, so the four
 * reads are fenced by the published generation identity read before and after
 * them: an unchanged generation and publication sequence proves no publication
 * happened in between and every part came from one immutable generation. Any
 * part's error (a 404 included) is only reported once the fence holds. A read
 * that straddles a publication is retried once, then fails closed with a
 * retryable 503. An unknown system rejects with the system route's 404
 * ApiError; no published generation rejects with 503.
 */
export async function getSystem(
  id64: Id64,
  signal?: AbortSignal,
): Promise<SystemDetail> {
  const path = { system_id: parseId64(id64) };
  for (let attempt = 0; attempt < INSPECT_GENERATION_ATTEMPTS; attempt += 1) {
    const before = await getV3CurrentGeneration({ throwOnError: true, signal });
    // Settle every part (including a 404) before judging it: a system that
    // was absent from the old generation may exist in a newly published one.
    const [system, bodies, rings, stations] = await Promise.allSettled([
      getV3System({ path, throwOnError: true, signal }),
      listV3SystemBodies({ path, throwOnError: true, signal }),
      listV3SystemRings({ path, throwOnError: true, signal }),
      listV3SystemStations({ path, throwOnError: true, signal }),
    ]);
    const after = await getV3CurrentGeneration({ throwOnError: true, signal });
    if (
      before.data.generation_id !== after.data.generation_id ||
      before.data.publication_sequence !== after.data.publication_sequence
    )
      continue;
    for (const part of [system, bodies, rings, stations])
      if (part.status === 'rejected') throw part.reason;
    if (
      system.status === 'fulfilled' &&
      bodies.status === 'fulfilled' &&
      rings.status === 'fulfilled' &&
      stations.status === 'fulfilled'
    )
      return systemDetailFromV3(
        system.value.data,
        bodies.value.data,
        rings.value.data,
        stations.value.data,
      );
  }
  throw new ApiError(
    503,
    `/api/v1/systems/${path.system_id}`,
    null,
    'The catalogue was republished while this system was loading',
  );
}

/** Existing sync-key watchlist rows; optional snapshots may be absent or null. */
export interface WatchlistEntry {
  readonly system_id64: Id64;
  readonly name: string;
  readonly x?: number | null;
  readonly y?: number | null;
  readonly z?: number | null;
  readonly population?: number | null;
  readonly is_colonised?: boolean | null;
  readonly added_at?: string | null;
  readonly last_checked_at?: string | null;
  readonly last_status?: string | null;
  readonly score?: number | null;
  readonly economy_suggestion?: string | null;
  readonly primary_archetype?: string | null;
  readonly secondary_archetype?: string | null;
  readonly archetype_score?: number | null;
  readonly buildability_score?: number | null;
  readonly purity_score?: number | null;
  readonly alert_min_development_score?: number | null;
  readonly alert_min_score?: number | null;
  readonly alert_economy?: string | null;
}

export interface WatchlistResponse {
  readonly sync_key: string;
  readonly watchlist: readonly WatchlistEntry[];
}

function watchlistRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new TypeError('The watchlist response is invalid');
  return value as Record<string, unknown>;
}

function watchlistNumber(
  row: Record<string, unknown>,
  field: string,
): number | null {
  const value = row[field];
  if (value == null) return null;
  if (typeof value !== 'number' || !Number.isFinite(value))
    throw new TypeError(`The watchlist ${field} is invalid`);
  return value;
}

function watchlistString(
  row: Record<string, unknown>,
  field: string,
): string | null {
  const value = row[field];
  if (value == null) return null;
  if (typeof value !== 'string')
    throw new TypeError(`The watchlist ${field} is invalid`);
  return value;
}

function watchlistBoolean(
  row: Record<string, unknown>,
  field: string,
): boolean | null {
  const value = row[field];
  if (value == null) return null;
  if (typeof value !== 'boolean')
    throw new TypeError(`The watchlist ${field} is invalid`);
  return value;
}

function normalizeWatchlistEntry(value: unknown): WatchlistEntry {
  const row = watchlistRecord(value);
  if (typeof row.name !== 'string' || !row.name.trim())
    throw new TypeError('The watchlist system name is invalid');
  return {
    system_id64: losslessId64(row.system_id64),
    name: row.name,
    x: watchlistNumber(row, 'x'),
    y: watchlistNumber(row, 'y'),
    z: watchlistNumber(row, 'z'),
    population: watchlistNumber(row, 'population'),
    is_colonised: watchlistBoolean(row, 'is_colonised'),
    added_at: watchlistString(row, 'added_at'),
    last_checked_at: watchlistString(row, 'last_checked_at'),
    last_status: watchlistString(row, 'last_status'),
    score: watchlistNumber(row, 'score'),
    economy_suggestion: watchlistString(row, 'economy_suggestion'),
    primary_archetype: watchlistString(row, 'primary_archetype'),
    secondary_archetype: watchlistString(row, 'secondary_archetype'),
    archetype_score: watchlistNumber(row, 'archetype_score'),
    buildability_score: watchlistNumber(row, 'buildability_score'),
    purity_score: watchlistNumber(row, 'purity_score'),
    alert_min_development_score: watchlistNumber(
      row,
      'alert_min_development_score',
    ),
    alert_min_score: watchlistNumber(row, 'alert_min_score'),
    alert_economy: watchlistString(row, 'alert_economy'),
  };
}

export async function getWatchlist(
  syncKey: string,
  signal?: AbortSignal,
): Promise<WatchlistResponse> {
  const { data } = await getWatchlistApiV2WatchlistSyncKeyGet({
    throwOnError: true,
    path: { sync_key: syncKey },
    signal,
  });
  // The existing backend has no response model, so the SDK returns unknown.
  // Validate that established shape here without changing the API contract.
  const response = watchlistRecord(data);
  if (response.sync_key !== syncKey || !Array.isArray(response.watchlist))
    throw new TypeError('The watchlist response is invalid');
  return {
    sync_key: syncKey,
    watchlist: response.watchlist.map(normalizeWatchlistEntry),
  };
}

export async function addWatchlist(
  syncKey: string,
  id64: Id64,
  signal?: AbortSignal,
): Promise<{ readonly ok: true; readonly sync_key: string }> {
  const { data } = await addWatchlistApiV2WatchlistSyncKeyId64Post({
    throwOnError: true,
    path: { sync_key: syncKey, id64: parseId64(id64) as unknown as number },
    signal,
  });
  const response = watchlistRecord(data);
  if (response.ok !== true || response.sync_key !== syncKey)
    throw new TypeError('The watchlist save response is invalid');
  return { ok: true, sync_key: syncKey };
}

export async function removeWatchlist(
  syncKey: string,
  id64: Id64,
  signal?: AbortSignal,
): Promise<{ readonly ok: true }> {
  const { data } = await removeWatchlistApiV2WatchlistSyncKeyId64Delete({
    throwOnError: true,
    path: { sync_key: syncKey, id64: parseId64(id64) as unknown as number },
    signal,
  });
  if (watchlistRecord(data).ok !== true)
    throw new TypeError('The watchlist remove response is invalid');
  return { ok: true };
}

export interface ProfileSyncPullResponse<TBlob> {
  blob: TBlob;
  updated_at: string;
  blob_bytes: number;
}

export interface ProfileSyncPushResponse {
  updated_at: string;
  blob_bytes: number;
}

export function pullProfileSync<TBlob>(
  syncKey: string,
  signal?: AbortSignal,
): Promise<ProfileSyncPullResponse<TBlob>> {
  return getProfileSyncApiProfileSyncSyncKeyGet({
    throwOnError: true,
    path: { sync_key: syncKey },
    signal,
  }).then((result) => result.data as unknown as ProfileSyncPullResponse<TBlob>);
}

export function pushProfileSync<TBlob>(
  syncKey: string,
  blob: TBlob,
  signal?: AbortSignal,
): Promise<ProfileSyncPushResponse> {
  return putProfileSyncApiProfileSyncSyncKeyPut({
    throwOnError: true,
    path: { sync_key: syncKey },
    body: { blob } as never,
    signal,
  }).then((result) => result.data as unknown as ProfileSyncPushResponse);
}

export const authLogout = async <T = AuthSessionResponse>(): Promise<T> =>
  (await authLogoutApiV1AuthLogoutPost({ throwOnError: true }))
    .data as unknown as T;

export const claimOwner = async <T = AuthSessionResponse>(
  adminToken: string,
): Promise<T> =>
  (
    await claimOwnerApiV1AuthOwnerClaimPost({
      throwOnError: true,
      body: { admin_token: adminToken },
    })
  ).data as unknown as T;

export const frontierLoginUrl = (returnTo: string): string =>
  `/api/v1/auth/frontier/login?return_to=${encodeURIComponent(returnTo)}`;
