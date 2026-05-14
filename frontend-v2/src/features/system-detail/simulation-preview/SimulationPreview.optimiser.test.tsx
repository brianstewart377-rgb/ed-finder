import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchOptimiserCandidates, getFacilityTemplates, getSimulationSummary, simulateBuild } from '@/lib/api';
import type { FacilityTemplate, OptimiserCandidatesResponse, SimulationSummary, SystemDetail } from '@/types/api';
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

describe('SimulationPreview optimiser candidate loading', () => {
  afterEach(() => {
    cleanup();
    mockedFetchOptimiserCandidates.mockReset();
    mockedGetFacilityTemplates.mockReset();
    mockedGetSimulationSummary.mockReset();
    mockedSimulateBuild.mockReset();
  });

  it('loads a selected optimiser candidate into the editable preview without auto-running simulation', async () => {
    mockedGetFacilityTemplates.mockResolvedValue(templates);
    mockedGetSimulationSummary.mockResolvedValue({
      classification: { primary_archetype: 'refinery_industrial' },
      buildability: { recommended_build_order: [] },
      regional_context: null,
    } as unknown as SimulationSummary);
    mockedFetchOptimiserCandidates.mockResolvedValue(optimiserResponse);

    renderPreview();

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
});
