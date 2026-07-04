import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getRegionalAnalysis } from '@/lib/api';
import type { SystemDetail } from '@/types/api';
import { useSystemDetail } from './useSystemDetail';
import { SystemDetailModal } from './SystemDetailModal';

vi.mock('./useSystemDetail', () => ({
  useSystemDetail: vi.fn(),
}));
vi.mock('./RatingRadar', () => ({ RatingRadar: () => <div>Rating radar</div> }));
vi.mock('@/lib/api', () => ({
  getRegionalAnalysis: vi.fn(),
}));

const mockedUseSystemDetail = vi.mocked(useSystemDetail);
const mockedGetRegionalAnalysis = vi.mocked(getRegionalAnalysis);
const system = {
  id64: 123,
  name: 'Blu Thua JS-J D9-1',
  x: 1,
  y: 2,
  z: 3,
  bodies: [],
  stations: [],
} as unknown as SystemDetail;

describe('SystemDetailModal colonisation access handoff', () => {
  afterEach(() => {
    mockedUseSystemDetail.mockReset();
    mockedGetRegionalAnalysis.mockReset();
  });

  it('starts a destination-first corridor plan for the selected system without substituting a target', () => {
    mockedUseSystemDetail.mockReturnValue({
      data: system,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });
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
    const onStartPlan = vi.fn();

    render(<SystemDetailModal id64={123} onClose={() => undefined} onStartPlan={onStartPlan} />);

    fireEvent.click(screen.getByTestId('start-corridor-plan'));

    expect(onStartPlan).toHaveBeenCalledTimes(1);
    expect(onStartPlan).toHaveBeenCalledWith(
      expect.objectContaining({ id64: 123, name: 'Blu Thua JS-J D9-1' }),
      {
        objective: 'destination_first_corridor',
        startApproach: 'destination_first_corridor',
      },
    );
  });
});
