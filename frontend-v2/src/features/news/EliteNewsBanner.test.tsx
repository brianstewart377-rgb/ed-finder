import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { EliteNewsBanner } from './EliteNewsBanner';
import { useEliteNewsFeed } from './useEliteNewsFeed';

vi.mock('./useEliteNewsFeed', () => ({
  useEliteNewsFeed: vi.fn(),
}));

const mockedUseEliteNewsFeed = vi.mocked(useEliteNewsFeed);

describe('EliteNewsBanner', () => {
  it('renders an offline fallback when official headlines are unavailable', () => {
    mockedUseEliteNewsFeed.mockReturnValue({
      items: [],
      status: 'offline',
      stale: false,
    });

    render(<EliteNewsBanner />);

    expect(screen.getByTestId('elite-news-banner')).toBeTruthy();
    expect(screen.getByText('offline')).toBeTruthy();
    expect(screen.getByText('Official Elite Dangerous headlines unavailable')).toBeTruthy();
  });

  it('renders headline links and stale state labels', () => {
    mockedUseEliteNewsFeed.mockReturnValue({
      items: [{
        title: 'June Dev Log 2026',
        url: 'https://www.elitedangerous.com/news/elite-dangerous-june-dev-log-2026',
        source: 'news',
      }],
      status: 'live',
      stale: true,
    });

    render(<EliteNewsBanner />);

    expect(screen.getByText('cached headlines')).toBeTruthy();
    expect(
      screen.getByTestId('elite-news-link-0').getAttribute('href'),
    ).toBe('https://www.elitedangerous.com/news/elite-dangerous-june-dev-log-2026');
  });
});
