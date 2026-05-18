import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { SystemDetail } from '@/types/api';
import { useSystemDetail } from '@/features/system-detail/useSystemDetail';
import { SimulationPreviewPanel } from '@/features/system-detail/SimulationPreviewPanel';
import { ColonyPlannerWorkspace } from './ColonyPlannerWorkspace';

vi.mock('@/features/system-detail/useSystemDetail', () => ({
  useSystemDetail: vi.fn(),
}));

vi.mock('@/features/system-detail/SimulationPreviewPanel', async () => {
  const React = await import('react');
  return {
    SimulationPreviewPanel: vi.fn(({ onPlanSnapshotChange }) => {
      React.useEffect(() => {
        onPlanSnapshotChange?.({
          placements: [
            { facility_template_id: 'orbital_port', local_body_id: 'body1', is_primary_port: true, build_order: 1 },
            { facility_template_id: 'surface_hub', local_body_id: '404', build_order: 2 },
            { facility_template_id: 'surface_hub', local_body_id: null, build_order: 3 },
          ],
          templates: [
            {
              id: 'orbital_port',
              name: 'Orbital Port',
              category: 'port',
              tier: 3,
              economy: null,
              is_port: true,
              is_support_facility: false,
              allowed_location: 'orbital',
              pad_size: 'large',
              confidence: 'confirmed',
              notes: null,
              yellow_cp_generated: 1,
              green_cp_generated: 1,
              yellow_cp_cost: 0,
              green_cp_cost: 0,
            },
            {
              id: 'surface_hub',
              name: 'Surface Hub',
              category: 'support',
              tier: 1,
              economy: 'Extraction',
              is_port: false,
              is_support_facility: true,
              allowed_location: 'surface',
              pad_size: 'medium',
              confidence: 'confirmed',
              notes: null,
              yellow_cp_generated: 0,
              green_cp_generated: 0,
              yellow_cp_cost: 1,
              green_cp_cost: 0,
            },
          ],
          targetArchetype: 'refinery_industrial',
        });
      }, [onPlanSnapshotChange]);
      return <div>Reused Colony Planner panel</div>;
    }),
  };
});

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
  bodies: [
    { id: 'star1', name: 'Workspace System A', body_type: 'Star', subtype: 'K' },
    { id: 'body1', name: 'Workspace System A 1', body_type: 'Planet', subtype: 'Water world', is_water_world: true },
  ],
  stations: [],
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

  it('renders the Stage 15D workspace shell, topology rail, and reused SimulationPreviewPanel', async () => {
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

    expect(screen.getAllByText('Workspace System').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Refinery').length).toBeGreaterThan(0);
    expect(screen.getByTestId('planner-workspace-shell-v2')).toBeTruthy();
    expect(screen.getByTestId('planner-topology-sidebar')).toBeTruthy();
    expect(screen.getByTestId('workspace-planner-content')).toBeTruthy();
    expect(screen.getByTestId('planner-summary-panel')).toBeTruthy();
    expect(screen.getByText('System topology')).toBeTruthy();
    expect(screen.getByTestId('topology-root-row')).toBeTruthy();
    expect(screen.getByTestId('topology-body-body1')).toBeTruthy();
    expect(screen.getByText('Planning Workspace')).toBeTruthy();
    expect(screen.getByText('Planner summary')).toBeTruthy();
    expect(screen.getByText('Workspace System A 1')).toBeTruthy();
    expect(screen.getByText('Reused Colony Planner panel')).toBeTruthy();
    expect(await screen.findByText('Unknown / unmatched body')).toBeTruthy();
    expect(screen.getByText('Unassigned placements')).toBeTruthy();
    const summaryPanel = screen.getByTestId('planner-summary-panel');
    expect(within(summaryPanel).getByText('Plan placements')).toBeTruthy();
    expect(within(summaryPanel).getAllByText('3').length).toBeGreaterThan(0);
    expect(mockedSimulationPreviewPanel).toHaveBeenCalledWith(
      expect.objectContaining({
        system,
        selectedPlan: null,
        onPlanSnapshotChange: expect.any(Function),
        topologySelection: { type: 'system' },
      }),
      undefined,
    );

    fireEvent.click(screen.getByText('Workspace System A 1'));
    expect(mockedSimulationPreviewPanel).toHaveBeenLastCalledWith(
      expect.objectContaining({
        topologySelection: { type: 'body', bodyId: 'body1' },
      }),
      undefined,
    );
    expect(screen.getByText('Read-only topology selection')).toBeTruthy();
    expect(screen.getByText(/Build Plan editing stays in the central planner/i)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /Back to system detail/i }));
    expect(onOpenSystemDetail).toHaveBeenCalledTimes(1);
    expect(onOpenSystemDetail).toHaveBeenCalledWith(123);
  });
});
