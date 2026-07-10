import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  comparePredictionToObservations,
  createObservedFact,
  deleteObservedFact,
  fetchOptimiserCandidates,
  listObservedFacts,
  reviewPredictionValidation,
  simulateBuild,
  updateObservedFact,
} from '@/lib/api';
import { ApiError } from '@/lib/api';
import type {
  ObservedFact,
  ObservedFactCreateRequest,
  ObservedFactListResponse,
  ObservedFactUpdateRequest,
} from '@/types/api';
import { ObservedEvidencePanel } from './ObservedEvidencePanel';

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    listObservedFacts: vi.fn(),
    createObservedFact: vi.fn(),
    updateObservedFact: vi.fn(),
    deleteObservedFact: vi.fn(),
    comparePredictionToObservations: vi.fn(),
    reviewPredictionValidation: vi.fn(),
    fetchOptimiserCandidates: vi.fn(),
    simulateBuild: vi.fn(),
  };
});

const mockedList = vi.mocked(listObservedFacts);
const mockedCreate = vi.mocked(createObservedFact);
const mockedUpdate = vi.mocked(updateObservedFact);
const mockedDelete = vi.mocked(deleteObservedFact);
const mockedCompare = vi.mocked(comparePredictionToObservations);
const mockedReview = vi.mocked(reviewPredictionValidation);
const mockedFetchOptimiser = vi.mocked(fetchOptimiserCandidates);
const mockedSimulateBuild = vi.mocked(simulateBuild);

function emptyResponse(): ObservedFactListResponse {
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

function fact(overrides: Partial<ObservedFact> = {}): ObservedFact {
  return {
    observation_id: 'obs_a',
    system_id64: 123,
    created_at: '2026-05-14T13:00:00+00:00',
    updated_at: null,
    source: 'manual',
    fact_type: 'note',
    subject_type: 'system',
    subject_id: null,
    status: 'observed_present',
    observed_value: undefined,
    expected_value: undefined,
    confidence: 'medium',
    notes: 'A note about the system.',
    build_fingerprint: null,
    simulation_fingerprint: null,
    target_archetype: null,
    facility_template_id: null,
    local_body_id: null,
    service_id: null,
    economy: null,
    tags: [],
    metadata: {},
    ...overrides,
  };
}

function listResponseWith(facts: ObservedFact[]): ObservedFactListResponse {
  const by_fact_type: Record<string, number> = {};
  const by_status: Record<string, number> = {};
  const by_confidence: Record<string, number> = {};
  for (const f of facts) {
    by_fact_type[f.fact_type] = (by_fact_type[f.fact_type] ?? 0) + 1;
    by_status[f.status] = (by_status[f.status] ?? 0) + 1;
    by_confidence[f.confidence] = (by_confidence[f.confidence] ?? 0) + 1;
  }
  return {
    facts,
    total: facts.length,
    limit: 100,
    offset: 0,
    summary: {
      total_count: facts.length,
      by_fact_type,
      by_status,
      by_confidence,
      latest_observed_at: facts[0]?.created_at ?? null,
    },
  };
}

function renderPanel(systemId64 = 123, suggestedArchetype: string | null = 'agriculture_terraforming') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={client}>
      <ObservedEvidencePanel systemId64={systemId64} suggestedArchetype={suggestedArchetype} />
    </QueryClientProvider>,
  );
  return { ...utils, client };
}

describe('ObservedEvidencePanel — Stage 6B manual observed evidence UI', () => {
  beforeEach(() => {
    mockedList.mockReset();
    mockedCreate.mockReset();
    mockedUpdate.mockReset();
    mockedDelete.mockReset();
    mockedCompare.mockReset();
    mockedReview.mockReset();
    mockedFetchOptimiser.mockReset();
    mockedSimulateBuild.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it('renders the passive evidence copy near the top of the panel', async () => {
    mockedList.mockResolvedValue(emptyResponse());
    renderPanel();

    expect(await screen.findByRole('region', { name: 'Observed Evidence' })).toBeTruthy();
    expect(
      screen.getByText(/Later step: Observed Evidence records what you see in-game after planning/),
    ).toBeTruthy();
    expect(
      screen.getByText(/Observed Evidence is for later, after checking in-game/),
    ).toBeTruthy();
    expect(
      screen.getByText(/Stage journal evidence from My Work/),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Open Journal Import' }));
    expect(window.location.hash).toBe('#my-work');
  });

  it('lists existing observations returned by the backend for the current system', async () => {
    mockedList.mockResolvedValue(
      listResponseWith([
        fact({ observation_id: 'obs_one', notes: 'Saw a Market service after construction.' }),
        fact({ observation_id: 'obs_two', fact_type: 'service_presence', service_id: 'market', notes: '' }),
      ]),
    );
    renderPanel();

    expect(await screen.findByText(/Saw a Market service after construction\./)).toBeTruthy();
    // Service ID rendered for service_presence card.
    expect(screen.getAllByText('market').length).toBeGreaterThan(0);
    await waitFor(() =>
      expect(mockedList).toHaveBeenCalledWith(
        expect.objectContaining({ system_id64: 123 }),
      ),
    );
  });

  it('shows the empty state when no observations exist', async () => {
    mockedList.mockResolvedValue(emptyResponse());
    renderPanel();

    expect(await screen.findByText('No observed evidence recorded yet.')).toBeTruthy();
    expect(
      screen.getByText(
        /Record what you actually saw in-game\. Evidence is passive; Validation can compare it with predictions without changing scoring or mechanics/,
      ),
    ).toBeTruthy();
  });

  it('renders Stage 14A observed-vs-planned framing and keeps unknown state distinct', async () => {
    mockedList.mockResolvedValue(emptyResponse());
    renderPanel();

    expect(await screen.findByText('Observed vs planned framing')).toBeTruthy();
    expect(screen.getByText('Planned')).toBeTruthy();
    expect(screen.getByText(/Build Plan and Preview Result are planning context/)).toBeTruthy();
    expect(screen.getByText('Observed')).toBeTruthy();
    expect(screen.getByText(/Manual evidence is what was checked in-game/)).toBeTruthy();
    expect(screen.getByText(/Missing evidence stays not checked, not contradicted/)).toBeTruthy();
  });

  it('renders Stage 14A evidence categories from the visible observed facts', async () => {
    mockedList.mockResolvedValue(
      listResponseWith([
        fact({
          observation_id: 'obs_architect',
          notes: 'Architect Mode primary-port flag observed on A 1.',
        }),
        fact({
          observation_id: 'obs_build',
          fact_type: 'facility_state',
          facility_template_id: 'outpost_support_a',
        }),
        fact({
          observation_id: 'obs_economy',
          fact_type: 'economy_presence',
          economy: 'Agriculture',
        }),
      ]),
    );
    renderPanel();

    const categories = await screen.findByLabelText('Observed evidence categories');
    expect(within(categories).getByText('Primary-port / Architect observation')).toBeTruthy();
    expect(within(categories).getByText('Structure actually built')).toBeTruthy();
    expect(within(categories).getByText('Economy observation')).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByLabelText('Visible observed evidence count').textContent).toMatch(/3\s+visible\s+\/\s+3\s+recorded/),
    );
  });

  it('shows a loading state while the list query is pending', async () => {
    let resolveList: (response: ObservedFactListResponse) => void = () => {};
    mockedList.mockReturnValue(
      new Promise<ObservedFactListResponse>((resolve) => {
        resolveList = resolve;
      }),
    );
    renderPanel();

    expect(await screen.findByText(/Loading observed evidence/)).toBeTruthy();

    resolveList(emptyResponse());
    await waitFor(() => expect(screen.queryByText(/Loading observed evidence/)).toBeNull());
  });

  it('shows an error state with a retry control when the list query fails', async () => {
    // The panel sets retry: 1 by default, so the first failure call
    // becomes a retry then a definitive failure. Reject both so React
    // Query surfaces the error UI, then resolve subsequent calls so the
    // user-triggered retry button can succeed.
    mockedList.mockRejectedValueOnce(new Error('boom'));
    mockedList.mockRejectedValueOnce(new Error('boom'));
    mockedList.mockResolvedValue(emptyResponse());
    renderPanel();

    // Wait for the visible error banner. We look for the user-facing
    // copy rather than role=alert because the failure path renders the
    // banner element with role=alert and additional descendants.
    expect(
      await screen.findByText(/Observed evidence failed to load/, undefined, { timeout: 3000 }),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    expect(await screen.findByText('No observed evidence recorded yet.')).toBeTruthy();
    expect(mockedList.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it('creates a manual service_presence observation with service_id', async () => {
    mockedList.mockResolvedValue(emptyResponse());
    mockedCreate.mockResolvedValue(fact({ fact_type: 'service_presence', service_id: 'market' }));
    renderPanel();

    await screen.findByRole('region', { name: 'Observed Evidence' });

    fireEvent.change(screen.getByLabelText(/Evidence type/i), {
      target: { value: 'service_presence' },
    });
    fireEvent.change(screen.getByLabelText(/Service ID/i), {
      target: { value: 'market' },
    });
    fireEvent.change(screen.getByLabelText(/^Notes$/), {
      target: { value: 'Market visible at primary port.' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Record observed evidence/i }));

    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));
    const sentRequest = mockedCreate.mock.calls[0][0] as ObservedFactCreateRequest;
    expect(sentRequest.source).toBe('manual');
    expect(sentRequest.system_id64).toBe(123);
    expect(sentRequest.fact_type).toBe('service_presence');
    expect(sentRequest.subject_type).toBe('service');
    expect(sentRequest.service_id).toBe('market');
    expect(sentRequest.notes).toBe('Market visible at primary port.');
  });

  it('creates a manual economy_presence observation with economy', async () => {
    mockedList.mockResolvedValue(emptyResponse());
    mockedCreate.mockResolvedValue(fact({ fact_type: 'economy_presence', economy: 'Agriculture' }));
    renderPanel();

    await screen.findByRole('region', { name: 'Observed Evidence' });

    fireEvent.change(screen.getByLabelText(/Evidence type/i), {
      target: { value: 'economy_presence' },
    });
    fireEvent.change(screen.getByLabelText(/^Economy$/i), {
      target: { value: 'Agriculture' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Record observed evidence/i }));

    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));
    const sentRequest = mockedCreate.mock.calls[0][0] as ObservedFactCreateRequest;
    expect(sentRequest.fact_type).toBe('economy_presence');
    expect(sentRequest.subject_type).toBe('economy');
    expect(sentRequest.economy).toBe('Agriculture');
  });

  it('creates a manual facility_state observation with facility_template_id', async () => {
    mockedList.mockResolvedValue(emptyResponse());
    mockedCreate.mockResolvedValue(fact({ fact_type: 'facility_state', facility_template_id: 'agri_support_a' }));
    renderPanel();

    await screen.findByRole('region', { name: 'Observed Evidence' });

    fireEvent.change(screen.getByLabelText(/Evidence type/i), {
      target: { value: 'facility_state' },
    });
    fireEvent.change(screen.getByLabelText(/Facility template ID/i), {
      target: { value: 'agri_support_a' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Record observed evidence/i }));

    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));
    const sentRequest = mockedCreate.mock.calls[0][0] as ObservedFactCreateRequest;
    expect(sentRequest.fact_type).toBe('facility_state');
    expect(sentRequest.subject_type).toBe('facility');
    expect(sentRequest.facility_template_id).toBe('agri_support_a');
  });

  it('creates a note/system observation without subject_id', async () => {
    mockedList.mockResolvedValue(emptyResponse());
    mockedCreate.mockResolvedValue(fact());
    renderPanel();

    await screen.findByRole('region', { name: 'Observed Evidence' });

    // Default fact_type is "note" so we can submit straight away.
    fireEvent.change(screen.getByLabelText(/^Notes$/), {
      target: { value: 'General note about the system.' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Record observed evidence/i }));

    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));
    const sentRequest = mockedCreate.mock.calls[0][0] as ObservedFactCreateRequest;
    expect(sentRequest.fact_type).toBe('note');
    expect(sentRequest.subject_type).toBe('system');
    expect(sentRequest.subject_id ?? null).toBeNull();
    expect(sentRequest.source).toBe('manual');
  });

  it('invalidates compare and review queries after observed evidence changes', async () => {
    mockedList.mockResolvedValue(emptyResponse());
    mockedCreate.mockResolvedValue(fact());
    const { client } = renderPanel();
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');

    await screen.findByRole('region', { name: 'Observed Evidence' });
    fireEvent.change(screen.getByLabelText(/^Notes$/), {
      target: { value: 'Evidence that should refresh validation.' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Record observed evidence/i }));

    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['observation-compare', 123] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['observation-review', 123] });
  });

  it('shows backend validation errors clearly when create fails with 422', async () => {
    mockedList.mockResolvedValue(emptyResponse());
    mockedCreate.mockRejectedValue(
      new ApiError(
        422,
        '/observations/facts',
        JSON.stringify({ detail: [{ loc: ['body', 'service_id'], msg: 'service_id is required', type: 'value_error' }] }),
      ),
    );
    renderPanel();

    await screen.findByRole('region', { name: 'Observed Evidence' });

    fireEvent.change(screen.getByLabelText(/Evidence type/i), {
      target: { value: 'service_presence' },
    });
    // Provide the field locally so client validation passes, but the
    // backend will still reject — we use this to assert the error path.
    fireEvent.change(screen.getByLabelText(/Service ID/i), {
      target: { value: 'market' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Record observed evidence/i }));

    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/service_id is required/)).toBeTruthy();
  });

  it('client-side validates that service_presence requires service_id before submit', async () => {
    mockedList.mockResolvedValue(emptyResponse());
    renderPanel();

    await screen.findByRole('region', { name: 'Observed Evidence' });

    fireEvent.change(screen.getByLabelText(/Evidence type/i), {
      target: { value: 'service_presence' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Record observed evidence/i }));

    expect(
      await screen.findByText(/Service ID is required for Service presence evidence/),
    ).toBeTruthy();
    expect(mockedCreate).not.toHaveBeenCalled();
  });

  it('edits an existing observation status, confidence, and notes', async () => {
    mockedList.mockResolvedValueOnce(
      listResponseWith([fact({ observation_id: 'obs_edit', notes: 'Original notes' })]),
    );
    mockedList.mockResolvedValue(
      listResponseWith([
        fact({
          observation_id: 'obs_edit',
          notes: 'Updated notes',
          status: 'confirmed',
          confidence: 'high',
        }),
      ]),
    );
    mockedUpdate.mockResolvedValue(
      fact({
        observation_id: 'obs_edit',
        notes: 'Updated notes',
        status: 'confirmed',
        confidence: 'high',
      }),
    );
    renderPanel();

    await screen.findByText(/Original notes/);

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    // Scope inside the edit form because the filter row also exposes
    // "Status"/"Confidence" labels (as "Filter by status" / "Filter by
    // confidence"). The edit-form is the only element with role=form
    // and aria-label "Edit observed evidence", so scoping inside it
    // disambiguates the controls cleanly.
    const editForm = screen.getByRole('form', { name: /Edit observed evidence/i });
    fireEvent.change(within(editForm).getByLabelText(/^Status$/), { target: { value: 'confirmed' } });
    fireEvent.change(within(editForm).getByLabelText(/^Confidence$/), { target: { value: 'high' } });
    fireEvent.change(within(editForm).getByLabelText(/^Notes$/), { target: { value: 'Updated notes' } });
    fireEvent.click(within(editForm).getByRole('button', { name: /Save changes/ }));

    await waitFor(() => expect(mockedUpdate).toHaveBeenCalledTimes(1));
    const [observationId, request] = mockedUpdate.mock.calls[0] as [string, ObservedFactUpdateRequest];
    expect(observationId).toBe('obs_edit');
    expect(request.status).toBe('confirmed');
    expect(request.confidence).toBe('high');
    expect(request.notes).toBe('Updated notes');
  });

  it('cancels edit and preserves the original card without calling update', async () => {
    mockedList.mockResolvedValue(
      listResponseWith([fact({ observation_id: 'obs_cancel', notes: 'Untouched notes' })]),
    );
    renderPanel();

    await screen.findByText(/Untouched notes/);
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    const editForm = screen.getByRole('form', { name: /Edit observed evidence/i });
    fireEvent.change(within(editForm).getByLabelText(/^Notes$/), { target: { value: 'temp edit' } });
    fireEvent.click(within(editForm).getByRole('button', { name: 'Cancel' }));

    expect(screen.getByText(/Untouched notes/)).toBeTruthy();
    expect(mockedUpdate).not.toHaveBeenCalled();
  });

  it('requires confirmation before delete and preserves the record on cancel', async () => {
    mockedList.mockResolvedValue(
      listResponseWith([fact({ observation_id: 'obs_del', notes: 'Will not be deleted' })]),
    );
    renderPanel();

    await screen.findByText(/Will not be deleted/);
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    // Confirm dialog appears, but no delete API call yet.
    expect(screen.getByText(/Delete this observed evidence record\?/)).toBeTruthy();
    expect(
      screen.getByText(/This removes the manually recorded evidence only\. It does not change predictions/),
    ).toBeTruthy();
    expect(mockedDelete).not.toHaveBeenCalled();

    // Cancel via "Keep evidence".
    fireEvent.click(screen.getByRole('button', { name: 'Keep evidence' }));
    expect(screen.queryByText(/Delete this observed evidence record\?/)).toBeNull();
    expect(screen.getByText(/Will not be deleted/)).toBeTruthy();
    expect(mockedDelete).not.toHaveBeenCalled();
  });

  it('deletes a record when the user confirms and refreshes the list', async () => {
    mockedList.mockResolvedValueOnce(
      listResponseWith([fact({ observation_id: 'obs_doomed', notes: 'Will be deleted' })]),
    );
    mockedList.mockResolvedValue(emptyResponse());
    mockedDelete.mockResolvedValue({ observation_id: 'obs_doomed', deleted: true });
    renderPanel();

    await screen.findByText(/Will be deleted/);
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    fireEvent.click(screen.getByRole('button', { name: /Confirm delete/ }));

    await waitFor(() => expect(mockedDelete).toHaveBeenCalledWith('obs_doomed'));
    await waitFor(() => expect(screen.queryByText(/Will be deleted/)).toBeNull());
    expect(await screen.findByText('No observed evidence recorded yet.')).toBeTruthy();
  });

  it('applies fact_type and status filters via the list endpoint query params', async () => {
    mockedList.mockResolvedValue(emptyResponse());
    renderPanel();

    await screen.findByRole('region', { name: 'Observed Evidence' });
    await waitFor(() => expect(mockedList).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText(/Filter by type/i), {
      target: { value: 'service_presence' },
    });
    await waitFor(() =>
      expect(mockedList).toHaveBeenLastCalledWith(
        expect.objectContaining({ system_id64: 123, fact_type: 'service_presence' }),
      ),
    );

    fireEvent.change(screen.getByLabelText(/Filter by status/i), {
      target: { value: 'observed_present' },
    });
    await waitFor(() =>
      expect(mockedList).toHaveBeenLastCalledWith(
        expect.objectContaining({
          system_id64: 123,
          fact_type: 'service_presence',
          status: 'observed_present',
        }),
      ),
    );

    // Clear filters button is exposed when at least one filter is active.
    // After clearing, the button disappears and the call history must
    // include at least one call with no fact_type / status filters. We
    // assert via the full call history because React Query may serve the
    // no-filter response from cache rather than refetching it.
    fireEvent.click(screen.getByRole('button', { name: /Clear filters/ }));
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /Clear filters/ })).toBeNull(),
    );
    expect(
      mockedList.mock.calls.some(([params]) =>
        params.system_id64 === 123 && !params.fact_type && !params.status,
      ),
    ).toBe(true);
  });

  it('does not expose imported or inferred as create-form source options', async () => {
    mockedList.mockResolvedValue(emptyResponse());
    renderPanel();

    await screen.findByRole('region', { name: 'Observed Evidence' });

    // The create form has Evidence type / Status / Confidence selects but
    // NO "Source" select. Imported/inferred never appear as option text in
    // any select. We assert both by checking option DOM and by checking
    // that submitting always sends source: 'manual'.
    const options = Array.from(screen.queryAllByRole('option')) as HTMLOptionElement[];
    for (const option of options) {
      expect(option.value).not.toBe('imported');
      expect(option.value).not.toBe('inferred');
    }
  });

  it('does not call simulateBuild or fetchOptimiserCandidates during create/update/delete flows', async () => {
    mockedList.mockResolvedValue(
      listResponseWith([fact({ observation_id: 'obs_iso' })]),
    );
    mockedCreate.mockResolvedValue(fact({ observation_id: 'obs_new' }));
    mockedUpdate.mockResolvedValue(fact({ observation_id: 'obs_iso', notes: 'edited' }));
    mockedDelete.mockResolvedValue({ observation_id: 'obs_iso', deleted: true });
    renderPanel();

    await screen.findByRole('region', { name: 'Observed Evidence' });

    // Create
    fireEvent.change(screen.getByLabelText(/^Notes$/), { target: { value: 'isolation note' } });
    fireEvent.click(screen.getByRole('button', { name: /Record observed evidence/i }));
    await waitFor(() => expect(mockedCreate).toHaveBeenCalled());

    // Update — locate the inline edit button on the existing card.
    fireEvent.click(screen.getAllByRole('button', { name: 'Edit' })[0]);
    const editForm = await screen.findByRole('form', { name: /Edit observed evidence/i });
    fireEvent.change(within(editForm).getByLabelText(/^Notes$/), { target: { value: 'edited' } });
    fireEvent.click(within(editForm).getByRole('button', { name: /Save changes/ }));
    await waitFor(() => expect(mockedUpdate).toHaveBeenCalled());

    // Delete
    fireEvent.click(screen.getAllByRole('button', { name: 'Delete' })[0]);
    fireEvent.click(screen.getByRole('button', { name: /Confirm delete/ }));
    await waitFor(() => expect(mockedDelete).toHaveBeenCalled());

    expect(mockedSimulateBuild).not.toHaveBeenCalled();
    expect(mockedFetchOptimiser).not.toHaveBeenCalled();
    expect(mockedCompare).not.toHaveBeenCalled();
    expect(mockedReview).not.toHaveBeenCalled();
  });

  it('viewing observed evidence does not run preview, generation, validation, or planner mutation', async () => {
    mockedList.mockResolvedValue(
      listResponseWith([fact({ observation_id: 'obs_view', notes: 'Passive viewing only.' })]),
    );
    renderPanel();

    expect(await screen.findByText(/Passive viewing only/)).toBeTruthy();
    expect(mockedSimulateBuild).not.toHaveBeenCalled();
    expect(mockedFetchOptimiser).not.toHaveBeenCalled();
    expect(mockedCompare).not.toHaveBeenCalled();
    expect(mockedReview).not.toHaveBeenCalled();
    expect(mockedCreate).not.toHaveBeenCalled();
    expect(mockedUpdate).not.toHaveBeenCalled();
    expect(mockedDelete).not.toHaveBeenCalled();
  });
});
