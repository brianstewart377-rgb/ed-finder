import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/lib/api';
import { useColonyProjectStore } from './colonyProjectStore';
import { PlannerRouteGuard } from './PlannerRouteGuard';

vi.mock('@/lib/api', () => ({ api: { system: vi.fn() } }));

const mockedSystem = vi.mocked(api.system);

function clearProjects() {
  useColonyProjectStore.setState({ projects: {} });
}

afterEach(() => {
  window.location.hash = '';
  mockedSystem.mockReset();
  clearProjects();
});

describe('PlannerRouteGuard', () => {
  it('shows an explicit no-active-draft state and only creates after the button is pressed', async () => {
    window.location.hash = '#colony-planner/system/123456';
    mockedSystem.mockResolvedValue({ id64: 123456, name: 'Lave', economy_suggestion: null, primary_economy: null } as never);

    render(<PlannerRouteGuard />);

    await waitFor(() => expect(screen.getByTestId('planner-no-active-draft-route').textContent).toContain('No active draft for this system'));
    expect(Object.keys(useColonyProjectStore.getState().projects)).toHaveLength(0);

    fireEvent.click(screen.getByTestId('planner-create-draft'));

    expect(Object.keys(useColonyProjectStore.getState().projects)).toHaveLength(1);
    expect(window.location.hash).toMatch(/^#colony-planner\/system\/123456\/project\//);
  });

  it('blocks a missing or mismatched project route rather than selecting another local draft', () => {
    window.location.hash = '#colony-planner/system/123456/project/project-for-another-system';
    useColonyProjectStore.setState({
      projects: {
        'project-for-another-system': {
          id: 'project-for-another-system',
          system_id64: 987654,
          system_name: 'Other system',
          project_name: 'Other draft',
          build_plan_placements: [],
          selected_body_assignments: {},
          declared_roles: [],
          target_archetype: 'refinery_industrial',
          notes: '',
          status: 'draft',
          created_at: '2026-07-04T00:00:00Z',
          updated_at: '2026-07-04T00:00:00Z',
          archived_at: null,
        },
      },
    });

    render(<PlannerRouteGuard />);

    const error = screen.getByTestId('planner-project-route-error').textContent ?? '';
    expect(error).toContain('Requested draft could not be opened');
    expect(error).toContain('different system');
  });
});
