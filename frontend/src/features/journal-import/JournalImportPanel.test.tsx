import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { importJournal } from '@/lib/api';
import { useJournalTelemetrySummary } from '@/features/my-work/useJournalTelemetrySummary';
import { JournalImportPanel } from './JournalImportPanel';
import { parseJournalFiles } from './parseJournalFiles';

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    importJournal: vi.fn(),
  };
});

vi.mock('./parseJournalFiles', () => ({
  parseJournalFiles: vi.fn(),
}));

vi.mock('@/features/my-work/useJournalTelemetrySummary', () => ({
  useJournalTelemetrySummary: vi.fn(),
}));

vi.mock('@/store/syncKeyStore', () => ({
  useSyncKeyStore: (selector: (state: { syncKey: string }) => string) => selector({ syncKey: 'sync-key-1234567890' }),
}));

const mockedImportJournal = vi.mocked(importJournal);
const mockedParseJournalFiles = vi.mocked(parseJournalFiles);
const mockedUseJournalTelemetrySummary = vi.mocked(useJournalTelemetrySummary);

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <JournalImportPanel />
    </QueryClientProvider>,
  );
}

describe('JournalImportPanel', () => {
  afterEach(() => {
    mockedImportJournal.mockReset();
    mockedParseJournalFiles.mockReset();
    mockedUseJournalTelemetrySummary.mockReset();
  });

  it('parses selected files and shows preview details', async () => {
    mockedUseJournalTelemetrySummary.mockReturnValue({
      data: null,
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useJournalTelemetrySummary>);
    mockedParseJournalFiles.mockResolvedValue({
      client_manifest: {
        parser_version: 'journal-import-worker-v1',
        files: [{ name: 'Journal.demo.log', event_count: 2 }],
      },
      observations: [
        {
          observation_key: 'abc123abc123abc123abc123abc123ab',
          source_file: 'Journal.demo.log',
          event_type: 'Scan',
          observed_at: '2026-07-08T18:00:00Z',
          system_id64: 123,
          system_name: 'Test System',
          subject_type: 'body',
          subject_id: '7',
          summary: 'Body scan observed.',
          payload: { BodyName: 'Test 7' },
          privacy_boundary: { strip_before_network: true },
        },
        {
          observation_key: 'def456def456def456def456def456de',
          source_file: 'Journal.demo.log',
          event_type: 'Location',
          observed_at: '2026-07-08T18:00:10Z',
          system_id64: 123,
          system_name: 'Test System',
          subject_type: 'system',
          subject_id: null,
          summary: 'Commander location observed.',
          payload: { StarSystem: 'Test System' },
          privacy_boundary: { strip_before_network: true },
        },
      ],
      preview: {
        files_processed: 1,
        lines_read: 4,
        observations_ready: 2,
        skipped_lines: 2,
        event_counts: { Scan: 1, Location: 1 },
      },
    });

    renderPanel();

    const input = screen.getByTestId('journal-import-file-input') as HTMLInputElement;
    const file = new File(['{"event":"Scan"}'], 'Journal.demo.log', { type: 'text/plain' });
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByTestId('journal-import-parse'));

    expect(await screen.findByTestId('journal-import-preview')).toBeTruthy();
    expect(screen.getByTestId('journal-import-preview-files').textContent).toContain('Journal.demo.log');
    expect(screen.getByText(/Scan 1 \| Location 1/)).toBeTruthy();
  });

  it('submits parsed observations and shows a receipt', async () => {
    mockedUseJournalTelemetrySummary.mockReturnValue({
      data: null,
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useJournalTelemetrySummary>);
    mockedParseJournalFiles.mockResolvedValue({
      client_manifest: {
        parser_version: 'journal-import-worker-v1',
        files: [{ name: 'Journal.demo.log', event_count: 1 }],
      },
      observations: [
        {
          observation_key: 'abc123abc123abc123abc123abc123ab',
          source_file: 'Journal.demo.log',
          event_type: 'Scan',
          observed_at: '2026-07-08T18:00:00Z',
          system_id64: 123,
          system_name: 'Test System',
          subject_type: 'body',
          subject_id: '7',
          summary: 'Body scan observed.',
          payload: { BodyName: 'Test 7' },
          privacy_boundary: { strip_before_network: true },
        },
      ],
      preview: {
        files_processed: 1,
        lines_read: 1,
        observations_ready: 1,
        skipped_lines: 0,
        event_counts: { Scan: 1 },
      },
    });
    mockedImportJournal.mockResolvedValue({
      run_key: 'jrnl-20260708-demo',
      status: 'succeeded',
      parser_version: 'journal-import-worker-v1',
      started_at: '2026-07-08T18:00:00Z',
      finished_at: '2026-07-08T18:00:01Z',
      files: [{ name: 'Journal.demo.log', event_count: 1 }],
      summary: {
        observations_received: 1,
        observations_staged: 1,
        duplicates_skipped: 0,
        conflicts_flagged: 0,
        files_seen: 1,
        event_counts: { Scan: 1 },
      },
    });

    renderPanel();

    const input = screen.getByTestId('journal-import-file-input') as HTMLInputElement;
    const file = new File(['{"event":"Scan"}'], 'Journal.demo.log', { type: 'text/plain' });
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByTestId('journal-import-parse'));
    await screen.findByTestId('journal-import-preview');

    fireEvent.click(screen.getByTestId('journal-import-submit'));

    await waitFor(() => expect(mockedImportJournal).toHaveBeenCalledTimes(1));
    expect(mockedImportJournal.mock.calls[0]?.[0]).toEqual(expect.objectContaining({
      sync_key: 'sync-key-1234567890',
      evidence_mode: 'staging_only',
    }));
    expect(await screen.findByTestId('journal-import-receipt')).toBeTruthy();
    expect(screen.getByTestId('journal-import-receipt-files').textContent).toContain('Journal.demo.log');
    expect(screen.getByText(/Event mix: Scan 1/)).toBeTruthy();
  });

  it('shows a personal telemetry snapshot when sync-key telemetry already exists', () => {
    mockedUseJournalTelemetrySummary.mockReturnValue({
      data: {
        sync_key: 'sync-key-1234567890',
        runs_count: 2,
        last_imported_at: '2026-07-11T12:00:00.000Z',
        observations_staged: 5,
        duplicates_skipped: 1,
        systems_observed: 3,
        body_observation_count: 4,
        docked_observation_count: 1,
        event_counts: { Scan: 4, Docked: 1 },
        recent_runs: [],
        recent_systems: [],
      },
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useJournalTelemetrySummary>);

    renderPanel();

    expect(screen.getByTestId('journal-import-telemetry-summary').textContent).toContain('Personal telemetry snapshot');
    expect(screen.getByTestId('journal-import-telemetry-summary').textContent).toContain('2 imports | 3 systems observed | 5 staged observations');
    expect(screen.getByText(/Event mix: Scan 4 \| Docked 1/)).toBeTruthy();
  });
});
