import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { SystemResult } from '@/types/api';
import { CompareTab } from './CompareTab';
import type { UseCompare } from './useCompare';
import type { ReviewSelectedSystem } from '@/components/ReviewWorkspaceHeader';

function compareWith(entries: SystemResult[]): UseCompare {
  return {
    entries,
    has: vi.fn(),
    toggle: vi.fn(),
    remove: vi.fn(),
    clear: vi.fn(),
    exportCsv: vi.fn(),
    lastError: null,
    clearError: vi.fn(),
  };
}

describe('CompareTab data trust display', () => {
  it('renders fake zero distance and unknown population conservatively', () => {
    const entries = [{
      id64: 2008132031194,
      name: 'Exioce',
      distance: 0,
      population: null,
      is_colonised: false,
      score: 80,
      score_extraction: 70,
    }] as unknown as SystemResult[];

    render(<CompareTab compare={compareWith(entries)} />);

    expect(screen.getByTestId('compare-cell-distance-from-ref-2008132031194').textContent).toBe('—');
    expect(screen.getByTestId('compare-cell-population-2008132031194').textContent).toBe('Unknown');
  });

  it('shows selected-system review context in the workspace header', () => {
    const entries = [{
      id64: 2008132031194,
      name: 'Exioce',
      distance: 12,
      population: 1234,
      is_colonised: false,
      score: 80,
      score_extraction: 70,
    }] as unknown as SystemResult[];
    const selectedSystem: ReviewSelectedSystem = {
      id64: 12866676218109,
      name: 'Shinrarta Dezhra',
      loading: false,
      evidenceLabel: 'Available candidate',
      evidenceTone: 'available',
      evidenceSummary: 'This system remains selected across Explore, Inspect, Plan, and Review until you choose another one.',
    };

    render(<CompareTab compare={compareWith(entries)} selectedSystem={selectedSystem} />);

    expect(screen.getByTestId('compare-workspace-header')).toBeTruthy();
    expect(screen.getByText('Shinrarta Dezhra')).toBeTruthy();
    expect(screen.getByText('Available candidate')).toBeTruthy();
    expect(screen.getByText(/selected across Explore, Inspect, Plan, and Review/i)).toBeTruthy();
  });
});
