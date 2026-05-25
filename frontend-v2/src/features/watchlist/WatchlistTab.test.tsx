import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { WatchlistTab } from './WatchlistTab';
import type { WatchlistEntry } from '@/lib/api';

describe('WatchlistTab data trust display', () => {
  it('renders unknown coords and population without inventing zeroes', () => {
    const entries: WatchlistEntry[] = [{
      system_id64: 2008132031194,
      name: 'Exioce',
      x: 0,
      y: 0,
      z: 0,
      population: null,
      is_colonised: false,
      added_at: '2026-05-25T00:00:00Z',
      score: null,
      economy_suggestion: null,
    }];

    render(
      <WatchlistTab
        entries={entries}
        loading={false}
        error={null}
        onRefresh={vi.fn()}
        onRemove={vi.fn()}
      />,
    );

    expect(screen.getAllByText('Unknown')).toHaveLength(2);
    expect(screen.queryByText('0.00, 0.00, 0.00')).toBeNull();
    expect(screen.queryByText('Uninhabited')).toBeNull();
  });
});
