import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { SystemDetail } from '@/types/api';
import { useSystemDetail } from './useSystemDetail';
import { SystemDetailModal } from './SystemDetailModal';

vi.mock('./useSystemDetail', () => ({
  useSystemDetail: vi.fn(),
}));

vi.mock('./RatingRadar', () => ({ RatingRadar: () => <div>Rating radar</div> }));
const {
  mockBuildabilityPanel,
  mockSlotPredictionPanel,
  mockRecommendedBuildsPanel,
  mockSimulationPreviewPanel,
  mockRegionalPositionPanel,
} = vi.hoisted(() => ({
  mockBuildabilityPanel: vi.fn(() => <div>Buildability panel</div>),
  mockSlotPredictionPanel: vi.fn(() => <div>Slot prediction panel</div>),
  mockRecommendedBuildsPanel: vi.fn(() => <div>Recommended builds panel</div>),
  mockSimulationPreviewPanel: vi.fn(() => <div>Embedded Colony Planner</div>),
  mockRegionalPositionPanel: vi.fn(() => <div>Regional position panel</div>),
}));

vi.mock('./BuildabilityPanel', () => ({ BuildabilityPanel: mockBuildabilityPanel }));
vi.mock('./SlotPredictionPanel', () => ({ SlotPredictionPanel: mockSlotPredictionPanel }));
vi.mock('./RecommendedBuildsPanel', () => ({ RecommendedBuildsPanel: mockRecommendedBuildsPanel }));
vi.mock('./SimulationPreviewPanel', () => ({ SimulationPreviewPanel: mockSimulationPreviewPanel }));
vi.mock('./RegionalPositionPanel', () => ({ RegionalPositionPanel: mockRegionalPositionPanel }));

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

function mockLoadedSystem(overrides: Partial<SystemDetail> = {}) {
  mockedUseSystemDetail.mockReturnValue({
    data: { ...system, ...overrides } as SystemDetail,
    loading: false,
    error: null,
    refetch: vi.fn(),
  });
}

describe('SystemDetailModal Colony Planner entry point', () => {
  afterEach(() => {
    mockedUseSystemDetail.mockReset();
    mockBuildabilityPanel.mockClear();
    mockSlotPredictionPanel.mockClear();
    mockRecommendedBuildsPanel.mockClear();
    mockSimulationPreviewPanel.mockClear();
    mockRegionalPositionPanel.mockClear();
    vi.restoreAllMocks();
  });

  it('renders a compact Colony Planner entry card on System Detail', () => {
    mockLoadedSystem();

    render(
      <SystemDetailModal
        id64={123}
        onClose={() => undefined}
        onOpenColonyPlanner={() => undefined}
      />,
    );

    expect(screen.getByTestId('colony-planner-entry-card')).toBeTruthy();
    expect(screen.getByText('Workspace available')).toBeTruthy();
    expect(
      screen.getByText(
        /Open the Colony Planner to create, compare, preview, and validate a build plan for this system/i,
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Suggested builds can be reviewed in the Colony Planner/i)).toBeTruthy();
    expect(screen.getAllByText('Test System').length).toBeGreaterThan(0);
    expect(screen.getByText('ID64 123')).toBeTruthy();
  });

  it('opens the dedicated Colony Planner workspace through the existing route handler', () => {
    const onOpenColonyPlanner = vi.fn();
    mockLoadedSystem();

    render(
      <SystemDetailModal
        id64={123}
        onClose={() => undefined}
        onOpenColonyPlanner={onOpenColonyPlanner}
      />,
    );

    fireEvent.click(screen.getByTestId('open-colony-planner'));

    expect(onOpenColonyPlanner).toHaveBeenCalledTimes(1);
    expect(onOpenColonyPlanner).toHaveBeenCalledWith(123);
  });

  it('does not render the full planner stack inline on System Detail', () => {
    mockLoadedSystem();

    render(
      <SystemDetailModal
        id64={123}
        onClose={() => undefined}
        onOpenColonyPlanner={() => undefined}
      />,
    );

    expect(screen.queryByText('Buildability panel')).toBeNull();
    expect(screen.queryByText('Regional position panel')).toBeNull();
    expect(screen.queryByText('Recommended builds panel')).toBeNull();
    expect(screen.queryByText('Embedded Colony Planner')).toBeNull();
    expect(screen.queryByText('Slot prediction panel')).toBeNull();
    expect(screen.queryByText('Colony Planning')).toBeNull();
    expect(screen.queryByText('Observed Evidence')).toBeNull();
    expect(screen.queryByText('Validation')).toBeNull();
    expect(screen.queryByTestId('colony-planner-focus-target')).toBeNull();
    expect(mockBuildabilityPanel).not.toHaveBeenCalled();
    expect(mockRegionalPositionPanel).not.toHaveBeenCalled();
    expect(mockRecommendedBuildsPanel).not.toHaveBeenCalled();
    expect(mockSimulationPreviewPanel).not.toHaveBeenCalled();
    expect(mockSlotPredictionPanel).not.toHaveBeenCalled();
  });

  it('keeps the normal System Detail overview visible', () => {
    mockLoadedSystem();

    render(
      <SystemDetailModal
        id64={123}
        onClose={() => undefined}
        onOpenColonyPlanner={() => undefined}
      />,
    );

    expect(screen.getByText('Rating radar')).toBeTruthy();
    expect(screen.getByText('System info')).toBeTruthy();
    expect(screen.getByText('Coordinates')).toBeTruthy();
    expect(screen.getByText('External')).toBeTruthy();
  });

  it('shows a friendly disabled planner state when no workspace handler is available', () => {
    mockLoadedSystem();

    render(<SystemDetailModal id64={123} onClose={() => undefined} />);

    expect(screen.getByText('Planner unavailable')).toBeTruthy();
    expect(screen.getByText(/Planner route is unavailable for this system record/i)).toBeTruthy();
    expect((screen.getByTestId('open-colony-planner') as HTMLButtonElement).disabled).toBe(true);
  });

  it('does not expose raw backend errors in the compact System Detail error state', () => {
    mockedUseSystemDetail.mockReturnValue({
      data: null,
      loading: false,
      error: '{"trace":"backend exploded"}',
      refetch: vi.fn(),
    });

    render(<SystemDetailModal id64={123} onClose={() => undefined} />);

    expect(screen.getByText(/System detail is unavailable right now/i)).toBeTruthy();
    expect(screen.queryByText(/backend exploded/i)).toBeNull();
  });

  it('keeps normal modal close behaviours working without an embedded planner target', () => {
    const onClose = vi.fn();
    mockLoadedSystem();

    render(
      <SystemDetailModal
        id64={123}
        onClose={onClose}
        onOpenColonyPlanner={() => undefined}
      />,
    );

    expect(screen.queryByTestId('colony-planner-focus-target')).toBeNull();
    fireEvent.click(screen.getByTestId('system-detail-close'));
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(2);

    fireEvent.click(screen.getByTestId('system-detail-modal'));
    expect(onClose).toHaveBeenCalledTimes(3);
  });
});
