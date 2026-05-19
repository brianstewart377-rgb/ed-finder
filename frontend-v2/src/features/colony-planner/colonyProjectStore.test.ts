import { beforeEach, describe, expect, it } from 'vitest';
import {
  activeProjectsForSystem,
  projectMatchesSnapshot,
  useColonyProjectStore,
} from './colonyProjectStore';

const placement = { facility_template_id: 'orbital_port', local_body_id: 'body1', is_primary_port: true, build_order: 1 };

describe('colonyProjectStore', () => {
  beforeEach(() => {
    localStorage.clear();
    useColonyProjectStore.setState({ projects: [] });
  });

  it('saves and matches a local colony project snapshot', () => {
    const saved = useColonyProjectStore.getState().saveProject(null, {
      system_id64: 123,
      system_name: 'Workspace System',
      project_name: 'Starter project',
      build_plan_placements: [placement],
      target_archetype: 'refinery_industrial',
      notes: 'Check Architect mode.',
    });

    expect(saved.id).toMatch(/^colony-123-/);
    expect(saved.status).toBe('draft');
    expect(saved.selected_body_assignments).toEqual({ 0: 'body1' });
    expect(saved.declared_roles).toEqual([]);
    expect(useColonyProjectStore.getState().projects).toHaveLength(1);
    expect(projectMatchesSnapshot(saved, [placement], 'refinery_industrial', 'Check Architect mode.', 'Starter project')).toBe(true);
    expect(projectMatchesSnapshot(saved, [placement], 'refinery_industrial', 'Changed notes.', 'Starter project')).toBe(false);
  });

  it('persists declared roles and defaults old project shapes safely', () => {
    const saved = useColonyProjectStore.getState().saveProject(null, {
      system_id64: 123,
      system_name: 'Workspace System',
      project_name: 'Role project',
      build_plan_placements: [placement],
      declared_roles: [{
        id: 'declared:body1:main_station_body',
        body_id: 'body1',
        role_id: 'main_station_body',
        source: 'declared',
        label: 'Main Station Body',
      }],
      target_archetype: 'refinery_industrial',
      notes: '',
    });

    expect(saved.declared_roles).toEqual([
      expect.objectContaining({ body_id: 'body1', role_id: 'main_station_body', source: 'declared' }),
    ]);
    expect(projectMatchesSnapshot(saved, [placement], 'refinery_industrial', '', 'Role project', saved.declared_roles)).toBe(true);
    expect(projectMatchesSnapshot(saved, [placement], 'refinery_industrial', '', 'Role project', [])).toBe(false);

    const oldProject = {
      ...saved,
      id: 'old-shape',
      declared_roles: undefined,
    } as never;
    expect(activeProjectsForSystem([oldProject], 123)[0].declared_roles).toEqual([]);
  });

  it('renames, duplicates, and archives projects without deleting the source data shape', () => {
    const saved = useColonyProjectStore.getState().saveProject(null, {
      system_id64: 123,
      system_name: 'Workspace System',
      project_name: 'Starter project',
      build_plan_placements: [placement],
      target_archetype: 'refinery_industrial',
      notes: '',
    });

    useColonyProjectStore.getState().renameProject(saved.id, 'Renamed project');
    expect(useColonyProjectStore.getState().projects[0].project_name).toBe('Renamed project');

    const duplicate = useColonyProjectStore.getState().duplicateProject(saved.id);
    expect(duplicate?.project_name).toBe('Renamed project copy');
    expect(duplicate?.id).not.toBe(saved.id);
    expect(duplicate?.build_plan_placements).toEqual([placement]);

    useColonyProjectStore.getState().archiveProject(saved.id);
    const projects = useColonyProjectStore.getState().projects;
    expect(projects.find((project) => project.id === saved.id)?.archived_at).toBeTruthy();
    expect(activeProjectsForSystem(projects, 123).map((project) => project.id)).toEqual([duplicate?.id]);
  });
});
