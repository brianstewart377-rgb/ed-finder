import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AdvancedSearchTuningTab } from './AdvancedSearchTuningTab';
import type { SearchTuningSourceSnapshot, UseSearchTuning } from './useSearchTuning';
import type { DevelopmentRerankResponse, SystemResult } from '@/types/api';

function makeSearchTuning(overrides: Partial<UseSearchTuning> = {}): UseSearchTuning {
  return {
    weights: {
      purity: 0.3,
      buildability: 0.25,
      slots: 0.2,
      expansion: 0.15,
      logistics: 0.1,
    },
    setWeight: vi.fn(),
    resetWeights: vi.fn(),
    weightSum: 1,
    state: { kind: 'idle' },
    run: vi.fn().mockResolvedValue(undefined),
    resetState: vi.fn(),
    ...overrides,
  } as UseSearchTuning;
}

function makeSystem(id64: number, name: string): SystemResult {
  return { id64, name } as SystemResult;
}

function makeSearch(results: SystemResult[] = []) {
  return { results } as never;
}

function makeSourceSnapshot(systems: SystemResult[]): SearchTuningSourceSnapshot {
  return Object.fromEntries(
    systems.map((system, index) => [
      system.id64,
      { originalRank: index + 1, name: system.name ?? null },
    ]),
  );
}

describe('AdvancedSearchTuningTab Development Tuning UX', () => {
  it('renders Development Tuning and explains current Finder-result scope', () => {
    render(<AdvancedSearchTuningTab searchTuning={makeSearchTuning()} search={makeSearch()} />);

    expect(screen.getByRole('heading', { name: 'Development Tuning' })).toBeTruthy();
    expect(screen.getAllByText('Uses current Finder results').length).toBeGreaterThan(0);
    expect(screen.getByText(/re-prioritises the current Finder results/i)).toBeTruthy();
    expect(screen.getByText(/It does not run a new search, save preferences, or change Colony Planner/i)).toBeTruthy();
    expect(screen.getByText(/builds a temporary tuned order from a copy of those results/i)).toBeTruthy();
    expect(screen.queryByText(/Optimizer/i)).toBeNull();
  });

  it('directs users to run Finder first when there are no current results', () => {
    render(<AdvancedSearchTuningTab searchTuning={makeSearchTuning()} search={makeSearch()} />);

    expect(screen.getByText('Run a Finder search first.')).toBeTruthy();
    expect(screen.getByText(/works on the current Finder results/i)).toBeTruthy();
    expect(screen.getByText(/cannot tune systems that have not been searched yet/i)).toBeTruthy();
    expect((screen.getByTestId('search-tuning-run') as HTMLButtonElement).disabled).toBe(true);
  });

  it('explains development-weight emphasis and weight scope', () => {
    render(<AdvancedSearchTuningTab searchTuning={makeSearchTuning()} search={makeSearch([makeSystem(123, 'Sol')])} />);

    expect(screen.getByText('Weights')).toBeTruthy();
    expect(screen.getByText(/Weights apply only to this tuning run/i)).toBeTruthy();
    expect(screen.getByText(/backend normalises them for the temporary development score/i)).toBeTruthy();
    expect(screen.getByTitle('Clean economy stack and low contamination')).toBeTruthy();
    expect(screen.getByTitle('Ease of build and scaling viability')).toBeTruthy();
    expect(screen.getByTitle('Available colony capacity signal')).toBeTruthy();
    expect(screen.getByTitle('Overall development headroom')).toBeTruthy();
    expect(screen.getByTitle('Travel and access practicality')).toBeTruthy();
  });

  it('keeps the run control wired to the current Finder result objects', () => {
    const run = vi.fn().mockResolvedValue(undefined);
    const searchTuning = makeSearchTuning({ run });
    const source = [makeSystem(123, 'Sol')];

    render(<AdvancedSearchTuningTab searchTuning={searchTuning} search={makeSearch(source)} />);
    fireEvent.click(screen.getByTestId('search-tuning-run'));

    expect(screen.getByText('Show tuned order')).toBeTruthy();
    expect(run).toHaveBeenCalledWith(source);
  });

  it('uses loading copy that does not imply a new search', () => {
    render(
      <AdvancedSearchTuningTab
        searchTuning={makeSearchTuning({ state: { kind: 'busy', sourceSnapshot: makeSourceSnapshot([makeSystem(123, 'Sol')]) } })}
        search={makeSearch([makeSystem(123, 'Sol')])}
      />,
    );

    expect(screen.getAllByText('Building tuned order...').length).toBeGreaterThan(0);
    expect(screen.getByText(/re-prioritising a copy of the current Finder results/i)).toBeTruthy();
  });

  it('renders API failures clearly', () => {
    render(
      <AdvancedSearchTuningTab
        searchTuning={makeSearchTuning({ state: { kind: 'err', message: 'API 500 on /archetypes/rerank: exploded' } })}
        search={makeSearch([makeSystem(123, 'Sol')])}
      />,
    );

    expect(screen.getByText('API 500 on /archetypes/rerank: exploded')).toBeTruthy();
  });

  it('shows original Finder rank, tuned rank, movement, temporary score, and archetype rationale labels', () => {
    const data: DevelopmentRerankResponse = {
      weights_applied: {
        purity: 0.3,
        buildability: 0.25,
        slots: 0.2,
        expansion: 0.15,
        logistics: 0.1,
      },
      results: [
        {
          id64: 2,
          reranked_score: 91,
          original_score: 80,
          confidence: 0.9,
          rationale: { summary: 'Beta archetype rationale' },
          contributions: {
            purity: 30,
            buildability: 24,
            slots: 22,
            expansion: 9,
            logistics: 1,
          },
        },
        {
          id64: 1,
          reranked_score: 75,
          original_score: 88,
          confidence: null,
          rationale: { summary: 'Alpha archetype rationale' },
        },
        {
          id64: 3,
          reranked_score: 70,
          original_score: 70,
          confidence: null,
          rationale: { summary: 'Gamma archetype rationale' },
        },
      ],
    };

    render(
      <AdvancedSearchTuningTab
        searchTuning={makeSearchTuning({
          state: {
            kind: 'ok',
            data,
            queriedAt: 123,
            sourceSnapshot: makeSourceSnapshot([
              makeSystem(1, 'Alpha'),
              makeSystem(2, 'Beta'),
              makeSystem(3, 'Gamma'),
            ]),
          },
        })}
        search={makeSearch([
          makeSystem(1, 'Alpha'),
          makeSystem(2, 'Beta'),
          makeSystem(3, 'Gamma'),
        ])}
      />,
    );

    const beta = screen.getByTestId('search-tuning-row-2');
    expect(within(beta).getByText('Finder #2 -> Tuned #1')).toBeTruthy();
    expect(within(beta).getByText('Moved up 1 place')).toBeTruthy();
    expect(within(beta).getByText('Temporary tuned score')).toBeTruthy();
    expect(within(beta).getByText('Original development score 80')).toBeTruthy();
    expect(within(beta).getByText(/Archetype rationale:/)).toBeTruthy();
    expect(within(beta).getByText(/Beta archetype rationale/)).toBeTruthy();
    expect(within(beta).getByText('Why this tuned position?')).toBeTruthy();
    expect(within(beta).getByText(/purity and buildability helped most/i)).toBeTruthy();
    expect(within(beta).getByText('Helped')).toBeTruthy();
    expect(within(beta).getByText('Purity +30.0')).toBeTruthy();
    expect(within(beta).getByText('Buildability +24.0')).toBeTruthy();
    expect(within(beta).queryByText('Slots +22.0')).toBeNull();
    expect(within(beta).getByText('Weaker signals')).toBeTruthy();
    expect(within(beta).getByText('Logistics +1.0')).toBeTruthy();
    expect(within(beta).getByText('Confidence adjustment: 90%.')).toBeTruthy();
    expect(within(beta).queryByText('Held back')).toBeNull();
    expect(within(beta).queryByText(/held this tuned position back/i)).toBeNull();
    expect(within(beta).queryByText(/optimal|guaranteed/i)).toBeNull();

    const alpha = screen.getByTestId('search-tuning-row-1');
    expect(within(alpha).getByText('Finder #1 -> Tuned #2')).toBeTruthy();
    expect(within(alpha).getByText('Moved down 1 place')).toBeTruthy();

    const gamma = screen.getByTestId('search-tuning-row-3');
    expect(within(gamma).getByText('Finder #3 -> Tuned #3')).toBeTruthy();
    expect(within(gamma).getByText('Unchanged')).toBeTruthy();

    expect(screen.getAllByText(/The tuned score is temporary for this run/i).length).toBe(3);
  });

  it('uses the tuning-run source snapshot for rank movement even when live Finder results changed', () => {
    const data: DevelopmentRerankResponse = {
      weights_applied: {
        purity: 0.3,
        buildability: 0.25,
        slots: 0.2,
        expansion: 0.15,
        logistics: 0.1,
      },
      results: [
        {
          id64: 2,
          reranked_score: 91,
          original_score: 80,
          confidence: null,
          rationale: { summary: 'Snapshot rationale' },
        },
      ],
    };

    render(
      <AdvancedSearchTuningTab
        searchTuning={makeSearchTuning({
          state: {
            kind: 'ok',
            data,
            queriedAt: 123,
            sourceSnapshot: {
              2: { originalRank: 2, name: 'Beta from tuning run' },
            },
          },
        })}
        search={makeSearch([
          makeSystem(2, 'Beta from later Finder search'),
          makeSystem(9, 'Different live result'),
        ])}
      />,
    );

    const beta = screen.getByTestId('search-tuning-row-2');
    expect(within(beta).getByText('Beta from tuning run')).toBeTruthy();
    expect(within(beta).getByText('Finder #2 -> Tuned #1')).toBeTruthy();
    expect(within(beta).getByText('Moved up 1 place')).toBeTruthy();
    expect(within(beta).queryByText('Finder #1 -> Tuned #1')).toBeNull();
    expect(within(beta).queryByText('Beta from later Finder search')).toBeNull();
  });

  it('renders a fallback when contribution breakdown is unavailable', () => {
    const data: DevelopmentRerankResponse = {
      weights_applied: {
        purity: 0.3,
        buildability: 0.25,
        slots: 0.2,
        expansion: 0.15,
        logistics: 0.1,
      },
      results: [
        {
          id64: 7,
          reranked_score: 60,
          original_score: 60,
          confidence: null,
          rationale: { summary: 'Stored only' },
        },
      ],
    };

    render(
      <AdvancedSearchTuningTab
        searchTuning={makeSearchTuning({
          state: {
            kind: 'ok',
            data,
            queriedAt: 123,
            sourceSnapshot: { 7: { originalRank: 1, name: 'Fallback' } },
          },
        })}
        search={makeSearch([makeSystem(7, 'Fallback')])}
      />,
    );

    const row = screen.getByTestId('search-tuning-row-7');
    expect(within(row).getAllByText('Contribution breakdown unavailable for this row.').length).toBeGreaterThan(0);
  });

  it('renders neutral copy for all-zero contribution rows', () => {
    const data: DevelopmentRerankResponse = {
      weights_applied: {
        purity: 0.3,
        buildability: 0.25,
        slots: 0.2,
        expansion: 0.15,
        logistics: 0.1,
      },
      results: [
        {
          id64: 8,
          reranked_score: 0,
          original_score: 0,
          confidence: null,
          rationale: { summary: 'No tracked support' },
          contributions: {
            purity: 0,
            buildability: 0,
            slots: 0,
            expansion: 0,
            logistics: 0,
          },
        },
      ],
    };

    render(
      <AdvancedSearchTuningTab
        searchTuning={makeSearchTuning({
          state: {
            kind: 'ok',
            data,
            queriedAt: 123,
            sourceSnapshot: { 8: { originalRank: 1, name: 'Zero support' } },
          },
        })}
        search={makeSearch([makeSystem(8, 'Zero support')])}
      />,
    );

    const row = screen.getByTestId('search-tuning-row-8');
    expect(within(row).getByText('Contribution values are available, but all tracked signals contributed 0.0 under the current weights.')).toBeTruthy();
    expect(within(row).queryByText(/helped most/i)).toBeNull();
    expect(within(row).getByText('Weaker signals')).toBeTruthy();
    expect(within(row).queryByText('Held back')).toBeNull();
  });

  it('opens system detail from detail actions and routes Evaluate to the dedicated Colony Planner callback', () => {
    const onOpenDetail = vi.fn();
    const onOpenColonyPlanner = vi.fn();
    const data: DevelopmentRerankResponse = {
      weights_applied: {
        purity: 0.3,
        buildability: 0.25,
        slots: 0.2,
        expansion: 0.15,
        logistics: 0.1,
      },
      results: [
        {
          id64: 42,
          reranked_score: 80,
          original_score: 75,
          confidence: null,
          rationale: { summary: 'Stored rationale' },
          contributions: {
            purity: 20,
            buildability: 12,
            slots: 15,
            expansion: 10,
            logistics: 8,
          },
        },
      ],
    };

    render(
      <AdvancedSearchTuningTab
        searchTuning={makeSearchTuning({
          state: {
            kind: 'ok',
            data,
            queriedAt: 123,
            sourceSnapshot: { 42: { originalRank: 2, name: 'Handoff' } },
          },
        })}
        search={makeSearch([makeSystem(42, 'Handoff')])}
        onOpenDetail={onOpenDetail}
        onOpenColonyPlanner={onOpenColonyPlanner}
      />,
    );

    fireEvent.click(screen.getByTestId('search-tuning-open-detail-42'));
    fireEvent.click(screen.getByTestId('search-tuning-evaluate-42'));
    fireEvent.click(screen.getByTestId('search-tuning-row-42'));

    expect(onOpenDetail).toHaveBeenCalledTimes(2);
    expect(onOpenDetail).toHaveBeenCalledWith(42);
    expect(onOpenDetail.mock.calls[0]).toEqual([42]);
    expect(onOpenDetail.mock.calls[1]).toEqual([42]);
    expect(onOpenColonyPlanner).toHaveBeenCalledTimes(1);
    expect(onOpenColonyPlanner).toHaveBeenCalledWith(42);
    expect(screen.getByText(/dedicated Colony Planner workspace/i)).toBeTruthy();
    expect(screen.getByText(/does not run Preview or generate builds/i)).toBeTruthy();
  });

  it('falls back to focused detail handoff when no workspace callback is provided', () => {
    const onOpenDetail = vi.fn();
    const data: DevelopmentRerankResponse = {
      weights_applied: {
        purity: 0.3,
        buildability: 0.25,
        slots: 0.2,
        expansion: 0.15,
        logistics: 0.1,
      },
      results: [
        {
          id64: 42,
          reranked_score: 80,
          original_score: 75,
          confidence: null,
          rationale: { summary: 'Stored rationale' },
        },
      ],
    };

    render(
      <AdvancedSearchTuningTab
        searchTuning={makeSearchTuning({
          state: {
            kind: 'ok',
            data,
            queriedAt: 123,
            sourceSnapshot: { 42: { originalRank: 1, name: 'Handoff' } },
          },
        })}
        search={makeSearch([makeSystem(42, 'Handoff')])}
        onOpenDetail={onOpenDetail}
      />,
    );

    fireEvent.click(screen.getByTestId('search-tuning-evaluate-42'));

    expect(onOpenDetail).toHaveBeenCalledTimes(1);
    expect(onOpenDetail).toHaveBeenCalledWith(42, { focus: 'colony-planner' });
    expect(screen.getByText(/focused on Colony Planner/i)).toBeTruthy();
    expect(screen.getByText(/does not run Preview or generate builds/i)).toBeTruthy();
  });
});
