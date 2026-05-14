import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchOptimiserCandidates, getFacilityTemplates, getSimulationSummary, simulateBuild } from '@/lib/api';
import type { FacilityTemplate, OptimiserCandidatesResponse, SimulateBuildResponse, SimulationSummary, SystemDetail } from '@/types/api';
import { SimulationPreview } from './SimulationPreview';

vi.mock('@/lib/api', () => ({
  fetchOptimiserCandidates: vi.fn(),
  getFacilityTemplates: vi.fn(),
  getSimulationSummary: vi.fn(),
  simulateBuild: vi.fn(),
}));

const mockedFetchOptimiserCandidates = vi.mocked(fetchOptimiserCandidates);
const mockedGetFacilityTemplates = vi.mocked(getFacilityTemplates);
const mockedGetSimulationSummary = vi.mocked(getSimulationSummary);
const mockedSimulateBuild = vi.mocked(simulateBuild);

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
  {
    id: 'agri_support_a',
    name: 'Agriculture Support A',
    category: 'support',
    tier: 1,
    economy: 'Agriculture',
    is_port: false,
    is_support_facility: true,
    allowed_location: 'surface',
    pad_size: null,
    confidence: 'inferred',
    notes: null,
    yellow_cp_generated: 0,
    green_cp_generated: 0,
    yellow_cp_cost: 0,
    green_cp_cost: 0,
  },
];

const optimiserResponse: OptimiserCandidatesResponse = {
  system_id64: 123,
  target_archetype: 'agriculture_terraforming',
  candidate_count: 1,
  candidates: [
    {
      candidate_id: 'candidate-a',
      label: 'Balanced Agriculture candidate',
      target_archetype: 'agriculture_terraforming',
      strategy: 'balanced',
      placements: [
        { facility_template_id: 'generic_port_alpha', local_body_id: 'body1', is_primary_port: true, build_order: 1 },
        { facility_template_id: 'agri_support_a', local_body_id: 'body1', is_primary_port: false, build_order: 2 },
      ],
      rationale: ['Good agricultural fit.'],
      warnings: [],
      assumptions: [],
      tags: [],
      preview_summary: null,
    },
  ],
  warnings: [],
  assumptions: [],
  ranking: null,
};

const system = {
  id64: 123,
  name: 'Test System',
  economy_suggestion: 'Refinery',
  bodies: [
    { id: 'body1', name: 'Test Body', body_type: 'Planet', is_landable: true },
  ],
} as unknown as SystemDetail;

function renderPreview() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SimulationPreview system={system} />
    </QueryClientProvider>,
  );
}

function mockNoRecommendedBuild() {
  mockedGetFacilityTemplates.mockResolvedValue(templates);
  mockedGetSimulationSummary.mockResolvedValue({
    classification: { primary_archetype: 'refinery_industrial' },
    buildability: { recommended_build_order: [] },
    regional_context: null,
  } as unknown as SimulationSummary);
  mockedFetchOptimiserCandidates.mockResolvedValue(optimiserResponse);
}

function mockRecommendedBuild() {
  mockedGetFacilityTemplates.mockResolvedValue(templates);
  mockedGetSimulationSummary.mockResolvedValue({
    classification: { primary_archetype: 'refinery_industrial' },
    buildability: {
      recommended_build_order: [
        { facility_id: 'generic_port_alpha', location: 'surface' },
        { facility_id: 'agri_support_a', location: 'surface' },
      ],
    },
    regional_context: null,
  } as unknown as SimulationSummary);
  mockedFetchOptimiserCandidates.mockResolvedValue(optimiserResponse);
}

function simulationResult(targetArchetype = 'agriculture_terraforming'): SimulateBuildResponse {
  return {
    system_id64: 123,
    mechanics_version: 'colonisation-engine-v2.1',
    target_archetype: targetArchetype,
    final_score: 80,
    composition_score: 80,
    buildability_score: 80,
    build_complexity: 'moderate',
    confidence: 0.7,
    cp: {
      yellow_cp_final: 0,
      green_cp_final: 0,
      yellow_cp_generated: 0,
      green_cp_generated: 0,
      yellow_cp_spent: 0,
      green_cp_spent: 0,
      t2_ports: 0,
      t3_ports: 0,
      warnings: [],
    },
    cp_timeline: [],
    cp_repair_suggestions: [],
    observation_summary: {
      status: 'predicted_only',
      observed_facts_count: 0,
      confirmed_count: 0,
      mismatch_count: 0,
      observed_only_count: 0,
      predicted_only_count: 0,
      unknown_count: 0,
      confidence_impact: 'none',
      summary: 'No observed player data is attached to this simulation yet. Results are predicted from current mechanics rules.',
    },
    prediction_observation_diffs: [],
    economy_composition: {},
    economy_order: [],
    economy_stack: {},
    port_economy_states: [],
    influence_ledger: [],
    inherited_economies: [],
    topology: {},
    services: {},
    port_service_states: [],
    service_unlock_ledger: [],
    data_quality: {
      slots: 'estimated',
      facility_catalogue: 'community_observed',
      topology: 'inferred',
    },
    confidence_signals: [],
    mechanics_trace: {},
    top_two_alignment: 'none',
    contamination_risk: 'low',
    warnings: [],
    strengths: [],
    recommendations: [],
    mechanics_notes: [],
    links: { strong_links: [], weak_links: [] },
  };
}

describe('SimulationPreview optimiser candidate loading', () => {
  afterEach(() => {
    cleanup();
    mockedFetchOptimiserCandidates.mockReset();
    mockedGetFacilityTemplates.mockReset();
    mockedGetSimulationSummary.mockReset();
    mockedSimulateBuild.mockReset();
  });

  it('loads a selected optimiser candidate into the editable preview without auto-running simulation', async () => {
    mockNoRecommendedBuild();
    renderPreview();

    expect(await screen.findByText('Colony Planner')).toBeTruthy();
    expect(screen.getByText(/Plan a colony build for this system/)).toBeTruthy();
    expect(screen.getAllByText('Build Plan').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Optimiser Candidates').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Preview Result').length).toBeGreaterThan(0);
    expect(screen.getByText(/Target archetype guides candidate generation, ranking, and preview scoring/)).toBeTruthy();

    fireEvent.click(await screen.findByRole('button', { name: 'Generate candidates' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Load into preview' }));

    await waitFor(() => expect(screen.getByText(/Loaded optimiser candidate:/)).toBeTruthy());
    expect(screen.getAllByText(/Balanced Agriculture candidate/).length).toBeGreaterThan(0);
    expect(screen.getByText(/You can edit the build and run the normal preview/)).toBeTruthy();
    expect((screen.getByLabelText(/Target archetype/i) as HTMLSelectElement).value).toBe('agriculture_terraforming');
    expect(screen.getAllByText('generic_port_alpha').length).toBeGreaterThan(0);
    expect(screen.getAllByText('agri_support_a').length).toBeGreaterThan(0);
    expect(screen.getByText('Optimiser candidate')).toBeTruthy();
    expect(mockedSimulateBuild).not.toHaveBeenCalled();
  });

  it('marks an optimiser-origin plan as edited after manual add', async () => {
    mockNoRecommendedBuild();
    renderPreview();

    fireEvent.click(await screen.findByRole('button', { name: 'Generate candidates' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Load into preview' }));
    await screen.findByText(/Loaded optimiser candidate:/);

    fireEvent.click(screen.getByRole('button', { name: /Add Facility/i }));

    expect(screen.getByText(/Started from optimiser candidate:/)).toBeTruthy();
    expect(screen.getByText(/has been edited since loading/)).toBeTruthy();
  });

  it('blank advanced mode clears optimiser origin state', async () => {
    mockNoRecommendedBuild();
    renderPreview();

    fireEvent.click(await screen.findByRole('button', { name: 'Generate candidates' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Load into preview' }));
    await screen.findByText(/Loaded optimiser candidate:/);

    fireEvent.click(screen.getByRole('button', { name: /Start blank advanced simulation/i }));

    expect(screen.queryByText(/Loaded optimiser candidate:/)).toBeNull();
    expect(screen.queryByText(/Started from optimiser candidate:/)).toBeNull();
    expect(screen.getByText(/Blank advanced simulation/)).toBeTruthy();
  });

  it('recommended plan loading clears optimiser origin state', async () => {
    mockRecommendedBuild();
    renderPreview();

    fireEvent.click(await screen.findByRole('button', { name: 'Generate candidates' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Load into preview' }));
    fireEvent.click(await screen.findByRole('button', { name: /Replace preview plan/i }));
    await screen.findByText(/Loaded optimiser candidate:/);

    fireEvent.click(screen.getByRole('button', { name: /Use recommended build/i }));

    expect(screen.queryByText(/Loaded optimiser candidate:/)).toBeNull();
    expect(screen.queryByText(/Started from optimiser candidate:/)).toBeNull();
    expect(screen.getByText(/Recommended build loaded/)).toBeTruthy();
  });

  it('run preview remains explicit and sends resequenced current placements', async () => {
    mockNoRecommendedBuild();
    mockedSimulateBuild.mockReturnValue(new Promise(() => {}) as never);
    renderPreview();

    fireEvent.click(await screen.findByRole('button', { name: 'Generate candidates' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Load into preview' }));
    await screen.findByText(/Loaded optimiser candidate:/);
    fireEvent.click(screen.getAllByRole('button', { name: /Move down/i })[0]);
    expect(mockedSimulateBuild).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /Run Preview/i }));

    await waitFor(() => expect(mockedSimulateBuild).toHaveBeenCalledTimes(1));
    expect(mockedSimulateBuild).toHaveBeenCalledWith({
      system_id64: 123,
      target_archetype: 'agriculture_terraforming',
      placements: [
        { facility_template_id: 'agri_support_a', local_body_id: 'body1', is_primary_port: false, build_order: 1 },
        { facility_template_id: 'generic_port_alpha', local_body_id: 'body1', is_primary_port: true, build_order: 2 },
      ],
    });
  });

  it('marks an existing preview result stale after target archetype changes without auto-running', async () => {
    mockNoRecommendedBuild();
    mockedSimulateBuild.mockResolvedValue(simulationResult());
    renderPreview();

    fireEvent.click(await screen.findByRole('button', { name: 'Generate candidates' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Load into preview' }));
    await screen.findByText(/Loaded optimiser candidate:/);
    fireEvent.click(screen.getByRole('button', { name: /Run Preview/i }));
    await screen.findByText(/Final Score/i);
    expect(screen.queryByText(/The Build Plan has changed since this preview was run/)).toBeNull();

    fireEvent.change(screen.getByLabelText(/Target archetype/i), { target: { value: 'trade_logistics' } });

    expect(screen.getByText(/The Build Plan has changed since this preview was run/)).toBeTruthy();
    expect(mockedSimulateBuild).toHaveBeenCalledTimes(1);
  });

  it('marks an existing preview result stale after placement edits and refreshes after explicit run', async () => {
    mockNoRecommendedBuild();
    mockedSimulateBuild.mockResolvedValue(simulationResult());
    renderPreview();

    fireEvent.click(await screen.findByRole('button', { name: 'Generate candidates' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Load into preview' }));
    await screen.findByText(/Loaded optimiser candidate:/);
    fireEvent.click(screen.getByRole('button', { name: /Run Preview/i }));
    await screen.findByText(/Final Score/i);

    fireEvent.click(screen.getAllByRole('button', { name: /Move down/i })[0]);
    expect(screen.getByText(/The Build Plan has changed since this preview was run/)).toBeTruthy();
    expect(mockedSimulateBuild).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: /Run Preview/i }));
    await waitFor(() => expect(mockedSimulateBuild).toHaveBeenCalledTimes(2));
    expect(screen.queryByText(/The Build Plan has changed since this preview was run/)).toBeNull();
  });

  it('supports generate compare load edit and run preview with current edited placements', async () => {
    mockRecommendedBuild();
    mockedSimulateBuild.mockReturnValue(new Promise(() => {}) as never);
    renderPreview();

    fireEvent.click(await screen.findByRole('button', { name: 'Generate candidates' }));
    expect(mockedSimulateBuild).not.toHaveBeenCalled();
    expect(await screen.findByText(/Compare with current preview/i)).toBeTruthy();
    expect(screen.getByText(/advisory and preview-only/i)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Load into preview' }));
    fireEvent.click(await screen.findByRole('button', { name: /Replace preview plan/i }));
    await screen.findByText(/Loaded optimiser candidate:/);
    expect(mockedSimulateBuild).not.toHaveBeenCalled();

    fireEvent.click(screen.getAllByRole('button', { name: /Move down/i })[0]);
    expect(screen.getByText(/Started from optimiser candidate:/)).toBeTruthy();
    expect(screen.getByText(/edited since loading/)).toBeTruthy();
    expect(mockedSimulateBuild).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /Run Preview/i }));

    await waitFor(() => expect(mockedSimulateBuild).toHaveBeenCalledTimes(1));
    expect(mockedSimulateBuild).toHaveBeenCalledWith({
      system_id64: 123,
      target_archetype: 'agriculture_terraforming',
      placements: [
        { facility_template_id: 'agri_support_a', local_body_id: 'body1', is_primary_port: false, build_order: 1 },
        { facility_template_id: 'generic_port_alpha', local_body_id: 'body1', is_primary_port: true, build_order: 2 },
      ],
    });
  });
});
