import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { SystemDetail } from '@/types/api';
import { useSystemDetail } from '@/features/system-detail/useSystemDetail';
import { SimulationPreviewPanel } from '@/features/system-detail/SimulationPreviewPanel';
import { ColonyPlannerWorkspace } from './ColonyPlannerWorkspace';

vi.mock('@/features/system-detail/useSystemDetail', () => ({
  useSystemDetail: vi.fn(),
}));

vi.mock('@/features/system-detail/SimulationPreviewPanel', () => ({
  SimulationPreviewPanel: vi.fn(() => <div>Reused Colony Planner panel</div>),
}));

const mockedUseSystemDetail = vi.mocked(useSystemDetail);
const mockedSimulationPreviewPanel = vi.mocked(SimulationPreviewPanel);

const system = {
  id64: 123,
  name: 'Workspace System',
  x: 1,
  y: 2,
  z: 3,
  population: 0,
  is_colonised: false,
  primary_economy: 'Agriculture',
  economy_suggestion: 'Refinery',
} as unknown as SystemDetail;

describe('ColonyPlannerWorkspace', () => {
  beforeEach(() => {
    mockedUseSystemDetail.mockReturnValue({
      data: null,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });
  });

  afterEach(() => {
    mockedUseSystemDetail.mockReset();
    mockedSimulationPreviewPanel.mockClear();
  });

  it('renders a no-system state for direct #colony-planner visits', () => {
    const onBackToFinder = vi.fn();

    render(
      <ColonyPlannerWorkspace
        id64={null}
        onBackToFinder={onBackToFinder}
        onOpenSystemDetail={vi.fn()}
      />,
    );

    expect(screen.getByTestId('colony-planner-workspace')).toBeTruthy();
    expect(screen.getByText('No system selected for Colony Planner.')).toBeTruthy();
    expect(screen.getByText(/Choose Evaluate in Colony Planner from Finder or Advanced Search Tuning/i)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Back to Finder/i }));
    expect(onBackToFinder).toHaveBeenCalledTimes(1);
    expect(mockedSimulationPreviewPanel).not.toHaveBeenCalled();
  });

  it('renders the loading state without mounting the planner', () => {
    mockedUseSystemDetail.mockReturnValue({
      data: null,
      loading: true,
      error: null,
      refetch: vi.fn(),
    });

    render(
      <ColonyPlannerWorkspace
        id64={123}
        onBackToFinder={vi.fn()}
        onOpenSystemDetail={vi.fn()}
      />,
    );

    expect(screen.getByText('Loading Colony Planner...')).toBeTruthy();
    expect(mockedUseSystemDetail).toHaveBeenCalledWith(123);
    expect(mockedSimulationPreviewPanel).not.toHaveBeenCalled();
  });

  it('renders the error state with retry and Back to Finder', () => {
    const onBackToFinder = vi.fn();
    const refetch = vi.fn();
    mockedUseSystemDetail.mockReturnValue({
      data: null,
      loading: false,
      error: 'network failed',
      refetch,
    });

    render(
      <ColonyPlannerWorkspace
        id64={123}
        onBackToFinder={onBackToFinder}
        onOpenSystemDetail={vi.fn()}
      />,
    );

    expect(screen.getByText('Failed to load Colony Planner.')).toBeTruthy();
    expect(screen.getByText('network failed')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Retry/i }));
    fireEvent.click(screen.getAllByRole('button', { name: /Back to Finder/i })[1]);
    expect(refetch).toHaveBeenCalledTimes(1);
    expect(onBackToFinder).toHaveBeenCalledTimes(1);
    expect(mockedSimulationPreviewPanel).not.toHaveBeenCalled();
  });

  it('renders loaded system context and reuses SimulationPreviewPanel', () => {
    const onOpenSystemDetail = vi.fn();
    mockedUseSystemDetail.mockReturnValue({
      data: system,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(
      <ColonyPlannerWorkspace
        id64={123}
        onBackToFinder={vi.fn()}
        onOpenSystemDetail={onOpenSystemDetail}
      />,
    );

    expect(screen.getByText('Workspace System')).toBeTruthy();
    expect(screen.getByText('Refinery')).toBeTruthy();
    expect(screen.getByText(/Nothing runs or loads automatically/i)).toBeTruthy();
    expect(screen.getByText('Reused Colony Planner panel')).toBeTruthy();
    expect(mockedSimulationPreviewPanel).toHaveBeenCalledWith(
      expect.objectContaining({ system, selectedPlan: null }),
      undefined,
    );

    fireEvent.click(screen.getByRole('button', { name: /Open full system detail/i }));
    expect(onOpenSystemDetail).toHaveBeenCalledTimes(1);
    expect(onOpenSystemDetail).toHaveBeenCalledWith(123);
  });
});
