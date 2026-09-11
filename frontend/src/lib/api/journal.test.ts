import { afterEach, describe, expect, it, vi } from 'vitest';
import { jsonFetch } from '@/lib/api/core';
import {
  createV3JournalImport,
  createV3ResearchExport,
  getV3JournalImport,
  getV3JournalSummary,
  getV3ResearchConsent,
  getV3ResearchExport,
  listV3JournalBodies,
  listV3JournalCodex,
  listV3JournalOrganics,
  listV3JournalSales,
  listV3JournalSystems,
  listV3ResearchExports,
  putV3ResearchConsent,
} from './journal';

vi.mock('@/lib/api/core', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api/core')>('@/lib/api/core');
  return { ...actual, jsonFetch: vi.fn() };
});

const mockedJsonFetch = vi.mocked(jsonFetch);

describe('V3 journal api module', () => {
  afterEach(() => {
    mockedJsonFetch.mockReset();
  });

  it('posts a journal import with the V3 payload shape', async () => {
    mockedJsonFetch.mockResolvedValue({ import_id: 'imp-1' });
    await createV3JournalImport({
      parser_version: 'journal-import-worker-v2',
      files: [{
        name: 'Journal.demo.log',
        content_sha256: 'a'.repeat(64),
        size_bytes: 12,
        line_count: 2,
        event_count: 1,
        first_event_at: '2026-08-28T10:00:01Z',
        last_event_at: '2026-08-28T10:00:01Z',
      }],
      events: [{
        event_type: 'Scan',
        event_timestamp: '2026-08-28T10:00:01Z',
        source_record_hash: 'b'.repeat(64),
        source_file: 'Journal.demo.log',
        source_offset: 0,
        payload: { BodyName: 'Demo A' },
      }],
    });

    expect(mockedJsonFetch).toHaveBeenCalledTimes(1);
    const [path, init] = mockedJsonFetch.mock.calls[0] ?? [];
    expect(path).toBe('/v1/journal/imports');
    expect(init).toMatchObject({ method: 'POST' });
    expect(JSON.parse(init?.body as string)).toMatchObject({
      parser_version: 'journal-import-worker-v2',
      files: [{ name: 'Journal.demo.log', content_sha256: 'a'.repeat(64), size_bytes: 12 }],
      events: [{ event_type: 'Scan', source_offset: 0 }],
    });
  });

  it('fetches an import receipt by id', async () => {
    mockedJsonFetch.mockResolvedValue({ import_id: 'imp-1' });
    await getV3JournalImport('imp-1');
    expect(mockedJsonFetch).toHaveBeenCalledWith('/v1/journal/imports/imp-1');
  });

  it('fetches the personal summary', async () => {
    mockedJsonFetch.mockResolvedValue({ events_stored: 3 });
    await getV3JournalSummary();
    expect(mockedJsonFetch).toHaveBeenCalledWith('/v1/journal/summary');
  });

  it('lists systems/bodies/sales with offset+limit query params and codex/organics without', async () => {
    mockedJsonFetch.mockResolvedValue([]);
    await listV3JournalSystems(10, 25);
    expect(mockedJsonFetch).toHaveBeenCalledWith('/v1/journal/systems?offset=10&limit=25');
    await listV3JournalBodies();
    expect(mockedJsonFetch).toHaveBeenCalledWith('/v1/journal/bodies?offset=0&limit=50');
    await listV3JournalSales(2, 5);
    expect(mockedJsonFetch).toHaveBeenCalledWith('/v1/journal/sales?offset=2&limit=5');
    await listV3JournalCodex();
    expect(mockedJsonFetch).toHaveBeenCalledWith('/v1/journal/codex');
    await listV3JournalOrganics();
    expect(mockedJsonFetch).toHaveBeenCalledWith('/v1/journal/organics');
  });

  it('reads and writes research consent', async () => {
    mockedJsonFetch.mockResolvedValue({ decision: 'NONE' });
    await getV3ResearchConsent();
    expect(mockedJsonFetch).toHaveBeenCalledWith('/v1/journal/research-consent');

    mockedJsonFetch.mockResolvedValue({ decision: 'GRANT' });
    await putV3ResearchConsent({ decision: 'GRANT' });
    expect(mockedJsonFetch).toHaveBeenCalledWith(
      '/v1/journal/research-consent',
      expect.objectContaining({ method: 'PUT' }),
    );
    const [, init] = mockedJsonFetch.mock.calls[1] ?? [];
    expect(JSON.parse(init?.body as string)).toEqual({ decision: 'GRANT' });
  });

  it('creates, lists and fetches research export batches', async () => {
    mockedJsonFetch.mockResolvedValue({ export_batch_id: 'exp-1' });
    await createV3ResearchExport({ limit: 1000 });
    expect(mockedJsonFetch).toHaveBeenCalledWith(
      '/v1/journal/research-exports',
      expect.objectContaining({ method: 'POST' }),
    );

    mockedJsonFetch.mockResolvedValue([]);
    await listV3ResearchExports();
    expect(mockedJsonFetch).toHaveBeenCalledWith('/v1/journal/research-exports');

    mockedJsonFetch.mockResolvedValue({ export_batch_id: 'exp-1', payload: {} });
    await getV3ResearchExport('exp-1');
    expect(mockedJsonFetch).toHaveBeenCalledWith('/v1/journal/research-exports/exp-1');
  });
});
