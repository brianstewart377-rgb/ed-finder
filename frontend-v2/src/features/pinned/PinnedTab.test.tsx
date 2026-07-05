import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PinnedTab } from './PinnedTab';
import type { UsePinned } from './usePinned';

describe('PinnedTab data trust display', () => {
  it('renders unknown coords and population without inventing zeroes', () => {
    const pinned: UsePinned = {
      entries: [{
        id64: 2008132031194,
        name: 'Exioce',
        x: 0,
        y: 0,
        z: 0,
        population: null,
        is_colonised: false,
        rating: null,
        economy: null,
        pinned_at: '2026-05-25T00:00:00Z',
        distance: null,
      }],
      has: vi.fn(),
      toggle: vi.fn(),
      remove: vi.fn(),
      clear: vi.fn(),
      exportJson: vi.fn(),
    };

    render(<PinnedTab pinned={pinned} />);

    expect(screen.getByText('Unknown')).toBeTruthy();
    expect(screen.queryByText('0.00, 0.00, 0.00')).toBeNull();
    expect(screen.queryByText('Uninhabited')).toBeNull();
  });

  it('surfaces pinned archetype snapshots as the primary development signal', () => {
    const pinned: UsePinned = {
      entries: [{
        id64: 42,
        name: 'Handoff',
        x: 1,
        y: 2,
        z: 3,
        population: 1000,
        is_colonised: false,
        rating: 82,
        economy: 'Refinery',
        archetype_score: 91,
        primary_archetype: 'refinery_industrial',
        secondary_archetype: 'trade_logistics',
        pinned_at: '2026-07-05T00:00:00Z',
        distance: 12.5,
      }],
      has: vi.fn(),
      toggle: vi.fn(),
      remove: vi.fn(),
      clear: vi.fn(),
      exportJson: vi.fn(),
    };

    render(<PinnedTab pinned={pinned} />);

    expect(screen.getByText('Development ↓')).toBeTruthy();
    expect(screen.getByText('S 91')).toBeTruthy();
    expect(screen.getByText('Legacy 82')).toBeTruthy();
    expect(screen.getByText('Refinery / Industrial Megacomplex')).toBeTruthy();
  });
});
