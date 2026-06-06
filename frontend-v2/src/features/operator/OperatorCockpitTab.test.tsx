import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/lib/api';
import type {
  OperatorDiagnosticRowSummary,
  OperatorSafetyGateSummary,
  OperatorSourceRunDetail,
  OperatorSourceRunSummary,
} from '@/types/api';
import { OperatorCockpitTab } from './OperatorCockpitTab';

vi.mock('@/lib/api', () => ({
  api: {
    operatorSafetyGates: vi.fn(),
    operatorSourceRuns: vi.fn(),
    operatorSourceRunDetail: vi.fn(),
    operatorDiagnosticRows: vi.fn(),
  },
}));

const apiMock = vi.mocked(api);

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
}: {
  gates?: OperatorSafetyGateSummary;
  runs?: OperatorSourceRunSummary[];
  diagnostics?: OperatorDiagnosticRowSummary[];
  selectedDetail?: OperatorSourceRunDetail;
} = {}) {
  sessionStorage.setItem('ed_admin_token', 'test-token');
  apiMock.operatorSafetyGates.mockResolvedValue(gates);
  apiMock.operatorSourceRuns.mockResolvedValue(runs);
  apiMock.operatorSourceRunDetail.mockResolvedValue(selectedDetail);
  apiMock.operatorDiagnosticRows.mockResolvedValue(diagnostics);
  return render(<OperatorCockpitTab />);
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
});
