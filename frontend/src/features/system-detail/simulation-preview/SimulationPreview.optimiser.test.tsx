import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  comparePredictionToObservations,
  createObservedFact,
  deleteObservedFact,
  fetchOptimiserCandidates,
  getFacilityTemplates,
  getSimulationSummary,
  getSlotPredictions,
  importSystemLayout,
  listObservedFacts,
  reviewPredictionValidation,
  simulateBuild,
  updateObservedFact,
} from '@/lib/api';
import type { FacilityTemplate, LayoutImportResponse, OptimiserCandidatesResponse, PredictionObservationCompareResponse, SimulateBuildRequest, SimulateBuildResponse, SimulationSummary, SystemDetail, ValidationReviewResponse } from '@/types/api';
import { SimulationPreview } from './SimulationPreview';

vi.mock('@/lib/api', () => ({
  fetchOptimiserCandidates: vi.fn(),
  getFacilityTemplates: vi.fn(),
  getSimulationSummary: vi.fn(),
  getSlotPredictions: vi.fn(),
  importSystemLayout: vi.fn(),
  simulateBuild: vi.fn(),
  // Stage 6B observation helpers — the optimiser test does not exercise
  // observation flows, but it does render the panel as part of the
  // composed SimulationPreview, so list/create/update/delete must be
  // mock-resolvable to keep the test deterministic.
  listObservedFacts: vi.fn(),
  createObservedFact: vi.fn(),
  updateObservedFact: vi.fn(),
  deleteObservedFact: vi.fn(),
  // Stage 6D validation compare helper — SimulationPreview now renders
  // the ValidationPanel which calls this once a preview result exists.
  comparePredictionToObservations: vi.fn(),
  reviewPredictionValidation: vi.fn(),
}));

const mockedFetchOptimiserCandidates = vi.mocked(fetchOptimiserCandidates);
const mockedGetFacilityTemplates = vi.mocked(getFacilityTemplates);
const mockedGetSimulationSummary = vi.mocked(getSimulationSummary);
const mockedGetSlotPredictions = vi.mocked(getSlotPredictions);
const mockedImportSystemLayout = vi.mocked(importSystemLayout);
const mockedSimulateBuild = vi.mocked(simulateBuild);
const mockedListObservedFacts = vi.mocked(listObservedFacts);
const mockedCreateObservedFact = vi.mocked(createObservedFact);
const mockedUpdateObservedFact = vi.mocked(updateObservedFact);
const mockedDeleteObservedFact = vi.mocked(deleteObservedFact);
const mockedCompare = vi.mocked(comparePredictionToObservations);
const mockedReview = vi.mocked(reviewPredictionValidation);

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
      tags: ['scale_starter'],
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

const slotPredictionResponse = {
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
      body_name: 'Test Body',
      predicted_orbital_slots: 4,
      predicted_ground_slots: 5,
      prediction_status: 'predicted',
      reasons: [],
    },
  ],
};

const layoutImportSuccess: LayoutImportResponse = {
  system_id64: 123,
  source: 'spansh',
  status: 'success',
  fetched_at: '2026-05-16T00:00:00Z',
  summary: {
    bodies_found: 4,
    stations_found: 2,
    bodies_upserted: 4,
    stations_upserted: 2,
    warnings_count: 0,
  },
  warnings: [],
  errors: [],
};

function renderPreview(options: { system?: SystemDetail; initialRequest?: SimulateBuildRequest; declaredRoles?: Parameters<typeof SimulationPreview>[0]['declaredRoles'] } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SimulationPreview
        system={options.system ?? system}
        initialRequest={options.initialRequest}
        declaredRoles={options.declaredRoles}
      />
    </QueryClientProvider>,
  );
}

async function openSuggestedBuildsMode() {
  fireEvent.click(await screen.findByRole('button', { name: /^Suggested Builds/i }));
  await screen.findByTestId('suggested-builds-workspace-view');
}

async function openEvidenceMode() {
  fireEvent.click(await screen.findByRole('button', { name: /^Evidence/i }));
  await screen.findByTestId('evidence-workspace-view');
}

async function openValidationMode() {
  fireEvent.click(await screen.findByRole('button', { name: /^Validation/i }));
  await screen.findByTestId('validation-workspace-view');
}

async function openPreviewMode() {
  fireEvent.click(await screen.findByRole('button', { name: /^Preview/i }));
  await screen.findByTestId('preview-workspace-view');
}

function emptyObservedFactsResponse() {
  return {
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
  };
}

function emptyReviewResponse(): ValidationReviewResponse {
  return {
    system_id64: 123,
    target_archetype: 'agriculture_terraforming',
    generated_at: '2026-05-15T12:00:00+00:00',
    summary: {
      overall_review_status: 'insufficient_evidence',
      confidence_impact: 'insufficient_evidence',
      highest_severity: 'info',
      review_needed_count: 0,
      evidence_strength: 'none',
      primary_review_areas: ['evidence_quality'],
      summary: 'No observed evidence has been recorded yet. Record evidence before reviewing prediction quality.',
    },
    signals: [],
    warnings: [],
    assumptions: [],
  };
}

function emptyCompareResponse(): PredictionObservationCompareResponse {
  return {
    system_id64: 123,
    target_archetype: 'agriculture_terraforming',
    generated_at: '2026-05-15T12:00:00+00:00',
    summary: {
      status: 'no_observations',
      observed_facts_count: 0,
      compared_predictions_count: 0,
      confirmed_count: 0,
      contradicted_count: 0,
      observed_only_count: 0,
      predicted_only_count: 0,
      unknown_count: 0,
      unverified_count: 0,
      confidence_impact: 'none',
      summary: 'No observations yet.',
    },
    comparisons: [],
    warnings: [],
    assumptions: [],
  };
}

function mockNoRecommendedBuild() {
  mockedGetFacilityTemplates.mockResolvedValue(templates);
  mockedGetSimulationSummary.mockResolvedValue({
    classification: { primary_archetype: 'refinery_industrial' },
    buildability: { recommended_build_order: [] },
    regional_context: null,
  } as unknown as SimulationSummary);
  mockedFetchOptimiserCandidates.mockResolvedValue(optimiserResponse);
  mockedGetSlotPredictions.mockResolvedValue(slotPredictionResponse as any);
  mockedImportSystemLayout.mockResolvedValue(layoutImportSuccess);
  mockedListObservedFacts.mockResolvedValue(emptyObservedFactsResponse());
  mockedCompare.mockResolvedValue(emptyCompareResponse());
  mockedReview.mockResolvedValue(emptyReviewResponse());
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
  mockedGetSlotPredictions.mockResolvedValue(slotPredictionResponse as any);
  mockedImportSystemLayout.mockResolvedValue(layoutImportSuccess);
  mockedListObservedFacts.mockResolvedValue(emptyObservedFactsResponse());
  mockedCompare.mockResolvedValue(emptyCompareResponse());
  mockedReview.mockResolvedValue(emptyReviewResponse());
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
    mockedGetSlotPredictions.mockReset();
    mockedImportSystemLayout.mockReset();
    mockedSimulateBuild.mockReset();
    mockedListObservedFacts.mockReset();
    mockedCreateObservedFact.mockReset();
    mockedUpdateObservedFact.mockReset();
    mockedDeleteObservedFact.mockReset();
    mockedCompare.mockReset();
    mockedReview.mockReset();
  });

  it('renders Evidence and Validation modes without mounting the panels by default', async () => {
    mockNoRecommendedBuild();
    renderPreview();

    const labels = await screen.findAllByText('Observed Evidence');
    expect(labels.length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: /^Evidence/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /^Validation/i })).toBeTruthy();
    expect(screen.queryByRole('region', { name: 'Observed Evidence' })).toBeNull();
    expect(screen.queryByRole('region', { name: 'Validation' })).toBeNull();

    await openEvidenceMode();
    expect(screen.getByRole('region', { name: 'Observed Evidence' })).toBeTruthy();
    expect(
      screen.getByText(/Later step: Observed Evidence records what you see in-game after planning/),
    ).toBeTruthy();
    expect(screen.queryByTestId('build-plan-workspace-view')).toBeNull();
    expect(screen.queryByTestId('suggested-builds-workspace-view')).toBeNull();
    expect(screen.queryByTestId('preview-workspace-view')).toBeNull();
  });

  it('shows observed-role review context in Evidence mode without changing declared roles', async () => {
    mockNoRecommendedBuild();
    mockedListObservedFacts.mockResolvedValue({
      ...emptyObservedFactsResponse(),
      total: 1,
      summary: {
        total_count: 1,
        by_fact_type: { economy_presence: 1 },
        by_status: { observed_present: 1 },
        by_confidence: { high: 1 },
        latest_observed_at: '2026-05-19T00:00:00.000Z',
      },
      facts: [{
        observation_id: 'obs-tourism',
        system_id64: 123,
        created_at: '2026-05-19T00:00:00.000Z',
        updated_at: null,
        source: 'manual',
        fact_type: 'economy_presence',
        subject_type: 'body',
        subject_id: 'body1',
        local_body_id: 'body1',
        status: 'observed_present',
        economy: 'Tourism',
        confidence: 'high',
        tags: [],
        metadata: {},
      }],
    });
    renderPreview({
      declaredRoles: [{
        id: 'declared:body1:industrial_core',
        body_id: 'body1',
        role_id: 'industrial_core',
        source: 'declared',
        label: 'Industrial Core',
      }],
    });

    await openEvidenceMode();

    expect(await screen.findByText('Evidence Role Review')).toBeTruthy();
    expect(screen.getAllByText('Strategy diverging').length).toBeGreaterThan(0);
    expect(screen.getByText('Declared Industrial Core but observed Observed Tourism Focus.')).toBeTruthy();
    const evidenceRoleReview = await screen.findByTestId('strategic-role-review-card');
    expect(evidenceRoleReview.textContent).toMatch(/Declared strategy/i);
    expect(evidenceRoleReview.textContent).toMatch(/Industrial/i);
    expect(evidenceRoleReview.textContent).toMatch(/Tourism Focus/i);
    expect(screen.getByText(/Review-only: role review never changes declared strategy/)).toBeTruthy();
    expect(mockedSimulateBuild).not.toHaveBeenCalled();
    expect(mockedFetchOptimiserCandidates).not.toHaveBeenCalled();
  });

  it('shows strategic role review context in Validation mode without optimiser side effects', async () => {
    mockNoRecommendedBuild();
    renderPreview({
      declaredRoles: [{
        id: 'declared:body1:main_station_body',
        body_id: 'body1',
        role_id: 'main_station_body',
        source: 'declared',
        label: 'Main Station Body',
      }],
    });

    await openValidationMode();

    expect(await screen.findByText('Validation Role Review')).toBeTruthy();
    expect(screen.getAllByText('Insufficient observed evidence').length).toBeGreaterThan(0);
    expect(screen.getByText('No observed evidence recorded yet.')).toBeTruthy();
    const validationRoleReview = await screen.findByTestId('strategic-role-review-card');
    expect(validationRoleReview.textContent).toMatch(/Declared strategy/i);
    expect(validationRoleReview.textContent).toMatch(/Main Station/i);
    expect(mockedFetchOptimiserCandidates).not.toHaveBeenCalled();
    expect(mockedSimulateBuild).not.toHaveBeenCalled();
  });

  it('does not call simulateBuild or optimiser candidate generation when the evidence drawer opens', async () => {
    mockNoRecommendedBuild();
    renderPreview();

    await openEvidenceMode();
    await screen.findByRole('region', { name: 'Observed Evidence' });
    await waitFor(() => expect(mockedListObservedFacts).toHaveBeenCalled());

    // No simulation or optimiser side effects from observed evidence flows.
    expect(mockedSimulateBuild).not.toHaveBeenCalled();
    expect(mockedFetchOptimiserCandidates).not.toHaveBeenCalled();
  });

  it('copies a selected suggested build into the editable Build Plan without auto-running simulation', async () => {
    mockNoRecommendedBuild();
    renderPreview();

    expect(await screen.findByText('Colony Planner')).toBeTruthy();
    expect(screen.getByText(/Plan a colony build for this system/)).toBeTruthy();
    expect(screen.getAllByText('Build Plan').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Suggested Builds').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Preview Result').length).toBeGreaterThan(0);
    expect(screen.getByText(/Target for Suggested Builds and Preview/)).toBeTruthy();
    expect(screen.queryByTestId('suggested-builds-workspace-view')).toBeNull();
    expect(screen.getByRole('button', { name: /Show Suggested Builds/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /Start blank/i })).toBeTruthy();
    expect(screen.getByText(/Advanced manual control/)).toBeTruthy();
    expect(screen.getByText(/0 placements in Build Plan/)).toBeTruthy();
    expect(screen.getAllByText(/Preview not run yet/).length).toBeGreaterThan(0);

    await openSuggestedBuildsMode();
    fireEvent.click(await screen.findByRole('button', { name: 'Generate Suggested Builds' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Load into Planner Workspace' }));

    await waitFor(() => expect(screen.getByText(/Copied suggested build:/)).toBeTruthy());
    expect(screen.queryByTestId('suggested-builds-workspace-view')).toBeNull();
    expect(screen.getByText('Build Plan role context')).toBeTruthy();
    expect(screen.getAllByText('Main Station Candidate').length).toBeGreaterThan(0);
    expect(screen.getByText(/Possible main-station body due to current orbital\/port concentration/i)).toBeTruthy();
    expect(screen.getByText(/You can edit the Build Plan and run Preview when ready/)).toBeTruthy();
    expect((screen.getByLabelText(/Target archetype/i) as HTMLSelectElement).value).toBe('agriculture_terraforming');
    expect(screen.getByDisplayValue('T1 - Generic Port Alpha')).toBeTruthy();
    expect(screen.getAllByRole('combobox').length).toBeGreaterThan(2);
    expect(screen.getByText('Suggested build')).toBeTruthy();
    expect(screen.getByText(/2 placements in Build Plan/)).toBeTruthy();
    expect(screen.getByText(/Preview has not been run for this plan yet/)).toBeTruthy();
    expect(mockedSimulateBuild).not.toHaveBeenCalled();

    await openPreviewMode();
    expect(screen.getByText('Preview role context')).toBeTruthy();
    expect(screen.getByText(/Advisory only; no role assignment or mechanics change is applied/i)).toBeTruthy();
  });

  it('opens Suggested Builds from the start card without generating or loading anything', async () => {
    mockNoRecommendedBuild();
    const { unmount } = renderPreview();

    const target = await screen.findByTestId('suggested-builds-focus-target');
    fireEvent.click(screen.getByRole('button', { name: /Show Suggested Builds/i }));

    expect(await screen.findByTestId('suggested-builds-workspace-view')).toBeTruthy();
    expect(screen.getByText('Suggested Builds role context')).toBeTruthy();
    expect(screen.getByText(/Suggested Builds can be compared against the selected strategic purpose/i)).toBeTruthy();
    expect(screen.queryByTestId('build-plan-workspace-view')).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(target));
    expect(mockedFetchOptimiserCandidates).not.toHaveBeenCalled();
    expect(mockedSimulateBuild).not.toHaveBeenCalled();
    expect(screen.queryByText(/Copied suggested build:/)).toBeNull();
    unmount();
  });

  it('shows Build Plan placement count and helper copy for manual planning', async () => {
    mockNoRecommendedBuild();
    renderPreview();

    await screen.findByText(/0 placements in Build Plan/);
    fireEvent.click(screen.getByRole('button', { name: /Start blank/i }));
    fireEvent.click(screen.getByRole('button', { name: /Add Facility/i }));

    expect(screen.getByText(/1 placement in Build Plan/)).toBeTruthy();
    expect(screen.getByText(/Target for Suggested Builds and Preview/)).toBeTruthy();
    expect(screen.getAllByText(/Check System Map > Architect Mode before final major station placement/).length).toBeGreaterThan(0);
    expect(screen.getByText('Architect survey: not observed')).toBeTruthy();
    expect(screen.getByText('Primary-port flag: unknown')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Add Facility/i }));
    expect(screen.getByText(/2 placements in Build Plan/)).toBeTruthy();
    expect(mockedSimulateBuild).not.toHaveBeenCalled();
  });

  it('toggles between List view and Body view without preview or suggested-build side effects', async () => {
    mockNoRecommendedBuild();
    renderPreview();

    await screen.findByText(/0 placements in Build Plan/);
    fireEvent.click(screen.getByRole('button', { name: /Start blank/i }));
    fireEvent.click(screen.getByRole('button', { name: /Add Facility/i }));

    expect(screen.getByRole('button', { name: /List view/i }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByDisplayValue('T1 - Generic Port Alpha')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /Body view/i }));

    expect(screen.getByRole('button', { name: /Body view/i }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByText(/Body view is the default planning surface\. List view is the advanced editor\./i)).toBeTruthy();
    expect(screen.getByRole('region', { name: /Layout plan summary/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /Select body Test Body/i })).toBeTruthy();
    expect(screen.getByText('Generic Port Alpha')).toBeTruthy();
    expect(screen.getAllByText('Primary port').length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: /Select body Test Body/i }));
    expect(screen.getByRole('button', { name: /Select body Test Body/i }).getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: /Placement 1: Generic Port Alpha/i }));
    expect(screen.getByRole('button', { name: /Placement 1: Generic Port Alpha/i }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByText(/Use List view to edit this placement/)).toBeTruthy();
    expect(mockedSimulateBuild).not.toHaveBeenCalled();
    expect(mockedFetchOptimiserCandidates).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /List view/i }));

    expect(screen.getByRole('button', { name: /List view/i }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByDisplayValue('T1 - Generic Port Alpha')).toBeTruthy();
    expect(mockedSimulateBuild).not.toHaveBeenCalled();
    expect(mockedFetchOptimiserCandidates).not.toHaveBeenCalled();
  });

  it('opens structure picker, filters/selects templates, and keeps preview/generation explicit', async () => {
    mockNoRecommendedBuild();
    renderPreview();

    await screen.findByText(/0 placements in Build Plan/);
    fireEvent.click(screen.getByRole('button', { name: /Start blank/i }));
    fireEvent.click(screen.getByRole('button', { name: /Add Facility/i }));
    expect(screen.getByDisplayValue('T1 - Generic Port Alpha')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /Browse structures/i }));
    await screen.findByTestId('structure-picker');
    expect(screen.getByText(/Uses current facility catalogue/)).toBeTruthy();
    expect(screen.getByText(/Evaluating against: Test Body/)).toBeTruthy();
    expect(screen.getByRole('searchbox', { name: /Search structures/i })).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Surface' }));
    fireEvent.change(screen.getByRole('searchbox', { name: /Search structures/i }), { target: { value: 'Agriculture' } });
    fireEvent.click(screen.getByRole('button', { name: /Select structure Agriculture Support A/i }));

    expect(screen.getByTestId('structure-replacement-comparison')).toBeTruthy();
    expect(screen.getByDisplayValue('T1 - Generic Port Alpha')).toBeTruthy();
    expect(mockedSimulateBuild).not.toHaveBeenCalled();
    expect(mockedFetchOptimiserCandidates).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /Apply replacement/i }));

    expect(screen.getByDisplayValue('T1 - Agriculture Support A - Agriculture')).toBeTruthy();
    expect(mockedSimulateBuild).not.toHaveBeenCalled();
    expect(mockedFetchOptimiserCandidates).not.toHaveBeenCalled();
  });

  it('manually imports system layout and shows success status without planner side effects', async () => {
    mockNoRecommendedBuild();
    let resolveImport: (value: LayoutImportResponse) => void = () => {};
    mockedImportSystemLayout.mockReturnValue(new Promise((resolve) => {
      resolveImport = resolve;
    }));
    renderPreview();

    await screen.findByText(/0 placements in Build Plan/);
    fireEvent.click(screen.getByRole('button', { name: /Start blank/i }));
    fireEvent.click(screen.getByRole('button', { name: /Add Facility/i }));
    expect(screen.getByDisplayValue('T1 - Generic Port Alpha')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /Import \/ refresh system layout/i }));

    expect(mockedImportSystemLayout).toHaveBeenCalledTimes(1);
    expect(mockedImportSystemLayout).toHaveBeenCalledWith(123, { source: 'spansh' });
    expect(screen.getByText(/Import request is running/)).toBeTruthy();

    resolveImport(layoutImportSuccess);

    await waitFor(() => expect(screen.getByText('success')).toBeTruthy());
    expect(screen.getByText('spansh')).toBeTruthy();
    expect(screen.getByText('Bodies imported')).toBeTruthy();
    expect(screen.getByText('Stations imported')).toBeTruthy();
    expect(screen.getAllByText('4').length).toBeGreaterThan(0);
    expect(screen.getAllByText('2').length).toBeGreaterThan(0);
    expect(screen.getByDisplayValue('T1 - Generic Port Alpha')).toBeTruthy();
    expect(mockedSimulateBuild).not.toHaveBeenCalled();
    expect(mockedFetchOptimiserCandidates).not.toHaveBeenCalled();
    expect(screen.queryByText(/Copied suggested build:/)).toBeNull();
  });

  it('shows failed layout import status and keeps the current Build Plan untouched', async () => {
    mockNoRecommendedBuild();
    mockedImportSystemLayout.mockRejectedValue(new Error('network unavailable'));
    renderPreview();

    await screen.findByText(/0 placements in Build Plan/);
    fireEvent.click(screen.getByRole('button', { name: /Start blank/i }));
    fireEvent.click(screen.getByRole('button', { name: /Add Facility/i }));
    fireEvent.click(screen.getByRole('button', { name: /Import \/ refresh system layout/i }));

    await screen.findByText(/Layout import failed: network unavailable/);
    expect(screen.getByText('failed')).toBeTruthy();
    expect(screen.getByDisplayValue('T1 - Generic Port Alpha')).toBeTruthy();
    expect(mockedSimulateBuild).not.toHaveBeenCalled();
    expect(mockedFetchOptimiserCandidates).not.toHaveBeenCalled();
  });

  it('surfaces body-assignment review warnings after manual layout import without reassigning placements', async () => {
    mockNoRecommendedBuild();
    const initialRequest: SimulateBuildRequest = {
      system_id64: 123,
      target_archetype: 'refinery_industrial',
      placements: [
        { facility_template_id: 'generic_port_alpha', local_body_id: 'missing-body', is_primary_port: true, build_order: 1 },
      ],
    };
    renderPreview({ initialRequest });

    await screen.findByDisplayValue('T1 - Generic Port Alpha');
    expect(screen.getByDisplayValue('System-wide / undecided body')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Import \/ refresh system layout/i }));

    await screen.findByText(/Needs review: imported\/current body data does not match assigned placement body IDs/);
    expect(screen.getByText(/missing-body/)).toBeTruthy();
    expect(screen.getByDisplayValue('System-wide / undecided body')).toBeTruthy();
    expect(mockedSimulateBuild).not.toHaveBeenCalled();
    expect(mockedFetchOptimiserCandidates).not.toHaveBeenCalled();
  });

  it('keeps current Build Plan edits when initialRequest object identity changes but content is unchanged', async () => {
    mockNoRecommendedBuild();
    const initialRequest: SimulateBuildRequest = {
      system_id64: 123,
      target_archetype: 'refinery_industrial',
      placements: [
        { facility_template_id: 'generic_port_alpha', local_body_id: 'body1', is_primary_port: true, build_order: 1 },
      ],
    };
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <SimulationPreview
          system={system}
          initialRequest={initialRequest}
        />
      </QueryClientProvider>,
    );

    await screen.findByDisplayValue('T1 - Generic Port Alpha');
    fireEvent.click(screen.getByRole('button', { name: /Add Facility/i }));
    await screen.findByText(/2 placements in Build Plan/i);

    const refreshedInitialRequest: SimulateBuildRequest = {
      system_id64: 123,
      target_archetype: 'refinery_industrial',
      placements: [
        { facility_template_id: 'generic_port_alpha', local_body_id: 'body1', is_primary_port: true, build_order: 1 },
      ],
    };
    rerender(
      <QueryClientProvider client={client}>
        <SimulationPreview
          system={system}
          initialRequest={refreshedInitialRequest}
        />
      </QueryClientProvider>,
    );

    expect(screen.getByText(/2 placements in Build Plan/i)).toBeTruthy();
    expect(screen.queryByText(/1 placement in Build Plan/i)).toBeNull();
  });

  it('marks an optimiser-origin plan as edited after manual add', async () => {
    mockNoRecommendedBuild();
    renderPreview();

    await openSuggestedBuildsMode();
    fireEvent.click(await screen.findByRole('button', { name: 'Generate Suggested Builds' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Load into Planner Workspace' }));
    await screen.findByText(/Copied suggested build:/);

    fireEvent.click(screen.getByRole('button', { name: /Add Facility/i }));

    expect(screen.getByText(/Started from suggested build:/)).toBeTruthy();
    expect(screen.getByText(/has been edited since loading/)).toBeTruthy();
  });

  it('blank advanced mode clears optimiser origin state', async () => {
    mockNoRecommendedBuild();
    renderPreview();

    await openSuggestedBuildsMode();
    fireEvent.click(await screen.findByRole('button', { name: 'Generate Suggested Builds' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Load into Planner Workspace' }));
    await screen.findByText(/Copied suggested build:/);

    fireEvent.click(screen.getByRole('button', { name: /Start blank/i }));

    expect(screen.queryByText(/Copied suggested build:/)).toBeNull();
    expect(screen.queryByText(/Started from suggested build:/)).toBeNull();
    expect(screen.getByText(/Blank manual Build Plan/)).toBeTruthy();
  });

  it('recommended plan loading clears optimiser origin state', async () => {
    mockRecommendedBuild();
    renderPreview();

    await openSuggestedBuildsMode();
    fireEvent.click(await screen.findByRole('button', { name: 'Generate Suggested Builds' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Load into Planner Workspace' }));
    const replaceButton = screen.queryByRole('button', { name: /Replace Build Plan/i });
    if (replaceButton) {
      fireEvent.click(replaceButton);
    }
    await screen.findByText(/Copied suggested build:/);

    fireEvent.click(screen.getByRole('button', { name: /Use recommended baseline/i }));

    expect(screen.queryByText(/Copied suggested build:/)).toBeNull();
    expect(screen.queryByText(/Started from suggested build:/)).toBeNull();
    expect(screen.getByText(/Recommended baseline loaded/)).toBeTruthy();
  });

  it('run preview remains explicit and sends resequenced current placements', async () => {
    mockNoRecommendedBuild();
    mockedSimulateBuild.mockReturnValue(new Promise(() => {}) as never);
    renderPreview();

    await openSuggestedBuildsMode();
    fireEvent.click(await screen.findByRole('button', { name: 'Generate Suggested Builds' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Load into Planner Workspace' }));
    await screen.findByText(/Copied suggested build:/);
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

    await openSuggestedBuildsMode();
    fireEvent.click(await screen.findByRole('button', { name: 'Generate Suggested Builds' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Load into Planner Workspace' }));
    await screen.findByText(/Copied suggested build:/);
    fireEvent.click(screen.getByRole('button', { name: /Run Preview/i }));
    await openPreviewMode();
    await screen.findByText(/Final Score/i);
    expect(screen.queryAllByText(/The Build Plan has changed since this preview was run/)).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: /^Build Plan/i }));
    await screen.findByTestId('build-plan-workspace-view');

    fireEvent.change(screen.getByLabelText(/Target archetype/i), { target: { value: 'trade_logistics' } });

    expect(screen.getByText(/Preview is stale - run Preview again/)).toBeTruthy();
    expect(screen.getByText(/Build Plan changed\. Run Preview to update the prediction/)).toBeTruthy();
    await openPreviewMode();
    expect(
      screen.getAllByText(/The Build Plan has changed since this preview was run/).length,
    ).toBeGreaterThan(0);
    expect(mockedSimulateBuild).toHaveBeenCalledTimes(1);
  });

  it('marks an existing preview result stale after placement edits and refreshes after explicit run', async () => {
    mockNoRecommendedBuild();
    mockedSimulateBuild.mockResolvedValue(simulationResult());
    renderPreview();

    await openSuggestedBuildsMode();
    fireEvent.click(await screen.findByRole('button', { name: 'Generate Suggested Builds' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Load into Planner Workspace' }));
    await screen.findByText(/Copied suggested build:/);
    fireEvent.click(screen.getByRole('button', { name: /Run Preview/i }));
    await openPreviewMode();
    await screen.findByText(/Final Score/i);
    fireEvent.click(screen.getByRole('button', { name: /^Build Plan/i }));
    await screen.findByTestId('build-plan-workspace-view');

    fireEvent.click(screen.getAllByRole('button', { name: /Move down/i })[0]);
    expect(screen.getByText(/Preview is stale - run Preview again/)).toBeTruthy();
    await openPreviewMode();
    expect(
      screen.getAllByText(/The Build Plan has changed since this preview was run/).length,
    ).toBeGreaterThan(0);
    expect(mockedSimulateBuild).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getAllByRole('button', { name: /Run Preview/i })[0]);
    await waitFor(() => expect(mockedSimulateBuild).toHaveBeenCalledTimes(2));
    expect(screen.queryAllByText(/The Build Plan has changed since this preview was run/)).toHaveLength(0);
  });

  it('supports generate compare load edit and run preview with current edited placements', async () => {
    mockRecommendedBuild();
    mockedSimulateBuild.mockReturnValue(new Promise(() => {}) as never);
    renderPreview();

    await openSuggestedBuildsMode();
    fireEvent.click(await screen.findByRole('button', { name: 'Generate Suggested Builds' }));
    expect(mockedSimulateBuild).not.toHaveBeenCalled();
    expect(await screen.findByText(/Compare with current plan/i)).toBeTruthy();
    expect(screen.getByText(/advisory and preview-only/i)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Load into Planner Workspace' }));
    fireEvent.click(await screen.findByRole('button', { name: /Replace Build Plan/i }));
    await screen.findByText(/Copied suggested build:/);
    expect(mockedSimulateBuild).not.toHaveBeenCalled();

    fireEvent.click(screen.getAllByRole('button', { name: /Move down/i })[0]);
    expect(screen.getByText(/Started from suggested build:/)).toBeTruthy();
    expect(screen.getByText(/edited since loading/)).toBeTruthy();
    expect(mockedSimulateBuild).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /Run Preview/i }));

    await waitFor(() => expect(mockedSimulateBuild).toHaveBeenCalledTimes(1));
    expect(screen.getByText(/Preview is running/)).toBeTruthy();
    expect(screen.getByText(/ED-Finder is evaluating the current Build Plan/)).toBeTruthy();
    expect(mockedSimulateBuild).toHaveBeenCalledWith({
      system_id64: 123,
      target_archetype: 'agriculture_terraforming',
      placements: [
        { facility_template_id: 'agri_support_a', local_body_id: 'body1', is_primary_port: false, build_order: 1 },
        { facility_template_id: 'generic_port_alpha', local_body_id: 'body1', is_primary_port: true, build_order: 2 },
      ],
    });
  });

  it('uses cautious current-preview status copy after an explicit successful run', async () => {
    mockNoRecommendedBuild();
    mockedSimulateBuild.mockResolvedValue(simulationResult());
    renderPreview();

    await openSuggestedBuildsMode();
    fireEvent.click(await screen.findByTestId('generate-suggested-builds'));
    fireEvent.click(await screen.findByRole('button', { name: 'Load into Planner Workspace' }));
    await screen.findByText(/Copied suggested build:/);
    fireEvent.click(screen.getByRole('button', { name: /Run Preview/i }));

    expect(await screen.findByText(/Preview matches current Build Plan/)).toBeTruthy();
    await openPreviewMode();
    await screen.findByText(/Final Score/i);
    expect(screen.getByText(/After checking in-game, record Observed Evidence/)).toBeTruthy();
    expect(screen.queryByText(/Preview is up to date/)).toBeNull();
  });

  // ── Stage 6D integration ────────────────────────────────────────────────
  it('opens Evidence and Validation modes explicitly', async () => {
    mockNoRecommendedBuild();
    renderPreview();

    expect((await screen.findAllByText('Validation')).length).toBeGreaterThan(0);

    await openEvidenceMode();
    expect(screen.queryByTestId('validation-workspace-view')).toBeNull();

    await openValidationMode();
    expect(screen.queryByTestId('evidence-workspace-view')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /^Build Plan/i }));
    expect(await screen.findByTestId('build-plan-workspace-view')).toBeTruthy();
    expect(screen.queryByTestId('validation-workspace-view')).toBeNull();
  });

  it('shows the no-preview empty state in Validation when no preview has been run', async () => {
    mockNoRecommendedBuild();
    renderPreview();

    await openValidationMode();
    await screen.findByRole('region', { name: 'Validation' });
    expect(
      screen.getByText(/Run Preview first, then record Observed Evidence after checking in-game/),
    ).toBeTruthy();
    // No compare call should occur without a preview result.
    expect(mockedCompare).not.toHaveBeenCalled();
  });

  it('calls compare API once a preview result exists, with system, target_archetype, and the SimulateBuildResponse as prediction', async () => {
    mockNoRecommendedBuild();
    mockedSimulateBuild.mockResolvedValue(simulationResult());
    mockedCompare.mockResolvedValue({
      system_id64: 123,
      target_archetype: 'agriculture_terraforming',
      generated_at: '2026-05-15T12:00:00+00:00',
      summary: {
        status: 'no_observations',
        observed_facts_count: 0,
        compared_predictions_count: 0,
        confirmed_count: 0,
        contradicted_count: 0,
        observed_only_count: 0,
        predicted_only_count: 0,
        unknown_count: 0,
        unverified_count: 0,
        confidence_impact: 'none',
        summary: 'No observations yet.',
      },
      comparisons: [],
      warnings: [],
      assumptions: [],
    } satisfies PredictionObservationCompareResponse);

    renderPreview();
    await openSuggestedBuildsMode();
    fireEvent.click(await screen.findByRole('button', { name: 'Generate Suggested Builds' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Load into Planner Workspace' }));
    await screen.findByText(/Copied suggested build:/);
    fireEvent.click(screen.getByRole('button', { name: /Run Preview/i }));

    await openPreviewMode();
    await screen.findByText(/Final Score/i);
    expect(mockedCompare).not.toHaveBeenCalled();
    await openValidationMode();
    await waitFor(() => expect(mockedCompare).toHaveBeenCalledTimes(1));
    const sent = mockedCompare.mock.calls[0][0];
    expect(sent.system_id64).toBe(123);
    expect(sent.target_archetype).toBe('agriculture_terraforming');
    expect((sent.prediction as { target_archetype?: string }).target_archetype).toBe(
      'agriculture_terraforming',
    );
  });
});
