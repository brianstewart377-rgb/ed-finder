import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  api,
  comparePredictionToObservations,
  createObservedFact,
  deleteObservedFact,
  fetchOptimiserCandidates,
  getFacilityTemplates,
  getSimulationSummary,
  getSlotPredictions,
  importSystemLayout,
  reviewPredictionValidation,
  simulateBuild,
  updateObservedFact,
} from '@/lib/api';
import type { FacilityTemplate, SimulationSummary, SystemDetail } from '@/types/api';
import { ColonyPlannerWorkspace } from './ColonyPlannerWorkspace';

vi.mock('@/lib/api', () => ({
  api: {
    system: vi.fn(),
  },
  fetchOptimiserCandidates: vi.fn(),
  getFacilityTemplates: vi.fn(),
  getSimulationSummary: vi.fn(),
  getSlotPredictions: vi.fn(),
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

const mockedApiSystem = vi.mocked(api.system);
const mockedGetFacilityTemplates = vi.mocked(getFacilityTemplates);
const mockedGetSimulationSummary = vi.mocked(getSimulationSummary);
const mockedGetSlotPredictions = vi.mocked(getSlotPredictions);
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
  bodies: [{ id: 1, name: 'Body 1', body_type: 'Planet', is_landable: true }],
} as unknown as SystemDetail;

function renderWorkspace() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ColonyPlannerWorkspace
        id64={123}
        onBackToFinder={vi.fn()}
        onOpenSystemDetail={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

describe('ColonyPlannerWorkspace real planner passivity', () => {
  afterEach(() => {
    mockedApiSystem.mockReset();
    mockedGetFacilityTemplates.mockReset();
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
    mockedApiSystem.mockResolvedValue(system);
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
          body_id: 1,
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

    renderWorkspace();

    expect((await screen.findAllByText('Passive Workspace')).length).toBeGreaterThan(0);
    expect(screen.getByTestId('whole-system-colony-planner')).toBeTruthy();
    expect(screen.getByTestId('whole-system-colony-planner').getAttribute('data-layout')).toBe('stage17n-docked-context-canvas');
    expect(screen.getByTestId('raven-real-planner-canvas')).toBeTruthy();
    expect(screen.getByTestId('planner-telemetry-region').getAttribute('data-layout')).toBe('telemetry-context-panel');
    expect(screen.getByRole('complementary', { name: /Workspace summary/i })).toBeTruthy();
    expect(screen.getByText('Whole-System Build Canvas')).toBeTruthy();
    expect(screen.getByText('Planner summary')).toBeTruthy();
    expect(await screen.findByText('Whole-System Planner')).toBeTruthy();
    expect(screen.getByTestId('raven-real-body-row-body1')).toBeTruthy();
    expect((await screen.findAllByText('Colony Planner Workspace')).length).toBeGreaterThan(0);
    expect(screen.queryByTestId('selected-body-planner-canvas')).toBeNull();
    expect(screen.queryByRole('button', { name: /Generate Suggested Build/i })).toBeNull();
    expect(screen.queryByTestId('suggested-builds-workspace-view')).toBeNull();
    expect(screen.queryByRole('button', { name: /Run Preview/i })).toBeNull();
    expect(screen.queryByTestId('advanced-planner-content')).toBeNull();

    await waitFor(() => expect(mockedGetSimulationSummary).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId('topology-body-button-body1'));
    expect(screen.getByTestId('raven-inline-body-expansion-body1')).toBeTruthy();
    expect(screen.getByText('Body slot planner')).toBeTruthy();
    expect(screen.getByText(/No orbit structures yet/i)).toBeTruthy();
    expect(screen.getAllByRole('button', { name: 'Add orbit structure' }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('button', { name: 'Add surface structure' }).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: 'Add flexible/unknown structure' })).toBeNull();

    expect(mockedApiSystem).toHaveBeenCalledWith(123);
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

  it('keeps main and inline slot lanes aligned and updates both after explicit structure adds', async () => {
    mockedApiSystem.mockResolvedValue(slotMapSystem);
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
          body_id: 1,
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

    renderWorkspace();

    await screen.findByTestId('raven-real-body-row-1');
    await waitFor(() => {
      expect(screen.getByTestId('1-orbital-slot-3')).toBeTruthy();
      expect(screen.getByTestId('1-ground-slot-4')).toBeTruthy();
    });

    fireEvent.click(screen.getByTestId('topology-body-button-1'));
    await screen.findByText(/Planning focus:/i);
    expect(screen.getByTestId('raven-inline-body-expansion-1')).toBeTruthy();
    await waitFor(() => {
      expect(screen.getByTestId('slot-lane-orbital')).toBeTruthy();
      expect(screen.getByTestId('slot-lane-surface')).toBeTruthy();
      expect(within(screen.getByTestId('slot-lane-orbital')).getByText('0/4 planned')).toBeTruthy();
      expect(within(screen.getByTestId('slot-lane-surface')).getByText('0/5 planned')).toBeTruthy();
      expect(screen.getByTestId('center-orbital-slot-3')).toBeTruthy();
      expect(screen.getByTestId('center-surface-slot-4')).toBeTruthy();
    });

    fireEvent.click(screen.getByTestId('center-orbital-slot-3'));
    fireEvent.click(await screen.findByTestId('body-structure-template-orbital_port'));
    await waitFor(() => {
      expect((screen.getByTestId('1-orbital-slot-0').textContent ?? '').trim().length).toBeGreaterThan(0);
      expect(within(screen.getByTestId('slot-lane-orbital')).getByText('1/4 planned')).toBeTruthy();
      expect(within(screen.getByTestId('slot-lane-items-orbital')).getByText(/Orbital Port/i)).toBeTruthy();
      expect((screen.getByTestId('center-orbital-slot-0').textContent ?? '').trim().length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByTestId('center-surface-slot-4'));
    fireEvent.click(await screen.findByTestId('body-structure-template-surface_hub'));
    await waitFor(() => {
      expect((screen.getByTestId('1-ground-slot-0').textContent ?? '').trim().length).toBeGreaterThan(0);
      expect(within(screen.getByTestId('slot-lane-surface')).getByText('1/5 planned')).toBeTruthy();
      expect(within(screen.getByTestId('slot-lane-items-surface')).getByText(/Surface Hub/i)).toBeTruthy();
      expect(within(screen.getByTestId('workspace-economy-ledger')).getByText(/Agri/i)).toBeTruthy();
      expect(within(screen.getByTestId('body-planning-economy')).getByText(/Agri/i)).toBeTruthy();
    });
  });
});
