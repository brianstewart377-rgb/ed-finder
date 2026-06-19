import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getProvenanceCockpit, getWarehousePlannerEvidence, listObservedFacts } from '@/lib/api';
import type { ProvenanceCockpitResponse, WarehousePlannerEvidenceContract } from '@/types/api';
import { ProvenanceCockpitPanel } from './ProvenanceCockpitPanel';


vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    getProvenanceCockpit: vi.fn(),
    getWarehousePlannerEvidence: vi.fn(),
    listObservedFacts: vi.fn(),
  };
});


const mockedGetProvenanceCockpit = vi.mocked(getProvenanceCockpit);
const mockedGetWarehousePlannerEvidence = vi.mocked(getWarehousePlannerEvidence);
const mockedListObservedFacts = vi.mocked(listObservedFacts);

function provenanceResponse(overrides: Partial<ProvenanceCockpitResponse> = {}): ProvenanceCockpitResponse {
  return {
    schema_version: 'stage20a_provenance_cockpit/v1',
    system: {
      id64: 12866676218109,
      name: 'Shinrarta Dezhra',
      primary_archetype: 'refinery_industrial',
    },
    provenance_summary: {
      state: 'available',
      latest_source_run_key: 'stage19av-expanded-source-run-staging-pilot-48688d9d46067867',
      warehouse_state: 'available',
      planner_evidence_state: 'available',
    },
    evidence_panels: {
      source_run: {
        state: 'available',
        source_name: 'edsm',
        rows_read: 250,
        rows_staged: 250,
        artifact_name: 'stage19av_edsm_import_20260615T062102Z.json',
      },
      warehouse: {
        state: 'available',
        report_only: true,
        canonical_writes_planned: 0,
        stale_records: 0,
      },
      planner: {
        state: 'available',
        observed_facts_count: 3,
        projected_build_count: 1,
        manual_review_required: true,
      },
    },
    guardrails: {
      stage19_paused: true,
      stage19_production_activation_complete: false,
      next_stage19_write_lane_authorized: false,
      canonical_apply_complete: false,
      rebaseline_complete: false,
      scheduler_enabled: false,
      db_writes_authorized: false,
      stage19_operator_commands_authorized: false,
    },
    warnings: [],
    ui_hints: {
      severity: 'info',
      empty_state_key: null,
    },
    ...overrides,
  };
}

function warehouseEvidenceResponse(overrides: Partial<WarehousePlannerEvidenceContract> = {}): WarehousePlannerEvidenceContract {
  return {
    schema_version: 'warehouse_planner_evidence/v1',
    system_id64: 12866676218109,
    generated_at: '2026-06-19T00:00:00Z',
    freshness: {
      status: 'fresh',
      evaluated_at: '2026-06-19T00:00:00Z',
    },
    source_run: {
      source_name: 'edsm',
      run_key: 'stage24c-contract-run',
    },
    evidence_envelope: {
      status: 'available',
      source_classes: ['canonical', 'observed_facts', 'bounded_staging', 'derived_report'],
      semantics: ['canonical_truth', 'observed_report', 'bounded_staging_evidence', 'report_only_review_context', 'not_full_coverage'],
      report_only: true,
      selected_system_only: true,
      planner_truth_source_class: 'canonical',
      claims_canonical_truth: false,
      claims_full_coverage: false,
      summary: 'Selected-system evidence is available in this read-only planner envelope. Source classes: canonical evidence, observed facts, bounded staging evidence, and derived report evidence.',
    },
    bounded_staging: {
      status: 'available',
      report_only: true,
      bounded_staging_only: true,
      source_name: 'edsm',
      source_batch_label: 'stage19bb-1000',
      source_sha256: 'redacted',
      source_run_key: 'stage19bb-1000-run',
      bridge_key: 'bridge-1',
      row_limit: 1000,
      available_row_limits: [100, 1000, 10000],
      matched_row_count: 1,
      latest_source_updated_at: '2026-06-18T00:00:00Z',
      summary: 'Bounded staging evidence is available for this selected system as read-only review context.',
    },
    evidence_summary: {
      availability: 'report_only',
      report_only: true,
      manual_review_required: true,
      items: [
        {
          label: 'report_only',
          source: 'canonical',
          summary: 'Canonical evidence remains separate from bounded staging review context.',
        },
        {
          label: 'needs_review',
          source: 'observed',
          summary: 'Observed facts remain separate from canonical evidence.',
        },
      ],
    },
    warnings: ['Warehouse evidence is read-only review context.'],
    ...overrides,
  };
}

function renderPanel(systemId64 = 12866676218109) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProvenanceCockpitPanel systemId64={systemId64} />
    </QueryClientProvider>,
  );
}

describe('ProvenanceCockpitPanel — Stage 20B read-only evidence and status surfaces', () => {
  beforeEach(() => {
    mockedGetProvenanceCockpit.mockReset();
    mockedGetWarehousePlannerEvidence.mockReset();
    mockedListObservedFacts.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it('renders the read-only provenance summary for the current system', async () => {
    mockedGetProvenanceCockpit.mockResolvedValue(provenanceResponse());
    mockedGetWarehousePlannerEvidence.mockResolvedValue(warehouseEvidenceResponse());
    mockedListObservedFacts.mockResolvedValue({
      facts: [],
      total: 3,
      limit: 1,
      offset: 0,
      summary: {
        total_count: 3,
        by_fact_type: {},
        by_status: {},
        by_confidence: {},
      },
    } as never);
    renderPanel();

    expect(await screen.findByRole('region', { name: 'Provenance cockpit' })).toBeTruthy();
    expect(screen.getByText(/Source-run, warehouse, and planner evidence are surfaced here for review only/)).toBeTruthy();
    expect(await screen.findByText('Shinrarta Dezhra')).toBeTruthy();
    expect(screen.getByText('stage19av-expanded-source-run-staging-pilot-48688d9d46067867')).toBeTruthy();
    expect(screen.getByText('stage19av_edsm_import_20260615T062102Z.json')).toBeTruthy();
    expect(screen.getAllByText('Observed facts').length).toBeGreaterThan(0);
    expect(screen.getByText('Observed fact source')).toBeTruthy();
    expect(screen.getByText('Live observations API')).toBeTruthy();
    expect(screen.getByText('Projected builds')).toBeTruthy();
    expect(screen.getByTestId('provenance-evidence-consistency-surface')).toBeTruthy();
    expect(screen.getByTestId('provenance-evidence-consistency-summary').textContent).toContain(
      'Available. Selected-system evidence is present as read-only review context only.',
    );
    expect(screen.getByTestId('provenance-evidence-consistency-highlights').textContent).toContain('Dedicated contract preferred');
    expect(screen.getByTestId('provenance-evidence-consistency-highlights').textContent).toContain('Stage 19BB bounded staging evidence');
    expect(screen.getByTestId('planner-warehouse-evidence')).toBeTruthy();
    const guardrails = screen.getByLabelText('Authority safety status');
    expect(within(guardrails).getByText('Stage 19 paused')).toBeTruthy();
    expect(within(guardrails).getByText('DB writes authorized')).toBeTruthy();
    await waitFor(() => expect(mockedGetProvenanceCockpit).toHaveBeenCalledWith(12866676218109));
    await waitFor(() => expect(mockedGetWarehousePlannerEvidence).toHaveBeenCalledWith(12866676218109));
  });

  it('renders stale warnings distinctly without implying authorization', async () => {
    mockedGetProvenanceCockpit.mockResolvedValue(
      provenanceResponse({
        provenance_summary: {
          state: 'stale',
          latest_source_run_key: 'stage19av-expanded-source-run-staging-pilot-48688d9d46067867',
          warehouse_state: 'stale',
          planner_evidence_state: 'available',
        },
        evidence_panels: {
          source_run: {
            state: 'available',
            source_name: 'edsm',
            rows_read: 250,
            rows_staged: 250,
            artifact_name: 'stage19av_edsm_import_20260615T062102Z.json',
          },
          warehouse: {
            state: 'stale',
            report_only: true,
            canonical_writes_planned: 0,
            stale_records: 14,
          },
          planner: {
            state: 'available',
            observed_facts_count: 1,
            projected_build_count: 0,
            manual_review_required: true,
          },
        },
        warnings: ['Warehouse freshness is stale; treat the reconciliation summary as review-only evidence.'],
        ui_hints: {
          severity: 'warning',
          empty_state_key: null,
        },
      }),
    );
    mockedGetWarehousePlannerEvidence.mockResolvedValue(warehouseEvidenceResponse());
    mockedListObservedFacts.mockResolvedValue({
      facts: [],
      total: 1,
      limit: 1,
      offset: 0,
      summary: {
        total_count: 1,
        by_fact_type: {},
        by_status: {},
        by_confidence: {},
      },
    } as never);
    renderPanel(9466842275401);

    const warnings = await screen.findByLabelText('Provenance warnings');
    expect(within(warnings).getByText(/Warehouse freshness is stale/)).toBeTruthy();
    expect(screen.queryByText(/DB writes remain unauthorized in this checkpoint/)).toBeNull();
  });

  it('shows loading then the unknown state without collapsing it to success', async () => {
    let resolveResponse: (value: ProvenanceCockpitResponse) => void = () => {};
    mockedGetProvenanceCockpit.mockReturnValue(
      new Promise<ProvenanceCockpitResponse>((resolve) => {
        resolveResponse = resolve;
      }),
    );
    mockedGetWarehousePlannerEvidence.mockResolvedValue(
      warehouseEvidenceResponse({
        evidence_envelope: {
          status: 'unknown',
          source_classes: ['unavailable'],
          semantics: ['report_only_review_context', 'not_full_coverage'],
          report_only: true,
          selected_system_only: true,
          planner_truth_source_class: 'canonical',
          claims_canonical_truth: false,
          claims_full_coverage: false,
          summary: 'Selected-system evidence remains unknown in this runtime. Source classes: no linked selected-system evidence.',
        },
        bounded_staging: {
          status: 'not_evaluated',
          report_only: true,
          bounded_staging_only: true,
          available_row_limits: [],
        },
        evidence_summary: {
          availability: 'unavailable',
          report_only: true,
          manual_review_required: true,
          items: [],
        },
      }),
    );
    mockedListObservedFacts.mockResolvedValue({
      facts: [],
      total: 2,
      limit: 1,
      offset: 0,
      summary: {
        total_count: 2,
        by_fact_type: {},
        by_status: {},
        by_confidence: {},
      },
    } as never);
    renderPanel(2293822313194);

    expect(await screen.findByText(/Loading provenance cockpit/)).toBeTruthy();
    resolveResponse(
      provenanceResponse({
        system: {
          id64: 2293822313194,
          name: null,
          primary_archetype: 'unknown',
        },
        provenance_summary: {
          state: 'unknown',
          latest_source_run_key: null,
          warehouse_state: 'unknown',
          planner_evidence_state: 'unknown',
        },
        evidence_panels: {
          source_run: {
            state: 'unknown',
            source_name: null,
            rows_read: null,
            rows_staged: null,
            artifact_name: null,
          },
          warehouse: {
            state: 'unknown',
            report_only: true,
            canonical_writes_planned: 0,
            stale_records: null,
          },
          planner: {
            state: 'unknown',
            observed_facts_count: 0,
            projected_build_count: 0,
            manual_review_required: true,
          },
        },
        warnings: ['No provenance artifact is configured for this system yet; unknown values remain unknown.'],
        ui_hints: {
          severity: 'neutral',
          empty_state_key: 'provenance.unknown',
        },
      }),
    );

    expect((await screen.findAllByText(/No provenance artifact is configured/)).length).toBeGreaterThan(0);
    expect(screen.getAllByText('unknown').length).toBeGreaterThan(0);
    expect(screen.getByText('ID64 2293822313194')).toBeTruthy();
    expect(screen.getByText('2')).toBeTruthy();
    expect(screen.getByTestId('provenance-evidence-consistency-summary').textContent).toContain(
      'Unknown. Selected-system evidence has not been established.',
    );
  });

  it('prefers the governed endpoint unavailable response over provenance fallback', async () => {
    mockedGetProvenanceCockpit.mockResolvedValue(provenanceResponse());
    mockedGetWarehousePlannerEvidence.mockResolvedValue(
      warehouseEvidenceResponse({
        evidence_envelope: {
          status: 'unavailable',
          source_classes: ['unavailable'],
          semantics: ['report_only_review_context', 'not_full_coverage'],
          report_only: true,
          selected_system_only: true,
          planner_truth_source_class: 'canonical',
          claims_canonical_truth: false,
          claims_full_coverage: false,
          summary: 'No approved bounded staging evidence is linked to this selected system.',
        },
        bounded_staging: {
          status: 'unavailable',
          report_only: true,
          bounded_staging_only: true,
          available_row_limits: [100, 1000, 10000],
          summary: 'No approved bounded staging evidence is linked to this selected system.',
        },
        evidence_summary: {
          availability: 'unavailable',
          report_only: true,
          manual_review_required: true,
          items: [],
        },
      }),
    );
    mockedListObservedFacts.mockResolvedValue({
      facts: [],
      total: 3,
      limit: 1,
      offset: 0,
      summary: {
        total_count: 3,
        by_fact_type: {},
        by_status: {},
        by_confidence: {},
      },
    } as never);

    renderPanel();

    expect(await screen.findByTestId('planner-warehouse-evidence')).toBeTruthy();
    expect(screen.getByTestId('provenance-evidence-consistency-summary').textContent).toContain(
      'Unavailable. No approved bounded staging evidence is linked to this selected system.',
    );
    expect(screen.getByTestId('warehouse-evidence-envelope-status-unavailable')).toBeTruthy();
    expect(screen.getByTestId('provenance-evidence-consistency-highlights').textContent).toContain('Dedicated contract preferred');
  });

  it('preserves the governed not-evaluated response as distinct from unavailable and unknown', async () => {
    mockedGetProvenanceCockpit.mockResolvedValue(provenanceResponse());
    mockedGetWarehousePlannerEvidence.mockResolvedValue(
      warehouseEvidenceResponse({
        evidence_envelope: {
          status: 'not_evaluated',
          source_classes: ['bounded_staging', 'derived_report'],
          semantics: ['bounded_staging_evidence', 'report_only_review_context', 'not_full_coverage'],
          report_only: true,
          selected_system_only: true,
          planner_truth_source_class: 'canonical',
          claims_canonical_truth: false,
          claims_full_coverage: false,
          summary: 'The staging boundary was not safely queryable for this selected system in this runtime.',
        },
        bounded_staging: {
          status: 'not_evaluated',
          report_only: true,
          bounded_staging_only: true,
          available_row_limits: [100, 1000, 10000],
          summary: 'The staging boundary was not safely queryable for this selected system in this runtime.',
        },
        evidence_summary: {
          availability: 'report_only',
          report_only: true,
          manual_review_required: true,
          items: [],
        },
      }),
    );
    mockedListObservedFacts.mockResolvedValue({
      facts: [],
      total: 3,
      limit: 1,
      offset: 0,
      summary: {
        total_count: 3,
        by_fact_type: {},
        by_status: {},
        by_confidence: {},
      },
    } as never);

    renderPanel();

    expect(await screen.findByTestId('planner-warehouse-evidence')).toBeTruthy();
    expect(screen.getByTestId('provenance-evidence-consistency-summary').textContent).toContain(
      'Not evaluated in this runtime. The staging boundary was not safely queryable for this request.',
    );
    expect(screen.getByTestId('warehouse-evidence-envelope-status-not_evaluated')).toBeTruthy();
  });

  it('uses provenance fallback only when the governed endpoint cannot be read', async () => {
    mockedGetProvenanceCockpit.mockResolvedValue(provenanceResponse());
    mockedGetWarehousePlannerEvidence.mockRejectedValue(new Error('warehouse endpoint unavailable'));
    mockedListObservedFacts.mockResolvedValue({
      facts: [],
      total: 3,
      limit: 1,
      offset: 0,
      summary: {
        total_count: 3,
        by_fact_type: {},
        by_status: {},
        by_confidence: {},
      },
    } as never);

    renderPanel();

    expect(await screen.findByTestId('planner-warehouse-evidence')).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByTestId('provenance-evidence-consistency-highlights').textContent).toContain('Provenance fallback'),
    );
    await waitFor(() =>
      expect(screen.getByTestId('warehouse-evidence-source-posture-provenance_bridge')).toBeTruthy(),
    );
  });
});
