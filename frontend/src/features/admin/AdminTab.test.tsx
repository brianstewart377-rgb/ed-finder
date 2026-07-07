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
    warehouseStatus: null,
    metaLoading: false,
    metaError: null,
    enrichmentLoading: false,
    enrichmentError: null,
    warehouseLoading: false,
    warehouseError: null,
    refresh: vi.fn(),
    actionState: { kind: 'idle' },
    clearCache: vi.fn(),
    rebuildClusters: vi.fn(),
    rebuildRatings: vi.fn(),
    resetActionState: vi.fn(),
    ...overrides,
    dataStatus: overrides.dataStatus ?? null,
    dataStatusLoading: overrides.dataStatusLoading ?? false,
    dataStatusError: overrides.dataStatusError ?? null,
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

  it('keeps warehouse status behind the admin token state', () => {
    render(<AdminTab admin={admin()} />);

    expect(screen.getByText('4. Warehouse status')).toBeTruthy();
    expect(screen.getByText(/Set an admin token to view read-only warehouse status/i)).toBeTruthy();
  });

  it('renders sanitized warehouse status without filesystem paths', () => {
    const { container } = render(
      <AdminTab
        admin={admin({
          token: 'token',
          hasToken: true,
          warehouseStatus: {
            available: true,
            configured: true,
            state: 'blocked',
            message: 'Warehouse status has blocked reconciliation evidence for review.',
            source: 'warehouse_reconciliation_status_json',
            artifact: {
              file_name: 'warehouse-status.json',
              exists: true,
              updated_at: '2026-06-01T00:00:00+00:00',
              age_seconds: 3600,
              path_visible: false,
            },
            latest_snapshot_load: {
              source_run_key: 'run-warehouse',
              source_file_key: 'file-warehouse',
              source: 'edsm_nightly_stations',
              source_files_considered: 2,
              source_type_distribution: { edsm_nightly_stations: 1 },
              source_format_distribution: { json: 1 },
            },
            latest_reconciliation_run: {
              schema_version: 'enrichment_staging_reconciliation/v1',
              coverage_schema_version: 'enrichment_warehouse_coverage_report/v1',
              dry_run: true,
              report_only: true,
              canonical_writes_planned: 0,
              staged_station_rows_considered: 12,
              staged_body_rows_considered: 8,
              staged_ring_rows_considered: 3,
              canonical_matches_found: 10,
              canonical_misses: 2,
              ambiguous_matches: 1,
              insufficient_evidence: 1,
              warnings: 2,
              errors: 0,
            },
            source_coverage: {
              station_candidates: 12,
              body_candidates: 8,
              ring_candidates: 3,
              systems_with_station_evidence: 4,
              systems_missing_station_evidence: 2,
              trusted_ring_evidence_bodies: 1,
              unknown_ring_evidence_bodies: 3,
              explicit_no_ring_evidence_bodies: 1,
              staged_ring_candidates: 3,
              trusted_local_matched_ring_candidates: 1,
            },
            evidence_health: {
              unresolved_stations: 5,
              blocked_conflicts: 2,
              risky_conflicts: 3,
              stale_records: 4,
              volatile_records: 1,
              stale_or_undated_source_records: 7,
              malformed_or_skipped_rows: 6,
              duplicate_source_records: 4,
              source_identity_conflicts: 2,
              high_value_systems_needing_better_evidence: 3,
            },
            canonical_safety: {
              canonical_tables_untouched: true,
              canonical_writes_planned: 0,
              dry_run: true,
              report_only: true,
            },
            warnings: ['volatile_source_evidence_not_canonical_update'],
            errors: [],
          },
        })}
      />,
    );

    expect(screen.getByText('Warehouse artifact')).toBeTruthy();
    expect(screen.getByText('warehouse-status.json')).toBeTruthy();
    expect(screen.getByText('Canonical untouched')).toBeTruthy();
    expect(screen.getByText('Missing station evidence')).toBeTruthy();
    expect(screen.getByText('Trusted ring bodies')).toBeTruthy();
    expect(screen.getByText('Needs evidence systems')).toBeTruthy();
    expect(screen.getByText('edsm_nightly_stations:1')).toBeTruthy();
    expect(container.textContent).not.toMatch(/\/tmp|\/data|\/home/i);
  });

  it('renders unavailable warehouse status honestly', () => {
    render(
      <AdminTab
        admin={admin({
          token: 'token',
          hasToken: true,
          warehouseStatus: {
            available: false,
            configured: false,
            state: 'not_configured',
            message: 'Warehouse status artifact is not configured.',
            source: 'warehouse_reconciliation_status_json',
            artifact: null,
            latest_snapshot_load: null,
            latest_reconciliation_run: null,
            source_coverage: null,
            evidence_health: null,
            canonical_safety: null,
            warnings: [],
            errors: [],
          },
        })}
      />,
    );

    expect(screen.getByText(/Warehouse status artifact is not configured/i)).toBeTruthy();
    expect(screen.getByText(/It does not generate reports, invoke Docker, call live APIs, or query the warehouse/i)).toBeTruthy();
  });
});
