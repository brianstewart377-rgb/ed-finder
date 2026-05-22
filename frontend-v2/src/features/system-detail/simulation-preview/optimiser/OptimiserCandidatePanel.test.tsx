import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchOptimiserCandidates } from '@/lib/api';
import type { FacilityTemplate, OptimiserCandidate, OptimiserCandidatesResponse, OptimiserRanking, SimulateBuildPlacement } from '@/types/api';
import { OptimiserCandidateCard } from './OptimiserCandidateCard';
import { OptimiserCandidateDetails } from './OptimiserCandidateDetails';
import { OptimiserCandidatePanel } from './OptimiserCandidatePanel';
import { OptimiserPlacementList } from './OptimiserPlacementList';
import { OptimiserRankingBreakdown } from './OptimiserRankingBreakdown';
import { candidatePlacementsToPreviewPlacements, sortCandidatesForDisplay } from './optimiserUtils';
import { filterUsefulSuggestedBuilds, suggestedBuildPresentation, suggestedBuildScale } from './optimiserQualityUtils';

vi.mock('@/lib/api', () => ({
  fetchOptimiserCandidates: vi.fn(),
}));

const mockedFetchOptimiserCandidates = vi.mocked(fetchOptimiserCandidates);

const templates: FacilityTemplate[] = [
  {
    id: 'generic_port_alpha',
    name: 'Generic Port Alpha',
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
    id: 'agri_support_a',
    name: 'Agriculture Support A',
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
    candidates: [
      {
        ...candidate('candidate-a', 'Candidate A'),
        placements: [
          { facility_template_id: 'generic_port_alpha', local_body_id: 'body1', is_primary_port: true, build_order: 1 },
          { facility_template_id: 'agri_support_b', local_body_id: 'body2', is_primary_port: false, build_order: 2 },
        ],
      },
      candidate('candidate-b', 'Candidate B'),
    ],
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

  it('filters trivial and duplicate suggested builds without mutating optimiser results', () => {
    const useful = candidate('useful', 'Useful plan');
    const duplicate = { ...candidate('duplicate', 'Duplicate plan'), placements: structuredClone(useful.placements) };
    const portOnly = {
      ...candidate('port-only', 'Port only'),
      placements: [{ facility_template_id: 'generic_port_alpha', local_body_id: 'body1', is_primary_port: true, build_order: 1 }],
      rationale: [],
      tags: [],
    };
    const original = [portOnly, useful, duplicate];
    const before = structuredClone(original);

    expect(filterUsefulSuggestedBuilds(original).map((item) => item.candidate_id)).toEqual(['useful']);
    expect(original).toEqual(before);
  });

  it('filters brittle trivial suggestions while keeping clear-role starter plans', () => {
    const colonyShipOnly = {
      ...candidate('ship-only', 'Colony Ship Only'),
      placements: [{ facility_template_id: 'colony_ship', local_body_id: null, is_primary_port: false, build_order: 1 }],
      rationale: [],
      tags: ['baseline'],
    };
    const shipAndGenericOutpost = {
      ...candidate('ship-outpost', 'Colony ship plus generic outpost'),
      placements: [
        { facility_template_id: 'colony_ship', local_body_id: null, is_primary_port: false, build_order: 1 },
        { facility_template_id: 'generic_outpost', local_body_id: 'body1', is_primary_port: true, build_order: 2 },
      ],
      rationale: ['Generic plan'],
      assumptions: ['baseline only'],
      tags: [],
    };
    const usefulStarter = {
      ...candidate('tourism-starter', 'Tourism starter'),
      placements: [{ facility_template_id: 'tourism_lodge', local_body_id: 'body1', is_primary_port: false, build_order: 1 }],
      rationale: ['Clear tourism starter for a civilian body.'],
      tags: ['tourism'],
    };

    expect(filterUsefulSuggestedBuilds([colonyShipOnly, shipAndGenericOutpost, usefulStarter]).map((item) => item.candidate_id))
      .toEqual(['tourism-starter']);
  });

  it('translates raw optimiser tags into player-facing suggested build language', () => {
    const presentation = suggestedBuildPresentation({
      ...candidate('tagged', 'Tagged plan'),
      tags: ['body_diversity', 'refinery'],
    });

    expect(presentation.tags).toContain('Uses multiple bodies');
    expect(presentation.tags).toContain('Refinery pressure');
    expect(presentation.tags).not.toContain('body_diversity');
    expect(presentation.purpose).toBeTruthy();
    expect(presentation.reason).toBeTruthy();
    expect(presentation.tradeoff).toBeTruthy();
    expect(presentation.nextAction).toMatch(/Review in Workspace/i);
  });

  it('derives suggested build scale tiers from placement counts and scale tags', () => {
    const starter = candidate('starter', 'Starter');
    starter.placements = [
      { facility_template_id: 'generic_port_alpha', local_body_id: 'body1', is_primary_port: true, build_order: 1 },
      { facility_template_id: 'agri_support_a', local_body_id: 'body1', is_primary_port: false, build_order: 2 },
      { facility_template_id: 'agri_support_b', local_body_id: 'body2', is_primary_port: false, build_order: 3 },
      { facility_template_id: 'agri_support_a', local_body_id: 'body2', is_primary_port: false, build_order: 4 },
      { facility_template_id: 'agri_support_b', local_body_id: 'body3', is_primary_port: false, build_order: 5 },
      { facility_template_id: 'agri_support_a', local_body_id: 'body3', is_primary_port: false, build_order: 6 },
    ];
    const bootstrapTagged = candidate('bootstrap', 'Bootstrap');
    bootstrapTagged.tags = ['scale_bootstrap'];
    bootstrapTagged.placements = bootstrapTagged.placements.slice(0, 2);

    expect(suggestedBuildScale(starter)).toBe('starter');
    expect(suggestedBuildScale(bootstrapTagged)).toBe('bootstrap');
    expect(suggestedBuildPresentation(starter).scaleLabel).toBe('Starter');
    expect(suggestedBuildPresentation(starter).placementCount).toBe(6);
    expect(suggestedBuildPresentation(starter).bodyCount).toBe(3);
  });

  it('defaults Suggested Builds scale to Expansion and avoids bootstrap-first display', async () => {
    const bootstrap = {
      ...candidate('bootstrap-option', 'Bootstrap option'),
      tags: ['scale_bootstrap', 'balanced'],
      placements: [
        { facility_template_id: 'generic_port_alpha', local_body_id: 'body1', is_primary_port: true, build_order: 1 },
        { facility_template_id: 'agri_support_a', local_body_id: 'body1', is_primary_port: false, build_order: 2 },
        { facility_template_id: 'agri_support_b', local_body_id: 'body2', is_primary_port: false, build_order: 3 },
        { facility_template_id: 'agri_support_a', local_body_id: 'body2', is_primary_port: false, build_order: 4 },
      ],
    };
    const expansion = {
      ...candidate('expansion-option', 'Expansion option'),
      tags: ['scale_expansion', 'balanced'],
      placements: [
        { facility_template_id: 'generic_port_alpha', local_body_id: 'body1', is_primary_port: true, build_order: 1 },
        { facility_template_id: 'agri_support_a', local_body_id: 'body1', is_primary_port: false, build_order: 2 },
        { facility_template_id: 'agri_support_b', local_body_id: 'body2', is_primary_port: false, build_order: 3 },
        { facility_template_id: 'agri_support_a', local_body_id: 'body2', is_primary_port: false, build_order: 4 },
        { facility_template_id: 'agri_support_b', local_body_id: 'body3', is_primary_port: false, build_order: 5 },
        { facility_template_id: 'agri_support_a', local_body_id: 'body3', is_primary_port: false, build_order: 6 },
        { facility_template_id: 'agri_support_b', local_body_id: 'body4', is_primary_port: false, build_order: 7 },
        { facility_template_id: 'agri_support_a', local_body_id: 'body4', is_primary_port: false, build_order: 8 },
        { facility_template_id: 'agri_support_b', local_body_id: 'body5', is_primary_port: false, build_order: 9 },
      ],
    };

    mockedFetchOptimiserCandidates.mockResolvedValue(response({
      candidate_count: 2,
      candidates: [bootstrap, expansion],
      ranking: null,
    }));

    render(<OptimiserCandidatePanel systemId64={123} targetArchetype="agriculture_terraforming" />);
    expect(screen.getByRole('button', { name: 'Expansion' }).getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByText('Generate Suggested Builds'));

    expect((await screen.findAllByText('Expansion option')).length).toBeGreaterThan(0);
    expect(screen.queryByText('Bootstrap option')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Starter' }));
    expect(screen.getAllByText('Bootstrap option').length).toBeGreaterThan(0);
  });

  it('keeps multi-structure candidates even when rationale text is sparse', () => {
    const sparseTextExpansion = {
      ...candidate('expansion', 'Expansion candidate'),
      rationale: [],
      tags: [],
      placements: [
        { facility_template_id: 'generic_port_alpha', local_body_id: 'body1', is_primary_port: true, build_order: 1 },
        { facility_template_id: 'agri_support_a', local_body_id: 'body1', is_primary_port: false, build_order: 2 },
        { facility_template_id: 'agri_support_b', local_body_id: 'body2', is_primary_port: false, build_order: 3 },
        { facility_template_id: 'agri_support_a', local_body_id: 'body2', is_primary_port: false, build_order: 4 },
        { facility_template_id: 'agri_support_b', local_body_id: 'body3', is_primary_port: false, build_order: 5 },
        { facility_template_id: 'agri_support_a', local_body_id: 'body3', is_primary_port: false, build_order: 6 },
      ],
    };

    expect(filterUsefulSuggestedBuilds([sparseTextExpansion]).map((item) => item.candidate_id)).toEqual(['expansion']);
  });

  it('renders selected suggested build comparison against current Build Plan and supports hide/show', () => {
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
        templates={templates}
      />,
    );

    expect(screen.getByText('Compare with current plan')).toBeTruthy();
    expect(screen.getByText('What this build is for')).toBeTruthy();
    expect(screen.getByText('Why suggested')).toBeTruthy();
    expect(screen.getByText('Tradeoff')).toBeTruthy();
    expect(screen.getByText('Next action')).toBeTruthy();
    expect(screen.getByText(/advisory and preview-only/i)).toBeTruthy();
    expect(screen.getAllByText('Prefer before').length).toBeGreaterThan(0);
    expect(screen.getByText('Tradeoff summary')).toBeTruthy();
    expect(screen.getByText('Target archetype')).toBeTruthy();
    expect(screen.getByText(/Changes from Refinery \/ Industrial Plan to Tourism \/ Agriculture Plan/)).toBeTruthy();
    expect(screen.getByText('Facility count changes')).toBeTruthy();
    expect(screen.getByTestId('candidate-projected-economy')).toBeTruthy();
    expect(within(screen.getByTestId('candidate-projected-economy')).getByText(/Agri/i)).toBeTruthy();
    expect(screen.getByText(/agri_support_a: 0 → 1/)).toBeTruthy();
    expect(screen.getByText(/legacy_support: removed/)).toBeTruthy();
    expect(screen.getByText('Preview summary deltas')).toBeTruthy();
    expect(screen.getByText('Ranking delta')).toBeTruthy();
    expect(screen.getByText(/Ranking delta is unavailable for the current manual Build Plan/)).toBeTruthy();
    expect(screen.getByText('Risk changes')).toBeTruthy();
    expect(screen.getByText('Warning changes')).toBeTruthy();
    expect(screen.getByText('Assumption changes')).toBeTruthy();
    expect(load).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Hide comparison' }));
    expect(screen.queryByText(/advisory and preview-only/i)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Show comparison' }));
    expect(screen.getByText(/advisory and preview-only/i)).toBeTruthy();
  });

  it('renders comparison empty copy when no current Build Plan exists', () => {
    render(
      <OptimiserCandidateDetails
        candidate={candidate('candidate-a', 'Candidate A')}
        ranking={ranking.ranked_candidates[1]}
        response={response()}
        currentPreviewPlacements={[]}
        currentTargetArchetype="agriculture_terraforming"
      />,
    );

    expect(screen.getByText('Compare with current plan')).toBeTruthy();
    expect(screen.getByText(/Comparison needs a current Build Plan/)).toBeTruthy();
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

    expect(screen.getByRole('button', { name: 'Load into Planner Workspace' })).toBeTruthy();
    expect(screen.getByText(/Nothing is committed in-game/)).toBeTruthy();
    expect(screen.getByText(/does not run Simulation Preview, save a build, or commit anything in-game/)).toBeTruthy();
    expect(container.textContent).not.toMatch(/\bApply candidate\b/i);
    expect(container.textContent).not.toMatch(/\bCommit build\b/i);
    expect(container.textContent).not.toMatch(/\bSave build\b/i);
    expect(container.textContent).not.toMatch(/\bOptimal build\b/i);
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

  it('does not render Load into Planner Workspace when no load callback is provided', () => {
    render(<OptimiserCandidateDetails candidate={candidate('candidate-a', 'Candidate A')} />);
    expect(screen.queryByRole('button', { name: 'Load into Planner Workspace' })).toBeNull();
  });

  it('renders Load into Planner Workspace with callback and loads immediately when no Build Plan exists', () => {
    const onLoadCandidate = vi.fn();
    const selected = candidate('candidate-a', 'Candidate A');
    render(<OptimiserCandidateDetails candidate={selected} onLoadCandidate={onLoadCandidate} />);

    expect(screen.getByText(/Nothing is committed in-game/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Load into Planner Workspace' }));

    expect(onLoadCandidate).toHaveBeenCalledTimes(1);
    expect(onLoadCandidate).toHaveBeenCalledWith(selected);
  });

  it('requires confirmation before replacing an existing Build Plan', () => {
    const onLoadCandidate = vi.fn();
    const selected = candidate('candidate-a', 'Candidate A');
    render(
      <OptimiserCandidateDetails
        candidate={selected}
        hasExistingPreviewPlan
        onLoadCandidate={onLoadCandidate}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Load into Planner Workspace' }));
    expect(screen.getByText('Replace current Build Plan with this suggested build?')).toBeTruthy();
    expect(screen.getByText(/This will replace your current Build Plan with this suggested build/)).toBeTruthy();
    expect(onLoadCandidate).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByText('Replace current Build Plan with this suggested build?')).toBeNull();
    expect(onLoadCandidate).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Load into Planner Workspace' }));
    fireEvent.click(screen.getByRole('button', { name: 'Replace Build Plan' }));
    expect(onLoadCandidate).toHaveBeenCalledTimes(1);
    expect(onLoadCandidate).toHaveBeenCalledWith(selected);
  });

  it('stale candidate load requires explicit older-candidate confirmation', () => {
    const onLoadCandidate = vi.fn();
    const selected = candidate('candidate-a', 'Candidate A');
    render(
      <OptimiserCandidateDetails
        candidate={selected}
        onLoadCandidate={onLoadCandidate}
        controlsChangedSinceGeneration
        generatedTargetArchetype="agriculture_terraforming"
        currentControlTargetArchetype="refinery_industrial"
      />,
    );

    expect(screen.getAllByText(/Copying is still possible, but requires confirmation/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: 'Load into Planner Workspace' }));
    expect(onLoadCandidate).not.toHaveBeenCalled();
    expect(screen.getByText('These suggested builds were generated with older controls')).toBeTruthy();
    expect(screen.getByText(/Generate again for the safest comparison/)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Copy older suggested build anyway' }));
    expect(onLoadCandidate).toHaveBeenCalledTimes(1);
    expect(onLoadCandidate).toHaveBeenCalledWith(selected);
  });

  it('stale candidate load with existing preview plan uses combined replacement confirmation', () => {
    const onLoadCandidate = vi.fn();
    const selected = candidate('candidate-a', 'Candidate A');
    render(
      <OptimiserCandidateDetails
        candidate={selected}
        hasExistingPreviewPlan
        onLoadCandidate={onLoadCandidate}
        controlsChangedSinceGeneration
        generatedTargetArchetype="agriculture_terraforming"
        currentControlTargetArchetype="refinery_industrial"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Load into Planner Workspace' }));
    expect(onLoadCandidate).not.toHaveBeenCalled();
    expect(screen.getByText('Replace current Build Plan with older suggested build?')).toBeTruthy();
    expect(screen.getByText(/generated with older controls/)).toBeTruthy();
    expect(screen.getByText(/does not save anything or affect in-game state/)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onLoadCandidate).not.toHaveBeenCalled();
    expect(screen.queryByText('Replace current Build Plan with older suggested build?')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Load into Planner Workspace' }));
    fireEvent.click(screen.getByRole('button', { name: 'Replace with older suggested build' }));
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
    expect(screen.getAllByText('Body assignment present').length).toBeGreaterThan(0);
  });

  it('renders initial read-only panel state with clear purpose copy and no apply button', () => {
    render(<OptimiserCandidatePanel systemId64={123} targetArchetype="agriculture_terraforming" />);
    expect(screen.getByText('Suggested Builds')).toBeTruthy();
    expect(screen.getByText(/Generate Suggested Builds to get possible build plans/i)).toBeTruthy();
    expect(screen.getByText(/filters generated candidates for usefulness before display/i)).toBeTruthy();
    expect(screen.getByText(/Nothing is saved or committed in-game/i)).toBeTruthy();
    expect(screen.getByText(/Generates bounded suggested build plans and lightweight preview summaries/i)).toBeTruthy();
    expect(screen.getByText(/does not run the main Simulation Preview or change your current Build Plan/i)).toBeTruthy();
    expect(screen.getByText(/Allows Suggested Builds to use inferred or incomplete data/i)).toBeTruthy();
    expect(screen.getByText(/confidence and warnings should be reviewed/i)).toBeTruthy();
    expect(screen.getByText(/Review suggested builds here without changing the editable Build Plan/i)).toBeTruthy();
    expect(screen.getByText('Generate Suggested Builds')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Load into Planner Workspace/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /apply/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /use this build/i })).toBeNull();
    expect(screen.queryByText('Optimiser Candidates')).toBeNull();
  });

  it('renders load-enabled panel copy when a load callback is provided', () => {
    render(
      <OptimiserCandidatePanel
        systemId64={123}
        targetArchetype="agriculture_terraforming"
        onLoadCandidate={() => undefined}
      />,
    );
    expect(screen.getByText(/review it as the editable Build Plan/i)).toBeTruthy();
    expect(screen.getByText(/Nothing is saved or committed in-game/i)).toBeTruthy();
    expect(screen.queryByText(/Review suggested builds here without changing the editable Build Plan/i)).toBeNull();
  });

  it('clicking Generate Suggested Builds calls API with ranking and preview enabled', async () => {
    mockedFetchOptimiserCandidates.mockResolvedValue(response());
    render(<OptimiserCandidatePanel systemId64={123} targetArchetype="agriculture_terraforming" />);
    fireEvent.click(screen.getByText('Generate Suggested Builds'));
    await waitFor(() => expect(mockedFetchOptimiserCandidates).toHaveBeenCalledTimes(1));
    expect(mockedFetchOptimiserCandidates).toHaveBeenCalledWith(expect.objectContaining({
      system_id64: 123,
      target_archetype: 'agriculture_terraforming',
      max_candidates: 5,
      allow_estimated_data: true,
      run_preview: true,
      include_ranking: true,
    }));
  });

  it('renders generated-parameter stamp after successful generation', async () => {
    mockedFetchOptimiserCandidates.mockResolvedValue(response());
    render(<OptimiserCandidatePanel systemId64={123} targetArchetype="agriculture_terraforming" />);
    fireEvent.click(screen.getByText('Generate Suggested Builds'));

    expect(await screen.findByText('Generated for')).toBeTruthy();
    expect(screen.getAllByText(/Target:/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Tourism \/ Agriculture Plan/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Max suggested builds:/)).toBeTruthy();
    expect(screen.getAllByText('5').length).toBeGreaterThan(0);
    expect(screen.getByText(/Estimated data:/)).toBeTruthy();
    expect(screen.getByText('on')).toBeTruthy();
  });

  it('warns when target archetype changes after generation', async () => {
    mockedFetchOptimiserCandidates.mockResolvedValue(response());
    const { rerender } = render(<OptimiserCandidatePanel systemId64={123} targetArchetype="agriculture_terraforming" />);
    fireEvent.click(screen.getByText('Generate Suggested Builds'));
    await screen.findByText('Generated for');

    rerender(<OptimiserCandidatePanel systemId64={123} targetArchetype="refinery_industrial" />);

    expect(screen.getByText(/Controls have changed since these suggested builds were generated/)).toBeTruthy();
  });

  it('warns when max candidates changes after generation', async () => {
    mockedFetchOptimiserCandidates.mockResolvedValue(response());
    render(<OptimiserCandidatePanel systemId64={123} targetArchetype="agriculture_terraforming" />);
    fireEvent.click(screen.getByText('Generate Suggested Builds'));
    await screen.findByText('Generated for');

    fireEvent.change(screen.getByDisplayValue('5'), { target: { value: '8' } });

    expect(screen.getByText(/Controls have changed since these suggested builds were generated/)).toBeTruthy();
  });

  it('warns when estimated-data toggle changes after generation', async () => {
    mockedFetchOptimiserCandidates.mockResolvedValue(response());
    render(<OptimiserCandidatePanel systemId64={123} targetArchetype="agriculture_terraforming" />);
    fireEvent.click(screen.getByText('Generate Suggested Builds'));
    await screen.findByText('Generated for');

    fireEvent.click(screen.getByLabelText(/Include estimated data/i));

    expect(screen.getByText(/Controls have changed since these suggested builds were generated/)).toBeTruthy();
  });

  it('renders loading state while candidates are being fetched', () => {
    mockedFetchOptimiserCandidates.mockReturnValue(new Promise(() => {}));
    render(<OptimiserCandidatePanel systemId64={123} targetArchetype="agriculture_terraforming" />);
    fireEvent.click(screen.getByText('Generate Suggested Builds'));
    expect(screen.getByText('Generating ranked Suggested Builds...')).toBeTruthy();
  });

  it('renders error state with retry', async () => {
    mockedFetchOptimiserCandidates.mockRejectedValue(new Error('{"detail":{"message":"backend down","stack":"private trace"}}'));
    render(<OptimiserCandidatePanel systemId64={123} targetArchetype="agriculture_terraforming" />);
    fireEvent.click(screen.getByText('Generate Suggested Builds'));
    expect(await screen.findByText(/Suggested Builds are temporarily unavailable/i)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy();
    expect(screen.getByText('Show technical details')).toBeTruthy();
    expect(screen.queryByText(/backend down/)).toBeNull();
    expect(screen.queryByText(/private trace/)).toBeNull();
    fireEvent.click(screen.getByText('Show technical details'));
    expect(screen.getByText(/backend down/)).toBeTruthy();
  });

  it('retry calls candidate generation again after a friendly error', async () => {
    mockedFetchOptimiserCandidates
      .mockRejectedValueOnce(new Error('backend down'))
      .mockResolvedValueOnce(response());
    render(<OptimiserCandidatePanel systemId64={123} targetArchetype="agriculture_terraforming" />);
    fireEvent.click(screen.getByText('Generate Suggested Builds'));
    await screen.findByText(/Suggested Builds are temporarily unavailable/i);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('Generated for')).toBeTruthy();
    expect(mockedFetchOptimiserCandidates).toHaveBeenCalledTimes(2);
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
    fireEvent.click(screen.getByText('Generate Suggested Builds'));
    expect(await screen.findByText('No Suggested Builds generated yet.')).toBeTruthy();
    expect(screen.getByText('Warning: No candidate anchors found.')).toBeTruthy();
    expect(screen.getByText('Assumption: Generated no plans.')).toBeTruthy();
  });

  it('replaces trivial generated builds with the useful-build empty state', async () => {
    mockedFetchOptimiserCandidates.mockResolvedValue(response({
      candidate_count: 1,
      candidates: [{
        ...candidate('port-only', 'Port only'),
        placements: [{ facility_template_id: 'generic_port_alpha', local_body_id: 'body1', is_primary_port: true, build_order: 1 }],
        rationale: [],
        tags: [],
      }],
      ranking: null,
    }));

    render(<OptimiserCandidatePanel systemId64={123} targetArchetype="agriculture_terraforming" />);
    fireEvent.click(screen.getByText('Generate Suggested Builds'));

    expect(await screen.findByText(/No useful .* suggested builds are available yet/i)).toBeTruthy();
    expect(screen.queryByText('Port only')).toBeNull();
  });

  it('displays ranked candidates in ranking order and details for the selected candidate', async () => {
    mockedFetchOptimiserCandidates.mockResolvedValue(response());
    render(<OptimiserCandidatePanel systemId64={123} targetArchetype="agriculture_terraforming" />);
    fireEvent.click(screen.getByRole('button', { name: 'Starter' }));
    fireEvent.click(screen.getByText('Generate Suggested Builds'));
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
    fireEvent.click(screen.getByRole('button', { name: 'Starter' }));
    fireEvent.click(screen.getByText('Generate Suggested Builds'));
    expect((await screen.findAllByText('Candidate A')).length).toBeGreaterThan(0);
    expect(screen.getByText('No ranking breakdown is available for this suggested build.')).toBeTruthy();
  });
});
