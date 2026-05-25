import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { SystemDetail } from '@/types/api';
import { economyColor } from '@/features/colony-planner/economyVisuals';
import { RatingRadar } from './RatingRadar';

// recharts uses ResizeObserver internally
vi.stubGlobal('ResizeObserver', class {
  observe() {}
  unobserve() {}
  disconnect() {}
});

const baseSys = {
  id64: 1,
  name: 'Test',
  x: 0, y: 0, z: 0,
  population: 0,
  bodies: [],
  stations: [],
  score: 82,
  score_agriculture: 45,
  score_refinery: 78,
  score_industrial: 60,
  score_hightech: 55,
  score_military: 30,
  score_tourism: 20,
  score_extraction: 65,
  economy_suggestion: 'Refinery',
  confidence: 0.85,
  rationale: 'Strong Refinery potential with 4 clean Rocky bodies.',
  rating_version: '3.4',
  primary_economy: 'Refinery',
  secondary_economy: 'Industrial',
  score_breakdown: {
    economies: {
      Agriculture: 45,
      Refinery: 78,
      Industrial: 60,
      HighTech: 55,
      Military: 30,
      Tourism: 20,
      Extraction: 65,
    },
    dimensions: {
      slots: 70,
      strategic: 55,
      safety: 80,
      terraforming: 30,
      diversity: 45,
    },
    top_pair: {
      a: 'Refinery',
      b: 'Industrial',
      a_score: 78,
      b_score: 60,
      pair_score: 82,
    },
    primary_economy: 'Refinery',
    secondary_economy: 'Industrial',
    has_standout: true,
    confidence: 0.85,
    rating_version: '3.4',
  },
} as unknown as SystemDetail;

describe('RatingRadar (Stage 17N.2)', () => {
  it('labels overall score as best-build potential', () => {
    render(<RatingRadar sys={baseSys} />);
    expect(screen.getByTestId('rating-headline').textContent).toContain('Best-build potential');
    expect(screen.getByTestId('rating-overall-score').textContent).toBe('82');
  });

  it('shows Extraction in the economy profile', () => {
    render(<RatingRadar sys={baseSys} />);
    expect(screen.getByTestId('rating-economy-extraction')).toBeTruthy();
    expect(screen.getByTestId('rating-economy-extraction').textContent).toContain('Extraction');
    expect(screen.getByTestId('rating-economy-bar-extraction').querySelector('span')?.getAttribute('data-economy-color')).toBe(economyColor('Extraction'));
  });

  it('shows top complementary pair when available', () => {
    render(<RatingRadar sys={baseSys} />);
    const topPair = screen.getByTestId('rating-top-pair');
    expect(topPair.textContent).toContain('Refinery');
    expect(topPair.textContent).toContain('Industrial');
  });

  it('shows confidence when available', () => {
    render(<RatingRadar sys={baseSys} />);
    const conf = screen.getByTestId('rating-confidence');
    expect(conf.textContent).toContain('High');
    expect(conf.textContent).toContain('85%');
  });

  it('shows confidence unknown when missing', () => {
    const sys = { ...baseSys, confidence: null } as unknown as SystemDetail;
    render(<RatingRadar sys={sys} />);
    expect(screen.getByTestId('rating-confidence-missing')).toBeTruthy();
    expect(screen.getByTestId('rating-confidence-missing').textContent).toContain('Confidence unknown');
  });

  it('shows rationale when available', () => {
    render(<RatingRadar sys={baseSys} />);
    expect(screen.getByTestId('rating-rationale')).toBeTruthy();
  });

  it('shows expandable dimension breakdown when breakdown data exists', () => {
    render(<RatingRadar sys={baseSys} />);
    const toggle = screen.getByTestId('rating-breakdown-toggle');
    expect(toggle).toBeTruthy();

    // Initially collapsed
    expect(screen.queryByTestId('rating-breakdown-panel')).toBeNull();

    // Click to expand
    fireEvent.click(toggle);
    expect(screen.getByTestId('rating-breakdown-panel')).toBeTruthy();
    expect(screen.getByTestId('rating-dim-slots')).toBeTruthy();
    expect(screen.getByTestId('rating-dim-strategic')).toBeTruthy();
    expect(screen.getByTestId('rating-dim-safety')).toBeTruthy();
    expect(screen.getByTestId('rating-dim-terraforming')).toBeTruthy();
    expect(screen.getByTestId('rating-dim-diversity')).toBeTruthy();
  });

  it('degrades gracefully when breakdown data is missing', () => {
    const sys = { ...baseSys, score_breakdown: null } as unknown as SystemDetail;
    render(<RatingRadar sys={sys} />);
    // Should still render headline, economy bars, etc.
    expect(screen.getByTestId('rating-headline')).toBeTruthy();
    expect(screen.getByTestId('rating-economy-extraction')).toBeTruthy();
    // No breakdown toggle
    expect(screen.queryByTestId('rating-breakdown-toggle')).toBeNull();
  });

  it('degrades gracefully when top pair is missing', () => {
    const sys = {
      ...baseSys,
      score_breakdown: { ...baseSys.score_breakdown as Record<string, unknown>, top_pair: null },
    } as unknown as SystemDetail;
    render(<RatingRadar sys={sys} />);
    expect(screen.queryByTestId('rating-top-pair')).toBeNull();
    // Rest still renders
    expect(screen.getByTestId('rating-headline')).toBeTruthy();
  });

  it('renders nothing when all scores are zero', () => {
    const sys = {
      ...baseSys,
      score: 0,
      score_agriculture: 0,
      score_refinery: 0,
      score_industrial: 0,
      score_hightech: 0,
      score_military: 0,
      score_tourism: 0,
      score_extraction: 0,
    } as unknown as SystemDetail;
    const { container } = render(<RatingRadar sys={sys} />);
    expect(container.innerHTML).toBe('');
  });

  it('score explanation text appears', () => {
    render(<RatingRadar sys={baseSys} />);
    expect(screen.getByText(/body mix, economy fit, strategic value/i)).toBeTruthy();
  });

  it('caveats saturated stored economy scores', () => {
    const sys = {
      ...baseSys,
      score_refinery: 100,
      score_industrial: 100,
      score_hightech: 100,
      score_military: 100,
    } as unknown as SystemDetail;
    render(<RatingRadar sys={sys} />);
    expect(screen.getByTestId('rating-caveat').textContent).toContain('Several economy scores are capped');
  });

  it('caveats missing rating version conservatively', () => {
    const sys = {
      ...baseSys,
      rating_version: null,
      score_breakdown: { ...baseSys.score_breakdown as Record<string, unknown>, rating_version: null },
    } as unknown as SystemDetail;

    render(<RatingRadar sys={sys} />);

    expect(screen.getByTestId('rating-caveat').textContent).toContain('predates the current scoring contract');
  });
});
