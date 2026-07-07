import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { EddnTicker } from './EddnTicker';
import { useEddnFeed } from './useEddnFeed';

vi.mock('./useEddnFeed', () => ({
  useEddnFeed: vi.fn(),
}));

const mockedUseEddnFeed = vi.mocked(useEddnFeed);

describe('EddnTicker', () => {
  it('renders a compact reconnecting state without raw transport error text', () => {
    mockedUseEddnFeed.mockReturnValue({
      events: [],
      error: 'reconnecting',
      status: 'reconnecting',
    });

    render(<EddnTicker />);

    expect(screen.getByTestId('eddn-ticker')).toBeTruthy();
    expect(screen.getByText('reconnecting')).toBeTruthy();
    expect(screen.getByText('EDDN reconnecting')).toBeTruthy();
    expect(screen.queryByText(/SSE connection interrupted/i)).toBeNull();
  });

  it('renders compact offline state when no events are available', () => {
    mockedUseEddnFeed.mockReturnValue({
      events: [],
      error: 'offline',
      status: 'offline',
    });

    render(<EddnTicker />);

    expect(screen.getByText('offline')).toBeTruthy();
    expect(screen.getByText('EDDN temporarily offline')).toBeTruthy();
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
      status: 'live',
    });

    render(<EddnTicker onOpenSystem={onOpenSystem} />);

    expect(screen.getByText('live feed')).toBeTruthy();
    fireEvent.click(screen.getAllByTestId('eddn-pip-123')[0]);
    expect(onOpenSystem).toHaveBeenCalledWith(123);
  });
});
