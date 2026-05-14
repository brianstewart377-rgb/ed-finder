import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchOptimiserCandidates } from '@/lib/api';
import type { OptimiserCandidate, OptimiserCandidatesResponse, OptimiserRanking, SimulateBuildPlacement } from '@/types/api';
import { OptimiserCandidateCard } from './OptimiserCandidateCard';
import { OptimiserCandidateDetails } from './OptimiserCandidateDetails';
import { OptimiserCandidatePanel } from './OptimiserCandidatePanel';
import { OptimiserPlacementList } from './OptimiserPlacementList';
import { OptimiserRankingBreakdown } from './OptimiserRankingBreakdown';
import { candidatePlacementsToPreviewPlacements, sortCandidatesForDisplay } from './optimiserUtils';

vi.mock('@/lib/api', () => ({
  fetchOptimiserCandidates: vi.fn(),
}));

const mockedFetchOptimiserCandidates = vi.mocked(fetchOptimiserCandidates);

function candidate(id: string, label = id): OptimiserCandidate {
  return {
    candidate_id: id,
    label,
    target_archetype: 'agriculture_terraforming',
    strategy: 'balanced',
    placements: [
      { facility_template_id: 'generic_port_alpha', local_body_id: 'body1', is_primary_port: true, build_order: 1 },
      { facility_template_id: 'agri_support_a', local_body_id: 'body1', is_primary_port: false, build_order: 2 },
    ],
    rationale: ['Good agricultural fit.'],
    warnings: [],
    assumptions: [],
    tags: ['balanced'],
    preview_summary: {
      final_score: 82.4,
      composition_score: 80,
      buildability_score: 78,
      confidence: 0.72,
      build_complexity: 'moderate',
      warnings_count: 1,
      cp_negative: false,
      top_two_alignment: 'strong',
    },
  };
}

const ranking: OptimiserRanking = {
  target_archetype: 'agriculture_terraforming',
  ranked_candidates: [
    {
      candidate_id: 'candidate-b',
      rank: 1,
      rank_score: 88.2,
      rank_tier: 'excellent',
      rank_breakdown: {
        preview_score_component: 28,
        composition_component: 16,
        buildability_component: 15,
        confidence_component: 11,
        alignment_component: 5,
        warning_penalty: -2,
        cp_penalty: 0,
        strategy_modifier: 4,
        total_score: 88.2,
        reasons: ['Strong top-two alignment.'],
      },
    },
    {
      candidate_id: 'candidate-a',
      rank: 2,
      rank_score: 70,
      rank_tier: 'strong',
      rank_breakdown: {
        preview_score_component: 20,
        composition_component: 14,
        buildability_component: 12,
        confidence_component: 9,
        alignment_component: 2,
        warning_penalty: 0,
        cp_penalty: 0,
        strategy_modifier: 3,
        total_score: 70,
        reasons: [],
      },
    },
  ],
  warnings: [],
  assumptions: [],
};

function response(overrides: Partial<OptimiserCandidatesResponse> = {}): OptimiserCandidatesResponse {
  return {
    system_id64: 123,
    target_archetype: 'agriculture_terraforming',
    candidate_count: 2,
    candidates: [candidate('candidate-a', 'Candidate A'), candidate('candidate-b', 'Candidate B')],
    warnings: [],
    assumptions: ['Stage 5C is read-only.'],
    ranking,
    ...overrides,
  };
}

describe('optimiser candidate comparison UI', () => {
  afterEach(() => {
    cleanup();
    mockedFetchOptimiserCandidates.mockReset();
  });

  it('candidatePlacementsToPreviewPlacements converts and resequences without mutating input', () => {
    const input = [
      { facility_template_id: 'support-second', local_body_id: undefined, is_primary_port: true, build_order: 20 },
      { facility_template_id: 'port-first', local_body_id: 'body1', is_primary_port: true, build_order: 10 },
      { facility_template_id: 'support-third', local_body_id: null, is_primary_port: false, build_order: 30 },
    ];
    const before = structuredClone(input);
    const output = candidatePlacementsToPreviewPlacements(input);

    expect(input).toEqual(before);
    expect(output).toEqual([
      { facility_template_id: 'port-first', local_body_id: 'body1', is_primary_port: true, build_order: 1 },
      { facility_template_id: 'support-second', local_body_id: null, is_primary_port: false, build_order: 2 },
      { facility_template_id: 'support-third', local_body_id: null, is_primary_port: false, build_order: 3 },
    ]);
    expect(output[0]).not.toBe(input[1]);
  });

  it('sorts ranked candidates without mutating the original array', () => {
    const original = [candidate('candidate-a'), candidate('candidate-b')];
    const before = original.map((item) => item.candidate_id);
    const sorted = sortCandidatesForDisplay(original, ranking);
    expect(sorted.map((item) => item.candidate_id)).toEqual(['candidate-b', 'candidate-a']);
    expect(original.map((item) => item.candidate_id)).toEqual(before);
    expect(sorted).not.toBe(original);
  });

  it('renders selected candidate comparison against current preview plan and supports hide/show', () => {
    const load = vi.fn();
    const currentPlacements: SimulateBuildPlacement[] = [
      { facility_template_id: 'generic_port_alpha', local_body_id: 'body1', is_primary_port: true, build_order: 1 },
      { facility_template_id: 'legacy_support', local_body_id: 'body2', is_primary_port: false, build_order: 2 },
    ];

    render(
      <OptimiserCandidateDetails
        candidate={candidate('candidate-b', 'Candidate B')}
        ranking={ranking.ranked_candidates[0]}
        response={response()}
        currentPreviewPlacements={currentPlacements}
        currentTargetArchetype="refinery_industrial"
        onLoadCandidate={load}
      />,
    );

    expect(screen.getByText('Compare with current preview')).toBeTruthy();
    expect(screen.getByText(/advisory and preview-only/i)).toBeTruthy();
    expect(screen.getAllByText('Prefer before').length).toBeGreaterThan(0);
    expect(screen.getByText('Tradeoff summary')).toBeTruthy();
    expect(screen.getByText('Target archetype')).toBeTruthy();
    expect(screen.getByText(/Changes from refinery_industrial to agriculture_terraforming/)).toBeTruthy();
    expect(screen.getByText('Facility count changes')).toBeTruthy();
    expect(screen.getByText(/agri_support_a: 0 → 1/)).toBeTruthy();
    expect(screen.getByText(/legacy_support: removed/)).toBeTruthy();
    expect(screen.getByText('Preview summary deltas')).toBeTruthy();
    expect(screen.getByText('Ranking delta')).toBeTruthy();
    expect(screen.getByText(/Ranking delta is unavailable for the current manual preview plan/)).toBeTruthy();
    expect(screen.getByText('Risk changes')).toBeTruthy();
    expect(screen.getByText('Warning changes')).toBeTruthy();
    expect(screen.getByText('Assumption changes')).toBeTruthy();
    expect(load).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Hide comparison' }));
    expect(screen.queryByText(/advisory and preview-only/i)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Show comparison' }));
    expect(screen.getByText(/advisory and preview-only/i)).toBeTruthy();
  });

  it('renders comparison empty copy when no current preview plan exists', () => {
    render(
      <OptimiserCandidateDetails
        candidate={candidate('candidate-a', 'Candidate A')}
        ranking={ranking.ranked_candidates[1]}
        response={response()}
        currentPreviewPlacements={[]}
        currentTargetArchetype="agriculture_terraforming"
      />,
    );

    expect(screen.getByText('Compare with current preview')).toBeTruthy();
    expect(screen.getByText(/Comparison needs a current preview plan/)).toBeTruthy();
  });

  it('updates comparison when current preview placements change and does not mutate inputs', () => {
    const selected = candidate('candidate-a', 'Candidate A');
    const firstPlacements: SimulateBuildPlacement[] = [
      { facility_template_id: 'legacy_support', local_body_id: 'body2', is_primary_port: false, build_order: 1 },
    ];
    const secondPlacements: SimulateBuildPlacement[] = [
      { facility_template_id: 'generic_port_alpha', local_body_id: 'body1', is_primary_port: true, build_order: 1 },
      { facility_template_id: 'agri_support_a', local_body_id: 'body1', is_primary_port: false, build_order: 2 },
    ];
    const candidateBefore = structuredClone(selected.placements);
    const firstBefore = structuredClone(firstPlacements);
    const { rerender } = render(
      <OptimiserCandidateDetails
        candidate={selected}
        ranking={ranking.ranked_candidates[1]}
        response={response()}
        currentPreviewPlacements={firstPlacements}
        currentTargetArchetype="refinery_industrial"
      />,
    );

    expect(screen.getByText(/legacy_support: removed/)).toBeTruthy();
    rerender(
      <OptimiserCandidateDetails
        candidate={selected}
        ranking={ranking.ranked_candidates[1]}
        response={response()}
        currentPreviewPlacements={secondPlacements}
        currentTargetArchetype="agriculture_terraforming"
      />,
    );

    expect(screen.queryByText(/legacy_support: removed/)).toBeNull();
    expect(screen.getByText('No facility count changes.')).toBeTruthy();
    expect(selected.placements).toEqual(candidateBefore);
    expect(firstPlacements).toEqual(firstBefore);
  });

  it('does not use unsafe wording in optimiser comparison UI', () => {
    const load = vi.fn();
    const { container } = render(
      <OptimiserCandidateDetails
        candidate={candidate('candidate-b', 'Candidate B')}
        ranking={ranking.ranked_candidates[0]}
        response={response()}
        currentPreviewPlacements={[
          { facility_template_id: 'generic_port_alpha', local_body_id: 'body1', is_primary_port: true, build_order: 1 },
        ]}
        currentTargetArchetype="agriculture_terraforming"
        onLoadCandidate={load}
      />,
    );

    expect(screen.getByRole('button', { name: 'Load into preview' })).toBeTruthy();
    expect(container.textContent).not.toMatch(/\bApply\b/i);
    expect(container.textContent).not.toMatch(/\bCommit\b/i);
    expect(container.textContent).not.toMatch(/\bSave build\b/i);
    expect(container.textContent).not.toMatch(/\bOptimal\b/i);
    expect(container.textContent).not.toMatch(/\bBest build\b/i);
    expect(container.textContent).not.toMatch(/\bGuaranteed\b/i);
    expect(container.textContent).not.toMatch(/\bProven\b/i);
    expect(load).not.toHaveBeenCalled();
  });

  it('renders ranking breakdown with alignment_component separately', () => {
    render(<OptimiserRankingBreakdown breakdown={ranking.ranked_candidates[0].rank_breakdown} />);
    expect(screen.getByText('Top-two alignment')).toBeTruthy();
    expect(screen.getByText('+5')).toBeTruthy();
    expect(screen.getByText('Warning penalty')).toBeTruthy();
  });

  it('renders candidate card rank, tier, score, strategy, warnings, and no apply button', () => {
    render(
      <OptimiserCandidateCard
        candidate={candidate('candidate-b', 'Candidate B')}
        ranking={ranking.ranked_candidates[0]}
        selected={false}
        onSelect={() => undefined}
      />,
    );
    expect(screen.getByText('#1')).toBeTruthy();
    expect(screen.getByText('excellent')).toBeTruthy();
    expect(screen.getByText('88.2')).toBeTruthy();
    expect(screen.getByText('balanced')).toBeTruthy();
    expect(screen.getByText('1 warning(s)')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /apply/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /use this build/i })).toBeNull();
  });

  it('renders a candidate without preview_summary gracefully', () => {
    const noPreview = { ...candidate('no-preview'), preview_summary: null };
    render(<OptimiserCandidateCard candidate={noPreview} selected={false} onSelect={() => undefined} />);
    expect(screen.getByText('No preview summary')).toBeTruthy();
  });

  it('does not render Load into preview when no load callback is provided', () => {
    render(<OptimiserCandidateDetails candidate={candidate('candidate-a', 'Candidate A')} />);
    expect(screen.queryByRole('button', { name: 'Load into preview' })).toBeNull();
  });

  it('renders Load into preview with callback and loads immediately when no preview plan exists', () => {
    const onLoadCandidate = vi.fn();
    const selected = candidate('candidate-a', 'Candidate A');
    render(<OptimiserCandidateDetails candidate={selected} onLoadCandidate={onLoadCandidate} />);

    expect(screen.getByText(/Nothing affects in-game state/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Load into preview' }));

    expect(onLoadCandidate).toHaveBeenCalledTimes(1);
    expect(onLoadCandidate).toHaveBeenCalledWith(selected);
  });

  it('requires confirmation before replacing an existing preview plan', () => {
    const onLoadCandidate = vi.fn();
    const selected = candidate('candidate-a', 'Candidate A');
    render(
      <OptimiserCandidateDetails
        candidate={selected}
        hasExistingPreviewPlan
        onLoadCandidate={onLoadCandidate}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Load into preview' }));
    expect(screen.getByText('Replace current preview plan with this optimiser candidate?')).toBeTruthy();
    expect(onLoadCandidate).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByText('Replace current preview plan with this optimiser candidate?')).toBeNull();
    expect(onLoadCandidate).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Load into preview' }));
    fireEvent.click(screen.getByRole('button', { name: 'Replace preview plan' }));
    expect(onLoadCandidate).toHaveBeenCalledTimes(1);
    expect(onLoadCandidate).toHaveBeenCalledWith(selected);
  });

  it('shows ranking reasons separately from warnings', () => {
    const warnedCandidate = {
      ...candidate('candidate-warning', 'Candidate Warning'),
      warnings: ['Candidate warning'],
      preview_summary: {
        ...candidate('candidate-warning').preview_summary!,
        warnings_count: 0,
      },
    };
    const ranked = {
      ...ranking.ranked_candidates[0],
      candidate_id: warnedCandidate.candidate_id,
      rank_breakdown: {
        ...ranking.ranked_candidates[0].rank_breakdown,
        reasons: ['Preview confidence is low.'],
      },
    };

    render(<OptimiserCandidateDetails candidate={warnedCandidate} ranking={ranked} />);

    expect(screen.getByText('Warnings')).toBeTruthy();
    expect(screen.getByText('• Candidate warning')).toBeTruthy();
    expect(screen.getByText('Ranking reasons')).toBeTruthy();
    expect(screen.getAllByText('• Preview confidence is low.').length).toBeGreaterThan(0);
    expect(screen.getByText('No additional assumptions were returned.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /apply/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /use this build/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /load candidate/i })).toBeNull();
  });

  it('renders placement build order and primary port', () => {
    render(<OptimiserPlacementList placements={candidate('candidate-a').placements} />);
    expect(screen.getByText('#1')).toBeTruthy();
    expect(screen.getByText('Primary port')).toBeTruthy();
    expect(screen.getByText('generic_port_alpha')).toBeTruthy();
    expect(screen.getAllByText('Body: body1').length).toBeGreaterThan(0);
  });

  it('renders initial read-only panel state with no apply button', () => {
    render(<OptimiserCandidatePanel systemId64={123} targetArchetype="agriculture_terraforming" />);
    expect(screen.getByText('Optimiser candidates')).toBeTruthy();
    expect(screen.getByText(/Read-only for now/i)).toBeTruthy();
    expect(screen.getByText('Generate candidates')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /load into preview/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /apply/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /use this build/i })).toBeNull();
  });

  it('renders load-enabled panel copy when a load callback is provided', () => {
    render(
      <OptimiserCandidatePanel
        systemId64={123}
        targetArchetype="agriculture_terraforming"
        onLoadCandidate={() => undefined}
      />,
    );
    expect(screen.getByText(/load a selected candidate into the editable preview/i)).toBeTruthy();
    expect(screen.getByText(/Nothing affects in-game state/i)).toBeTruthy();
    expect(screen.queryByText(/Read-only for now/i)).toBeNull();
  });

  it('clicking Generate candidates calls API with ranking and preview enabled', async () => {
    mockedFetchOptimiserCandidates.mockResolvedValue(response());
    render(<OptimiserCandidatePanel systemId64={123} targetArchetype="agriculture_terraforming" />);
    fireEvent.click(screen.getByText('Generate candidates'));
    await waitFor(() => expect(mockedFetchOptimiserCandidates).toHaveBeenCalledTimes(1));
    expect(mockedFetchOptimiserCandidates).toHaveBeenCalledWith(expect.objectContaining({
      system_id64: 123,
      target_archetype: 'agriculture_terraforming',
      run_preview: true,
      include_ranking: true,
    }));
  });

  it('renders loading state while candidates are being fetched', () => {
    mockedFetchOptimiserCandidates.mockReturnValue(new Promise(() => {}));
    render(<OptimiserCandidatePanel systemId64={123} targetArchetype="agriculture_terraforming" />);
    fireEvent.click(screen.getByText('Generate candidates'));
    expect(screen.getByText('Generating ranked optimiser candidates...')).toBeTruthy();
  });

  it('renders error state with retry', async () => {
    mockedFetchOptimiserCandidates.mockRejectedValue(new Error('backend down'));
    render(<OptimiserCandidatePanel systemId64={123} targetArchetype="agriculture_terraforming" />);
    fireEvent.click(screen.getByText('Generate candidates'));
    expect(await screen.findByText(/backend down/)).toBeTruthy();
    expect(screen.getByText('retry')).toBeTruthy();
  });

  it('renders empty state with backend warning and assumption', async () => {
    mockedFetchOptimiserCandidates.mockResolvedValue(response({
      candidate_count: 0,
      candidates: [],
      warnings: ['No candidate anchors found.'],
      assumptions: ['Generated no plans.'],
      ranking: null,
    }));
    render(<OptimiserCandidatePanel systemId64={123} targetArchetype="agriculture_terraforming" />);
    fireEvent.click(screen.getByText('Generate candidates'));
    expect(await screen.findByText('No optimiser candidates generated yet.')).toBeTruthy();
    expect(screen.getByText('Warning: No candidate anchors found.')).toBeTruthy();
    expect(screen.getByText('Assumption: Generated no plans.')).toBeTruthy();
  });

  it('displays ranked candidates in ranking order and details for the selected candidate', async () => {
    mockedFetchOptimiserCandidates.mockResolvedValue(response());
    render(<OptimiserCandidatePanel systemId64={123} targetArchetype="agriculture_terraforming" />);
    fireEvent.click(screen.getByText('Generate candidates'));
    await screen.findAllByText('Candidate B');
    const cards = screen.getAllByRole('button');
    const cardB = cards.find((item) => item.textContent?.includes('Candidate B'));
    const cardA = cards.find((item) => item.textContent?.includes('Candidate A'));
    expect(cardB).toBeTruthy();
    expect(cardA).toBeTruthy();
    expect(cardB!.compareDocumentPosition(cardA!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText('Ranking breakdown')).toBeTruthy();
    expect(screen.getByText('Top-two alignment')).toBeTruthy();
  });

  it('renders candidates without ranking gracefully', async () => {
    mockedFetchOptimiserCandidates.mockResolvedValue(response({ ranking: null }));
    render(<OptimiserCandidatePanel systemId64={123} targetArchetype="agriculture_terraforming" />);
    fireEvent.click(screen.getByText('Generate candidates'));
    expect((await screen.findAllByText('Candidate A')).length).toBeGreaterThan(0);
    expect(screen.getByText('No ranking breakdown is available for this candidate.')).toBeTruthy();
  });
});
