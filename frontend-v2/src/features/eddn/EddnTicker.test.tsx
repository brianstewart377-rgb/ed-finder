import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { EddnTicker } from './EddnTicker';
import { useEddnFeed } from './useEddnFeed';

vi.mock('./useEddnFeed', () => ({
  useEddnFeed: vi.fn(),
}));

const mockedUseEddnFeed = vi.mocked(useEddnFeed);

describe('EddnTicker', () => {
  it('renders a compact reconnecting state without raw SSE error text', () => {
    mockedUseEddnFeed.mockReturnValue({
      events: [],
      error: 'SSE connection interrupted (auto-reconnect)',
    });

    render(<EddnTicker />);

    expect(screen.getByTestId('eddn-ticker')).toBeTruthy();
    expect(screen.getByText('reconnecting')).toBeTruthy();
    expect(screen.getByText('EDDN feed reconnecting')).toBeTruthy();
    expect(screen.queryByText(/SSE connection interrupted/i)).toBeNull();
  });

  it('renders live events and opens a system pip without crashing', () => {
    const onOpenSystem = vi.fn();
    mockedUseEddnFeed.mockReturnValue({
      events: [{
        id64: 123,
        system_name: 'Ticker System',
        type: 'FSDJump',
        timestamp: new Date().toISOString(),
      }],
      error: null,
    });

    render(<EddnTicker onOpenSystem={onOpenSystem} />);

    expect(screen.getByText('live feed')).toBeTruthy();
    fireEvent.click(screen.getAllByTestId('eddn-pip-123')[0]);
    expect(onOpenSystem).toHaveBeenCalledWith(123);
  });
});
