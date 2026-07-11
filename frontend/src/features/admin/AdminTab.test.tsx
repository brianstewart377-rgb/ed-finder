import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AdminOperationHistoryEntry } from '@/types/api';
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
    cronStatus: null,
    metaLoading: false,
    metaError: null,
    enrichmentLoading: false,
    enrichmentError: null,
    warehouseLoading: false,
    warehouseError: null,
    cronStatusLoading: false,
    cronStatusError: null,
    importSafetyGates: null,
    importSourceRuns: [],
    operationHistory: [],
    refresh: vi.fn(),
    importDashboardLoading: false,
    importDashboardError: null,
    operationHistoryLoading: false,
    operationHistoryError: null,
    lastOperationResult: null,
    actionState: { kind: 'idle' },
    clearCache: vi.fn(),
    rebuildClusters: vi.fn(),
    rebuildRatings: vi.fn(),
    runTelemetryHotLogSnapshot: vi.fn(),
    runDataInvariants: vi.fn(),
    resetActionState: vi.fn(),
    clearLastOperationResult: vi.fn(),
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

    expect(screen.getByText('5. Enrichment status')).toBeTruthy();
    expect(screen.getByText(/Set an admin token to view read-only enrichment status/i)).toBeTruthy();
  });

  it('keeps scheduler status behind the admin token state', () => {
    render(<AdminTab admin={admin()} />);

    expect(screen.getByText('4. Scheduler status')).toBeTruthy();
    expect(screen.getByText(/Set an admin token to view scheduler and cron recency/i)).toBeTruthy();
  });

  it('renders scheduler and cron recency details', () => {
    render(
      <AdminTab
        admin={admin({
          token: 'token',
          hasToken: true,
          cronStatus: {
            schema_version: 'admin_cron_status/v1',
            read_only: true,
            last_nightly_update: '2026-07-11T01:30:00Z',
            scheduled_source_runs: {
              runs_last_24h: 4,
              failed_runs_last_24h: 1,
              latest_started_at: '2026-07-11T02:00:00Z',
              latest_finished_at: '2026-07-11T02:05:00Z',
              recent_sources: [
                {
                  source_name: 'spansh_import',
                  domain: 'canonical',
                  trigger_context: 'scheduled_nightly',
                  status: 'succeeded',
                  started_at: '2026-07-11T02:00:00Z',
                  finished_at: '2026-07-11T02:05:00Z',
                  rows_read: 900,
                  rows_staged: 850,
                },
              ],
            },
            ratings_backlog: {
              dirty_systems: 12,
              oldest_dirty_updated_at: '2026-07-10T23:30:00Z',
              newest_dirty_updated_at: '2026-07-11T02:15:00Z',
            },
            jobs: {
              cluster_rebuild: {
                status: 'completed',
                start_time: '2026-07-11T02:10:00Z',
                end_time: '2026-07-11T02:12:00Z',
                exit_code: 0,
                error: null,
              },
              ratings_rebuild: {
                status: 'completed',
                start_time: '2026-07-11T02:15:00Z',
                end_time: '2026-07-11T02:16:00Z',
                exit_code: 0,
                error: null,
                dirty_before: 12,
                cleared: 12,
              },
            },
          },
        })}
      />,
    );

    expect(screen.getByTestId('admin-cron-status').textContent).toContain('Scheduled runs (24h)');
    expect(screen.getByTestId('admin-cron-status').textContent).toContain('Dirty ratings backlog');
    expect(screen.getByText(/Cluster rebuild/i)).toBeTruthy();
    expect(screen.getByText(/Ratings rebuild/i)).toBeTruthy();
    expect(screen.getByText(/spansh_import \(canonical\)/i)).toBeTruthy();
    expect(screen.getByText(/900 read \| 850 staged/i)).toBeTruthy();
  });

  it('keeps the import dashboard behind the admin token state', () => {
    render(<AdminTab admin={admin()} />);

    expect(screen.getByText('3. Import dashboard')).toBeTruthy();
    expect(screen.getByText(/Set an admin token to view import runs, safety posture, and recent ingest health/i)).toBeTruthy();
  });

  it('shows approved operations inside the admin actions panel', () => {
    render(<AdminTab admin={admin()} />);

    expect(screen.getByText('8. Actions & operations')).toBeTruthy();
    expect(screen.getByText(/Telemetry hot-log snapshot/i)).toBeTruthy();
    expect(screen.getByText(/Data invariants/i)).toBeTruthy();
  });

  it('renders the latest admin operation output in the admin panel', () => {
    render(
      <AdminTab
        admin={admin({
          token: 'token',
          hasToken: true,
          lastOperationResult: {
            what: 'telemetryHotLogSnapshot',
            status: 'completed',
            exitCode: 0,
            jobRunId: 77,
            outputText: 'ED-Finder telemetry hot-log snapshot\njournal_import_staging:\n  total_rows: 26',
          },
        })}
      />,
    );

    expect(screen.getByTestId('admin-operation-output').textContent).toContain('job #77');
    expect(screen.getByTestId('admin-operation-output').textContent).toContain('ED-Finder telemetry hot-log snapshot');
    expect(screen.getByTestId('admin-operation-output').textContent).toContain('journal_import_staging');
  });

  it('renders persisted admin operation history with captured output', () => {
    const history: AdminOperationHistoryEntry[] = [
      {
        job_run_id: 91,
        job_key: 'telemetry_hot_log_snapshot',
        operation_key: 'telemetry_hot_log_snapshot',
        script_name: 'telemetry_hot_log_snapshot.py',
        status: 'completed',
        started_at: '2026-07-11T12:30:00Z',
        finished_at: '2026-07-11T12:30:04Z',
        exit_code: 0,
        error_text: null,
        output_text: 'ED-Finder telemetry hot-log snapshot\njournal_import_staging:\n  total_rows: 26',
      },
    ];

    render(
      <AdminTab
        admin={admin({
          token: 'token',
          hasToken: true,
          operationHistory: history,
        })}
      />,
    );

    expect(screen.getByTestId('admin-operation-history').textContent).toContain('Recent persisted operation history');
    expect(screen.getByTestId('admin-operation-history-91').textContent).toContain('telemetry_hot_log_snapshot');
    expect(screen.getByTestId('admin-operation-history-91').textContent).toContain('telemetry_hot_log_snapshot.py');
    expect(screen.getByTestId('admin-operation-history-91').textContent).toContain('journal_import_staging');
  });

  it('renders recent import status in the admin dashboard', () => {
    render(
      <AdminTab
        admin={admin({
          token: 'token',
          hasToken: true,
          importSafetyGates: {
            no_running_source_runs: true,
            latest_artifacts_present: true,
            bridge_fk_path_verified: true,
            diagnostic_rows_isolated: true,
            no_failed_unrecovered_source_runs: false,
            scheduler_assumed_disabled: true,
            canonical_apply_assumed_disabled: true,
            safe_to_proceed: false,
            blockers: ['A failed run needs review before proceeding.'],
            latest_source_run_key: 'run_frontier_002',
            notes: [],
          },
          importSourceRuns: [
            {
              source_run_key: 'run_frontier_002',
              source_name: 'frontier_journal',
              source_category: 'journal',
              domain: 'telemetry',
              import_scope: 'sync_key',
              status: 'failed',
              started_at: '2026-07-11T12:00:00Z',
              finished_at: '2026-07-11T12:05:00Z',
              duration_ms: 300000,
              rows_read: 120,
              rows_staged: 100,
              rows_rejected: 0,
              rows_skipped: 20,
              artifact_present: true,
              artifact_hash_present: true,
              bridge_present: false,
              staging_rows_known: true,
              trigger_context: 'manual',
              git_commit_sha: 'abc123',
              error_code: 'import_failed',
              error_summary: 'Importer stopped after a malformed batch.',
            },
            {
              source_run_key: 'run_spansh_001',
              source_name: 'spansh_import',
              source_category: 'import',
              domain: 'canonical',
              import_scope: 'bulk',
              status: 'succeeded',
              started_at: '2026-07-11T09:00:00Z',
              finished_at: '2026-07-11T09:10:00Z',
              duration_ms: 600000,
              rows_read: 900,
              rows_staged: 850,
              rows_rejected: 0,
              rows_skipped: 50,
              artifact_present: true,
              artifact_hash_present: true,
              bridge_present: true,
              staging_rows_known: true,
              trigger_context: 'scheduled',
              git_commit_sha: 'def456',
              error_code: null,
              error_summary: null,
            },
          ],
        })}
      />,
    );

    expect(screen.getByTestId('admin-import-dashboard').textContent).toContain('Recent runs');
    expect(screen.getByTestId('admin-import-dashboard').textContent).toContain('A failed run needs review before proceeding.');
    expect(screen.getByTestId('admin-import-run-run_frontier_002').textContent).toContain('frontier_journal');
    expect(screen.getByTestId('admin-import-run-run_frontier_002').textContent).toContain('Importer stopped after a malformed batch.');
    expect(screen.getByTestId('admin-import-run-run_spansh_001').textContent).toContain('spansh_import');
  });

  it('filters recent imports by source and hands off a selected run to operator', () => {
    const onOpenOperator = vi.fn();
    render(
      <AdminTab
        admin={admin({
          token: 'token',
          hasToken: true,
          importSafetyGates: {
            no_running_source_runs: true,
            latest_artifacts_present: true,
            bridge_fk_path_verified: true,
            diagnostic_rows_isolated: true,
            no_failed_unrecovered_source_runs: true,
            scheduler_assumed_disabled: true,
            canonical_apply_assumed_disabled: true,
            safe_to_proceed: true,
            blockers: [],
            latest_source_run_key: 'run_frontier_002',
            notes: [],
          },
          importSourceRuns: [
            {
              source_run_key: 'run_frontier_002',
              source_name: 'frontier_journal',
              source_category: 'journal',
              domain: 'telemetry',
              import_scope: 'sync_key',
              status: 'failed',
              started_at: '2026-07-11T12:00:00Z',
              finished_at: '2026-07-11T12:05:00Z',
              duration_ms: 300000,
              rows_read: 120,
              rows_staged: 100,
              rows_rejected: 0,
              rows_skipped: 20,
              artifact_present: true,
              artifact_hash_present: true,
              bridge_present: false,
              staging_rows_known: true,
              trigger_context: 'manual',
              git_commit_sha: 'abc123',
              error_code: 'import_failed',
              error_summary: 'Importer stopped after a malformed batch.',
            },
            {
              source_run_key: 'run_spansh_001',
              source_name: 'spansh_import',
              source_category: 'import',
              domain: 'canonical',
              import_scope: 'bulk',
              status: 'succeeded',
              started_at: '2026-07-11T09:00:00Z',
              finished_at: '2026-07-11T09:10:00Z',
              duration_ms: 600000,
              rows_read: 900,
              rows_staged: 850,
              rows_rejected: 0,
              rows_skipped: 50,
              artifact_present: true,
              artifact_hash_present: true,
              bridge_present: true,
              staging_rows_known: true,
              trigger_context: 'scheduled',
              git_commit_sha: 'def456',
              error_code: null,
              error_summary: null,
            },
          ],
        })}
        onOpenOperator={onOpenOperator}
      />,
    );

    const filter = screen.getByTestId('admin-import-source-filter');
    expect(filter).toBeTruthy();
    fireEvent.change(filter, { target: { value: 'spansh_import' } });

    expect(screen.queryByTestId('admin-import-run-run_frontier_002')).toBeNull();
    expect(screen.getByTestId('admin-import-run-run_spansh_001')).toBeTruthy();

    fireEvent.click(screen.getByTestId('admin-open-operator-run_spansh_001'));
    expect(onOpenOperator).toHaveBeenCalledWith('run_spansh_001');
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

    expect(screen.getByText('6. Warehouse status')).toBeTruthy();
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
