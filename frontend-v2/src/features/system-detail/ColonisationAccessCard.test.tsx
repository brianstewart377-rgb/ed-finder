import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getRegionalAnalysis } from '@/lib/api';
import type { SystemDetail } from '@/types/api';
import { ColonisationAccessCard } from './ColonisationAccessCard';

vi.mock('@/lib/api', () => ({
  getRegionalAnalysis: vi.fn(),
}));

const mockedGetRegionalAnalysis = vi.mocked(getRegionalAnalysis);
const system = { id64: 123, name: 'Locked Target' } as SystemDetail;

function renderCard(onStartCorridorPlan = vi.fn()) {
  render(<ColonisationAccessCard system={system} onStartCorridorPlan={onStartCorridorPlan} />);
  return onStartCorridorPlan;
}

describe('ColonisationAccessCard', () => {
  afterEach(() => {
    mockedGetRegionalAnalysis.mockReset();
  });

  it('shows nearest-colony distance while leaving an unverified bridge count unavailable', async () => {
    mockedGetRegionalAnalysis.mockResolvedValue({
      system_id64: 123,
      mechanics_version: 'test',
      nearest_colonised_system: { id64: 456, name: 'Frontier Start', distance_ly: 74.2 },
      counts: { within_25ly: 0, within_50ly: 0, within_100ly: 1, within_250ly: 4 },
      scores: { isolation: 0, density: 0, expansion: 0, competition: 0 },
      regional_role: 'frontier_hub',
      archetype_regional_fit: {},
      rationale: { summary: '', strengths: [], warnings: [], archetype_notes: {} },
      data_quality: { regional_position: 'inferred' },
      confidence_signals: [],
      computed_at: null,
    });

    renderCard();

    await screen.findByText('Frontier Start');
    const card = screen.getByTestId('colonisation-access-card');
    expect(card.textContent).toContain('74.2 LY away');
    expect(card.textContent).toContain('Minimum bridge unavailable');
    expect(card.textContent).toContain('Route search not run');
    expect(card.textContent).not.toContain('verified route');
  });

  it('keeps the selected system as the corridor destination', () => {
    mockedGetRegionalAnalysis.mockResolvedValue({
      system_id64: 123,
      mechanics_version: 'test',
      nearest_colonised_system: null,
      counts: { within_25ly: 0, within_50ly: 0, within_100ly: 0, within_250ly: 0 },
      scores: { isolation: 0, density: 0, expansion: 0, competition: 0 },
      regional_role: 'unknown',
      archetype_regional_fit: {},
      rationale: { summary: '', strengths: [], warnings: [], archetype_notes: {} },
      data_quality: { regional_position: 'unknown' },
      confidence_signals: [],
      computed_at: null,
    });
    const onStartCorridorPlan = renderCard();

    fireEvent.click(screen.getByTestId('start-corridor-plan'));

    expect(onStartCorridorPlan).toHaveBeenCalledWith(system);
    expect(onStartCorridorPlan).toHaveBeenCalledTimes(1);
  });
});
