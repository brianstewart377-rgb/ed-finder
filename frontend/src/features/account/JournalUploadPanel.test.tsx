import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, createV3JournalImport } from '@/lib/api';
import type { V3JournalImportRequest } from '@/lib/api';
import { useAuth } from '@/features/auth/useAuth';
import { parseJournalFiles } from '@/features/journal-import/parseJournalFiles';
import type { JournalImportParseResult } from '@ed-finder/planner-core/journal';
import { AccountWorkspace } from './AccountWorkspace';
import { JournalUploadPanel } from './JournalUploadPanel';

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    createV3JournalImport: vi.fn(),
  };
});

vi.mock('@/features/journal-import/parseJournalFiles', () => ({
  parseJournalFiles: vi.fn(),
}));

vi.mock('@/features/auth/useAuth', () => ({
  useAuth: vi.fn(),
}));

const mockedCreateV3JournalImport = vi.mocked(createV3JournalImport);
const mockedParseJournalFiles = vi.mocked(parseJournalFiles);
const mockedUseAuth = vi.mocked(useAuth);

const PARSE_RESULT: JournalImportParseResult = {
  client_manifest: {
    parser_version: 'journal-import-worker-v2',
    files: [{ name: 'Journal.demo.log', event_count: 1 }],
  },
  file_manifest: [{
    name: 'Journal.demo.log',
    content_sha256: 'c'.repeat(64),
    size_bytes: 10,
    event_count: 1,
    line_count: 2,
  }],
  observations: [{
    observation_key: 'd'.repeat(64),
    source_file: 'Journal.demo.log',
    event_type: 'Scan',
    observed_at: '2026-08-28T10:00:01Z',
    system_id64: '123',
    system_name: 'Demo',
    subject_type: 'body',
    subject_id: '1',
    summary: 'Body scan observed.',
    payload: { BodyName: 'Demo A' },
    privacy_boundary: { strip_before_network: true },
  }],
  powerplay_events: [],
  checkpoints: [],
  preview: {
    files_processed: 1,
    lines_read: 2,
    observations_ready: 1,
    powerplay_events_ready: 0,
    skipped_lines: 0,
    event_counts: { Scan: 1 },
  },
};

function makeReceipt(overrides: Partial<Record<'files_skipped' | 'duplicates_skipped' | 'events_inserted' | 'privacy_stripped_fields', number>> = {}) {
  return {
    import_id: 'imp-1',
    status: 'READY',
    files_received: 1,
    files_skipped: overrides.files_skipped ?? 0,
    files_admitted: 1,
    events_received: 1,
    events_inserted: overrides.events_inserted ?? 1,
    duplicates_skipped: overrides.duplicates_skipped ?? 0,
    privacy_stripped_fields: overrides.privacy_stripped_fields ?? 0,
    event_counts: { Scan: 1 },
    started_at: '2026-08-28T10:00:02Z',
    finished_at: '2026-08-28T10:00:02Z',
  };
}

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <JournalUploadPanel />
    </QueryClientProvider>,
  );
}

function selectJournalFile() {
  const input = screen.getByTestId('journal-upload-file-input') as HTMLInputElement;
  const file = new File([`{"event":"Scan"}\n`], 'Journal.demo.log', { type: 'text/plain' });
  fireEvent.change(input, { target: { files: [file] } });
  return file;
}

describe('JournalUploadPanel', () => {
  afterEach(() => {
    mockedCreateV3JournalImport.mockReset();
    mockedParseJournalFiles.mockReset();
    mockedUseAuth.mockReset();
  });

  it('parses selected files, shows live progress, uploads the V3 request shape, and renders the receipt', async () => {
    mockedParseJournalFiles.mockImplementation(async (_files, onProgress) => {
      onProgress?.({ files_processed: 1, files_total: 1, events_parsed: 1 });
      return PARSE_RESULT;
    });
    mockedCreateV3JournalImport.mockResolvedValue(makeReceipt({ files_skipped: 1, duplicates_skipped: 2, privacy_stripped_fields: 3 }));

    renderPanel();
    selectJournalFile();

    const progressCounts = await screen.findByTestId('journal-upload-progress-counts');
    expect(progressCounts.textContent).toContain('Files processed 1/1');
    expect(progressCounts.textContent).toContain('Events parsed 1');

    await waitFor(() => expect(mockedCreateV3JournalImport).toHaveBeenCalledTimes(1));
    expect(mockedCreateV3JournalImport.mock.calls[0]?.[0]).toEqual({
      parser_version: 'journal-import-worker-v2',
      files: [{
        name: 'Journal.demo.log',
        content_sha256: 'c'.repeat(64),
        size_bytes: 10,
        line_count: 2,
        event_count: 1,
        first_event_at: '2026-08-28T10:00:01Z',
        last_event_at: '2026-08-28T10:00:01Z',
      }],
      events: [{
        event_type: 'Scan',
        event_timestamp: '2026-08-28T10:00:01Z',
        source_record_hash: 'd'.repeat(64),
        source_file: 'Journal.demo.log',
        source_offset: 0,
        payload: { BodyName: 'Demo A' },
      }],
    });

    const receipt = await screen.findByTestId('journal-upload-receipt');
    expect(receipt).toBeTruthy();
    expect(screen.getByTestId('journal-upload-metric-events-inserted').textContent).toContain('1');
    expect(screen.getByTestId('journal-upload-metric-duplicates-skipped').textContent).toContain('2');
    expect(screen.getByTestId('journal-upload-metric-privacy-stripped-fields').textContent).toContain('3');
    expect(screen.getByTestId('journal-upload-files-skipped').textContent).toContain('1 file unchanged, skipped');
  });

  it('handles dropped .log/.json files through the same parse path', async () => {
    mockedParseJournalFiles.mockResolvedValue(PARSE_RESULT);
    mockedCreateV3JournalImport.mockResolvedValue(makeReceipt());

    renderPanel();
    const dropzone = screen.getByTestId('journal-upload-dropzone');
    // jsdom does not implement the DataTransfer constructor — a plain
    // { files } object exercises the same handler path.
    const dataTransfer = {
      files: [
        new File(['{"event":"Scan"}\n'], 'Journal.drop.log', { type: 'text/plain' }),
        new File(['ignored'], 'notes.txt', { type: 'text/plain' }),
      ],
    } as unknown as DataTransfer;
    fireEvent.drop(dropzone, { dataTransfer });

    await waitFor(() => expect(mockedParseJournalFiles).toHaveBeenCalledTimes(1));
    const dropped = mockedParseJournalFiles.mock.calls[0]?.[0] as File[];
    expect(dropped.map((f) => f.name)).toEqual(['Journal.drop.log']);
    expect(await screen.findByTestId('journal-upload-receipt')).toBeTruthy();
  });

  it('hides the folder picker when webkitdirectory is unsupported', () => {
    renderPanel();
    expect(screen.getByTestId('journal-upload-file-input')).toBeTruthy();
    // jsdom does not implement webkitdirectory — the feature-detect hides it.
    expect(screen.queryByTestId('journal-upload-folder-input')).toBeNull();
  });

  it('surfaces the daily quota message on a 429 receipt', async () => {
    mockedParseJournalFiles.mockResolvedValue(PARSE_RESULT);
    mockedCreateV3JournalImport.mockRejectedValue(
      new ApiError(429, '/v1/journal/imports', '{"title":"Quota exceeded"}'),
    );

    renderPanel();
    selectJournalFile();

    expect((await screen.findByTestId('journal-upload-error')).textContent).toContain('Daily import quota exceeded (429)');
  });

  it('refuses a selection over the 50,000-event cap with friendly copy and no raw RFC 7807 body', async () => {
    const oversized = {
      ...PARSE_RESULT,
      observations: Array.from({ length: 50_001 }, (_, i) => ({
        ...PARSE_RESULT.observations[0],
        observation_key: `o-${i}`.padEnd(64, 'k'),
      })),
    };
    mockedParseJournalFiles.mockResolvedValue(oversized);

    renderPanel();
    selectJournalFile();

    const errorBox = await screen.findByTestId('journal-upload-error');
    expect(errorBox.textContent).toContain('50,000-event per-upload cap');
    expect(errorBox.textContent).toContain('50,001');
    // Friendly pre-flight copy — never the raw API 422 body.
    expect(errorBox.textContent).not.toContain('/v1/journal/imports');
    expect(errorBox.textContent).not.toContain('"detail"');
    expect(mockedCreateV3JournalImport).not.toHaveBeenCalled();
  });

  it('uploads a selection at exactly the 50,000-event cap', async () => {
    const atCap = {
      ...PARSE_RESULT,
      observations: Array.from({ length: 50_000 }, (_, i) => ({
        ...PARSE_RESULT.observations[0],
        observation_key: `c-${i}`.padEnd(64, 'k'),
      })),
    };
    mockedParseJournalFiles.mockResolvedValue(atCap);
    mockedCreateV3JournalImport.mockResolvedValue(makeReceipt());

    renderPanel();
    selectJournalFile();

    await waitFor(() => expect(mockedCreateV3JournalImport).toHaveBeenCalledTimes(1));
    expect(await screen.findByTestId('journal-upload-receipt')).toBeTruthy();
  });

  it('ignores a re-entrant start while a run is in flight and disables the pickers', async () => {
    let resolveParse!: (result: JournalImportParseResult) => void;
    mockedParseJournalFiles.mockImplementation(
      () => new Promise<JournalImportParseResult>((resolve) => { resolveParse = resolve; }),
    );
    mockedCreateV3JournalImport.mockResolvedValue(makeReceipt());

    renderPanel();
    const file = new File(['{"event":"Scan"}\n'], 'Journal.demo.log', { type: 'text/plain' });
    const input = screen.getByTestId('journal-upload-file-input') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
    // Re-entrant start while the first parse is still in flight.
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(mockedParseJournalFiles).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(input.disabled).toBe(true));
    expect(screen.getByTestId('journal-upload-dropzone').getAttribute('aria-disabled')).toBe('true');

    // Dropping files while busy is inert too.
    fireEvent.drop(screen.getByTestId('journal-upload-dropzone'), {
      dataTransfer: { files: [file] } as unknown as DataTransfer,
    });
    expect(mockedParseJournalFiles).toHaveBeenCalledTimes(1);

    resolveParse(PARSE_RESULT);
    await screen.findByTestId('journal-upload-receipt');
    expect(mockedCreateV3JournalImport).toHaveBeenCalledTimes(1);
    expect(mockedParseJournalFiles).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(input.disabled).toBe(false));
  });

  it('warns with a count when observations lack a timestamp instead of silently dropping them', async () => {
    const withDrop = {
      ...PARSE_RESULT,
      observations: [
        PARSE_RESULT.observations[0],
        { ...PARSE_RESULT.observations[0], observation_key: 'e'.repeat(64), observed_at: null },
      ],
    };
    mockedParseJournalFiles.mockResolvedValue(withDrop);
    mockedCreateV3JournalImport.mockResolvedValue(makeReceipt());

    renderPanel();
    selectJournalFile();

    const warnings = await screen.findByTestId('journal-upload-warnings');
    expect(warnings.textContent).toContain('1 observation without a timestamp was not uploaded');

    await waitFor(() => expect(mockedCreateV3JournalImport).toHaveBeenCalledTimes(1));
    const request = mockedCreateV3JournalImport.mock.calls[0]?.[0] as V3JournalImportRequest;
    expect(request.events).toHaveLength(1);
  });

  it('never mentions research contribution or consent in the upload surface', () => {
    renderPanel();
    expect(screen.queryByText(/consent/i)).toBeNull();
    expect(screen.queryByText(/research/i)).toBeNull();
  });

  it('shows a sign-in prompt instead of the panels for anonymous visitors', () => {
    mockedUseAuth.mockReturnValue({
      loading: false,
      authenticated: false,
      user: null,
      ownerClaimAvailable: false,
      error: null,
      signIn: vi.fn(),
      signOut: vi.fn(),
      claimOwner: vi.fn(),
      refresh: vi.fn(),
    });

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <AccountWorkspace />
      </QueryClientProvider>,
    );

    expect(screen.getByTestId('account-sign-in-prompt')).toBeTruthy();
    expect(screen.queryByTestId('journal-upload-panel')).toBeNull();
    expect(screen.queryByTestId('research-consent-card')).toBeNull();
  });
});
