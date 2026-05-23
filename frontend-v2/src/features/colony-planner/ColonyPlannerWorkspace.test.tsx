import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { FacilityTemplate, SimulationSummary, SlotPredictionResponse, SystemDetail } from '@/types/api';
import { useSystemDetail } from '@/features/system-detail/useSystemDetail';
import { SimulationPreviewPanel } from '@/features/system-detail/SimulationPreviewPanel';
import { getFacilityTemplates, getSimulationSummary, getSlotPredictions } from '@/lib/api';
import { ColonyPlannerWorkspace } from './ColonyPlannerWorkspace';
import { useColonyProjectStore } from './colonyProjectStore';

vi.mock('@/features/system-detail/useSystemDetail', () => ({
  useSystemDetail: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  getFacilityTemplates: vi.fn(),
  getSimulationSummary: vi.fn(),
  getSlotPredictions: vi.fn(),
}));

vi.mock('@/features/system-detail/SimulationPreviewPanel', async () => {
  const React = await import('react');
  return {
    SimulationPreviewPanel: vi.fn(({ onPlanSnapshotChange }) => {
      React.useEffect(() => {
        onPlanSnapshotChange?.({
          placements: [
            { facility_template_id: 'orbital_port', local_body_id: 'body1', is_primary_port: true, build_order: 1 },
            { facility_template_id: 'flex_lab', local_body_id: 'body1', build_order: 2 },
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
            {
              id: 'flex_lab',
              name: 'Flexible Lab',
              category: 'science',
              tier: 2,
              economy: 'HighTech',
              is_port: false,
              is_support_facility: true,
              allowed_location: 'surface_or_orbit',
              pad_size: 'medium',
              confidence: 'confirmed',
              notes: null,
              yellow_cp_generated: 1,
              green_cp_generated: 0,
              yellow_cp_cost: 1,
              green_cp_cost: 0,
            },
          ],
          targetArchetype: 'refinery_industrial',
          projection: {
            candidateId: 'expansion-1',
            label: 'Expansion candidate',
            placements: [
              { facility_template_id: 'surface_hub', local_body_id: 'body1', build_order: 5 },
            ],
          },
        });
      }, [onPlanSnapshotChange]);
      return <div>Reused Colony Planner panel</div>;
    }),
  };
});

const mockedUseSystemDetail = vi.mocked(useSystemDetail);
const mockedSimulationPreviewPanel = vi.mocked(SimulationPreviewPanel);
const mockedGetFacilityTemplates = vi.mocked(getFacilityTemplates);
const mockedGetSimulationSummary = vi.mocked(getSimulationSummary);
const mockedGetSlotPredictions = vi.mocked(getSlotPredictions);

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
    { id: 'body1', name: 'Workspace System A 1', body_type: 'Planet', subtype: 'Water world', is_water_world: true, is_landable: false },
  ],
  stations: [],
} as unknown as SystemDetail;

const facilityTemplates: FacilityTemplate[] = [
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
  {
    id: 'flex_lab',
    name: 'Flexible Lab',
    category: 'science',
    tier: 2,
    economy: 'HighTech',
    is_port: false,
    is_support_facility: true,
    allowed_location: 'surface_or_orbit',
    pad_size: 'medium',
    confidence: 'confirmed',
    notes: null,
    yellow_cp_generated: 1,
    green_cp_generated: 0,
    yellow_cp_cost: 1,
    green_cp_cost: 0,
  },
];

const slotPredictions: SlotPredictionResponse = {
  system_id64: 123,
  data_source: 'eddn',
  body_count: 2,
  predicted_orbital_slots_total: 4,
  predicted_ground_slots_total: 5,
  prediction_status: 'predicted',
  prediction_version: 'validated-slot-v1',
  confidence_label: 'validated_high_accuracy',
  disclaimer: 'Predicted slots — high-accuracy algorithm, not guaranteed. Verify in Architect Mode.',
  validation_note: 'Validated against the supplied evidence set with only 2 true mismatches after data-entry corrections.',
  required_input_missing: [],
  predictions: [
    {
      system_address: 123,
      body_id: 'body1' as never,
      body_name: 'Workspace System A 1',
      planet_class: 'Water world',
      predicted_orbital_slots: 4,
      predicted_ground_slots: 5,
      prediction_status: 'predicted',
      reasons: [],
    },
  ],
};

function renderPlanner(props?: Partial<Parameters<typeof ColonyPlannerWorkspace>[0]>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ColonyPlannerWorkspace
        id64={123}
        onBackToFinder={vi.fn()}
        onOpenSystemDetail={vi.fn()}
        {...props}
      />
    </QueryClientProvider>,
  );
}

function storedProjectByName(projectName: string) {
  return Object.values(useColonyProjectStore.getState().projects)
    .find((project) => project.project_name === projectName) ?? null;
}

describe('ColonyPlannerWorkspace', () => {
  beforeEach(() => {
    localStorage.clear();
    useColonyProjectStore.setState({ projects: {} });
    mockedSimulationPreviewPanel.mockClear();
    mockedUseSystemDetail.mockReturnValue({
      data: null,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockedGetFacilityTemplates.mockResolvedValue(facilityTemplates);
    mockedGetSimulationSummary.mockResolvedValue({
      classification: { primary_archetype: 'refinery_industrial' },
      buildability: { recommended_build_order: [] },
      regional_context: null,
    } as unknown as SimulationSummary);
    mockedGetSlotPredictions.mockResolvedValue(slotPredictions);
  });

  afterEach(() => {
    mockedUseSystemDetail.mockReset();
    mockedSimulationPreviewPanel.mockClear();
    mockedGetFacilityTemplates.mockReset();
    mockedGetSimulationSummary.mockReset();
    mockedGetSlotPredictions.mockReset();
    localStorage.clear();
    useColonyProjectStore.setState({ projects: {} });
  });

  it('renders a no-system state for direct #colony-planner visits', () => {
    const onBackToFinder = vi.fn();

    renderPlanner({ id64: null, onBackToFinder });

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

    renderPlanner();

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

    renderPlanner({ onBackToFinder });

    expect(screen.getByText('Failed to load Colony Planner.')).toBeTruthy();
    expect(screen.getByText('network failed')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Retry/i }));
    fireEvent.click(screen.getAllByRole('button', { name: /Back to Finder/i })[1]);
    expect(refetch).toHaveBeenCalledTimes(1);
    expect(onBackToFinder).toHaveBeenCalledTimes(1);
    expect(mockedSimulationPreviewPanel).not.toHaveBeenCalled();
  });

  it('renders the new whole-system planner by default and keeps Advanced Planner collapsed', async () => {
    const onOpenSystemDetail = vi.fn();
    mockedUseSystemDetail.mockReturnValue({
      data: system,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPlanner({ onOpenSystemDetail });

    expect(screen.getAllByText('Workspace System').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Refinery').length).toBeGreaterThan(0);
    expect(screen.getByTestId('whole-system-colony-planner')).toBeTruthy();
    expect(screen.getByTestId('whole-system-colony-planner').getAttribute('data-layout')).toBe('stage17n-docked-context-canvas');
    expect(screen.getByTestId('raven-real-planner-canvas')).toBeTruthy();
    expect(screen.getByTestId('workspace-planner-content')).toBeTruthy();
    expect(screen.getByTestId('workspace-planner-content').getAttribute('data-readability')).toBe('stage17n');
    expect(screen.getByTestId('workspace-planner-content').getAttribute('data-layout')).toBe('main-system-canvas');
    expect(screen.getByTestId('planner-telemetry-region').getAttribute('data-layout')).toBe('telemetry-context-panel');
    expect(screen.getByTestId('planner-telemetry-region').getAttribute('data-mobile-dock')).toBe('closed');
    expect(screen.getByTestId('planner-telemetry-dock-toggle')).toBeTruthy();
    expect(screen.getByTestId('planner-telemetry-dock-content').getAttribute('data-open')).toBe('false');
    fireEvent.click(screen.getByTestId('planner-telemetry-dock-toggle'));
    expect(screen.getByTestId('planner-telemetry-region').getAttribute('data-mobile-dock')).toBe('open');
    expect(screen.getByTestId('planner-telemetry-dock-content').getAttribute('data-open')).toBe('true');
    expect(screen.getByTestId('raven-real-telemetry-panel')).toBeTruthy();
    expect(screen.getByTestId('planner-summary-panel')).toBeTruthy();
    expect(screen.getByTestId('workspace-economy-ledger')).toBeTruthy();
    expect(screen.getByTestId('summary-economy-ledger')).toBeTruthy();
    expect(screen.getByRole('region', { name: /Raven-style real planner canvas/i })).toBeTruthy();
    expect(screen.getByText('Whole-System Build Canvas')).toBeTruthy();
    expect(screen.getByTestId('raven-real-body-row-body1')).toBeTruthy();
    expect(await screen.findByText('Whole-System Planner')).toBeTruthy();
    expect(screen.queryByTestId('selected-body-planner-canvas')).toBeNull();
    expect(screen.queryByTestId('system-overview-planner-canvas')).toBeNull();
    expect(screen.queryByTestId('system-overview-map')).toBeNull();
    expect(await screen.findByTestId('body1-orbital-slot-3')).toBeTruthy();
    expect(screen.getByTestId('body1-ground-slot-4')).toBeTruthy();
    expect(screen.getByTestId('advanced-workspace-toggle')).toBeTruthy();
    expect(screen.getByTestId('advanced-workspace-toggle').textContent).toContain('Open');
    expect(screen.queryByTestId('advanced-planner-content')).toBeNull();
    expect(screen.queryByText('Reused Colony Planner panel')).toBeNull();
    expect(mockedSimulationPreviewPanel).not.toHaveBeenCalled();
    expect(screen.getByText('Planner summary')).toBeTruthy();
    fireEvent.click(screen.getByTestId('summary-rail-collapse-toggle'));
    expect(screen.getByTestId('project-card')).toBeTruthy();
    expect(screen.getByTestId('plan-health-card')).toBeTruthy();
    expect(screen.getByTestId('selection-card')).toBeTruthy();
    expect(screen.getByTestId('preview-suggested-card')).toBeTruthy();
    expect(screen.getByTestId('topology-body-button-body1').getAttribute('title')).toBe('Workspace System A 1');
    expect(screen.getByText(/Saved locally in this browser/i)).toBeTruthy();
    const summaryPanel = screen.getByTestId('planner-summary-panel');
    expect(within(screen.getByTestId('plan-health-card')).getByText('Placements')).toBeTruthy();
    expect(within(summaryPanel).getAllByText('0').length).toBeGreaterThan(0);
    expect(within(screen.getByTestId('plan-health-card')).getByText('Unassigned')).toBeTruthy();
    expect(within(screen.getByTestId('plan-health-card')).getByText('Warnings')).toBeTruthy();
    expect(within(screen.getByTestId('plan-health-card')).getByText('Refinery / Industrial Plan')).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/Stage 15|15H|15I|deferred to next stages/i);
    expect(screen.queryByText('Attached Structures')).toBeNull();

    fireEvent.click(screen.getByTestId('topology-body-button-body1'));
    expect(screen.getByText(/Planning focus: Workspace System A 1/i)).toBeTruthy();
    expect(screen.getByTestId('raven-real-body-row-body1').getAttribute('data-expanded')).toBe('true');
    const inlineExpansion = screen.getByTestId('raven-inline-body-expansion-body1');
    expect(within(screen.getByTestId('raven-real-planner-canvas')).getByTestId('raven-inline-body-expansion-body1')).toBeTruthy();
    expect(screen.queryByTestId('selected-role-summary-card')).toBeNull();
    expect(screen.queryByText('Body Hint')).toBeNull();
    const bodySurface = within(inlineExpansion).getByTestId('selected-body-planner-canvas');
    expect(within(bodySurface).getByText('Body slot planner')).toBeTruthy();
    expect(within(bodySurface).getByTestId('slot-lane-orbital')).toBeTruthy();
    expect(within(bodySurface).getByTestId('slot-lane-surface')).toBeTruthy();
    expect(within(bodySurface).queryByTestId('slot-lane-flex')).toBeNull();
    expect(within(bodySurface).getByTestId('body-planning-economy')).toBeTruthy();
    expect(within(bodySurface).getByTestId('slot-lane-add-orbital')).toBeTruthy();
    expect((within(bodySurface).getByTestId('slot-lane-add-surface') as HTMLButtonElement).disabled).toBe(true);
    expect(within(bodySurface).queryByTestId('slot-lane-add-flex')).toBeNull();
    expect(within(bodySurface).getByText(/surface limited: water world/i)).toBeTruthy();
    expect(within(bodySurface).getByRole('button', { name: 'Review structures' })).toBeTruthy();
    expect(within(bodySurface).getByRole('button', { name: /Close/i })).toBeTruthy();
    expect(screen.queryByRole('combobox', { name: 'Declared role' })).toBeNull();
    expect(screen.queryByRole('textbox', { name: /role/i })).toBeNull();

    fireEvent.click(screen.getByTestId('advanced-workspace-toggle'));
    expect(await screen.findByTestId('advanced-planner-content')).toBeTruthy();
    expect(screen.getByText('Reused Colony Planner panel')).toBeTruthy();
    expect((await screen.findAllByTestId('raven-projected-ghost-structure')).length).toBeGreaterThan(0);
    expect(screen.getByTestId('raven-real-body-row-body1').getAttribute('data-projected')).toBe('true');
    expect((screen.getByTestId('body1-ground-slot-0').textContent ?? '')).toMatch(/Surfa|Surface/i);
    expect((within(screen.getByTestId('slot-lane-items-surface')).getByTestId('slot-projected-0').textContent ?? '')).toMatch(/Surface Hub/i);
    expect((screen.getByTestId('workspace-economy-ledger').textContent ?? '')).toMatch(/\+1/);
    expect(mockedSimulationPreviewPanel).toHaveBeenCalledWith(
      expect.objectContaining({
        system,
        selectedPlan: null,
        onPlanSnapshotChange: expect.any(Function),
        initialRequest: {
          system_id64: 123,
          target_archetype: 'refinery_industrial',
          placements: [],
        },
      }),
      undefined,
    );

    fireEvent.click(screen.getByRole('button', { name: /Back to system detail/i }));
    expect(onOpenSystemDetail).toHaveBeenCalledTimes(1);
    expect(onOpenSystemDetail).toHaveBeenCalledWith(123);
  });

  it('opens body-aware structure picker from inline canvas without mounting Advanced Planner', async () => {
    mockedUseSystemDetail.mockReturnValue({
      data: system,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPlanner();

    fireEvent.click(await screen.findByTestId('topology-body-button-body1'));
    fireEvent.click(screen.getByTestId('slot-lane-add-orbital'));

    const picker = screen.getByTestId('body-structure-picker');
    expect(picker).toBeTruthy();
    expect(within(picker).getByText(/Add orbit structure/i)).toBeTruthy();
    expect(screen.queryByTestId('body-structure-template-surface_hub')).toBeNull();
    expect(screen.queryByTestId('body-structure-template-flex_lab')).toBeNull();
    expect(within(picker).getByTestId('canvas-picker-compatibility-summary').textContent).toContain('2 incompatible hidden');
    fireEvent.click(screen.getByTestId('body-structure-template-orbital_port'));

    expect((screen.getByTestId('body1-orbital-slot-0').textContent ?? '').trim().length).toBeGreaterThan(0);
    expect(within(screen.getByTestId('slot-lane-orbital')).getByText('1/4 planned')).toBeTruthy();
    expect(within(screen.getByTestId('slot-lane-items-orbital')).getByText(/Orbital Port/i)).toBeTruthy();
    expect(screen.queryByTestId('advanced-planner-content')).toBeNull();
    expect(mockedSimulationPreviewPanel).not.toHaveBeenCalled();
  });

  it('keeps body clicks focused on planning rather than role editing side effects', async () => {
    mockedUseSystemDetail.mockReturnValue({
      data: system,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPlanner();

    fireEvent.click(await screen.findByTestId('topology-body-button-body1'));
    const surface = screen.getByTestId('selected-body-planner-canvas');
    expect(within(surface).getByText('Body slot planner')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Add role' })).toBeNull();
    expect(screen.queryByRole('combobox', { name: 'Declared role' })).toBeNull();
    expect(screen.queryByText('Observed: Primary Port')).toBeNull();
    expect(mockedSimulationPreviewPanel).not.toHaveBeenCalled();

  });

  it('does not render role conflict controls in the default rescue surface', async () => {
    mockedUseSystemDetail.mockReturnValue({
      data: system,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPlanner();

    fireEvent.click(await screen.findByTestId('topology-body-button-body1'));
    expect(screen.queryByRole('combobox', { name: 'Declared role' })).toBeNull();
    expect(screen.queryByText('Role conflict: Tourism + Heavy Industrial')).toBeNull();
    expect(screen.queryByText('Observed: not recorded')).toBeNull();
  });

  it('keeps the summary rail compact without review-toggle clutter', async () => {
    mockedUseSystemDetail.mockReturnValue({
      data: system,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPlanner();

    const summary = await screen.findByTestId('planner-summary-panel');
    expect(within(summary).getByTestId('summary-rail-compact-view')).toBeTruthy();
    expect(within(summary).getByTestId('summary-rail-collapse-toggle')).toBeTruthy();
    fireEvent.click(within(summary).getByTestId('summary-rail-collapse-toggle'));
    expect(within(summary).getByTestId('preview-suggested-card')).toBeTruthy();
    expect(within(summary).queryByRole('button', { name: 'Evidence' })).toBeNull();
    expect(within(summary).queryByRole('button', { name: 'Validation' })).toBeNull();
  });

  it('saves, renames, duplicates, and archives a local Colony Project with confirmation', async () => {
    mockedUseSystemDetail.mockReturnValue({
      data: system,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPlanner();

    fireEvent.click((await screen.findByTestId('summary-rail-collapse-toggle')));
    expect(await screen.findByTestId('project-card')).toBeTruthy();
    expect(screen.getByTestId('project-unsaved-indicator').textContent).toContain('Saved');

    fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'Local starter' } });
    fireEvent.click(screen.getByTestId('project-details-toggle'));
    fireEvent.change(screen.getByLabelText('Project notes'), { target: { value: 'Check Architect mode before final placement.' } });
    fireEvent.click(screen.getByTestId('topology-body-button-body1'));
    fireEvent.click(screen.getByTestId('slot-lane-add-orbital'));
    fireEvent.click(await screen.findByTestId('body-structure-template-orbital_port'));
    fireEvent.click(screen.getByRole('button', { name: 'Save project' }));

    expect(screen.getByTestId('project-unsaved-indicator').textContent).toContain('Saved');
    expect(storedProjectByName('Local starter')?.build_plan_placements).toHaveLength(1);
    expect(storedProjectByName('Local starter')?.declared_roles).toEqual([]);

    fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'Renamed local starter' } });
    fireEvent.click(screen.getByRole('button', { name: 'Rename project' }));
    expect(storedProjectByName('Renamed local starter')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Duplicate project' }));
    expect(storedProjectByName('Renamed local starter copy')).toBeTruthy();
    expect(storedProjectByName('Renamed local starter copy')?.declared_roles).toEqual([]);

    fireEvent.click(screen.getByRole('button', { name: 'Delete / archive project' }));
    expect(screen.getByText(/Archive this local project/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Archive project' }));
    expect(storedProjectByName('Renamed local starter copy')?.archived_at).toBeTruthy();
  });

  it('loads old local projects without declared roles safely', async () => {
    useColonyProjectStore.setState({
      projects: {
        'old-project': {
          id: 'old-project',
          system_id64: 123,
          system_name: 'Workspace System',
          project_name: 'Old project',
          build_plan_placements: [],
          selected_body_assignments: {},
          target_archetype: 'refinery_industrial',
          notes: 'No role field.',
          status: 'draft',
          created_at: '2026-05-01T00:00:00.000Z',
          updated_at: '2026-05-01T00:00:00.000Z',
          archived_at: null,
        } as never,
      },
    });
    mockedUseSystemDetail.mockReturnValue({
      data: system,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPlanner();

    fireEvent.click((await screen.findByTestId('summary-rail-collapse-toggle')));
    expect((await screen.findAllByText('Old project')).length).toBeGreaterThan(0);
    expect(screen.queryByTestId('selected-body-planner-canvas')).toBeNull();
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

    renderPlanner();

    fireEvent.click((await screen.findByTestId('summary-rail-collapse-toggle')));
    expect((await screen.findAllByText('Reloaded project')).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByTestId('topology-body-button-body1'));
    expect(within(await screen.findByTestId('slot-lane-items-surface')).getByText(/Surface Hub/i)).toBeTruthy();
    expect(mockedSimulationPreviewPanel).not.toHaveBeenCalled();
  });
});
