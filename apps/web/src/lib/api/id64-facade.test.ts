import { afterEach, describe, expect, it, vi } from 'vitest';
import { getSystem } from './client';
import { parseId64 } from '$lib/domain/id64';

afterEach(() => vi.restoreAllMocks());

describe('id64-bearing application API facade', () => {
  it('parses an oversized system identifier before JavaScript can round it', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        '{"system":{"id64":18446744073709551615,"system_id64":9007199254740993,"name":"Lossless"}}',
        {
          status: 200,
          headers: { 'content-type': 'application/json' },
        },
      ),
    );

    const result = await getSystem(parseId64('18446744073709551615'));

    expect(result).toEqual({
      id64: '18446744073709551615',
      system_id64: '9007199254740993',
      name: 'Lossless',
    });
    // The generated Hey API transport dispatches a single same-origin,
    // credentialed Request object rather than a (url, init) pair.
    const request = fetchMock.mock.calls[0]?.[0] as Request;
    expect(request).toBeInstanceOf(Request);
    expect(fetchMock.mock.calls[0]?.[1]).toBeUndefined();
    expect(request.url).toContain('/api/system/18446744073709551615');
    expect(request.credentials).toBe('include');
  });
});
