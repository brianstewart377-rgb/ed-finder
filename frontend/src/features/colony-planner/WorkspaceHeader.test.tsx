import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { WorkspaceHeader } from './WorkspaceHeader';
import type { SystemDetail } from '@/types/api';
import type { ColonyProject } from './colonyProjectStore';

const system = {
  id64: 2008132031194,
  name: 'Exioce',
  x: 0,
  y: 0,
  z: 0,
  population: null,
  is_colonised: true,
  primary_economy: null,
} as unknown as SystemDetail;

const draftProject = {
  id: 'colony-2008132031194-draft',
  system_id64: 2008132031194,
  system_name: 'Exioce',
  project_name: 'Exioce - Materials coverage',
  build_plan_placements: [],
  selected_body_assignments: {},
  declared_roles: [],
  target_archetype: 'refinery_industrial',
  notes: '',
  objective: 'materials_coverage',
  start_approach: 'manual',
  created_from: 'system_detail',
  status: 'draft',
  created_at: '2026-06-24T00:00:00.000Z',
  updated_at: '2026-06-24T00:00:00.000Z',
} satisfies ColonyProject;

function openDeleteConfirmation({
  plannedStructureCount = 0,
  onDeleteActiveProject = vi.fn(() => true),
  onOpenMyWork = vi.fn(),
  onPlanDeleted = vi.fn(),
}: {
  plannedStructureCount?: number;
  onDeleteActiveProject?: () => boolean;
  onOpenMyWork?: () => void;
  onPlanDeleted?: (projectName: string) => void;
} = {}) {
  render(
    <WorkspaceHeader
      system={system}
      onBackToFinder={vi.fn()}
      onOpenSystemDetail={vi.fn()}
      onOpenMyWork={onOpenMyWork}
      onPlanDeleted={onPlanDeleted}
      activeProject={draftProject}
      plannedStructureCount={plannedStructureCount}
      onDeleteActiveProject={onDeleteActiveProject}
    />,
  );

  fireEvent.click(screen.getByTestId('planner-plan-actions'));
  fireEvent.click(screen.getByTestId('planner-delete-plan-menu-item'));
  return screen.getByTestId('planner-delete-confirmation');
}

describe('WorkspaceHeader data trust display', () => {
  it('renders unknown coords and population for non-Sol origin records', () => {
    render(
      <WorkspaceHeader
        system={system}
        onBackToFinder={vi.fn()}
        onOpenSystemDetail={vi.fn()}
      />,
    );

    expect(screen.getByText('Colonised')).toBeTruthy();
    expect(screen.getAllByText('Unknown').length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText('0.00, 0.00, 0.00')).toBeNull();
    expect(screen.queryByText('Uninhabited')).toBeNull();
  });

  it('exposes My Work management and a clear delete action for drafts', () => {
    const onOpenMyWork = vi.fn();

    render(
      <WorkspaceHeader
        system={system}
        onBackToFinder={vi.fn()}
        onOpenSystemDetail={vi.fn()}
        onOpenMyWork={onOpenMyWork}
        activeProject={draftProject}
        unsavedChanges={false}
      />,
    );

    expect(screen.getByTestId('planner-arrival-context')).toBeTruthy();
    expect(screen.getByTestId('planner-project-name').textContent).toContain('Exioce - Materials coverage');
    expect(screen.getByTestId('planner-objective-context').textContent).toContain('Materials coverage');
    expect(screen.getByTestId('planner-project-status').textContent).toContain('Draft');

    fireEvent.click(screen.getByTestId('planner-manage-my-work'));
    expect(onOpenMyWork).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId('planner-plan-actions'));
    expect(screen.getByTestId('planner-plan-actions-menu').textContent).toContain('Delete draft');
  });

  it('uses calm draft deletion title, labels, and no-structure copy', () => {
    const confirmation = openDeleteConfirmation();

    expect(within(confirmation).getByRole('heading', { name: 'Delete this draft?' })).toBeTruthy();
    expect(confirmation.textContent).toContain('Delete “Exioce - Materials coverage” from My Work.');
    expect(confirmation.textContent).toContain('Your saved system will stay.');
    expect(confirmation.textContent).toContain('This draft has no planned structures yet.');
    expect(confirmation.textContent).toContain('This cannot be undone.');
    expect(within(confirmation).getByRole('button', { name: 'Keep draft' })).toBeTruthy();
    expect(within(confirmation).getByRole('button', { name: 'Delete draft' })).toBeTruthy();
    expect(confirmation.textContent).not.toContain('local storage');
    expect(confirmation.textContent).not.toContain('Elite Dangerous');
  });

  it('uses singular planned-structure wording', () => {
    const confirmation = openDeleteConfirmation({ plannedStructureCount: 1 });

    expect(confirmation.textContent).toContain('This will remove 1 planned structure from this draft.');
    expect(confirmation.textContent).not.toContain('1 planned structures');
  });

  it('uses plural planned-structures wording', () => {
    const confirmation = openDeleteConfirmation({ plannedStructureCount: 2 });

    expect(confirmation.textContent).toContain('This will remove 2 planned structures from this draft.');
  });

  it('requires confirmation before deleting and keep draft leaves the project intact', () => {
    const onDeleteActiveProject = vi.fn(() => true);
    const onOpenMyWork = vi.fn();
    const onPlanDeleted = vi.fn();

    const confirmation = openDeleteConfirmation({
      plannedStructureCount: 2,
      onDeleteActiveProject,
      onOpenMyWork,
      onPlanDeleted,
    });

    fireEvent.click(within(confirmation).getByRole('button', { name: 'Keep draft' }));

    expect(onDeleteActiveProject).not.toHaveBeenCalled();
    expect(onOpenMyWork).not.toHaveBeenCalled();
    expect(onPlanDeleted).not.toHaveBeenCalled();
    expect(screen.queryByTestId('planner-delete-confirmation')).toBeNull();
  });

  it('confirms deletion through the existing callback and routes to My Work', () => {
    const onDeleteActiveProject = vi.fn(() => true);
    const onOpenMyWork = vi.fn();
    const onPlanDeleted = vi.fn();

    const confirmation = openDeleteConfirmation({
      plannedStructureCount: 0,
      onDeleteActiveProject,
      onOpenMyWork,
      onPlanDeleted,
    });
    fireEvent.click(within(confirmation).getByRole('button', { name: 'Delete draft' }));

    expect(onDeleteActiveProject).toHaveBeenCalledTimes(1);
    expect(onPlanDeleted).toHaveBeenCalledWith('Exioce - Materials coverage');
    expect(onOpenMyWork).toHaveBeenCalledTimes(1);
  });
});
