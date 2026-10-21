import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, getSystem } from './client';
import { parseId64 } from '$lib/domain/id64';

afterEach(() => vi.restoreAllMocks());

const GENERATION_1 =
  '{"generation_id":"g-1","generation_key":"k1","publication_sequence":"1","published_at":"2026-10-01T00:00:00+00:00"}';
const GENERATION_2 =
  '{"generation_id":"g-2","generation_key":"k2","publication_sequence":"2","published_at":"2026-10-02T00:00:00+00:00"}';

const json = (body: string) =>
  new Response(body, {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });

const pathOf = (input: unknown) => new URL((input as Request).url).pathname;

describe('id64-bearing application API facade', () => {
  it('reads Inspect from the V3 canonical routes with the exact decimal id64', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(async (input) => {
        const path = pathOf(input);
        if (path === '/api/v1/generation') return json(GENERATION_1);
        if (path === '/api/v1/systems/9007199254740993')
          return json(
            '{"id64":"9007199254740993","name":"Lossless","x_ly":1,"y_ly":2,"z_ly":3,"source_body_count":1,"loaded_body_count":1,"lifecycle_state":"ACTIVE","source_updated_at":null}',
          );
        if (path === '/api/v1/systems/9007199254740993/bodies')
          return json(
            '[{"body_id":"36028797018963969","source_body_id64":"36028797018963969","frontier_body_id":"0","direct_parent_body_id":null,"name":"Lossless","body_type":"star","is_main_star":true,"spectral_class":"K1","luminosity_class":"V","is_landable":null,"radius_km":500000,"planet_mass_earth":null,"stellar_mass_solar":0.8,"surface_pressure_atm":null,"semi_major_axis_km":null,"distance_from_arrival_ls":0,"lifecycle_state":"ACTIVE","signals":[]}]',
          );
        return json('[]');
      });

    const result = await getSystem(parseId64('9007199254740993'));

    expect(result.id64).toBe('9007199254740993');
    expect(result.name).toBe('Lossless');
    expect(result.bodies).toHaveLength(1);
    // Canonical body keys beyond 2^53 stay lossless decimal strings.
    expect(result.bodies[0]?.bodyKey).toBe('36028797018963969');
    expect(result.bodies[0]?.id).toBe(0);
    const requests = fetchMock.mock.calls.map(([input]) => input as Request);
    // The four reads are fenced by the generation identity on both sides.
    expect(pathOf(requests[0])).toBe('/api/v1/generation');
    expect(pathOf(requests.at(-1))).toBe('/api/v1/generation');
    expect(requests.map(pathOf).sort()).toEqual([
      '/api/v1/generation',
      '/api/v1/generation',
      '/api/v1/systems/9007199254740993',
      '/api/v1/systems/9007199254740993/bodies',
      '/api/v1/systems/9007199254740993/rings',
      '/api/v1/systems/9007199254740993/stations',
    ]);
    for (const request of requests) {
      // The generated Hey API transport dispatches a single same-origin,
      // credentialed Request object rather than a (url, init) pair.
      expect(request).toBeInstanceOf(Request);
      expect(request.credentials).toBe('include');
    }
    expect(fetchMock.mock.calls[0]?.[1]).toBeUndefined();
  });

  it('retries a read that straddles a publication, then fails closed', async () => {
    const generations = [
      GENERATION_1,
      GENERATION_2,
      GENERATION_2,
      GENERATION_2,
    ];
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(async (input) => {
        const path = pathOf(input);
        if (path === '/api/v1/generation') return json(generations.shift()!);
        if (path === '/api/v1/systems/42')
          return json(
            '{"id64":"42","name":"Fenced","x_ly":0,"y_ly":0,"z_ly":0,"source_body_count":null,"loaded_body_count":0,"lifecycle_state":"ACTIVE","source_updated_at":null}',
          );
        return json('[]');
      });

    // The first attempt straddles g-1 -> g-2; the retry sees g-2 on both sides.
    const fenced = await getSystem(parseId64('42'));
    expect(fenced.name).toBe('Fenced');
    expect(
      fetchMock.mock.calls.filter(
        ([input]) => pathOf(input) === '/api/v1/systems/42',
      ),
    ).toHaveLength(2);

    generations.push(GENERATION_1, GENERATION_2, GENERATION_1, GENERATION_2);
    const failure = await getSystem(parseId64('42')).catch((error) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).status).toBe(503);
  });

  it('re-reads a 404 that straddled a publication and reports a stable 404', async () => {
    const generations = [
      GENERATION_1,
      GENERATION_2,
      GENERATION_2,
      GENERATION_2,
    ];
    let published = false;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = pathOf(input);
      if (path === '/api/v1/generation') {
        const next = generations.shift()!;
        published = next === GENERATION_2;
        return json(next);
      }
      if (/^\/api\/v1\/systems\/[0-9]+$/u.test(path))
        return path.endsWith('/77') && published && generations.length < 3
          ? json(
              '{"id64":"77","name":"Newly published","x_ly":0,"y_ly":0,"z_ly":0,"source_body_count":null,"loaded_body_count":0,"lifecycle_state":"ACTIVE","source_updated_at":null}',
            )
          : new Response('{"detail":"not found"}', {
              status: 404,
              headers: { 'content-type': 'application/json' },
            });
      return json('[]');
    });

    // Attempt 1 sees g-1 before and g-2 after with a 404 in between: the 404
    // is not trusted, and the retry (g-2 on both sides) finds the system.
    await expect(getSystem(parseId64('77'))).resolves.toMatchObject({
      name: 'Newly published',
    });

    generations.push(GENERATION_2, GENERATION_2);
    published = false;
    const missing = await getSystem(parseId64('4242')).catch((error) => error);
    expect(missing).toBeInstanceOf(ApiError);
    expect((missing as ApiError).status).toBe(404);
  });
});
