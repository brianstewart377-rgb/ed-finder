import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  comparePredictionToObservations,
  fetchOptimiserCandidates,
  simulateBuild,
  createObservedFact,
  deleteObservedFact,
  listObservedFacts,
  reviewPredictionValidation,
  updateObservedFact,
} from '@/lib/api';
import type {
  PredictionObservationCompareResponse,
  SimulateBuildResponse,
  ValidationReviewResponse,
} from '@/types/api';
import { ValidationPanel } from './ValidationPanel';

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    comparePredictionToObservations: vi.fn(),
    reviewPredictionValidation: vi.fn(),
    fetchOptimiserCandidates: vi.fn(),
    simulateBuild: vi.fn(),
    listObservedFacts: vi.fn(),
    createObservedFact: vi.fn(),
    updateObservedFact: vi.fn(),
    deleteObservedFact: vi.fn(),
  };
});

const mockedCompare = vi.mocked(comparePredictionToObservations);
const mockedReview = vi.mocked(reviewPredictionValidation);
const mockedSimulateBuild = vi.mocked(simulateBuild);
const mockedFetchOptimiser = vi.mocked(fetchOptimiserCandidates);
const mockedListObservedFacts = vi.mocked(listObservedFacts);
const mockedCreateObservedFact = vi.mocked(createObservedFact);
const mockedUpdateObservedFact = vi.mocked(updateObservedFact);
const mockedDeleteObservedFact = vi.mocked(deleteObservedFact);
const validationDir = dirname(fileURLToPath(import.meta.url));

function validationSourceFiles(dir = validationDir): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return validationSourceFiles(path);
    if (!entry.name.match(/\.(ts|tsx)$/) || entry.name.endsWith('.test.tsx')) return [];
    return [path];
  });
}

function previewResult(overrides: Partial<SimulateBuildResponse> = {}): SimulateBuildResponse {
  return {
    system_id64: 123,
    mechanics_version: 'colonisation-engine-v2.1',
    target_archetype: 'trade_logistics',
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
      summary: 'No observed player data attached yet.',
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
    data_quality: {},
    confidence_signals: [],
    mechanics_trace: {},
    top_two_alignment: 'none',
    contamination_risk: 'low',
    warnings: [],
    strengths: [],
    recommendations: [],
    mechanics_notes: [],
    links: { strong_links: [], weak_links: [] },
    ...overrides,
  };
}

function compareResponse(
  overrides: Partial<PredictionObservationCompareResponse> = {},
): PredictionObservationCompareResponse {
  return {
    system_id64: 123,
    target_archetype: 'trade_logistics',
    generated_at: '2026-05-15T12:00:00+00:00',
    summary: {
      status: 'mixed',
      observed_facts_count: 3,
      compared_predictions_count: 4,
      confirmed_count: 1,
      contradicted_count: 1,
      observed_only_count: 1,
      predicted_only_count: 1,
      unknown_count: 0,
      unverified_count: 0,
      confidence_impact: 'mixed',
      summary: '1 confirmed, 1 contradicted, 1 observed-only, 1 predicted-only.',
    },
    comparisons: [
      {
        comparison_id: 'service:refining',
        area: 'service',
        subject_type: 'service',
        subject_id: 'refining',
        predicted_value: 'active',
        observed_value: { present: true },
        status: 'confirmed',
        severity: 'info',
        confidence: 'high',
        reason: 'Predicted active and observed present.',
        recommended_action: null,
        evidence: [
          {
            observation_id: 'obs_conf',
            fact_type: 'service_presence',
            subject_type: 'service',
            subject_id: 'refining',
            status: 'observed_present',
            confidence: 'high',
            observed_value: { present: true },
            expected_value: null,
            notes: 'Saw refining at port.',
          },
        ],
        prediction_source: 'services',
      },
      {
        comparison_id: 'service:repair',
        area: 'service',
        subject_type: 'service',
        subject_id: 'repair',
        predicted_value: 'active',
        observed_value: { present: false },
        status: 'contradicted',
        severity: 'medium',
        confidence: 'medium',
        reason: 'Predicted active but observed absent.',
        recommended_action: 'Re-check station services.',
        evidence: [
          {
            observation_id: 'obs_contra',
            fact_type: 'service_presence',
            subject_type: 'service',
            subject_id: 'repair',
            status: 'observed_absent',
            confidence: 'medium',
            observed_value: { present: false },
            expected_value: null,
            notes: null,
          },
        ],
        prediction_source: 'services',
      },
      {
        comparison_id: 'service:fuel',
        area: 'service',
        subject_type: 'service',
        subject_id: 'fuel',
        predicted_value: 'active',
        observed_value: null,
        status: 'predicted_only',
        severity: 'info',
        confidence: 'unknown',
        reason: 'Predicted active; no matching observation recorded.',
        recommended_action: null,
        evidence: [],
        prediction_source: 'services',
      },
      {
        comparison_id: 'service:tourism',
        area: 'service',
        subject_type: 'service',
        subject_id: 'tourism',
        predicted_value: null,
        observed_value: { present: true },
        status: 'observed_only',
        severity: 'info',
        confidence: 'medium',
        reason: 'Observed present; prediction does not mention this service.',
        recommended_action: null,
        evidence: [
          {
            observation_id: 'obs_obs_only',
            fact_type: 'service_presence',
            subject_type: 'service',
            subject_id: 'tourism',
            status: 'observed_present',
            confidence: 'medium',
            observed_value: { present: true },
            expected_value: null,
            notes: null,
          },
        ],
        prediction_source: null,
      },
    ],
    warnings: [],
    assumptions: [],
    ...overrides,
  };
}

function reviewResponse(
  overrides: Partial<ValidationReviewResponse> = {},
): ValidationReviewResponse {
  return {
    system_id64: 123,
    target_archetype: 'trade_logistics',
    generated_at: '2026-05-15T12:00:00+00:00',
    summary: {
      overall_review_status: 'mixed_evidence',
      confidence_impact: 'mixed',
      highest_severity: 'medium',
      review_needed_count: 3,
      evidence_strength: 'mixed',
      primary_review_areas: ['service_rules', 'economy_rules', 'cp_rules'],
      summary: 'Evidence is mixed: some predictions are confirmed while others need review.',
    },
    signals: [
      {
        signal_id: 'service_rules:contradicted',
        area: 'service_rules',
        severity: 'medium',
        confidence: 'medium',
        status: 'review_recommended',
        title: 'Service prediction rules may need review',
        message: 'Needs-review service rows point to this area. This is a review lead, not an automatic rule change.',
        recommended_action: 'Review service unlock assumptions and facility/service mapping.',
        comparison_ids: ['service:repair'],
      },
      {
        signal_id: 'economy_rules:contradicted',
        area: 'economy_rules',
        severity: 'medium',
        confidence: 'medium',
        status: 'review_recommended',
        title: 'Economy prediction rules may need review',
        message: 'Economy evidence may need review.',
        recommended_action: 'Review economy inheritance, facility pressure, and economy composition assumptions.',
        comparison_ids: ['economy:extraction'],
      },
      {
        signal_id: 'cp_rules:contradicted',
        area: 'cp_rules',
        severity: 'medium',
        confidence: 'medium',
        status: 'review_recommended',
        title: 'CP calculation may need review',
        message: 'CP evidence may need review.',
        recommended_action: 'Review CP source values and final CP calculation.',
        comparison_ids: ['cp:yellow'],
      },
      {
        signal_id: 'evidence:low_confidence_contradictions',
        area: 'evidence_quality',
        severity: 'low',
        confidence: 'low',
        status: 'monitor',
        title: 'Contradiction is based on low-confidence evidence',
        message: 'Some needs-review rows are based on low-confidence evidence.',
        recommended_action: 'Confirm in-game before changing assumptions.',
        comparison_ids: ['service:repair'],
      },
      {
        signal_id: 'service_rules:high_priority',
        area: 'service_rules',
        severity: 'high',
        confidence: 'high',
        status: 'review_high_priority',
        title: 'Service prediction rules may need review',
        message: 'High-confidence service evidence may need review.',
        recommended_action: 'Review service unlock assumptions and facility/service mapping.',
        comparison_ids: ['service:shipyard'],
      },
    ],
    warnings: [],
    assumptions: [],
    ...overrides,
  };
}

interface RenderOptions {
  systemId64?: number;
  targetArchetype?: string | null;
  preview?: SimulateBuildResponse | null;
  stale?: boolean;
}

function renderPanel({
  systemId64 = 123,
  targetArchetype = 'trade_logistics',
  preview = previewResult(),
  stale = false,
}: RenderOptions = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={client}>
      <ValidationPanel
        systemId64={systemId64}
        targetArchetype={targetArchetype}
        previewResult={preview}
        isPreviewResultStale={stale}
      />
    </QueryClientProvider>,
  );
  return { ...utils, client };
}

describe('ValidationPanel - Stage 6D validation display', () => {
  beforeEach(() => {
    mockedCompare.mockReset();
    mockedReview.mockReset();
    mockedReview.mockResolvedValue(reviewResponse());
    mockedSimulateBuild.mockReset();
    mockedFetchOptimiser.mockReset();
    mockedListObservedFacts.mockReset();
    mockedCreateObservedFact.mockReset();
    mockedUpdateObservedFact.mockReset();
    mockedDeleteObservedFact.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it('renders the advisory passive copy near the top of the panel', () => {
    renderPanel({ preview: null });
    expect(screen.getByRole('region', { name: 'Validation' })).toBeTruthy();
    expect(
      screen.getByText(/This validation is advisory\. It compares the current preview result/),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /does not change scoring, optimiser ranking, generated candidates, or in-game state/,
      ),
    ).toBeTruthy();
  });

  it('keeps validation source free of preview, optimiser, and observation mutation helpers', () => {
    const forbidden = [
      'simulateBuild',
      'fetchOptimiserCandidates',
      'createObservedFact',
      'updateObservedFact',
      'deleteObservedFact',
    ];
    const offenders = validationSourceFiles().flatMap((path) => {
      const source = readFileSync(path, 'utf8');
      return forbidden
        .filter((token) => source.includes(token))
        .map((token) => `${path.replace(`${validationDir}/`, '')}: ${token}`);
    });

    expect(offenders).toEqual([]);
  });

  it('shows the no-preview empty state and does not call compare API when there is no preview result', async () => {
    renderPanel({ preview: null });
    expect(
      screen.getByText(/Run Preview to compare predictions with observed evidence/),
    ).toBeTruthy();
    // Wait a tick to be sure no async query was kicked off.
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(mockedCompare).not.toHaveBeenCalled();
    expect(mockedReview).not.toHaveBeenCalled();
  });

  it('calls the compare API with system_id64, target_archetype, and the prediction when a preview is present', async () => {
    mockedCompare.mockResolvedValue(compareResponse());
    renderPanel();
    await waitFor(() => expect(mockedCompare).toHaveBeenCalledTimes(1));
    const sent = mockedCompare.mock.calls[0][0];
    expect(sent.system_id64).toBe(123);
    expect(sent.target_archetype).toBe('trade_logistics');
    // The prediction passed to the compare API is the SimulateBuildResponse verbatim.
    expect((sent.prediction as { mechanics_version?: string }).mechanics_version).toBe(
      'colonisation-engine-v2.1',
    );
  });

  it('calls the review endpoint with the same prediction when a preview is present', async () => {
    mockedCompare.mockResolvedValue(compareResponse());
    renderPanel();
    await waitFor(() => expect(mockedReview).toHaveBeenCalledTimes(1));
    const sent = mockedReview.mock.calls[0][0];
    expect(sent.system_id64).toBe(123);
    expect(sent.target_archetype).toBe('trade_logistics');
    expect((sent.prediction as { mechanics_version?: string }).mechanics_version).toBe(
      'colonisation-engine-v2.1',
    );
  });

  it('renders the summary block with overall status, confidence impact, and per-bucket counts', async () => {
    mockedCompare.mockResolvedValue(compareResponse());
    renderPanel();
    expect(await screen.findByTestId('validation-summary')).toBeTruthy();
    expect(screen.getByTestId('validation-summary-overall-status').textContent).toMatch(/Mixed evidence/);
    expect(screen.getByTestId('validation-summary-confidence-impact').textContent).toMatch(/Mixed/);
    expect(screen.getByTestId('validation-summary-observed-facts').textContent).toBe('3');
    expect(screen.getByTestId('validation-summary-compared').textContent).toBe('4');
    expect(screen.getByTestId('validation-summary-confirmed').textContent).toBe('1');
    expect(screen.getByTestId('validation-summary-contradicted').textContent).toBe('1');
    expect(screen.getByTestId('validation-summary-predicted-only').textContent).toBe('1');
    expect(screen.getByTestId('validation-summary-observed-only').textContent).toBe('1');
  });

  it('renders review guidance advisory copy and summary metrics', async () => {
    mockedCompare.mockResolvedValue(compareResponse());
    renderPanel();
    expect(await screen.findByTestId('validation-review-panel')).toBeTruthy();
    expect(screen.getByTestId('validation-review-advisory-copy').textContent).toMatch(/Review guidance is advisory/);
    expect(screen.getByTestId('validation-review-advisory-copy').textContent).toMatch(/does not change mechanics or scoring/i);
    expect(screen.getByTestId('validation-review-status').textContent).toBe('Mixed evidence');
    expect(screen.getByTestId('validation-review-evidence-strength').textContent).toBe('mixed');
    expect(screen.getByTestId('validation-review-highest-severity').textContent).toBe('Medium');
    expect(screen.getByTestId('validation-review-primary-areas').textContent).toMatch(/Service rules/);
  });

  it('renders service, economy, CP, and evidence-quality review signals', async () => {
    mockedCompare.mockResolvedValue(compareResponse());
    renderPanel();
    const panel = await screen.findByTestId('validation-review-panel');
    expect(within(panel).getAllByText('Service rules').length).toBeGreaterThan(0);
    expect(within(panel).getByText('Economy rules')).toBeTruthy();
    expect(within(panel).getByText('CP rules')).toBeTruthy();
    expect(within(panel).getByText('Evidence quality')).toBeTruthy();
    expect(within(panel).getByText('Monitor')).toBeTruthy();
    expect(within(panel).getByText(/Confirm in-game before changing assumptions/)).toBeTruthy();
    expect(panel.textContent ?? '').not.toMatch(/wrong/i);
    expect(panel.textContent ?? '').not.toMatch(/proof/i);
  });

  it('renders a confirmed row labelled "Confirmed"', async () => {
    mockedCompare.mockResolvedValue(compareResponse());
    renderPanel();
    const cards = await screen.findAllByTestId('validation-comparison-card');
    const confirmedCard = cards.find((card) => card.getAttribute('data-status') === 'confirmed');
    expect(confirmedCard).toBeTruthy();
    expect(within(confirmedCard!).getByTestId('validation-card-status').textContent).toBe('Confirmed');
  });

  it('renders a contradicted row as "Needs review" and avoids high-certainty wording', async () => {
    mockedCompare.mockResolvedValue(compareResponse());
    renderPanel();
    const cards = await screen.findAllByTestId('validation-comparison-card');
    const contradicted = cards.find((card) => card.getAttribute('data-status') === 'contradicted');
    expect(contradicted).toBeTruthy();
    expect(within(contradicted!).getByTestId('validation-card-status').textContent).toBe('Needs review');
    expect(screen.getByTestId('validation-panel').textContent ?? '').not.toMatch(/wrong/i);
    expect(screen.getByTestId('validation-panel').textContent ?? '').not.toMatch(/proof/i);
  });

  it('renders the conservative copy for predicted_only rows', async () => {
    mockedCompare.mockResolvedValue(compareResponse());
    renderPanel();
    const cards = await screen.findAllByTestId('validation-comparison-card');
    const predOnly = cards.find((card) => card.getAttribute('data-status') === 'predicted_only');
    expect(predOnly).toBeTruthy();
    expect(
      within(predOnly!).getByTestId('validation-card-conservative-note').textContent,
    ).toMatch(/Predicted, but no matching observation has been recorded yet\./);
  });

  it('renders the conservative copy for observed_only rows', async () => {
    mockedCompare.mockResolvedValue(compareResponse());
    renderPanel();
    const cards = await screen.findAllByTestId('validation-comparison-card');
    const obsOnly = cards.find((card) => card.getAttribute('data-status') === 'observed_only');
    expect(obsOnly).toBeTruthy();
    expect(
      within(obsOnly!).getByTestId('validation-card-conservative-note').textContent,
    ).toMatch(/Observed evidence exists, but the current prediction has no matching item\./);
  });

  it('renders evidence observation_id, fact_type, status, confidence, and notes inside the evidence list', async () => {
    mockedCompare.mockResolvedValue(compareResponse());
    renderPanel();
    const cards = await screen.findAllByTestId('validation-comparison-card');
    const confirmedCard = cards.find((card) => card.getAttribute('data-status') === 'confirmed')!;
    const evidenceItems = within(confirmedCard).getAllByTestId('validation-card-evidence-item');
    expect(evidenceItems.length).toBeGreaterThan(0);
    const first = evidenceItems[0];
    expect(within(first).getByTestId('validation-evidence-observation-id').textContent).toBe('obs_conf');
    expect(within(first).getByTestId('validation-evidence-fact-type').textContent).toBe('service_presence');
    expect(within(first).getByTestId('validation-evidence-status').textContent).toBe('observed_present');
    expect(within(first).getByTestId('validation-evidence-confidence').textContent).toBe('high');
    expect(within(first).getByTestId('validation-evidence-notes').textContent).toMatch(/Saw refining at port\./);
  });

  it('narrows the visible rows when the status filter changes', async () => {
    mockedCompare.mockResolvedValue(compareResponse());
    renderPanel();
    expect((await screen.findAllByTestId('validation-comparison-card')).length).toBe(4);

    fireEvent.change(screen.getByTestId('validation-status-filter'), {
      target: { value: 'contradicted' },
    });

    const cards = screen.getAllByTestId('validation-comparison-card');
    expect(cards.length).toBe(1);
    expect(cards[0].getAttribute('data-status')).toBe('contradicted');
  });

  it('shows a loading state while the compare query is pending', async () => {
    let resolveCompare: (value: PredictionObservationCompareResponse) => void = () => {};
    mockedCompare.mockReturnValue(
      new Promise<PredictionObservationCompareResponse>((resolve) => {
        resolveCompare = resolve;
      }),
    );
    renderPanel();
    expect(await screen.findByTestId('validation-loading')).toBeTruthy();
    resolveCompare(compareResponse());
    await waitFor(() => expect(screen.queryByTestId('validation-loading')).toBeNull());
  });

  it('uses the refresh label while review guidance is still fetching', async () => {
    let resolveReview: (value: ValidationReviewResponse) => void = () => {};
    mockedCompare.mockResolvedValue(compareResponse());
    mockedReview.mockReturnValue(
      new Promise<ValidationReviewResponse>((resolve) => {
        resolveReview = resolve;
      }),
    );
    renderPanel();
    await screen.findByTestId('validation-summary');
    const refresh = screen.getByTestId('validation-refresh-button');
    expect(refresh.textContent).toBe('Refreshing...');
    expect((refresh as HTMLButtonElement).disabled).toBe(true);
    resolveReview(reviewResponse());
    await waitFor(() => expect(refresh.textContent).toBe('Refresh validation'));
  });

  it('shows an error state with a Retry control when compare fails, and retries on click', async () => {
    mockedCompare.mockRejectedValueOnce(new Error('boom'));
    mockedCompare.mockRejectedValueOnce(new Error('boom'));
    mockedCompare.mockResolvedValue(compareResponse());
    renderPanel();
    expect(
      await screen.findByText(/Validation failed to load/, undefined, { timeout: 3000 }),
    ).toBeTruthy();
    fireEvent.click(screen.getByTestId('validation-retry-button'));
    expect(await screen.findByTestId('validation-summary')).toBeTruthy();
  });

  it('shows review error while comparison rows still render', async () => {
    mockedCompare.mockResolvedValue(compareResponse());
    mockedReview.mockRejectedValueOnce(new Error('review boom'));
    mockedReview.mockRejectedValueOnce(new Error('review boom'));
    renderPanel();
    expect(await screen.findByTestId('validation-review-error', undefined, { timeout: 3000 })).toBeTruthy();
    expect((await screen.findAllByTestId('validation-comparison-card')).length).toBe(4);
  });

  it('shows the stale preview warning when isPreviewResultStale is true', () => {
    mockedCompare.mockResolvedValue(compareResponse());
    renderPanel({ stale: true });
    expect(screen.getByTestId('validation-stale-warning')).toBeTruthy();
    expect(
      screen.getByText(/The Build Plan has changed since this preview was run/),
    ).toBeTruthy();
    // Stage 6D polish: the stale copy makes clear that the rendered
    // validation may still reflect the previous preview result.
    expect(
      screen.getByText(/this validation may reflect the previous preview result/),
    ).toBeTruthy();
  });

  it('does not render the stale preview warning when isPreviewResultStale is false', async () => {
    mockedCompare.mockResolvedValue(compareResponse());
    renderPanel({ stale: false });
    await waitFor(() => expect(screen.queryByTestId('validation-stale-warning')).toBeNull());
  });

  it('refreshes both compare and review queries when Refresh validation is clicked', async () => {
    mockedCompare.mockResolvedValue(compareResponse());
    mockedReview.mockResolvedValue(reviewResponse());
    renderPanel();
    // Wait for the success state, not just the queryFn invocation, so
    // the refresh button is no longer in its disabled "Refreshing..."
    // state when we click it.
    await screen.findByTestId('validation-summary');
    expect(mockedCompare).toHaveBeenCalledTimes(1);
    expect(mockedReview).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId('validation-refresh-button'));
    await waitFor(() => expect(mockedCompare).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(mockedReview).toHaveBeenCalledTimes(2));
  });

  it('refetches compare and review when a backend-read prediction field changes', async () => {
    mockedCompare.mockResolvedValue(compareResponse());
    mockedReview.mockResolvedValue(reviewResponse());
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const serviceEntry = {
      service: 'market',
      status: 'locked',
      target_port_id: 'port-a',
      target_port_name: 'Port A',
      unlock_type: 'economy',
      confidence: 'medium',
      reason: 'test',
      requirements: [],
      caveats: [],
    };
    const firstPreview = previewResult({
      services: {
        market: { status: 'locked', reason: 'top-level status unchanged', requirements: [] },
      },
      port_service_states: [
        {
          port_id: 'port-a',
          port_name: 'Port A',
          location_type: 'surface',
          effective_role: 'primary',
          active_services: {},
          locked_services: { market: serviceEntry },
          unknown_services: {},
          service_sources: [],
          warnings: [],
          recommendations: [],
        },
      ],
    });
    const secondPreview = previewResult({
      services: {
        market: { status: 'locked', reason: 'top-level status unchanged', requirements: [] },
      },
      port_service_states: [
        {
          port_id: 'port-a',
          port_name: 'Port A',
          location_type: 'surface',
          effective_role: 'primary',
          active_services: { market: { ...serviceEntry, status: 'active' } },
          locked_services: {},
          unknown_services: {},
          service_sources: [],
          warnings: [],
          recommendations: [],
        },
      ],
    });

    const { rerender } = render(
      <QueryClientProvider client={client}>
        <ValidationPanel
          systemId64={123}
          targetArchetype="trade_logistics"
          previewResult={firstPreview}
        />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(mockedCompare).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(mockedReview).toHaveBeenCalledTimes(1));

    rerender(
      <QueryClientProvider client={client}>
        <ValidationPanel
          systemId64={123}
          targetArchetype="trade_logistics"
          previewResult={secondPreview}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(mockedCompare).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(mockedReview).toHaveBeenCalledTimes(2));
  });

  it('does not call simulateBuild, fetchOptimiserCandidates, or observation mutation helpers during rendering', async () => {
    mockedCompare.mockResolvedValue(compareResponse());
    renderPanel();
    await screen.findByTestId('validation-summary');
    fireEvent.click(screen.getByTestId('validation-refresh-button'));
    await waitFor(() => expect(mockedCompare).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(mockedReview).toHaveBeenCalledTimes(2));
    expect(mockedSimulateBuild).not.toHaveBeenCalled();
    expect(mockedFetchOptimiser).not.toHaveBeenCalled();
    expect(mockedCreateObservedFact).not.toHaveBeenCalled();
    expect(mockedUpdateObservedFact).not.toHaveBeenCalled();
    expect(mockedDeleteObservedFact).not.toHaveBeenCalled();
  });

  it('renders the empty comparisons state when the backend returns zero comparison rows', async () => {
    mockedCompare.mockResolvedValue(
      compareResponse({
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
          summary: 'No observations recorded for this system yet.',
        },
        comparisons: [],
      }),
    );
    renderPanel();
    expect(await screen.findByTestId('validation-comparison-empty')).toBeTruthy();
    expect(screen.getByTestId('validation-summary-overall-status').textContent).toMatch(
      /No observations yet/,
    );
  });
});
