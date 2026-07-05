import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  comparePredictionToObservations,
  createObservedFact,
  deleteObservedFact,
  fetchOptimiserCandidates,
  getFacilityTemplates,
  getProvenanceCockpit,
  getSimulationSummary,
  getSlotPredictions,
  getWarehousePlannerEvidence,
  importSystemLayout,
  reviewPredictionValidation,
  simulateBuild,
  updateObservedFact,
} from '@/lib/api';
import type { FacilityTemplate, SimulationSummary, SystemDetail } from '@/types/api';
import { ColonyPlannerWorkspace } from './ColonyPlannerWorkspace';
import { useColonyProjectStore } from './colonyProjectStore';

vi.mock('@/lib/api', () => ({
  fetchOptimiserCandidates: vi.fn(),
  getFacilityTemplates: vi.fn(),
  getProvenanceCockpit: vi.fn(),
  getSimulationSummary: vi.fn(),
  getSlotPredictions: vi.fn(),
  getWarehousePlannerEvidence: vi.fn(),
  importSystemLayout: vi.fn(),
  simulateBuild: vi.fn(),
  listObservedFacts: vi.fn().mockResolvedValue({
    facts: [],
    total: 0,
    limit: 100,
    offset: 0,
    summary: {
      total_count: 0,
      by_fact_type: {},
      by_status: {},
      by_confidence: {},
      latest_observed_at: null,
    },
  }),
  createObservedFact: vi.fn(),
  updateObservedFact: vi.fn(),
  deleteObservedFact: vi.fn(),
  comparePredictionToObservations: vi.fn(),
  reviewPredictionValidation: vi.fn(),
}));

const mockedGetFacilityTemplates = vi.mocked(getFacilityTemplates);
const mockedGetProvenanceCockpit = vi.mocked(getProvenanceCockpit);
const mockedGetSimulationSummary = vi.mocked(getSimulationSummary);
const mockedGetSlotPredictions = vi.mocked(getSlotPredictions);
const mockedGetWarehousePlannerEvidence = vi.mocked(getWarehousePlannerEvidence);
const mockedImportSystemLayout = vi.mocked(importSystemLayout);
const mockedFetchOptimiserCandidates = vi.mocked(fetchOptimiserCandidates);
const mockedSimulateBuild = vi.mocked(simulateBuild);
const mockedCreateObservedFact = vi.mocked(createObservedFact);
const mockedUpdateObservedFact = vi.mocked(updateObservedFact);
const mockedDeleteObservedFact = vi.mocked(deleteObservedFact);
const mockedCompare = vi.mocked(comparePredictionToObservations);
const mockedReview = vi.mocked(reviewPredictionValidation);

const system = {
  id64: 123,
  name: 'Passive Workspace',
  x: 1,
  y: 2,
  z: 3,
  population: 0,
  is_colonised: false,
  primary_economy: 'Agriculture',
  economy_suggestion: 'Refinery',
  bodies: [{ id: 'body1', name: 'Body 1', body_type: 'Planet', is_landable: true }],
  stations: [],
} as unknown as SystemDetail;

const templates: FacilityTemplate[] = [
  {
    id: 'orbital_port',
    name: 'Orbital Port',
    category: 'port',
    tier: 1,
    economy: null,
    is_port: true,
    is_support_facility: false,
    allowed_location: 'orbital',
    pad_size: 'large',
    confidence: 'inferred',
    notes: null,
    yellow_cp_generated: 0,
    green_cp_generated: 0,
    yellow_cp_cost: 0,
    green_cp_cost: 0,
  },
  {
    id: 'surface_hub',
    name: 'Surface Hub',
    category: 'support',
    tier: 1,
    economy: 'Agriculture',
    is_port: false,
    is_support_facility: true,
    allowed_location: 'surface',
    pad_size: 'medium',
    confidence: 'inferred',
    notes: null,
    yellow_cp_generated: 0,
    green_cp_generated: 0,
    yellow_cp_cost: 0,
    green_cp_cost: 0,
  },
];

const slotMapSystem = {
  ...system,
  bodies: [{ id: 'body1', name: 'Body 1', body_type: 'Planet', is_landable: true }],
} as unknown as SystemDetail;

const activeProject = {
  id: 'project-1',
  system_id64: 123,
  system_name: 'Passive Workspace',
  project_name: 'Active draft',
  build_plan_placements: [],
  target_archetype: 'refinery_industrial',
  notes: '',
  status: 'draft',
  created_at: '2026-07-04T00:00:00Z',
  updated_at: '2026-07-04T00:00:00Z',
  archived_at: null,
};

async function renderWorkspace(options?: {
  id64?: number | null;
  projectId?: string | null;
  invalidSystemRoute?: boolean;
  invalidProjectRoute?: boolean;
  system?: SystemDetail | null;
  systemLoading?: boolean;
  systemError?: string | null;
  onCreateDraft?: (system: SystemDetail) => void;
}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => {
    await useColonyProjectStore.persist.rehydrate();
  });
  useColonyProjectStore.setState((state) => ({
    ...state,
    projects: options?.projectId === null
      ? state.projects
      : {
        ...state.projects,
        [activeProject.id]: activeProject as any,
      },
  }));
  const view = render(
    <QueryClientProvider client={client}>
      <ColonyPlannerWorkspace
        id64={options?.id64 ?? 123}
        projectId={options?.projectId === undefined ? activeProject.id : options.projectId}
        invalidSystemRoute={options?.invalidSystemRoute ?? false}
        invalidProjectRoute={options?.invalidProjectRoute ?? false}
        system={options?.system ?? system}
        systemLoading={options?.systemLoading ?? false}
        systemError={options?.systemError ?? null}
        onRetrySystem={vi.fn()}
        onCreateDraft={options?.onCreateDraft ?? vi.fn()}
        onBackToFinder={vi.fn()}
        onOpenSystemDetail={vi.fn()}
      />
    </QueryClientProvider>,
  );
  await act(async () => {
    await new Promise((resolve) => window.setTimeout(resolve, 0));
  });
  return view;
}

async function click(element: HTMLElement) {
  await act(async () => {
    fireEvent.click(element);
    await new Promise((resolve) => window.setTimeout(resolve, 0));
  });
}

function provenanceResponse() {
  return {
    schema_version: 'stage20a_provenance_cockpit/v1',
    system: { id64: 123, name: 'Passive Workspace', primary_archetype: 'refinery_industrial' },
    provenance_summary: {
      state: 'available',
      latest_source_run_key: 'warehouse/run-123',
      warehouse_state: 'available',
      planner_evidence_state: 'available',
    },
    evidence_panels: {
      source_run: {
        state: 'available',
        source_name: 'eddn',
        rows_read: 12,
        rows_staged: 12,
        artifact_name: 'run-123.json',
      },
      warehouse: {
        state: 'available',
        report_only: true,
        canonical_writes_planned: 0,
        stale_records: 0,
      },
      planner: {
        state: 'available',
        observed_facts_count: 0,
        projected_build_count: 0,
        manual_review_required: false,
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
  } as const;
}

function warehousePlannerEvidenceResponse() {
  return {
    schema_version: 'warehouse_planner_evidence/v1',
    system_id64: 123,
    generated_at: '2026-06-17T14:00:00Z',
    freshness: {
      status: 'fresh',
      evaluated_at: '2026-06-17T14:00:00Z',
    },
    source_run: {
      source_name: 'warehouse_reconciliation',
      run_key: 'warehouse/run-20260617.json',
    },
    evidence_summary: {
      availability: 'report_only',
      report_only: true,
      manual_review_required: false,
      items: [
        {
          label: 'report_only',
          source: 'warehouse_report_only',
          summary: 'Warehouse reconciliation evidence is available for this system as report-only context.',
        },
      ],
    },
    warnings: [],
  } as const;
}

describe('ColonyPlannerWorkspace real planner passivity', () => {
  beforeEach(() => {
    mockedGetWarehousePlannerEvidence.mockResolvedValue(warehousePlannerEvidenceResponse() as never);
    mockedGetProvenanceCockpit.mockResolvedValue(provenanceResponse() as never);
  });

  afterEach(() => {
    cleanup();
    mockedGetFacilityTemplates.mockReset();
    mockedGetWarehousePlannerEvidence.mockReset();
    mockedGetProvenanceCockpit.mockReset();
    mockedGetSimulationSummary.mockReset();
    mockedGetSlotPredictions.mockReset();
    mockedImportSystemLayout.mockReset();
    mockedFetchOptimiserCandidates.mockReset();
    mockedSimulateBuild.mockReset();
    mockedCreateObservedFact.mockReset();
    mockedUpdateObservedFact.mockReset();
    mockedDeleteObservedFact.mockReset();
    mockedCompare.mockReset();
    mockedReview.mockReset();
  });

  it('loads system context and passive planner data without running Preview or Suggested Builds', async () => {
    mockedGetFacilityTemplates.mockResolvedValue(templates);
    mockedGetWarehousePlannerEvidence.mockResolvedValue(warehousePlannerEvidenceResponse() as never);
    mockedGetProvenanceCockpit.mockResolvedValue(provenanceResponse() as never);
    mockedGetSimulationSummary.mockResolvedValue({
      classification: { primary_archetype: 'refinery_industrial' },
      buildability: { recommended_build_order: [] },
      regional_context: null,
    } as unknown as SimulationSummary);
    mockedGetSlotPredictions.mockResolvedValue({
      system_id64: 123,
      data_source: 'eddn',
      body_count: 1,
      predicted_orbital_slots_total: 4,
      predicted_ground_slots_total: 5,
      prediction_status: 'predicted',
      prediction_version: 'validated-slot-v1',
      confidence_label: 'validated_high_accuracy',
      disclaimer: 'Predicted slots — high-accuracy algorithm, not guaranteed. Verify in Architect Mode.',
      validation_note: 'Validated against the supplied evidence set with only 2 true mismatches after data-entry corrections.',
      required_input_missing: [],
      predictions: [
        {
          system_address: 123,
          body_id: 'body1',
          body_name: 'Body 1',
          predicted_orbital_slots: 4,
          predicted_ground_slots: 5,
          prediction_status: 'predicted',
          reasons: [],
        },
      ],
    } as any);
    mockedImportSystemLayout.mockResolvedValue({
      system_id64: 123,
      source: 'spansh',
      status: 'success',
      fetched_at: '2026-05-16T00:00:00Z',
      summary: {
        bodies_found: 0,
        stations_found: 0,
        bodies_upserted: 0,
        stations_upserted: 0,
        warnings_count: 0,
      },
      warnings: [],
      errors: [],
    });

    await renderWorkspace({ system: slotMapSystem });

    expect((await screen.findAllByText('Passive Workspace')).length).toBeGreaterThan(0);
    expect(screen.getByTestId('planner-warehouse-evidence')).toBeTruthy();
    expect(screen.getByText(/Warehouse reconciliation evidence is available/i)).toBeTruthy();
    expect(mockedGetWarehousePlannerEvidence).toHaveBeenCalledWith(123);
    expect(mockedGetProvenanceCockpit).not.toHaveBeenCalled();
    expect(screen.getByTestId('whole-system-colony-planner')).toBeTruthy();
    expect(screen.getByTestId('whole-system-colony-planner').getAttribute('data-layout')).toBe('stage17n-docked-context-canvas');
    expect(screen.getByTestId('raven-real-planner-canvas')).toBeTruthy();
    expect(screen.getByTestId('planner-telemetry-region').getAttribute('data-layout')).toBe('plan-details-panel');
    expect(screen.queryByTestId('raven-real-telemetry-panel')).toBeNull();
    expect(screen.getByRole('complementary', { name: /Workspace summary/i })).toBeTruthy();
    expect(screen.getByText('System Build Map')).toBeTruthy();
    expect(screen.queryByText('Whole-System Build Canvas')).toBeNull();
    expect(screen.getByText('Planner summary')).toBeTruthy();
    expect(await screen.findByText('Whole-System Planner')).toBeTruthy();
    expect(screen.getByTestId('raven-real-body-row-body1')).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Colony Planner' })).toBeTruthy();
    expect(screen.queryByTestId('selected-body-planner-canvas')).toBeNull();
    expect(screen.queryByRole('button', { name: /Generate Suggested Build/i })).toBeNull();
    expect(screen.queryByTestId('suggested-builds-workspace-view')).toBeNull();
    expect(screen.queryByRole('button', { name: /Run Preview/i })).toBeNull();
    expect(screen.queryByTestId('advanced-planner-content')).toBeNull();

    await waitFor(() => expect(mockedGetSimulationSummary).toHaveBeenCalled());
    await click(screen.getByTestId('topology-body-button-body1'));
    expect(screen.getByTestId('raven-real-body-row-body1').getAttribute('data-selected')).toBe('true');
    expect(screen.queryByTestId('raven-inline-body-expansion-body1')).toBeNull();
    expect(screen.queryByText('Body slot planner')).toBeNull();
    expect(screen.getByTestId('body1-orbital-add')).toBeTruthy();
    expect(screen.getByTestId('body1-ground-add')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Add flexible/unknown structure' })).toBeNull();

    expect(mockedGetFacilityTemplates).toHaveBeenCalled();

    expect(mockedSimulateBuild).not.toHaveBeenCalled();
    expect(mockedFetchOptimiserCandidates).not.toHaveBeenCalled();
    expect(mockedImportSystemLayout).not.toHaveBeenCalled();
    expect(mockedCreateObservedFact).not.toHaveBeenCalled();
    expect(mockedUpdateObservedFact).not.toHaveBeenCalled();
    expect(mockedDeleteObservedFact).not.toHaveBeenCalled();
    expect(mockedCompare).not.toHaveBeenCalled();
    expect(mockedReview).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: /Copy to Build Plan/i })).toBeNull();
  });

  it('keeps main row slot lanes aligned and updates them after explicit structure adds', async () => {
    mockedGetFacilityTemplates.mockResolvedValue(templates);
    mockedGetSimulationSummary.mockResolvedValue({
      classification: { primary_archetype: 'refinery_industrial' },
      buildability: { recommended_build_order: [] },
      regional_context: null,
    } as unknown as SimulationSummary);
    mockedGetSlotPredictions.mockResolvedValue({
      system_id64: 123,
      data_source: 'eddn',
      body_count: 1,
      predicted_orbital_slots_total: 4,
      predicted_ground_slots_total: 5,
      prediction_status: 'predicted',
      prediction_version: 'validated-slot-v1',
      confidence_label: 'validated_high_accuracy',
      disclaimer: 'Predicted slots — high-accuracy algorithm, not guaranteed. Verify in Architect Mode.',
      validation_note: 'Validated against the supplied evidence set with only 2 true mismatches after data-entry corrections.',
      required_input_missing: [],
      predictions: [
        {
          system_address: 123,
          body_id: 'body1',
          body_name: 'Body 1',
          predicted_orbital_slots: 4,
          predicted_ground_slots: 5,
          prediction_status: 'predicted',
          reasons: [],
        },
      ],
    } as any);
    mockedImportSystemLayout.mockResolvedValue({
      system_id64: 123,
      source: 'spansh',
      status: 'success',
      fetched_at: '2026-05-16T00:00:00Z',
      summary: {
        bodies_found: 0,
        stations_found: 0,
        bodies_upserted: 0,
        stations_upserted: 0,
        warnings_count: 0,
      },
      warnings: [],
      errors: [],
    });

    await renderWorkspace({ system: slotMapSystem });

    await screen.findByTestId('raven-real-body-row-body1');
    await click(screen.getByTestId('topology-body-button-body1'));
    await waitFor(() => {
      expect(screen.getByTestId('body1-orbital-slot-3')).toBeTruthy();
      expect(screen.getByTestId('body1-ground-slot-4')).toBeTruthy();
    });

    await screen.findByText(/Planning focus:/i);
    expect(screen.queryByTestId('raven-inline-body-expansion-body1')).toBeNull();
    expect(screen.queryByTestId('selected-body-planner-canvas')).toBeNull();
    await waitFor(() => {
      expect(screen.getByTestId('body1-orbital-add')).toBeTruthy();
      expect(screen.getByTestId('body1-ground-add')).toBeTruthy();
    });

    await click(screen.getByTestId('body1-orbital-add'));
    await click(await screen.findByTestId('body-structure-template-orbital_port'));
    await waitFor(() => {
      expect((screen.getByTestId('body1-orbital-slot-0').textContent ?? '').trim().length).toBeGreaterThan(0);
      expect(screen.getByTestId('body1-orbital-slot-0').textContent).toMatch(/Orbital|Port/i);
    });

    await click(screen.getByTestId('body1-ground-add'));
    await click(await screen.findByTestId('body-structure-template-surface_hub'));
    await waitFor(() => {
      expect((screen.getByTestId('body1-ground-slot-0').textContent ?? '').trim().length).toBeGreaterThan(0);
      expect(within(screen.getByTestId('workspace-economy-ledger')).getByText(/Agri/i)).toBeTruthy();
    });
  });

  it('adds structures directly from Raven canvas slots without Preview, generation, or Advanced Planner dependency', async () => {
    mockedGetFacilityTemplates.mockResolvedValue(templates);
    mockedGetSimulationSummary.mockResolvedValue({
      classification: { primary_archetype: 'refinery_industrial' },
      buildability: { recommended_build_order: [] },
      regional_context: null,
    } as unknown as SimulationSummary);
    mockedGetSlotPredictions.mockResolvedValue({
      system_id64: 123,
      data_source: 'eddn',
      body_count: 1,
      predicted_orbital_slots_total: 4,
      predicted_ground_slots_total: 5,
      prediction_status: 'predicted',
      prediction_version: 'validated-slot-v1',
      confidence_label: 'validated_high_accuracy',
      disclaimer: 'Predicted slots — high-accuracy algorithm, not guaranteed. Verify in Architect Mode.',
      validation_note: 'Validated against the supplied evidence set with only 2 true mismatches after data-entry corrections.',
      required_input_missing: [],
      predictions: [
        {
          system_address: 123,
          body_id: 'body1',
          body_name: 'Body 1',
          predicted_orbital_slots: 4,
          predicted_ground_slots: 5,
          prediction_status: 'predicted',
          reasons: [],
        },
      ],
    } as any);

    await renderWorkspace({ system: slotMapSystem });

    await screen.findByTestId('raven-real-body-row-body1');
    await click(screen.getByTestId('topology-body-button-body1'));
    await waitFor(() => {
      expect(screen.getByTestId('body1-orbital-slot-3')).toBeTruthy();
      expect(screen.getByTestId('body1-ground-slot-4')).toBeTruthy();
    });

    await click(screen.getByTestId('body1-orbital-add'));
    const orbitalPicker = await screen.findByTestId('body-structure-picker');
    expect(orbitalPicker).toBeTruthy();
    expect(within(orbitalPicker).getByRole('heading', { name: 'Add to Body 1' })).toBeTruthy();
    expect(within(orbitalPicker).getAllByText(/Orbit lane/i).length).toBeGreaterThan(0);
    expect(within(orbitalPicker).getByTestId('canvas-picker-compatible-count').textContent).toContain('1 compatible option');
    expect(screen.getByTestId('body-structure-template-orbital_port')).toBeTruthy();
    expect(screen.queryByTestId('body-structure-template-surface_hub')).toBeNull();
    await click(screen.getByRole('button', { name: /Close structure picker/i }));

    await click(screen.getByTestId('body1-ground-add'));
    const surfaceAddPicker = await screen.findByTestId('body-structure-picker');
    expect(surfaceAddPicker).toBeTruthy();
    expect(within(surfaceAddPicker).getAllByText(/Surface lane/i).length).toBeGreaterThan(0);
    expect(screen.getByTestId('body-structure-template-surface_hub')).toBeTruthy();
    await click(screen.getByRole('button', { name: /Close structure picker/i }));

    await click(screen.getByTestId('body1-orbital-add'));
    expect(within(await screen.findByTestId('body-structure-picker')).getAllByText(/Orbit lane/i).length).toBeGreaterThan(0);
    await click(screen.getByTestId('body-structure-template-orbital_port'));
    await waitFor(() => {
      expect(screen.getByTestId('canvas-add-structure-feedback').textContent).toContain('Added Orbital Port to Body 1 / Orbit.');
      expect((screen.getByTestId('body1-orbital-slot-0').textContent ?? '')).toMatch(/Orbital|Port/i);
      expect(screen.queryByTestId('raven-inline-body-expansion-body1')).toBeNull();
      expect(screen.getByTestId('planner-status-strip').textContent).toMatch(/Planned\s*1/);
      expect(within(screen.getByTestId('planner-status-strip')).getByText('Unsaved changes')).toBeTruthy();
    });

    await click(screen.getByTestId('body1-ground-add'));
    expect(within(await screen.findByTestId('body-structure-picker')).getAllByText(/Surface lane/i).length).toBeGreaterThan(0);
    await click(screen.getByTestId('body-structure-template-surface_hub'));
    await waitFor(() => {
      expect((screen.getByTestId('body1-ground-slot-0').textContent ?? '')).toMatch(/Surface|Hub/i);
      expect(screen.getByTestId('canvas-add-structure-feedback').textContent).toContain('Body 1 / Surface');
      expect(screen.getByTestId('planner-status-strip').textContent).toMatch(/Planned\s*2/);
    });

    expect(screen.queryByTestId('advanced-planner-content')).toBeNull();
    expect(mockedSimulateBuild).not.toHaveBeenCalled();
    expect(mockedFetchOptimiserCandidates).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: /Copy to Build Plan/i })).toBeNull();

    await click(screen.getByTestId('advanced-workspace-toggle'));
    const advanced = await screen.findByTestId('advanced-planner-content');
    expect(within(advanced).getByText('2 placements in Build Plan')).toBeTruthy();
    expect(within(advanced).getAllByText(/Orbital Port/i).length).toBeGreaterThan(0);
    expect(within(advanced).getAllByText(/Surface Hub/i).length).toBeGreaterThan(0);
    expect(mockedSimulateBuild).not.toHaveBeenCalled();
    expect(mockedFetchOptimiserCandidates).not.toHaveBeenCalled();
  });

  it('shows the direct planner no-draft state and creates a draft only on explicit action', async () => {
    const onCreateDraft = vi.fn();

    await renderWorkspace({ projectId: null, onCreateDraft });

    expect(screen.getByText('No active draft for this system')).toBeTruthy();
    expect(screen.queryByTestId('whole-system-colony-planner')).toBeNull();

    await click(screen.getByRole('button', { name: 'Create draft' }));
    expect(onCreateDraft).toHaveBeenCalledWith(system);
  });

  it('rejects missing, archived, malformed, and cross-system project routes without falling back', async () => {
    useColonyProjectStore.setState({
      projects: {
        archived: {
          id: 'archived',
          system_id64: 123,
          system_name: 'Passive Workspace',
          project_name: 'Archived draft',
          build_plan_placements: [],
          target_archetype: 'refinery_industrial',
          notes: '',
          status: 'draft',
          created_at: '2026-07-04T00:00:00Z',
          updated_at: '2026-07-04T00:00:00Z',
          archived_at: '2026-07-04T00:10:00Z',
        },
        foreign: {
          id: 'foreign',
          system_id64: 999,
          system_name: 'Other system',
          project_name: 'Foreign draft',
          build_plan_placements: [],
          target_archetype: 'refinery_industrial',
          notes: '',
          status: 'draft',
          created_at: '2026-07-04T00:00:00Z',
          updated_at: '2026-07-04T00:00:00Z',
          archived_at: null,
        },
        fallback: {
          id: 'fallback',
          system_id64: 123,
          system_name: 'Passive Workspace',
          project_name: 'Fallback draft',
          build_plan_placements: [],
          target_archetype: 'refinery_industrial',
          notes: '',
          status: 'draft',
          created_at: '2026-07-04T00:00:00Z',
          updated_at: '2026-07-04T00:00:00Z',
          archived_at: null,
        },
      } as any,
    });

    const missingView = await renderWorkspace({ projectId: 'missing' });
    expect(screen.getByText('Selected project unavailable')).toBeTruthy();
    expect(screen.queryByTestId('whole-system-colony-planner')).toBeNull();
    missingView.unmount();

    const archivedView = await renderWorkspace({ projectId: 'archived' });
    expect(screen.getByText('Selected project is archived')).toBeTruthy();
    expect(screen.queryByTestId('whole-system-colony-planner')).toBeNull();
    archivedView.unmount();

    const foreignView = await renderWorkspace({ projectId: 'foreign' });
    expect(screen.getByText('Selected project does not belong to this system')).toBeTruthy();
    expect(screen.queryByTestId('whole-system-colony-planner')).toBeNull();
    foreignView.unmount();

    await renderWorkspace({ projectId: '', invalidProjectRoute: true });
    expect(screen.getByText('Selected project route invalid')).toBeTruthy();
    expect(screen.queryByTestId('whole-system-colony-planner')).toBeNull();
  });
});
