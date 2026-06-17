import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getProvenanceCockpit, listObservedFacts } from '@/lib/api';
import { ExportReadinessWorkspaceView } from './ExportReadinessWorkspaceView';


vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    getProvenanceCockpit: vi.fn(),
    listObservedFacts: vi.fn(),
  };
});

const mockedGetProvenanceCockpit = vi.mocked(getProvenanceCockpit);
const mockedListObservedFacts = vi.mocked(listObservedFacts);

function renderView() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ExportReadinessWorkspaceView
        system={{ id64: 12866676218109, name: 'Shinrarta Dezhra' } as never}
        targetArchetype="refinery_industrial"
        placements={[
          { facility_template_id: 'orbital_port_small', local_body_id: '12', is_primary_port: true, build_order: 1 },
        ] as never}
        templates={[{ id: 'orbital_port_small', name: 'Orbital Port', is_port: true }] as never}
        bodies={[{ id: 12, name: 'Body A' }] as never}
        previewResult={{ final_score: 88, cp: null, cp_timeline: [], cp_repair_suggestions: [] } as never}
        previewResultStale={false}
        roleReview={{ consistencyLabel: 'Aligned' } as never}
      />
    </QueryClientProvider>,
  );
}

describe('ExportReadinessWorkspaceView', () => {
  beforeEach(() => {
    mockedGetProvenanceCockpit.mockReset();
    mockedListObservedFacts.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it('renders reviewable Markdown, JSON, and CSV export packs', async () => {
    mockedGetProvenanceCockpit.mockResolvedValue({
      provenance_summary: { latest_source_run_key: 'run-20260617' },
      warnings: ['Warehouse evidence is read-only review context.'],
      evidence_panels: {
        source_run: { artifact_name: 'stage20e_operator_pack.json' },
        warehouse: { state: 'available', report_only: true, stale_records: 0 },
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
    } as never);
    mockedListObservedFacts.mockResolvedValue({
      facts: [{ fact_type: 'service_presence' }, { fact_type: 'cp_value' }],
    } as never);

    renderView();

    expect(await screen.findByTestId('export-markdown')).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId('operator-review-references').textContent).toMatch(/run-20260617/));
    expect(screen.getByTestId('export-json')).toBeTruthy();
    expect(screen.getByTestId('export-csv')).toBeTruthy();
    expect(screen.getByText('Closeout readiness')).toBeTruthy();
    expect(screen.getByText('Operator review and audit')).toBeTruthy();
    expect(screen.getByTestId('operator-review-focus').textContent).toMatch(/no closeout blockers/i);
    expect(screen.getByTestId('operator-review-references').textContent).toMatch(/run-20260617/);
    expect(screen.getByTestId('operator-review-references').textContent).toMatch(/stage20e_operator_pack\.json/);
    expect(screen.getByTestId('operator-review-sections').textContent).toMatch(/planned/i);
    expect(screen.getByDisplayValue(/## Planned/)).toBeTruthy();
    expect(screen.getByDisplayValue(/## Operator review/)).toBeTruthy();
    expect(screen.getByDisplayValue(/"closeout_readiness"/)).toBeTruthy();
    expect(screen.getByDisplayValue(/"operator_review"/)).toBeTruthy();
    expect(screen.getByDisplayValue(/step,facility_template_id,facility_name,body_name,is_primary_port/)).toBeTruthy();
  });
});
