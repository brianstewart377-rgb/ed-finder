import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { SystemDetail } from '@/types/api';
import { useSystemDetail } from './useSystemDetail';
import { SystemDetailModal } from './SystemDetailModal';

vi.mock('./useSystemDetail', () => ({
  useSystemDetail: vi.fn(),
}));

vi.mock('./RatingRadar', () => ({ RatingRadar: () => <div>Rating radar</div> }));
vi.mock('./BuildabilityPanel', () => ({ BuildabilityPanel: () => <div>Buildability panel</div> }));
vi.mock('./SlotPredictionPanel', () => ({ SlotPredictionPanel: () => <div>Slot prediction panel</div> }));
vi.mock('./RecommendedBuildsPanel', () => ({ RecommendedBuildsPanel: () => <div>Recommended builds panel</div> }));
vi.mock('./SimulationPreviewPanel', () => ({ SimulationPreviewPanel: () => <div>Embedded Colony Planner</div> }));
vi.mock('./RegionalPositionPanel', () => ({ RegionalPositionPanel: () => <div>Regional position panel</div> }));

const mockedUseSystemDetail = vi.mocked(useSystemDetail);

const system = {
  id64: 123,
  name: 'Test System',
  x: 1,
  y: 2,
  z: 3,
  bodies: [],
  stations: [],
} as unknown as SystemDetail;

describe('SystemDetailModal Colony Planner entry point', () => {
  afterEach(() => {
    mockedUseSystemDetail.mockReset();
    vi.restoreAllMocks();
  });

  it('renders a prominent Open Colony Planner CTA and focuses the embedded planner', async () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    mockedUseSystemDetail.mockReturnValue({
      data: system,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<SystemDetailModal id64={123} onClose={() => undefined} />);

    expect(screen.getByTestId('open-colony-planner')).toBeTruthy();
    expect(screen.getByText(/start from Suggested Builds/i)).toBeTruthy();

    fireEvent.click(screen.getByTestId('open-colony-planner'));

    const target = screen.getByTestId('colony-planner-focus-target');
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' });
    expect(document.activeElement).toBe(target);
  });

  it('honours Search Tuning focus intent when the modal opens', async () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    mockedUseSystemDetail.mockReturnValue({
      data: system,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<SystemDetailModal id64={123} focusIntent="colony-planner" onClose={() => undefined} />);

    await waitFor(() => expect(scrollIntoView).toHaveBeenCalled());
    expect(document.activeElement).toBe(screen.getByTestId('colony-planner-focus-target'));
  });
});
