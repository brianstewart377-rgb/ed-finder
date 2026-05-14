import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { OptimizerTab } from './OptimizerTab';
import type { UseOptimizer } from './useOptimizer';

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

function makeSearch(results: unknown[] = []) {
  return { results } as never;
}

describe('OptimizerTab legacy Search Tuning rename', () => {
  it('renders Search Tuning heading and explains Finder-result reranking scope', () => {
    render(<OptimizerTab optimizer={makeOptimizer()} search={makeSearch()} />);

    expect(screen.getByText('🎚️ Search Tuning')).toBeTruthy();
    expect(screen.getByText('Re-weight and reorder your current Finder results.')).toBeTruthy();
    expect(screen.getByText('This tunes Finder search results only. It does not generate colony build plans.')).toBeTruthy();
    expect(screen.getByText(/Run a Finder search first/)).toBeTruthy();
    expect(screen.getByText(/reorders the systems already in your Finder results/)).toBeTruthy();
  });

  it('shows ready-state copy when Finder results exist', () => {
    render(<OptimizerTab optimizer={makeOptimizer()} search={makeSearch([{ id64: 123, name: 'Sol' }])} />);

    expect(screen.getByText('Ready to tune search results')).toBeTruthy();
    expect(screen.getByText('Adjust what matters most, then rerank the current Finder results.')).toBeTruthy();
    expect(screen.getByText('Source: 1 system from current Finder results')).toBeTruthy();
  });

  it('keeps the rerank button behavior and test ids unchanged', () => {
    const run = vi.fn().mockResolvedValue(undefined);
    const optimizer = makeOptimizer({ run });
    const source = [{ id64: 123, name: 'Sol' }];

    render(<OptimizerTab optimizer={optimizer} search={makeSearch(source)} />);
    fireEvent.click(screen.getByTestId('optimizer-run'));

    expect(screen.getByText('▶ Rerank results')).toBeTruthy();
    expect(run).toHaveBeenCalledWith(source);
  });
});
