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
  listObservedFacts,
  reviewPredictionValidation,
  simulateBuild,
  updateObservedFact,
} from '@/lib/api';
import type { FacilityTemplate, OptimiserCandidatesResponse, PredictionObservationCompareResponse, SimulateBuildResponse, SimulationSummary, SystemDetail, ValidationReviewResponse } from '@/types/api';
import { SimulationPreview } from './SimulationPreview';

vi.mock('@/lib/api', () => ({
  fetchOptimiserCandidates: vi.fn(),
  getFacilityTemplates: vi.fn(),
  getSimulationSummary: vi.fn(),
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
    mockedSimulateBuild.mockReset();
    mockedListObservedFacts.mockReset();
    mockedCreateObservedFact.mockReset();
    mockedUpdateObservedFact.mockReset();
    mockedDeleteObservedFact.mockReset();
    mockedCompare.mockReset();
    mockedReview.mockReset();
  });

  it('renders Observed Evidence panel and the passive evidence notice', async () => {
    mockNoRecommendedBuild();
    renderPreview();

    // Observed Evidence label appears in both the section nav and the panel
    // section region. getAllByText keeps this assertion robust.
    const labels = await screen.findAllByText('Observed Evidence');
    expect(labels.length).toBeGreaterThan(0);
    // The region itself is exposed via aria-label so test code can scope
    // assertions inside the Observed Evidence panel deterministically.
    expect(screen.getByRole('region', { name: 'Observed Evidence' })).toBeTruthy();
    // Passive copy is present so the user does not think evidence affects scoring.
    expect(
      screen.getByText(/Later step: Observed Evidence records what you see in-game after planning/),
    ).toBeTruthy();
    // Section nav still renders predicted-side labels too.
    expect(screen.getAllByText('Build Plan').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Suggested Builds').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Preview Result').length).toBeGreaterThan(0);
  });

  it('does not call simulateBuild or optimiser candidate generation when only the observed evidence panel renders', async () => {
    mockNoRecommendedBuild();
    renderPreview();

    // Wait for the panel to settle.
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
    expect(screen.getByText(/Target archetype affects predicted economy, service, and buildability outcomes/)).toBeTruthy();
    expect(screen.getAllByText('Generate Suggested Builds').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: /Show Suggested Builds/i })).toBeTruthy();
    expect(screen.getByText(/Start blank/)).toBeTruthy();
    expect(screen.getByText(/Advanced manual control/)).toBeTruthy();
    expect(screen.getByText(/0 placements in Build Plan/)).toBeTruthy();
    expect(screen.getAllByText(/Preview not run yet/).length).toBeGreaterThan(0);

    fireEvent.click(await screen.findByRole('button', { name: 'Generate Suggested Builds' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Copy to Build Plan' }));

    await waitFor(() => expect(screen.getByText(/Copied suggested build:/)).toBeTruthy());
    expect(screen.getAllByText(/Balanced Agriculture candidate/).length).toBeGreaterThan(0);
    expect(screen.getByText(/You can edit the Build Plan and run Preview when ready/)).toBeTruthy();
    expect((screen.getByLabelText(/Target archetype/i) as HTMLSelectElement).value).toBe('agriculture_terraforming');
    expect(screen.getAllByText('generic_port_alpha').length).toBeGreaterThan(0);
    expect(screen.getAllByText('agri_support_a').length).toBeGreaterThan(0);
    expect(screen.getByText('Suggested build')).toBeTruthy();
    expect(screen.getByText(/2 placements in Build Plan/)).toBeTruthy();
    expect(screen.getByText(/Preview has not been run for this plan yet/)).toBeTruthy();
    expect(mockedSimulateBuild).not.toHaveBeenCalled();
  });

  it('focuses Suggested Builds from the start card without generating or loading anything', async () => {
    const scrollIntoView = vi.fn();
    const clearTimeoutSpy = vi.spyOn(window, 'clearTimeout');
    Element.prototype.scrollIntoView = scrollIntoView;
    mockNoRecommendedBuild();
    const { unmount } = renderPreview();

    const target = await screen.findByTestId('suggested-builds-focus-target');
    fireEvent.click(screen.getByRole('button', { name: /Show Suggested Builds/i }));
    fireEvent.click(screen.getByRole('button', { name: /Show Suggested Builds/i }));

    expect(scrollIntoView).toHaveBeenCalledTimes(2);
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' });
    expect(document.activeElement).toBe(target);
    expect(clearTimeoutSpy).toHaveBeenCalled();
    expect(mockedFetchOptimiserCandidates).not.toHaveBeenCalled();
    expect(mockedSimulateBuild).not.toHaveBeenCalled();
    expect(screen.queryByText(/Copied suggested build:/)).toBeNull();
    unmount();
    expect(clearTimeoutSpy).toHaveBeenCalled();
  });

  it('shows Build Plan placement count and helper copy for manual planning', async () => {
    mockNoRecommendedBuild();
    renderPreview();

    await screen.findByText(/0 placements in Build Plan/);
    fireEvent.click(screen.getByRole('button', { name: /Start blank/i }));
    fireEvent.click(screen.getByRole('button', { name: /Add Facility/i }));

    expect(screen.getByText(/1 placement in Build Plan/)).toBeTruthy();
    expect(screen.getByText(/Target archetype affects predicted economy, service, and buildability outcomes/)).toBeTruthy();
    expect(screen.getByText(/Primary port is a major planning choice/)).toBeTruthy();
    expect(screen.getByText(/Yellow CP supports Tier 2 construction/)).toBeTruthy();
    expect(screen.getByText(/Green CP supports Tier 3 construction/)).toBeTruthy();
    expect(screen.getByText(/Build order can affect CP timing and port escalation/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Add Facility/i }));
    expect(screen.getByText(/2 placements in Build Plan/)).toBeTruthy();
    expect(mockedSimulateBuild).not.toHaveBeenCalled();
  });

  it('marks an optimiser-origin plan as edited after manual add', async () => {
    mockNoRecommendedBuild();
    renderPreview();

    fireEvent.click(await screen.findByRole('button', { name: 'Generate Suggested Builds' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Copy to Build Plan' }));
    await screen.findByText(/Copied suggested build:/);

    fireEvent.click(screen.getByRole('button', { name: /Add Facility/i }));

    expect(screen.getByText(/Started from suggested build:/)).toBeTruthy();
    expect(screen.getByText(/has been edited since loading/)).toBeTruthy();
  });

  it('blank advanced mode clears optimiser origin state', async () => {
    mockNoRecommendedBuild();
    renderPreview();

    fireEvent.click(await screen.findByRole('button', { name: 'Generate Suggested Builds' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Copy to Build Plan' }));
    await screen.findByText(/Copied suggested build:/);

    fireEvent.click(screen.getByRole('button', { name: /Start blank/i }));

    expect(screen.queryByText(/Copied suggested build:/)).toBeNull();
    expect(screen.queryByText(/Started from suggested build:/)).toBeNull();
    expect(screen.getByText(/Blank advanced simulation/)).toBeTruthy();
  });

  it('recommended plan loading clears optimiser origin state', async () => {
    mockRecommendedBuild();
    renderPreview();

    fireEvent.click(await screen.findByRole('button', { name: 'Generate Suggested Builds' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Copy to Build Plan' }));
    fireEvent.click(await screen.findByRole('button', { name: /Replace Build Plan/i }));
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

    fireEvent.click(await screen.findByRole('button', { name: 'Generate Suggested Builds' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Copy to Build Plan' }));
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

    fireEvent.click(await screen.findByRole('button', { name: 'Generate Suggested Builds' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Copy to Build Plan' }));
    await screen.findByText(/Copied suggested build:/);
    fireEvent.click(screen.getByRole('button', { name: /Run Preview/i }));
    await screen.findByText(/Final Score/i);
    expect(screen.queryAllByText(/The Build Plan has changed since this preview was run/)).toHaveLength(0);

    fireEvent.change(screen.getByLabelText(/Target archetype/i), { target: { value: 'trade_logistics' } });

    // Stage 6D: the stale wording can now appear in BOTH PreviewResult
    // and ValidationPanel (each with their own copy). Both are
    // legitimate UX signals that a re-run is needed.
    expect(
      screen.getAllByText(/The Build Plan has changed since this preview was run/).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText(/Preview is stale - run Preview again/)).toBeTruthy();
    expect(screen.getByText(/Build Plan changed\. Run Preview to update the prediction/)).toBeTruthy();
    expect(mockedSimulateBuild).toHaveBeenCalledTimes(1);
  });

  it('marks an existing preview result stale after placement edits and refreshes after explicit run', async () => {
    mockNoRecommendedBuild();
    mockedSimulateBuild.mockResolvedValue(simulationResult());
    renderPreview();

    fireEvent.click(await screen.findByRole('button', { name: 'Generate Suggested Builds' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Copy to Build Plan' }));
    await screen.findByText(/Copied suggested build:/);
    fireEvent.click(screen.getByRole('button', { name: /Run Preview/i }));
    await screen.findByText(/Final Score/i);

    fireEvent.click(screen.getAllByRole('button', { name: /Move down/i })[0]);
    expect(
      screen.getAllByText(/The Build Plan has changed since this preview was run/).length,
    ).toBeGreaterThan(0);
    expect(mockedSimulateBuild).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: /Run Preview/i }));
    await waitFor(() => expect(mockedSimulateBuild).toHaveBeenCalledTimes(2));
    expect(screen.queryAllByText(/The Build Plan has changed since this preview was run/)).toHaveLength(0);
  });

  it('supports generate compare load edit and run preview with current edited placements', async () => {
    mockRecommendedBuild();
    mockedSimulateBuild.mockReturnValue(new Promise(() => {}) as never);
    renderPreview();

    fireEvent.click(await screen.findByRole('button', { name: 'Generate Suggested Builds' }));
    expect(mockedSimulateBuild).not.toHaveBeenCalled();
    expect(await screen.findByText(/Compare with current plan/i)).toBeTruthy();
    expect(screen.getByText(/advisory and preview-only/i)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Copy to Build Plan' }));
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

    fireEvent.click(await screen.findByTestId('generate-suggested-builds'));
    fireEvent.click(await screen.findByRole('button', { name: 'Copy to Build Plan' }));
    await screen.findByText(/Copied suggested build:/);
    fireEvent.click(screen.getByRole('button', { name: /Run Preview/i }));

    await screen.findByText(/Final Score/i);
    expect(screen.getByText(/Preview matches current Build Plan/)).toBeTruthy();
    expect(screen.getByText(/This Preview Result was generated for the current Build Plan/)).toBeTruthy();
    expect(screen.queryByText(/Preview is up to date/)).toBeNull();
  });

  // ── Stage 6D integration ────────────────────────────────────────────────
  it('renders the Validation section after Observed Evidence and the section nav exposes a Validation label', async () => {
    mockNoRecommendedBuild();
    renderPreview();

    // Validation chip appears in the section nav.
    expect((await screen.findAllByText('Validation')).length).toBeGreaterThan(0);
    // Validation panel renders as a separate aria region.
    const validation = await screen.findByRole('region', { name: 'Validation' });
    const observed = await screen.findByRole('region', { name: 'Observed Evidence' });

    // The Validation region must appear *after* the Observed Evidence
    // region in DOM order (Colony Planner section ordering rule).
    const order = observed.compareDocumentPosition(validation);
    expect(order & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('shows the no-preview empty state in Validation when no preview has been run', async () => {
    mockNoRecommendedBuild();
    renderPreview();

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
    fireEvent.click(await screen.findByRole('button', { name: 'Generate Suggested Builds' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Copy to Build Plan' }));
    await screen.findByText(/Copied suggested build:/);
    fireEvent.click(screen.getByRole('button', { name: /Run Preview/i }));

    await waitFor(() => expect(mockedCompare).toHaveBeenCalledTimes(1));
    const sent = mockedCompare.mock.calls[0][0];
    expect(sent.system_id64).toBe(123);
    expect(sent.target_archetype).toBe('agriculture_terraforming');
    expect((sent.prediction as { target_archetype?: string }).target_archetype).toBe(
      'agriculture_terraforming',
    );
  });
});
