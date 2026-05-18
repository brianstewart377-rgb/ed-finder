import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { SystemDetail } from '@/types/api';
import { useSystemDetail } from '@/features/system-detail/useSystemDetail';
import { SimulationPreviewPanel } from '@/features/system-detail/SimulationPreviewPanel';
import { ColonyPlannerWorkspace } from './ColonyPlannerWorkspace';
import { useColonyProjectStore } from './colonyProjectStore';

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
    localStorage.clear();
    useColonyProjectStore.setState({ projects: [] });
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
    localStorage.clear();
    useColonyProjectStore.setState({ projects: [] });
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

  it('renders the workspace shell, summary cards, topology rail, and reused SimulationPreviewPanel', async () => {
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
    expect(screen.getByTestId('project-card')).toBeTruthy();
    expect(screen.getByTestId('plan-health-card')).toBeTruthy();
    expect(screen.getByTestId('selection-card')).toBeTruthy();
    expect(screen.getByTestId('architect-card')).toBeTruthy();
    expect(screen.getByTestId('workspace-modes-card')).toBeTruthy();
    expect(screen.getByText('Workspace System A 1')).toBeTruthy();
    expect(screen.getByText('Reused Colony Planner panel')).toBeTruthy();
    expect(await screen.findByText('Unknown / unmatched body')).toBeTruthy();
    expect(screen.getByText('Unassigned placements')).toBeTruthy();
    expect(screen.getByText(/Saved projects are stored locally in this browser/i)).toBeTruthy();
    expect(screen.getByText(/They are not cloud-synced/i)).toBeTruthy();
    expect(screen.getByText(/Architect flag not recorded/)).toBeTruthy();
    const summaryPanel = screen.getByTestId('planner-summary-panel');
    expect(within(screen.getByTestId('plan-health-card')).getByText('Placements')).toBeTruthy();
    expect(within(summaryPanel).getAllByText('3').length).toBeGreaterThan(0);
    expect(within(screen.getByTestId('plan-health-card')).getByText('Unassigned')).toBeTruthy();
    expect(within(screen.getByTestId('plan-health-card')).getByText('Warnings')).toBeTruthy();
    expect(within(screen.getByTestId('plan-health-card')).getByText('Refinery / Industrial Plan')).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/Stage 15|15H|15I|deferred to next stages/i);
    expect(mockedSimulationPreviewPanel).toHaveBeenCalledWith(
      expect.objectContaining({
        system,
        selectedPlan: null,
        onPlanSnapshotChange: expect.any(Function),
        topologySelection: { type: 'system' },
        initialRequest: null,
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
    expect(screen.getByTestId('planning-focus-banner').textContent).toContain('Planning focus: Workspace System A 1');
    expect(screen.getByText(/Build Plan editing stays in the central planner/i)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /Back to system detail/i }));
    expect(onOpenSystemDetail).toHaveBeenCalledTimes(1);
    expect(onOpenSystemDetail).toHaveBeenCalledWith(123);
  });

  it('opens review drawers from workspace modes without running planner side effects', async () => {
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
        onOpenSystemDetail={vi.fn()}
      />,
    );

    await screen.findByTestId('workspace-modes-card');
    fireEvent.click(screen.getByRole('button', { name: 'Evidence drawer' }));
    expect(mockedSimulationPreviewPanel).toHaveBeenLastCalledWith(
      expect.objectContaining({ workspaceDrawer: 'evidence' }),
      undefined,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Validation drawer' }));
    expect(mockedSimulationPreviewPanel).toHaveBeenLastCalledWith(
      expect.objectContaining({ workspaceDrawer: 'validation' }),
      undefined,
    );
  });

  it('saves, renames, duplicates, and archives a local Colony Project with confirmation', async () => {
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
        onOpenSystemDetail={vi.fn()}
      />,
    );

    expect(await screen.findByTestId('project-card')).toBeTruthy();
    expect(screen.getByTestId('project-unsaved-indicator').textContent).toContain('Unsaved changes');

    fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'Local starter' } });
    fireEvent.change(screen.getByLabelText('Project notes'), { target: { value: 'Check Architect mode before final placement.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save project' }));

    expect(screen.getByTestId('project-unsaved-indicator').textContent).toContain('Saved');
    expect(useColonyProjectStore.getState().projects[0].project_name).toBe('Local starter');
    expect(useColonyProjectStore.getState().projects[0].build_plan_placements).toHaveLength(3);

    fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'Renamed local starter' } });
    fireEvent.click(screen.getByRole('button', { name: 'Rename project' }));
    expect(useColonyProjectStore.getState().projects[0].project_name).toBe('Renamed local starter');

    fireEvent.click(screen.getByRole('button', { name: 'Duplicate project' }));
    expect(useColonyProjectStore.getState().projects[0].project_name).toBe('Renamed local starter copy');

    fireEvent.click(screen.getByRole('button', { name: 'Delete / archive project' }));
    expect(screen.getByText(/Archive this local project/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Archive project' }));
    expect(useColonyProjectStore.getState().projects[0].archived_at).toBeTruthy();
  });

  it('restores the latest saved local project into the workspace on reload', async () => {
    useColonyProjectStore.getState().saveProject(null, {
      system_id64: 123,
      system_name: 'Workspace System',
      project_name: 'Reloaded project',
      build_plan_placements: [
        { facility_template_id: 'surface_hub', local_body_id: 'body1', is_primary_port: false, build_order: 1 },
      ],
      target_archetype: 'tourism_agriculture',
      notes: 'Reload me.',
    });
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
        onOpenSystemDetail={vi.fn()}
      />,
    );

    expect((await screen.findAllByText('Reloaded project')).length).toBeGreaterThan(0);
    expect(mockedSimulationPreviewPanel).toHaveBeenLastCalledWith(
      expect.objectContaining({
        initialRequest: {
          system_id64: 123,
          target_archetype: 'tourism_agriculture',
          placements: [
            { facility_template_id: 'surface_hub', local_body_id: 'body1', is_primary_port: false, build_order: 1 },
          ],
        },
      }),
      undefined,
    );
  });
});
