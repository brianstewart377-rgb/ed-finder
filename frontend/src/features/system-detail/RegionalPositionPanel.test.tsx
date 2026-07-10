import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getRegionalAnalysis } from '@/lib/api';
import { RegionalPositionPanel } from './RegionalPositionPanel';
import type { RegionalAnalysisResponse } from '@/types/api';

vi.mock('@/lib/api', () => ({
  getRegionalAnalysis: vi.fn(),
}));

const mockedGetRegionalAnalysis = vi.mocked(getRegionalAnalysis);

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <RegionalPositionPanel id64={123} />
    </QueryClientProvider>,
  );
}

describe('RegionalPositionPanel', () => {
  afterEach(() => {
    cleanup();
    mockedGetRegionalAnalysis.mockReset();
  });

  it('renders a loading state', () => {
    mockedGetRegionalAnalysis.mockReturnValue(new Promise(() => {}));

    renderPanel();

    expect(screen.getByTestId('regional-position-loading')).toBeTruthy();
  });

  it('renders an error state', async () => {
    mockedGetRegionalAnalysis.mockRejectedValue(new Error('regional table missing'));

    renderPanel();

    const errorPanel = await screen.findByTestId('regional-position-error', {}, { timeout: 3000 });
    expect(errorPanel.textContent).toContain('regional table missing');
  });

  it('renders an unknown state', async () => {
    mockedGetRegionalAnalysis.mockResolvedValue({
      system_id64: 123,
      mechanics_version: 'colonisation-engine-v2.1',
      claim_range_ly: 16,
      analysis_radius_ly: 250,
      nearest_colonised_system: null,
      counts: { within_25ly: 0, within_50ly: 0, within_100ly: 0, within_250ly: 0 },
      scores: { isolation: 0, density: 0, expansion: 0, competition: 0 },
      regional_role: 'unknown',
      archetype_regional_fit: {},
      rationale: { summary: 'Coordinates are missing.' },
      data_quality: { regional_position: 'unknown' },
      confidence_signals: [],
      computed_at: null,
    });

    renderPanel();

    expect((await screen.findByTestId('regional-position-unknown')).textContent).toContain('Coordinates are missing.');
  });

  it('renders regional metrics and archetype fit', async () => {
    mockedGetRegionalAnalysis.mockResolvedValue({
      system_id64: 123,
      mechanics_version: 'colonisation-engine-v2.1',
      claim_range_ly: 16,
      analysis_radius_ly: 250,
      nearest_colonised_system: { id64: 456, name: 'Frontier Stop', distance_ly: 74.2 },
      counts: { within_25ly: 0, within_50ly: 1, within_100ly: 3, within_250ly: 18 },
      scores: { isolation: 82, density: 31, expansion: 91, competition: 12 },
      regional_role: 'frontier_hub',
      archetype_regional_fit: {
        expansion_capital: 94,
        refinery_industrial: 86,
        hitech_tourism: 62,
      },
      rationale: {
        summary: 'Moderate isolation with enough nearby colonies for logistics.',
        strengths: ['Frontier access'],
        warnings: ['Tourism fit is mixed.'],
        archetype_notes: {},
      },
      data_quality: { regional_position: 'inferred' },
      confidence_signals: [{ area: 'regional_position', level: 'inferred', reason: 'Regional metrics are inferred.' }],
      computed_at: '2026-05-13T00:00:00Z',
    } satisfies RegionalAnalysisResponse);

    renderPanel();

    const panel = await screen.findByTestId('regional-position-success');
    expect(panel.textContent).toContain('Colonisation Proximity');
    expect(panel.textContent).toContain('Frontier Hub');
    expect(panel.textContent).toContain('Out of claim range');
    expect(panel.textContent).toContain('Frontier Stop');
    expect(panel.textContent).toContain('Inferred');
    expect(panel.textContent).toContain('94 regional fit');
    expect(panel.textContent).toContain('Tourism fit is mixed.');
    expect(panel.textContent).toContain('16 ly claim-range setting');
  });

  it('shows an in-range verdict when the nearest anchor is inside the claim range', async () => {
    mockedGetRegionalAnalysis.mockResolvedValue({
      system_id64: 123,
      mechanics_version: 'colonisation-engine-v2.1',
      claim_range_ly: 16,
      analysis_radius_ly: 250,
      nearest_colonised_system: { id64: 456, name: 'Claim Anchor', distance_ly: 11.2 },
      counts: { within_25ly: 1, within_50ly: 2, within_100ly: 4, within_250ly: 15 },
      scores: { isolation: 24, density: 76, expansion: 55, competition: 21 },
      regional_role: 'cluster_adjacent',
      archetype_regional_fit: {},
      rationale: {
        summary: 'Existing colonised support is already nearby.',
        strengths: [],
        warnings: [],
        archetype_notes: {},
      },
      data_quality: { regional_position: 'inferred' },
      confidence_signals: [{ area: 'regional_position', level: 'inferred', reason: 'Regional metrics are inferred.' }],
      computed_at: '2026-05-13T00:00:00Z',
    } satisfies RegionalAnalysisResponse);

    renderPanel();

    const verdict = await screen.findByTestId('regional-position-verdict');
    expect(verdict.textContent).toContain('Within claim range');
    expect(verdict.textContent).toContain('Claim Anchor');
    expect(verdict.textContent).toContain('11.2 ly');
  });

  it('shows an explicit bounded-search empty state when no anchor is present', async () => {
    mockedGetRegionalAnalysis.mockResolvedValue({
      system_id64: 123,
      mechanics_version: 'colonisation-engine-v2.1',
      claim_range_ly: 16,
      analysis_radius_ly: 250,
      nearest_colonised_system: null,
      counts: { within_25ly: 0, within_50ly: 0, within_100ly: 0, within_250ly: 0 },
      scores: { isolation: 95, density: 4, expansion: 88, competition: 1 },
      regional_role: 'isolated_frontier',
      archetype_regional_fit: {},
      rationale: {
        summary: 'Deep-space candidate with no nearby colonised support.',
        strengths: [],
        warnings: [],
        archetype_notes: {},
      },
      data_quality: { regional_position: 'inferred' },
      confidence_signals: [{ area: 'regional_position', level: 'inferred', reason: 'Regional metrics are inferred.' }],
      computed_at: '2026-05-13T00:00:00Z',
    } satisfies RegionalAnalysisResponse);

    renderPanel();

    const emptyState = await screen.findByTestId('regional-position-no-anchor');
    expect(emptyState.textContent).toContain('250 ly regional-analysis radius');
    expect(screen.getByTestId('regional-position-verdict').textContent).toContain('16 ly claim-range setting');
  });
});
