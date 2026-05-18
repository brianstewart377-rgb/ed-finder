import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { FacilityTemplate, SimulateBuildPlacement, SystemDetail } from '@/types/api';
import { useSystemDetail } from '@/features/system-detail/useSystemDetail';
import { SimulationPreviewPanel } from '@/features/system-detail/SimulationPreviewPanel';
import { ColonyPlannerWorkspace } from './ColonyPlannerWorkspace';
import { ColonyTopologyRail } from './ColonyTopologyRail';

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

const bodiesSystem = {
  ...system,
  bodies: [
    { id: 1, name: 'Primary Star', body_type: 'Star', distance_from_star: 0 },
    { id: 2, name: 'A 1', body_type: 'Planet', subtype: 'High metal content world', is_landable: true, distance_from_star: 120 },
    { id: 3, name: 'A 1 a', body_type: 'Planet', is_landable: false, parent_id: 2, distance_from_star: 121 },
    { id: 4, name: null, body_type: null, subtype: null, is_landable: null },
  ],
} as unknown as SystemDetail;

const templates: FacilityTemplate[] = [
  {
    id: 'orbital_port',
    name: 'Orbital Port',
    category: 'port',
    tier: 1,
    economy: 'Refinery',
    is_port: true,
    is_support_facility: false,
    allowed_location: 'orbital',
    pad_size: 'large',
    confidence: 'confirmed',
    notes: null,
    yellow_cp_generated: 2,
    green_cp_generated: 0,
    yellow_cp_cost: 0,
    green_cp_cost: 0,
  },
  {
    id: 'surface_hab',
    name: 'Surface Habitat',
    category: 'habitation',
    tier: 1,
    economy: null,
    is_port: false,
    is_support_facility: true,
    allowed_location: 'surface',
    pad_size: null,
    confidence: 'estimated',
    notes: null,
    yellow_cp_generated: 0,
    green_cp_generated: 1,
    yellow_cp_cost: 1,
    green_cp_cost: 0,
  },
];

const placements: SimulateBuildPlacement[] = [
  { facility_template_id: 'orbital_port', local_body_id: '2', is_primary_port: true, build_order: 1 },
  { facility_template_id: 'surface_hab', local_body_id: '2', build_order: 2 },
  { facility_template_id: 'surface_hab', local_body_id: null, build_order: 3 },
  { facility_template_id: 'surface_hab', local_body_id: '404', build_order: 4 },
];

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

    expect(screen.getAllByText('Workspace System').length).toBeGreaterThan(0);
    expect(screen.getByText('Refinery')).toBeTruthy();
    expect(screen.getByText(/Nothing runs or loads automatically/i)).toBeTruthy();
    expect(screen.getByText('Reused Colony Planner panel')).toBeTruthy();
    expect(mockedSimulationPreviewPanel).toHaveBeenCalledWith(
      expect.objectContaining({ system, selectedPlan: null, onPlanContextChange: expect.any(Function) }),
      undefined,
    );

    fireEvent.click(screen.getByRole('button', { name: /Open full system detail/i }));
    expect(onOpenSystemDetail).toHaveBeenCalledTimes(1);
    expect(onOpenSystemDetail).toHaveBeenCalledWith(123);
  });

  it('shows selected body context in the read-only workspace summary', () => {
    mockedUseSystemDetail.mockReturnValue({
      data: bodiesSystem,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    const onOpenSystemDetail = vi.fn();
    render(
      <ColonyPlannerWorkspace
        id64={123}
        onBackToFinder={vi.fn()}
        onOpenSystemDetail={onOpenSystemDetail}
      />,
    );

    fireEvent.click(screen.getByTestId('topology-body-2'));
    expect(screen.getAllByText('A 1').length).toBeGreaterThan(0);
    expect(screen.getByText('Read-only topology selection')).toBeTruthy();
    expect(onOpenSystemDetail).not.toHaveBeenCalled();
  });
});

describe('ColonyTopologyRail', () => {
  it('renders body rows, placement counts, metadata chips, and unknown/unassigned groups', () => {
    render(
      <ColonyTopologyRail
        system={bodiesSystem}
        planContext={{ placements, templates }}
        selection={{ kind: 'system' }}
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByTestId('topology-body-2')).toBeTruthy();
    expect(screen.getByText('A 1 a')).toBeTruthy();
    expect(screen.getByText('2 planned')).toBeTruthy();
    expect(screen.getByText('orbital 1')).toBeTruthy();
    expect(screen.getByText('surface 1')).toBeTruthy();
    expect(screen.getByText('primary port')).toBeTruthy();
    expect(screen.getByText('sparse metadata')).toBeTruthy();
    expect(screen.getByText('Unknown / unmatched body')).toBeTruthy();
    expect(screen.getByText('Unassigned placements')).toBeTruthy();
  });

  it('selects bodies and placements without invoking planner action callbacks', () => {
    const onSelect = vi.fn();
    render(
      <ColonyTopologyRail
        system={bodiesSystem}
        planContext={{ placements, templates }}
        selection={{ kind: 'body', bodyId: '2' }}
        onSelect={onSelect}
      />,
    );

    fireEvent.click(screen.getByTestId('topology-body-2'));
    fireEvent.click(screen.getByRole('button', { name: /Orbital Port/i }));

    expect(onSelect).toHaveBeenCalledWith({ kind: 'body', bodyId: '2' });
    expect(onSelect).toHaveBeenCalledWith({ kind: 'placement', bodyId: '2', placementIndex: 0 });
    expect(mockedSimulationPreviewPanel).not.toHaveBeenCalled();
  });

  it('renders the friendly empty body state', () => {
    render(
      <ColonyTopologyRail
        system={{ ...system, bodies: [] } as unknown as SystemDetail}
        planContext={{ placements: [], templates }}
        selection={{ kind: 'system' }}
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByText('No body layout imported yet. Use the planner tools to import/refresh layout when available.')).toBeTruthy();
  });
});
