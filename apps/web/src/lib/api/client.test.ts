import { beforeEach, describe, expect, it, vi } from 'vitest';

// Partial mock (preserving every other real export via loadOriginal, per the
// $lib/api/client mocking convention in SystemDetail.test.ts /
// SystemOverlay.test.ts) so this file's other tests keep exercising the real
// generated SDK/transport while getMapHeatmap's test stubs only the one
// heatmap operation.
vi.mock('$lib/api/generated/sdk.gen', async (loadOriginal) => {
  const original =
    await loadOriginal<typeof import('$lib/api/generated/sdk.gen')>();
  return {
    ...original,
    mapHeatmapApiMapHeatmapGet: vi.fn(async () => ({
      data: { source: 'pyramid', cells: [] },
    })),
  };
});

import {
  ADMIN_TOKEN_SESSION_KEY,
  ApiError,
  LEGACY_ADMIN_ENDPOINTS,
  apiRequest,
  autocompleteSystems,
  claimOwner,
  getAuthIdentities,
  getAuthSession,
  getGalaxyImpact,
  getHealth,
  getMapHeatmap,
  getSystem,
  searchExploreSystems,
  startFrontierLink,
  unlinkAuthIdentity,
} from './client';
// Allowed only in a .test. file: exercise the generated client configuration
// (interceptors) the facade installs, on a route the facade does not wrap.
import { statusApiStatusGet } from './generated/sdk.gen';
import * as sdk from './generated/sdk.gen';

const jsonResponse = (body: unknown, init: ResponseInit = {}) =>
  new Response(JSON.stringify(body), {
    ...init,
    headers: { 'content-type': 'application/json', ...init.headers },
  });

describe('typed V3 API facade over the generated Hey API SDK', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  it('loads private galaxy totals through the generated own-account route with cancellation', async () => {
    const summary = {
      systems_discovered: 1302,
      bodies_scanned: 9000,
      earth_like_worlds: 6,
      water_worlds: 4,
      ammonia_worlds: 2,
      terraformable_candidates: 7,
      gas_giants: 38,
    };
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse(summary));
    const controller = new AbortController();

    await expect(getGalaxyImpact(controller.signal)).resolves.toEqual(summary);

    const request = fetchMock.mock.calls[0]?.[0] as Request;
    expect(request).toBeInstanceOf(Request);
    expect(new URL(request.url).pathname).toBe('/api/v1/journal/galaxy-impact');
    expect(new URL(request.url).search).toBe('');
    expect(request.credentials).toBe('include');
    controller.abort();
    expect(request.signal.aborted).toBe(true);
  });

  it('delegates ordinary bootstrap operations to the generated SDK over the credentialed same-origin transport', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        jsonResponse({ status: 'ok', database: 'connected' }),
      )
      .mockResolvedValueOnce(
        jsonResponse({ authenticated: false, user: null }),
      );

    await expect(getHealth()).resolves.toMatchObject({ status: 'ok' });
    await expect(getAuthSession()).resolves.toMatchObject({
      authenticated: false,
    });

    // The generated client-fetch transport dispatches a single Request object,
    // not a (url, init) pair — proving the facade delegates to the generated
    // operation rather than hand-rolling the fetch.
    const healthRequest = fetchMock.mock.calls[0]?.[0] as Request;
    const sessionRequest = fetchMock.mock.calls[1]?.[0] as Request;
    expect(healthRequest).toBeInstanceOf(Request);
    expect(fetchMock.mock.calls[0]?.[1]).toBeUndefined();
    expect(healthRequest.url).toContain('/api/health');
    expect(healthRequest.credentials).toBe('include');
    expect(sessionRequest).toBeInstanceOf(Request);
    expect(sessionRequest.url).toContain('/api/v1/auth/session');
    expect(sessionRequest.credentials).toBe('include');
  });

  it('preserves oversized id64 identifiers losslessly through the application facade', async () => {
    // 18446744073709551615 (uint64 max) is far beyond Number.MAX_SAFE_INTEGER.
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('{"system":{"id64":18446744073709551615,"name":"Deep"}}', {
        headers: { 'content-type': 'application/json' },
      }),
    );

    const system = await getSystem('18446744073709551615' as never);
    expect(system.id64).toBe('18446744073709551615');
  });

  it('uses typed generated Explore operations and normalizes every result id64', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(
          '{"results":[{"id64":9007199254740993,"name":"Far Reach","x":1,"y":2,"z":3}]}',
          { headers: { 'content-type': 'application/json' } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          '{"results":[{"id64":18446744073709551615,"name":"Edge","coords":{"x":4,"y":5,"z":6}}],"count":1}',
          { headers: { 'content-type': 'application/json' } },
        ),
      );

    await expect(autocompleteSystems('Far')).resolves.toMatchObject({
      results: [{ id64: '9007199254740993', name: 'Far Reach' }],
    });
    await expect(
      searchExploreSystems({ galaxy_wide: true, size: 24 }),
    ).resolves.toMatchObject({
      results: [{ id64: '18446744073709551615', name: 'Edge' }],
    });

    const autocompleteRequest = fetchMock.mock.calls[0]?.[0] as Request;
    const searchRequest = fetchMock.mock.calls[1]?.[0] as Request;
    expect(autocompleteRequest.url).toContain(
      '/api/local/autocomplete?q=Far&limit=10',
    );
    expect(searchRequest.url).toContain('/api/local/search');
    expect(await searchRequest.clone().json()).toEqual({
      galaxy_wide: true,
      size: 24,
    });
  });

  it('raises a structured ApiError carrying status and path on a non-2xx response', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ detail: 'unavailable' }, { status: 503 }),
    );

    const error = await getHealth().catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(503);
    expect((error as ApiError).path).toContain('/api/health');
  });

  it('keeps identity management on the credentialed same-origin facade', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        jsonResponse([
          {
            external_identity_id: 'identity-1',
            provider: 'frontier',
            linked_at: '2026-09-09T12:00:00Z',
          },
        ]),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          authorization_url: 'https://auth.frontierstore.net/auth?state=one',
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ authenticated: true, user: null }));

    await expect(getAuthIdentities()).resolves.toEqual([
      {
        external_identity_id: 'identity-1',
        provider: 'frontier',
        linked_at: '2026-09-09T12:00:00Z',
      },
    ]);
    await expect(startFrontierLink('/')).resolves.toContain(
      'auth.frontierstore.net',
    );
    await expect(unlinkAuthIdentity('identity-1')).resolves.toMatchObject({
      authenticated: true,
    });

    // Every identity operation is dispatched by the generated client as a
    // credentialed same-origin Request, exactly like the bootstrap lane.
    const identitiesRequest = fetchMock.mock.calls[0]?.[0] as Request;
    const linkRequest = fetchMock.mock.calls[1]?.[0] as Request;
    const unlinkRequest = fetchMock.mock.calls[2]?.[0] as Request;
    expect(identitiesRequest).toBeInstanceOf(Request);
    expect(identitiesRequest.url).toContain('/api/v1/auth/identities');
    expect(identitiesRequest.credentials).toBe('include');
    expect(linkRequest.url).toContain('/api/v1/auth/frontier/link');
    expect(linkRequest.url).toContain('return_to=%2F');
    expect(linkRequest.method).toBe('POST');
    expect(unlinkRequest.url).toContain('/api/v1/auth/identities/identity-1');
    expect(unlinkRequest.method).toBe('DELETE');
  });

  it('injects the bounded session admin token only for require_admin routes', async () => {
    sessionStorage.setItem(ADMIN_TOKEN_SESSION_KEY, 'session-admin');
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse({ ok: true }));

    // /api/status is in the require_admin inventory.
    await statusApiStatusGet({ throwOnError: true });
    const request = fetchMock.mock.calls[0]?.[0] as Request;
    expect(request.headers.get('X-Admin-Token')).toBe('session-admin');
  });

  it('keeps the one-time owner secret in the body and off reusable headers', async () => {
    sessionStorage.setItem(ADMIN_TOKEN_SESSION_KEY, 'session-admin');
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({
        authenticated: true,
        user: { commander_name: 'CMDR', is_owner: true },
      }),
    );

    await claimOwner('one-time-owner-secret');
    const request = fetchMock.mock.calls[0]?.[0] as Request;
    // /api/v1/auth/owner/claim is not an admin-classified route: the reusable
    // session token must not be attached, and the one-time secret rides only
    // in the body.
    expect(request).toBeInstanceOf(Request);
    expect(request.headers.has('X-Admin-Token')).toBe(false);
    expect(await request.clone().text()).toBe(
      JSON.stringify({ admin_token: 'one-time-owner-secret' }),
    );
    expect(request.url).toContain('/api/v1/auth/owner/claim');
  });

  it('re-exports the single shared transport inventory rather than duplicating it', () => {
    expect(LEGACY_ADMIN_ENDPOINTS).toHaveLength(28);
    expect(apiRequest).toBeTypeOf('function');
  });
});

describe('getMapHeatmap', () => {
  it('calls the heatmap SDK with query + throwOnError and returns data', async () => {
    const out = await getMapHeatmap({ voxel_size: 500, max_cells: 40000 });
    expect(out).toMatchObject({ source: 'pyramid' });
    expect(vi.mocked(sdk.mapHeatmapApiMapHeatmapGet)).toHaveBeenCalledWith(
      expect.objectContaining({
        query: { voxel_size: 500, max_cells: 40000 },
        throwOnError: true,
      }),
    );
  });
});

// ---------------------------------------------------------------------------
// Finder F4a: typed ranking foundation (page envelopes, row normalization)
// ---------------------------------------------------------------------------

import {
  FINDER_NAVIGATION_LIMIT,
  SOL_ID64,
  distanceReferenceForAnchor,
  getArchetypeRankings,
  normalizeAnySearchResponse,
  normalizeRankingProvenance,
  normalizeRankingsResponse,
  type ArchetypeRankingsPage,
  type DistanceAnchor,
} from './client';
import { parseId64 } from '@ed-finder/api-client/id64';

const provenance = {
  ranking_version: 'v3-colony-potential-2',
  ranking_sha256: 'ranking-sha',
  derived_generation_id: 'generation-id',
  publication_sequence: 1,
  archetype_version: 'v3-archetype-1',
  archetype_manifest_sha256: 'manifest-sha',
  archetype_model_sha256: 'model-sha',
};

const rankingRow = (id64: string, score: number, tier: 'S' | 'A' | 'B') => ({
  id64: id64 as unknown as number,
  name: `System ${id64}`,
  coords: { x: 1, y: 2, z: 3 },
  distance_to_sol: 139.45,
  score,
  tier,
  selected_archetype: 'flexible',
  primary_archetype: 'flexible',
  secondary_archetype: null,
  archetype_confidence: 0.91,
  overall_development_potential: 100,
  confidence: 0.82,
  completeness: 0.64,
  elw_count: 1,
});

const rankingsEnvelope = (
  results: ReturnType<typeof rankingRow>[],
  extra: Record<string, unknown> = {},
) => ({
  archetype: 'flexible',
  archetype_label: 'Flexible Multi-Role Colony',
  results,
  total: results.length,
  count: results.length,
  is_truncated: false,
  ranking: provenance,
  ...extra,
});

const flexibleRequest = {
  archetype: 'flexible' as const,
  min_score: 60 as const,
  page_size: 1,
  offset: 0,
};

describe('selected-archetype rankings facade', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('maps facade page_size=1 to wire limit=1 and sends the tier floor, no hard filter', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify(
          rankingsEnvelope([rankingRow('9007199254740993', 100, 'S')], {
            total: 3,
          }),
        ).replace('"9007199254740993"', '9007199254740993'),
        { headers: { 'content-type': 'application/json' } },
      ),
    );

    const page = await getArchetypeRankings(flexibleRequest);

    const request = fetchMock.mock.calls[0]?.[0] as Request;
    const url = new URL(request.url);
    expect(url.pathname).toBe('/api/archetypes/rankings');
    expect(Object.fromEntries(url.searchParams.entries())).toEqual({
      archetype: 'flexible',
      min_score: '60',
      limit: '1',
      offset: '0',
    });
    expect(request.credentials).toBe('include');
    expect(page.page).toEqual({
      page_size: 1,
      count: 1,
      total: 3,
      navigable_total: 3,
      offset: 0,
      navigation_limit: 10_000,
      truncation: { source: 'rankings', is_truncated: false },
    });
    expect(page.ranking).toEqual(provenance);
    expect(page.results[0]).toMatchObject({
      id64: '9007199254740993',
      ranking_score: 100,
      ranking_tier: 'S',
      score_kind: 'selected_fit',
      selected_archetype: 'flexible',
      distance: 139.45,
      distance_reference: { kind: 'sol', id64: SOL_ID64, name: 'Sol' },
      ranking_provenance: provenance,
      overall_development_potential: 100,
      confidence: 0.82,
      completeness: 0.64,
      archetype_score: null,
      archetype_tier: null,
    });
    expect(page.results[0]).not.toHaveProperty('best_tier');
  });

  it('clamps the wire limit at the 10,000 window and rejects offsets beyond it', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(rankingsEnvelope([])), {
        headers: { 'content-type': 'application/json' },
      }),
    );
    await getArchetypeRankings({
      ...flexibleRequest,
      page_size: 50,
      offset: 9_975,
    });
    const url = new URL((fetchMock.mock.calls[0]?.[0] as Request).url);
    expect(url.searchParams.get('limit')).toBe('25');
    expect(url.searchParams.get('offset')).toBe('9975');

    for (const offset of [10_000, -1, 1.5, 2_000_000_000]) {
      await expect(
        getArchetypeRankings({ ...flexibleRequest, offset }),
      ).rejects.toThrow(RangeError);
    }
    for (const page_size of [0, 51, 24.5]) {
      await expect(
        getArchetypeRankings({ ...flexibleRequest, page_size }),
      ).rejects.toThrow(RangeError);
    }
    await expect(
      getArchetypeRankings({ ...flexibleRequest, archetype: 'agri' as never }),
    ).rejects.toThrow(RangeError);
    expect(FINDER_NAVIGATION_LIMIT).toBe(10_000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('preserves the independent API-owned truncation flag and total = min(qualifying, 10000)', () => {
    const rows = [rankingRow('1', 95, 'S')];
    const truncated = normalizeRankingsResponse(
      rankingsEnvelope(rows, { total: 10_000, is_truncated: true }),
      { ...flexibleRequest, page_size: 50, offset: 9_950 },
    );
    expect(truncated.page).toMatchObject({
      total: 10_000,
      navigable_total: 10_000,
      offset: 9_950,
      truncation: { source: 'rankings', is_truncated: true },
    });
    const exact = normalizeRankingsResponse(
      rankingsEnvelope(rows, { total: 10_000, is_truncated: false }),
      flexibleRequest,
    );
    expect(exact.page.truncation).toEqual({
      source: 'rankings',
      is_truncated: false,
    });
    const below = normalizeRankingsResponse(
      rankingsEnvelope(rows, { total: 3, is_truncated: false }),
      flexibleRequest,
    );
    expect(below.page.navigable_total).toBe(3);
  });

  it('fails closed on a truncated empty window and on a row without score/tier', () => {
    expect(() =>
      normalizeRankingsResponse(
        rankingsEnvelope([], { total: 0, is_truncated: true }),
        flexibleRequest,
      ),
    ).toThrow(TypeError);
    expect(() =>
      normalizeRankingsResponse(
        rankingsEnvelope([{ ...rankingRow('1', 95, 'S'), tier: 'X' as never }]),
        flexibleRequest,
      ),
    ).toThrow(TypeError);
    expect(() =>
      normalizeRankingsResponse(
        rankingsEnvelope([], { ranking: { ranking_version: 'v' } }),
        flexibleRequest,
      ),
    ).toThrow(TypeError);
  });

  it('copies all seven provenance fields and yields null for an incomplete envelope', () => {
    expect(normalizeRankingProvenance(provenance)).toEqual(provenance);
    const { archetype_model_sha256: _dropped, ...sixOnly } = provenance;
    void _dropped;
    expect(normalizeRankingProvenance(sixOnly)).toBeNull();
    expect(normalizeRankingProvenance(undefined)).toBeNull();
    expect(
      normalizeRankingProvenance({ ...provenance, publication_sequence: -1 }),
    ).toBeNull();
  });

  it('passes an abort signal through to the generated operation', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(rankingsEnvelope([])), {
        headers: { 'content-type': 'application/json' },
      }),
    );
    const controller = new AbortController();
    const page: ArchetypeRankingsPage = await getArchetypeRankings(
      flexibleRequest,
      controller.signal,
    );
    expect(page.results).toEqual([]);
    controller.abort();
    expect((fetchMock.mock.calls[0]?.[0] as Request).signal.aborted).toBe(true);
  });
});

describe('Any (local search) page envelope normalization', () => {
  const anyRow = (id64: string, distance: number | null = 12.5) => ({
    id64: id64 as unknown as number,
    name: `System ${id64}`,
    coords: { x: 1, y: 2, z: 3 },
    distance,
    archetype_score: 81,
    archetype_tier: 'A' as const,
    primary_archetype: 'paradise',
    secondary_archetype: 'flexible',
    overall_development_potential: 84,
    confidence: 0.9,
    completeness: 0.85,
  });
  const searchEnvelope = (
    results: ReturnType<typeof anyRow>[],
    extra: Record<string, unknown> = {},
  ) => ({
    results,
    total: results.length,
    count: results.length,
    ranking: provenance,
    ...extra,
  });
  const anchored = {
    reference_coords: { x: 1, y: 2, z: 3 },
    filters: { distance: { min: 0, max: 500 }, economy: 'any' as const },
    sort_by: 'distance',
    size: 50,
    from: 0,
  };
  const star: DistanceAnchor = {
    id64: parseId64('158872029'),
    name: 'HD 38179',
  };

  it('carries the overall score, anchor reference and all seven provenance fields on every row', () => {
    const page = normalizeAnySearchResponse(
      searchEnvelope([anyRow('42'), anyRow('43', null)], { total: 2 }),
      anchored,
      star,
    );
    expect(page.page).toEqual({
      page_size: 50,
      count: 2,
      total: 2,
      navigable_total: 2,
      offset: 0,
      navigation_limit: 10_000,
      truncation: { source: 'local-search', total_is_capped: false },
    });
    expect(page.results[0]).toMatchObject({
      id64: '42',
      ranking_score: 81,
      ranking_tier: 'A',
      score_kind: 'overall_potential',
      selected_archetype: null,
      distance_reference: {
        kind: 'anchor',
        id64: '158872029',
        name: 'HD 38179',
      },
      ranking_provenance: provenance,
      archetype_score: 81,
      overall_development_potential: 84,
      confidence: 0.9,
      completeness: 0.85,
    });
    // No measured distance means no reference, even on an anchored search.
    expect(page.results[1]?.distance_reference).toBeNull();
  });

  it('normalizes a Sol anchor to the sol reference and galaxy-wide to no reference', () => {
    const sol: DistanceAnchor = { id64: SOL_ID64, name: 'Sol' };
    expect(distanceReferenceForAnchor(sol)).toEqual({
      kind: 'sol',
      id64: SOL_ID64,
      name: 'Sol',
    });
    expect(distanceReferenceForAnchor(star)).toEqual({
      kind: 'anchor',
      ...star,
    });
    expect(distanceReferenceForAnchor(null)).toBeNull();
    const solPage = normalizeAnySearchResponse(
      searchEnvelope([anyRow('42', 0)]),
      anchored,
      sol,
    );
    expect(solPage.results[0]?.distance_reference?.kind).toBe('sol');
    expect(solPage.results[0]?.distance).toBe(0);
    const galaxyWide = normalizeAnySearchResponse(
      searchEnvelope([anyRow('42', null)], { total: 1 }),
      { galaxy_wide: true, sort_by: 'development', size: 24, from: 0 },
      star,
    );
    expect(galaxyWide.results[0]?.distance_reference).toBeNull();
    expect(galaxyWide.page.page_size).toBe(24);
  });

  it('exposes the sentinel-backed Any count states: below cap, exact 10,000 and overflow', () => {
    const request = { ...anchored, size: 1, from: 2 };
    const below = normalizeAnySearchResponse(
      searchEnvelope([anyRow('42')], { total: 3, total_is_capped: false }),
      request,
      star,
    );
    expect(below.page).toMatchObject({
      page_size: 1,
      offset: 2,
      total: 3,
      navigable_total: 3,
      truncation: { source: 'local-search', total_is_capped: false },
    });
    const exact = normalizeAnySearchResponse(
      searchEnvelope([anyRow('42')], { total: 10_000, total_is_capped: false }),
      request,
      star,
    );
    expect(exact.page).toMatchObject({
      total: 10_000,
      navigable_total: 10_000,
      truncation: { source: 'local-search', total_is_capped: false },
    });
    const overflow = normalizeAnySearchResponse(
      searchEnvelope([anyRow('42')], { total: 10_000, total_is_capped: true }),
      request,
      star,
    );
    expect(overflow.page).toMatchObject({
      total: 10_000,
      navigable_total: 10_000,
      truncation: { source: 'local-search', total_is_capped: true },
    });
    // A null/absent flag is never read as capped.
    const unflagged = normalizeAnySearchResponse(
      searchEnvelope([anyRow('42')], { total: 10_000, total_is_capped: null }),
      request,
      star,
    );
    expect(unflagged.page.truncation).toEqual({
      source: 'local-search',
      total_is_capped: false,
    });
  });

  it('lists rows without provenance when the envelope lacks the ranking identity', () => {
    const page = normalizeAnySearchResponse(
      { results: [anyRow('42')], count: 1 } as never,
      anchored,
      star,
    );
    expect(page.results[0]?.ranking_provenance).toBeNull();
    expect(page.page.total).toBe(1);
  });
});

describe('facade page size versus clamped wire limit near the 10,000 ceiling', () => {
  const nearCeiling = (body: unknown) =>
    new Response(JSON.stringify(body), {
      headers: { 'content-type': 'application/json' },
    });

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('Any (?page_size=50&offset=9975): wire size 25, envelope page_size 50', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      nearCeiling({
        results: [],
        total: 10_000,
        count: 0,
        total_is_capped: true,
        ranking: provenance,
      }),
    );
    const response = await searchExploreSystems(
      { galaxy_wide: true, sort_by: 'development', size: 25, from: 9_975 },
      undefined,
      null,
      50,
    );
    const request = fetchMock.mock.calls[0]?.[0] as Request;
    expect(await request.clone().json()).toMatchObject({
      size: 25,
      from: 9_975,
    });
    expect(response.page).toMatchObject({
      page_size: 50,
      offset: 9_975,
      total: 10_000,
      navigable_total: 10_000,
    });
    // Without an explicit facade size (the live default-off path) the wire
    // size is the page size, and an invalid facade size never dispatches.
    expect(
      normalizeAnySearchResponse(
        { results: [], total: 3, ranking: provenance },
        { galaxy_wide: true, size: 24, from: 0 },
      ).page.page_size,
    ).toBe(24);
    await expect(
      searchExploreSystems(
        { galaxy_wide: true, size: 25 },
        undefined,
        null,
        51,
      ),
    ).rejects.toThrow(RangeError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('selected (?archetype=flexible&page_size=50&offset=9975): wire limit 25, envelope page_size 50', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      nearCeiling({
        archetype: 'flexible',
        archetype_label: 'Flexible Multi-Role Colony',
        results: [],
        total: 10_000,
        count: 0,
        is_truncated: true,
        ranking: provenance,
      }),
    );
    const page = await getArchetypeRankings({
      archetype: 'flexible',
      min_score: 60,
      page_size: 50,
      offset: 9_975,
    });
    const url = new URL((fetchMock.mock.calls[0]?.[0] as Request).url);
    expect(url.searchParams.get('limit')).toBe('25');
    expect(url.searchParams.get('offset')).toBe('9975');
    expect(page.page).toMatchObject({
      page_size: 50,
      offset: 9_975,
      total: 10_000,
      truncation: { source: 'rankings', is_truncated: true },
    });
  });
});
