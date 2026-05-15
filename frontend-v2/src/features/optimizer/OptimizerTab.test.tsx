import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { OptimizerTab } from './OptimizerTab';
import type { UseOptimizer } from './useOptimizer';
import type { RerankResponse, SystemResult } from '@/types/api';

function makeOptimizer(overrides: Partial<UseOptimizer> = {}): UseOptimizer {
  return {
    weights: {
      economy: 0.3,
      slots: 0.2,
      strategic: 0.15,
      safety: 0.15,
      terraforming: 0.1,
      diversity: 0.1,
    },
    setWeight: vi.fn(),
    resetWeights: vi.fn(),
    weightSum: 1,
    economy: null,
    setEconomy: vi.fn(),
    state: { kind: 'idle' },
    run: vi.fn().mockResolvedValue(undefined),
    resetState: vi.fn(),
    ...overrides,
  } as UseOptimizer;
}

function makeSystem(id64: number, name: string): SystemResult {
  return { id64, name } as SystemResult;
}

function makeSearch(results: SystemResult[] = []) {
  return { results } as never;
}

describe('OptimizerTab Advanced Search Tuning UX', () => {
  it('renders Advanced Search Tuning and explains current Finder-result scope', () => {
    render(<OptimizerTab optimizer={makeOptimizer()} search={makeSearch()} />);

    expect(screen.getByRole('heading', { name: 'Advanced Search Tuning' })).toBeTruthy();
    expect(screen.getAllByText('Uses current Finder results').length).toBeGreaterThan(0);
    expect(screen.getByText(/re-prioritises the current Finder results/i)).toBeTruthy();
    expect(screen.getByText(/It does not run a new search, save preferences, or change Colony Planner/i)).toBeTruthy();
    expect(screen.getByText(/reranks a copy of those results into a temporary tuned order/i)).toBeTruthy();
    expect(screen.queryByText(/Optimizer/i)).toBeNull();
  });

  it('directs users to run Finder first when there are no current results', () => {
    render(<OptimizerTab optimizer={makeOptimizer()} search={makeSearch()} />);

    expect(screen.getByText('Run a Finder search first.')).toBeTruthy();
    expect(screen.getByText(/works on the current Finder results/i)).toBeTruthy();
    expect(screen.getByText(/cannot tune systems that have not been searched yet/i)).toBeTruthy();
    expect((screen.getByTestId('optimizer-run') as HTMLButtonElement).disabled).toBe(true);
  });

  it('explains economy scoring emphasis and weight scope', () => {
    render(<OptimizerTab optimizer={makeOptimizer()} search={makeSearch([makeSystem(123, 'Sol')])} />);

    expect(screen.getByText('Economy scoring emphasis')).toBeTruthy();
    expect(screen.getByText(/It does not filter systems out/i)).toBeTruthy();
    expect(screen.getByText(/Auto uses the best available stored economy score per system/i)).toBeTruthy();
    expect(screen.getByText(/Weights apply only to this tuning run/i)).toBeTruthy();
    expect(screen.getByText(/backend normalises them for the temporary tuned score/i)).toBeTruthy();
    expect(screen.getByTitle('Economy-score emphasis')).toBeTruthy();
    expect(screen.getByTitle('Available/buildable capacity signal')).toBeTruthy();
    expect(screen.getByTitle('Body quality / strategic value signal')).toBeTruthy();
    expect(screen.getByTitle('Orbital safety signal')).toBeTruthy();
    expect(screen.getByTitle('Terraforming potential signal')).toBeTruthy();
    expect(screen.getByTitle('Body diversity signal')).toBeTruthy();
  });

  it('keeps the run control wired to the current Finder result objects', () => {
    const run = vi.fn().mockResolvedValue(undefined);
    const optimizer = makeOptimizer({ run });
    const source = [makeSystem(123, 'Sol')];

    render(<OptimizerTab optimizer={optimizer} search={makeSearch(source)} />);
    fireEvent.click(screen.getByTestId('optimizer-run'));

    expect(screen.getByText('Show tuned order')).toBeTruthy();
    expect(run).toHaveBeenCalledWith(source);
  });

  it('uses loading copy that does not imply a new search', () => {
    render(<OptimizerTab optimizer={makeOptimizer({ state: { kind: 'busy' } })} search={makeSearch([makeSystem(123, 'Sol')])} />);

    expect(screen.getAllByText('Building tuned order...').length).toBeGreaterThan(0);
    expect(screen.getByText(/re-prioritising a copy of the current Finder results/i)).toBeTruthy();
  });

  it('renders API failures clearly', () => {
    render(
      <OptimizerTab
        optimizer={makeOptimizer({ state: { kind: 'err', message: 'API 500 on /ratings/rerank: exploded' } })}
        search={makeSearch([makeSystem(123, 'Sol')])}
      />,
    );

    expect(screen.getByText('API 500 on /ratings/rerank: exploded')).toBeTruthy();
  });

  it('shows original Finder rank, tuned rank, movement, temporary score, and stored rationale labels', () => {
    const data: RerankResponse = {
      weights_applied: {
        economy: 0.3,
        slots: 0.2,
        strategic: 0.15,
        safety: 0.15,
        terraforming: 0.1,
        diversity: 0.1,
      },
      economy_used: null,
      results: [
        {
          id64: 2,
          reranked_score: 91,
          original_score: 80,
          confidence: 0.9,
          rationale: 'Beta stored rationale',
          economy_used: 'Tourism',
        },
        {
          id64: 1,
          reranked_score: 75,
          original_score: 88,
          confidence: null,
          rationale: 'Alpha stored rationale',
          economy_used: 'Agriculture',
        },
        {
          id64: 3,
          reranked_score: 70,
          original_score: 70,
          confidence: null,
          rationale: 'Gamma stored rationale',
          economy_used: 'Industrial',
        },
      ],
    };

    render(
      <OptimizerTab
        optimizer={makeOptimizer({ state: { kind: 'ok', data, queriedAt: 123 } })}
        search={makeSearch([
          makeSystem(1, 'Alpha'),
          makeSystem(2, 'Beta'),
          makeSystem(3, 'Gamma'),
        ])}
      />,
    );

    const beta = screen.getByTestId('optimizer-row-2');
    expect(within(beta).getByText('Finder #2 -> Tuned #1')).toBeTruthy();
    expect(within(beta).getByText('Moved up 1 place')).toBeTruthy();
    expect(within(beta).getByText('Temporary tuned score')).toBeTruthy();
    expect(within(beta).getByText('Original stored score 80')).toBeTruthy();
    expect(within(beta).getByText(/Stored rating rationale:/)).toBeTruthy();
    expect(within(beta).getByText(/Beta stored rationale/)).toBeTruthy();

    const alpha = screen.getByTestId('optimizer-row-1');
    expect(within(alpha).getByText('Finder #1 -> Tuned #2')).toBeTruthy();
    expect(within(alpha).getByText('Moved down 1 place')).toBeTruthy();

    const gamma = screen.getByTestId('optimizer-row-3');
    expect(within(gamma).getByText('Finder #3 -> Tuned #3')).toBeTruthy();
    expect(within(gamma).getByText('Unchanged')).toBeTruthy();

    expect(screen.getAllByText(/The tuned score is temporary for this run/i).length).toBe(3);
    expect(screen.getAllByText(/Stored rating rationale comes from the existing rating data/i).length).toBe(3);
  });
});
