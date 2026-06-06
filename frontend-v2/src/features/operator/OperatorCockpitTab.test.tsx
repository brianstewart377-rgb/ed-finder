import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/lib/api';
import type {
  OperatorDiagnosticRowSummary,
  OperatorSafetyGateSummary,
  OperatorSourceRunDetail,
  OperatorSourceRunSummary,
} from '@/types/api';
import { OperatorCockpitTab, type OperatorCockpitTabProps } from './OperatorCockpitTab';

vi.mock('@/lib/api', () => ({
  api: {
    operatorSafetyGates: vi.fn(),
    operatorSourceRuns: vi.fn(),
    operatorSourceRunDetail: vi.fn(),
    operatorDiagnosticRows: vi.fn(),
  },
}));

const apiMock = vi.mocked(api);

type TestAdmin = OperatorCockpitTabProps['admin'];

function admin(overrides: Partial<TestAdmin> = {}): TestAdmin {
  return {
    token: 'test-token',
    setToken: vi.fn(),
    forgetToken: vi.fn(),
    hasToken: true,
    ...overrides,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function safety(overrides: Partial<OperatorSafetyGateSummary> = {}): OperatorSafetyGateSummary {
  return {
    no_running_source_runs: true,
    latest_artifacts_present: true,
    bridge_fk_path_verified: true,
    diagnostic_rows_isolated: true,
    no_failed_unrecovered_source_runs: true,
    scheduler_assumed_disabled: true,
    canonical_apply_assumed_disabled: true,
    safe_to_proceed: true,
    blockers: [],
    latest_source_run_key: 'run-001',
    notes: ['Read-only visibility only.'],
    ...overrides,
  };
}

function sourceRun(overrides: Partial<OperatorSourceRunSummary> = {}): OperatorSourceRunSummary {
  return {
    source_run_key: 'run-001',
    source_name: 'edsm',
    source_category: 'nightly',
    domain: 'stations',
    import_scope: 'staging_only',
    status: 'completed',
    started_at: '2026-06-06T08:00:00Z',
    finished_at: '2026-06-06T08:01:00Z',
    duration_ms: 60_000,
    rows_read: 25,
    rows_staged: 25,
    rows_rejected: 0,
    rows_skipped: 0,
    artifact_present: true,
    artifact_hash_present: true,
    bridge_present: true,
    staging_rows_known: true,
    trigger_context: 'manual_rehearsal',
    git_commit_sha: '1234567890abcdef',
    error_code: null,
    error_summary: null,
    ...overrides,
  };
}

function diagnosticRow(overrides: Partial<OperatorDiagnosticRowSummary> = {}): OperatorDiagnosticRowSummary {
  return {
    row_id: 42,
    legacy_source_run_id: 7,
    station_name: 'Jameson Memorial',
    station_type: 'Coriolis Starport',
    system_name: 'Shinrarta Dezhra',
    source_class: 'diagnostic-only',
    confidence: 'high',
    marker_keys: ['stage19anr_diagnostic_mark'],
    canonical_write_allowed: false,
    ...overrides,
  };
}

function detail(overrides: Partial<OperatorSourceRunDetail> = {}): OperatorSourceRunDetail {
  const summary = sourceRun();
  return {
    summary,
    importer_name: 'operator-rehearsal',
    importer_version: '19ap',
    source_uri_redacted: '[redacted]/nightly/edsm-stations.json',
    source_input_sha256: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    source_manifest_sha256: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    safety_boundary: { read_only: true },
    metadata_summary: { keys: ['operator_notes'] },
    artifact_summary: {
      source_run_key: summary.source_run_key,
      artifact_path_redacted: '[redacted]/artifacts/edsm-stations.json',
      artifact_sha256: 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
      artifact_integrity_sha256: 'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',
      artifact_record_present: true,
      file_exists: true,
      file_sha256_matches: true,
      integrity_hash_matches: true,
      schema_version: 'source_run_artifact/v1',
      rows_read: 25,
      rows_staged: 25,
      status: 'present',
      validation_note: 'Artifact hash verified.',
    },
    bridge_summary: {
      bridge_key: 'source_runs:run-001',
      legacy_source_run_id: 7,
      source_run_key: summary.source_run_key,
      bridge_present: true,
      dry_run: true,
      adapter_name: 'source-run-compat',
      adapter_version: 'v1',
      target_staging_fk: 'enrichment_source_runs(id)',
      metadata_has_compatibility_bridge: true,
      staging_policy_blocks_source_runs_id: true,
    },
    staging_impact_summary: {
      source_run_key: summary.source_run_key,
      bridge_key: 'source_runs:run-001',
      legacy_source_run_id: 7,
      staging_table: 'staging_edsm_stations',
      rows_total: 25,
      rows_diagnostic_only: 25,
      rows_canonical_write_blocked: 25,
      rows_with_stage_markers: 25,
      rows_using_legacy_bridge_id: 25,
      rows_using_source_runs_id: 0,
      sample_rows: [diagnosticRow()],
      warnings: [],
    },
    validation_warnings: [],
    operator_notes: ['Pilot remains blocked until gates stay green.'],
    ...overrides,
  };
}

function arrange({
  gates = safety(),
  runs = [sourceRun()],
  diagnostics = [diagnosticRow()],
  selectedDetail = detail(),
  adminState = admin(),
}: {
  gates?: OperatorSafetyGateSummary;
  runs?: OperatorSourceRunSummary[];
  diagnostics?: OperatorDiagnosticRowSummary[];
  selectedDetail?: OperatorSourceRunDetail;
  adminState?: TestAdmin;
} = {}) {
  apiMock.operatorSafetyGates.mockResolvedValue(gates);
  apiMock.operatorSourceRuns.mockResolvedValue(runs);
  apiMock.operatorSourceRunDetail.mockResolvedValue(selectedDetail);
  apiMock.operatorDiagnosticRows.mockResolvedValue(diagnostics);
  return render(<OperatorCockpitTab admin={adminState} />);
}

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
});

afterEach(() => {
  cleanup();
});

describe('OperatorCockpitTab', () => {
  it('renders green safety gate state', async () => {
    arrange();

    expect(await screen.findByText('Safe to proceed')).toBeTruthy();
    expect(screen.getByText(/Scheduler\/timers remain assumed disabled/i)).toBeTruthy();
    expect(screen.getByText(/The 25-row pilot should not proceed if safety gates are red/i)).toBeTruthy();
  });

  it('renders red safety gate blockers', async () => {
    arrange({
      gates: safety({
        safe_to_proceed: false,
        latest_artifacts_present: false,
        blockers: ['latest artifacts missing', 'diagnostic rows are not isolated'],
      }),
    });

    expect(await screen.findByText('Not safe to proceed')).toBeTruthy();
    expect(screen.getByText('latest artifacts missing')).toBeTruthy();
    expect(screen.getByText('diagnostic rows are not isolated')).toBeTruthy();
  });

  it('renders recent source run rows', async () => {
    arrange();

    expect(await screen.findByRole('button', { name: 'run-001' })).toBeTruthy();
    expect(screen.getByText('edsm / nightly / stations / staging_only')).toBeTruthy();
    expect(screen.getByText(/25 read \/ 25 staged \/ 0 rejected \/ 0 skipped/i)).toBeTruthy();
    expect(screen.getByText('manual_rehearsal')).toBeTruthy();
    expect(screen.getByText('12345678')).toBeTruthy();
  });

  it('selects a source run and renders detail panels', async () => {
    arrange();

    fireEvent.click(await screen.findByRole('button', { name: 'run-001' }));

    await waitFor(() => {
      expect(apiMock.operatorSourceRunDetail).toHaveBeenCalledWith('test-token', 'run-001');
    });
    expect(await screen.findByText('Artifact summary')).toBeTruthy();
    expect(screen.getByText('Bridge summary')).toBeTruthy();
    expect(screen.getByText('Staging impact summary')).toBeTruthy();
    expect(screen.getByText('[redacted]/artifacts/edsm-stations.json')).toBeTruthy();
    expect(screen.getByText('Pilot remains blocked until gates stay green.')).toBeTruthy();
  });

  it('ignores stale detail and diagnostic responses from an earlier selected source run', async () => {
    const detailA = deferred<OperatorSourceRunDetail>();
    const diagnosticsA = deferred<OperatorDiagnosticRowSummary[]>();
    const detailB = deferred<OperatorSourceRunDetail>();
    const diagnosticsB = deferred<OperatorDiagnosticRowSummary[]>();
    arrange({
      runs: [
        sourceRun({ source_run_key: 'run-A' }),
        sourceRun({ source_run_key: 'run-B', git_commit_sha: 'bbbbbbbb90abcdef' }),
      ],
      diagnostics: [diagnosticRow({ row_id: 1, station_name: 'Latest station' })],
    });
    apiMock.operatorSourceRunDetail.mockImplementation((_token, sourceRunKey) => (
      sourceRunKey === 'run-A' ? detailA.promise : detailB.promise
    ));
    apiMock.operatorDiagnosticRows.mockImplementation((_token, options = {}) => {
      if (options.sourceRunKey === 'run-A') return diagnosticsA.promise;
      if (options.sourceRunKey === 'run-B') return diagnosticsB.promise;
      return Promise.resolve([diagnosticRow({ row_id: 1, station_name: 'Latest station' })]);
    });

    fireEvent.click(await screen.findByRole('button', { name: 'run-A' }));
    fireEvent.click(await screen.findByRole('button', { name: 'run-B' }));

    detailB.resolve(detail({
      source_uri_redacted: '[redacted]/run-B.json',
      operator_notes: ['B detail remains selected.'],
    }));
    diagnosticsB.resolve([
      diagnosticRow({
        row_id: 200,
        station_name: 'B Station',
        system_name: 'B System',
        station_type: 'B Type',
      }),
    ]);

    expect(await screen.findByText('[redacted]/run-B.json')).toBeTruthy();
    expect(screen.getByText('B detail remains selected.')).toBeTruthy();
    expect(screen.getByText('B Station / B System / B Type')).toBeTruthy();

    detailA.resolve(detail({
      source_uri_redacted: '[redacted]/run-A.json',
      operator_notes: ['A detail must not overwrite B.'],
    }));
    diagnosticsA.resolve([
      diagnosticRow({
        row_id: 100,
        station_name: 'A Station',
        system_name: 'A System',
        station_type: 'A Type',
      }),
    ]);

    await waitFor(() => {
      expect(screen.getByText('[redacted]/run-B.json')).toBeTruthy();
      expect(screen.queryByText('[redacted]/run-A.json')).toBeNull();
      expect(screen.queryByText('A Station / A System / A Type')).toBeNull();
    });
  });

  it('clears selected source-run state on full refresh before showing unscoped diagnostics', async () => {
    apiMock.operatorSafetyGates.mockResolvedValue(safety());
    apiMock.operatorSourceRuns.mockResolvedValue([sourceRun()]);
    apiMock.operatorSourceRunDetail.mockResolvedValue(detail());
    apiMock.operatorDiagnosticRows.mockImplementation((_token, options = {}) => {
      if (options.sourceRunKey) {
        return Promise.resolve([
          diagnosticRow({
            row_id: 301,
            station_name: 'Scoped Station',
            system_name: 'Scoped System',
            station_type: 'Scoped Type',
          }),
        ]);
      }
      return Promise.resolve([
        diagnosticRow({
          row_id: 401,
          station_name: 'Latest Refresh Station',
          system_name: 'Latest Refresh System',
          station_type: 'Latest Refresh Type',
        }),
      ]);
    });
    render(<OperatorCockpitTab admin={admin()} />);

    fireEvent.click(await screen.findByRole('button', { name: 'run-001' }));

    expect(await screen.findByText(/Diagnostic staging rows scoped to run-001\./)).toBeTruthy();
    expect(screen.getByText('Scoped Station / Scoped System / Scoped Type')).toBeTruthy();

    fireEvent.click(screen.getByTestId('operator-refresh'));

    expect(await screen.findByText(/Latest diagnostic staging rows\./)).toBeTruthy();
    expect(screen.getByText('Latest Refresh Station / Latest Refresh System / Latest Refresh Type')).toBeTruthy();
    expect(screen.getByText('Select a source run to load detail.')).toBeTruthy();
    expect(screen.queryByText(/Diagnostic staging rows scoped to run-001\./)).toBeNull();
    expect(screen.queryByText('Scoped Station / Scoped System / Scoped Type')).toBeNull();
  });

  it('renders diagnostic rows without raw payload text', async () => {
    const { container } = arrange();

    expect(await screen.findByText('Jameson Memorial / Shinrarta Dezhra / Coriolis Starport')).toBeTruthy();
    expect(screen.getByText('stage19anr_diagnostic_mark')).toBeTruthy();
    expect(container.textContent).not.toMatch(/raw_payload|payload_json|secret_source_payload/i);
  });

  it('keeps redacted paths and URIs redacted in detail', async () => {
    const { container } = arrange();

    fireEvent.click(await screen.findByRole('button', { name: 'run-001' }));

    expect(await screen.findByText('[redacted]/nightly/edsm-stations.json')).toBeTruthy();
    expect(screen.getByText('[redacted]/artifacts/edsm-stations.json')).toBeTruthy();
    expect(container.textContent).not.toMatch(/C:\\prod\\warehouse|s3:\/\/ed-prod-private/i);
  });

  it('does not expose import, scheduler, canonical write, or canonical apply action buttons', async () => {
    arrange();

    await screen.findByText('Safe to proceed');
    const buttonText = screen.getAllByRole('button')
      .map((button) => button.textContent ?? '')
      .join(' ');

    expect(buttonText).not.toMatch(/import/i);
    expect(buttonText).not.toMatch(/scheduler/i);
    expect(buttonText).not.toMatch(/canonical write/i);
    expect(buttonText).not.toMatch(/canonical apply/i);
  });

  it('uses the shared admin token handlers when saving and forgetting a token', async () => {
    const setToken = vi.fn();
    const forgetToken = vi.fn();
    render(
      <OperatorCockpitTab
        admin={admin({
          token: '',
          hasToken: false,
          setToken,
          forgetToken,
        })}
      />,
    );

    fireEvent.change(screen.getByTestId('operator-token-input'), {
      target: { value: 'new-admin-token' },
    });
    fireEvent.click(screen.getByTestId('operator-token-save'));

    expect(setToken).toHaveBeenCalledWith('new-admin-token');
    expect(sessionStorage.getItem('ed_admin_token')).toBeNull();

    cleanup();
    apiMock.operatorSafetyGates.mockResolvedValue(safety());
    apiMock.operatorSourceRuns.mockResolvedValue([]);
    apiMock.operatorDiagnosticRows.mockResolvedValue([]);
    render(<OperatorCockpitTab admin={admin({ forgetToken })} />);

    expect(await screen.findByText('No source runs found.')).toBeTruthy();
    fireEvent.click(screen.getByTestId('operator-token-forget'));

    expect(forgetToken).toHaveBeenCalled();
  });
});
