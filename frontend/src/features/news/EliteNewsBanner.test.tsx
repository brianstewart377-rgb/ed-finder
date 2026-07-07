import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { EliteNewsBar } from './EliteNewsBar';
import { useEliteNewsFeed } from './useEliteNewsFeed';

vi.mock('./useEliteNewsFeed', () => ({
  useEliteNewsFeed: vi.fn(),
}));

const mockedUseEliteNewsFeed = vi.mocked(useEliteNewsFeed);

describe('EliteNewsBar', () => {
  it('renders an offline fallback when official headlines are unavailable', () => {
    mockedUseEliteNewsFeed.mockReturnValue({
      items: [],
      status: 'offline',
      stale: false,
    });

    render(<EliteNewsBar />);

    expect(screen.getByTestId('elite-news-banner')).toBeTruthy();
    expect(screen.getByText('offline')).toBeTruthy();
    expect(screen.getByText('Official feed unavailable right now. Quick links stay available below.')).toBeTruthy();
    expect(screen.getByTestId('elite-news-link-0').getAttribute('href')).toBe('https://www.elitedangerous.com/news');
    expect(screen.getByTestId('elite-news-link-1').getAttribute('href')).toBe('https://www.elitedangerous.com/en-US/Galnet');
    expect(screen.getAllByRole('link')).toHaveLength(2);
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

    render(<EliteNewsBar />);

    expect(screen.getByText('cached headlines')).toBeTruthy();
    expect(
      screen.getByTestId('elite-news-link-0').getAttribute('href'),
    ).toBe('https://www.elitedangerous.com/news/elite-dangerous-june-dev-log-2026');
  });
});
