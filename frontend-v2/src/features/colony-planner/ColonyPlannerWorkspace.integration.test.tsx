import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  api,
  comparePredictionToObservations,
  createObservedFact,
  deleteObservedFact,
  fetchOptimiserCandidates,
  getFacilityTemplates,
  getSimulationSummary,
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
    id: 'generic_port_alpha',
    name: 'Generic Port Alpha',
    category: 'port',
    tier: 1,
    economy: null,
    is_port: true,
    is_support_facility: false,
    allowed_location: 'surface_or_orbit',
    pad_size: 'large',
    confidence: 'inferred',
    notes: null,
    yellow_cp_generated: 0,
    green_cp_generated: 0,
    yellow_cp_cost: 0,
    green_cp_cost: 0,
  },
];

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

    expect(await screen.findByText('Passive Workspace')).toBeTruthy();
    expect(screen.getByTestId('planner-workspace-shell-v2')).toBeTruthy();
    expect(screen.getByRole('complementary', { name: /Topology sidebar/i })).toBeTruthy();
    expect(screen.getByRole('complementary', { name: /Workspace summary/i })).toBeTruthy();
    expect(screen.getByText('System topology')).toBeTruthy();
    expect(screen.getByText('Planner summary')).toBeTruthy();
    expect(screen.getByText('Planning Workspace')).toBeTruthy();
    expect(screen.getByText('Body tree placeholder')).toBeTruthy();
    expect((await screen.findAllByText('Colony Planner')).length).toBeGreaterThan(0);
    expect(screen.getByText('Contained planner')).toBeTruthy();
    expect(screen.getByRole('button', { name: /Generate Suggested Builds/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /Run Preview/i })).toBeTruthy();

    await waitFor(() => expect(mockedGetSimulationSummary).toHaveBeenCalled());
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
});
