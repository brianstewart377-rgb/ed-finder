import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { UseAdmin } from './useAdmin';
import { AdminTab } from './AdminTab';

vi.mock('@/features/profile-sync/useProfileSync', () => ({
  useProfileSync: () => ({
    syncKey: '',
    setSyncKey: vi.fn(),
    hasKey: false,
    lastPushAt: null,
    pull: vi.fn(),
    push: vi.fn(),
    state: { kind: 'idle' },
    resetState: vi.fn(),
    generateKey: () => 'generated-sync-key-123456',
  }),
}));

function admin(overrides: Partial<UseAdmin> = {}): UseAdmin {
  return {
    token: '',
    setToken: vi.fn(),
    forgetToken: vi.fn(),
    hasToken: false,
    status: null,
    cache: null,
    enrichmentStatus: null,
    metaLoading: false,
    metaError: null,
    enrichmentLoading: false,
    enrichmentError: null,
    refresh: vi.fn(),
    actionState: { kind: 'idle' },
    clearCache: vi.fn(),
    rebuildClusters: vi.fn(),
    rebuildRatings: vi.fn(),
    resetActionState: vi.fn(),
    ...overrides,
  };
}

describe('AdminTab enrichment status', () => {
  afterEach(() => cleanup());

  it('keeps enrichment status behind the admin token state', () => {
    render(<AdminTab admin={admin()} />);

    expect(screen.getByText('3. Enrichment status')).toBeTruthy();
    expect(screen.getByText(/Set an admin token to view read-only enrichment status/i)).toBeTruthy();
  });

  it('renders sanitized enrichment status without filesystem paths', () => {
    const { container } = render(
      <AdminTab
        admin={admin({
          token: 'token',
          hasToken: true,
          enrichmentStatus: {
            available: true,
            configured: true,
            state: 'warning',
            message: 'Enrichment status loaded with warnings.',
            source: 'station_enrichment_status_json',
            artifact: {
              file_name: 'station-status.json',
              exists: true,
              updated_at: '2026-06-01T00:00:00+00:00',
              age_seconds: 125,
              path_visible: false,
            },
            checkpoint: {
              exists: true,
              valid: true,
              processed_count: 42,
              last_system_id64: 123456,
              invalid_entry_count: 0,
              error: null,
            },
            latest_run: {
              output_root_exists: true,
              output_dir_name: '20260530-181500-all-records',
              latest_all_records_output_dir_name: '20260530-181500-all-records',
              latest_any_output_dir_name: '20260530-181500-all-records',
              latest_log_file_name: 'station-enrichment.log',
              latest_log_file_exists: true,
            },
            latest_batch: {
              number: 3,
              state: 'completed',
              latest_phase_name: 'final dry-run',
              latest_report_file_name: 'final_dryrun.json',
              latest_stderr_file_name: 'final_dryrun.json.stderr.txt',
            },
            latest_report: {
              valid: true,
              phase_name: 'final dry-run',
              systems_processed: 10,
              metadata_updates: 0,
              confirmed_links: 0,
              conflicts: 1,
              skipped: 0,
              fetch_errors: 2,
              systems_fetch_failed: 1,
              suppressed_station_writes: 0,
              ignored_transient_non_slot: 0,
              dirty_marked_planned: '0/0',
              error: null,
            },
            latest_progress: {
              current: 7,
              total: 10,
              batch_progress_percent: 70,
              latest_system_name: 'Alpha',
              latest_system_id64: 123456,
              fetch_errors: 2,
              systems_fetch_failed: 1,
              all_records_aborted: false,
            },
            rate_limit: {
              recent_429_lines: 3,
              max_consecutive_429_lines: 3,
              repeated_429_detected: true,
              guard_warning_429_count: 3,
              most_recent_429_system: 'Alpha',
              most_recent_429_system_id64: 123456,
              most_recent_retry_after: '120',
              most_recent_backoff_seconds: 120,
            },
            warnings: ['WARNING: latest batch has fetch failures'],
          },
        })}
      />,
    );

    expect(screen.getByText('Checkpointed systems')).toBeTruthy();
    expect(screen.getByText('42')).toBeTruthy();
    expect(screen.getByText('Fetch failures')).toBeTruthy();
    expect(screen.getByText('station-status.json')).toBeTruthy();
    expect(container.textContent).not.toMatch(/\/tmp|\/data|\/home/i);
  });

  it('renders unavailable enrichment status honestly', () => {
    render(
      <AdminTab
        admin={admin({
          token: 'token',
          hasToken: true,
          enrichmentStatus: {
            available: false,
            configured: false,
            state: 'not_configured',
            message: 'Enrichment status artifact is not configured.',
            source: 'station_enrichment_status_json',
            artifact: null,
            checkpoint: null,
            latest_run: null,
            latest_batch: null,
            latest_report: null,
            latest_progress: null,
            rate_limit: null,
            warnings: [],
          },
        })}
      />,
    );

    expect(screen.getByText(/Enrichment status artifact is not configured/i)).toBeTruthy();
    expect(screen.getByText(/It does not run enrichment, Docker, EDSM, or database work/i)).toBeTruthy();
  });
});
