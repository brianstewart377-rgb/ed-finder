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
    useColonyProjectStore.setState({ projects: {} });
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
    expect(Object.values(useColonyProjectStore.getState().projects)).toHaveLength(1);
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
      objective: 'balanced',
      start_approach: 'manual',
      created_from: 'system_detail',
    });

    expect(saved.declared_roles).toEqual([
      expect.objectContaining({ body_id: 'body1', role_id: 'main_station_body', source: 'declared' }),
    ]);
    expect(saved.objective).toBe('balanced');
    expect(saved.start_approach).toBe('manual');
    expect(saved.created_from).toBe('system_detail');
    expect(projectMatchesSnapshot(saved, [placement], 'refinery_industrial', '', 'Role project', saved.declared_roles)).toBe(true);
    expect(projectMatchesSnapshot(saved, [placement], 'refinery_industrial', '', 'Role project', [])).toBe(false);

    const oldProject = {
      ...saved,
      id: 'old-shape',
      declared_roles: undefined,
      objective: undefined,
      start_approach: undefined,
      created_from: undefined,
    } as never;
    expect(activeProjectsForSystem([oldProject], 123)[0].declared_roles).toEqual([]);
    expect(activeProjectsForSystem([oldProject], 123)[0].objective).toBeNull();
    expect(activeProjectsForSystem([oldProject], 123)[0].start_approach).toBeNull();
    expect(activeProjectsForSystem([oldProject], 123)[0].created_from).toBeNull();
  });

  it('renames, duplicates, and archives projects without deleting the source data shape', () => {
    const saved = useColonyProjectStore.getState().saveProject(null, {
      system_id64: 123,
      system_name: 'Workspace System',
      project_name: 'Starter project',
      build_plan_placements: [placement],
      target_archetype: 'refinery_industrial',
      notes: '',
      objective: 'materials_coverage',
      start_approach: 'recommendation_assisted',
      created_from: 'system_detail',
    });

    useColonyProjectStore.getState().renameProject(saved.id, 'Renamed project');
    expect(useColonyProjectStore.getState().projects[saved.id].project_name).toBe('Renamed project');

    useColonyProjectStore.getState().updateProjectStatus(saved.id, 'ready_to_build');
    expect(useColonyProjectStore.getState().projects[saved.id].status).toBe('ready_to_build');

    const duplicate = useColonyProjectStore.getState().duplicateProject(saved.id);
    expect(duplicate?.project_name).toBe('Renamed project - Copy');
    expect(duplicate?.id).not.toBe(saved.id);
    expect(duplicate?.build_plan_placements).toEqual([placement]);
    expect(duplicate?.objective).toBe('materials_coverage');
    expect(duplicate?.start_approach).toBe('recommendation_assisted');
    expect(duplicate?.created_from).toBe('system_detail');
    expect(duplicate?.status).toBe('draft');

    useColonyProjectStore.getState().archiveProject(saved.id);
    const projects = useColonyProjectStore.getState().projects;
    expect(projects[saved.id].archived_at).toBeTruthy();
    expect(activeProjectsForSystem(Object.values(projects), 123).map((project) => project.id)).toEqual([duplicate?.id]);
  });

  it('migrates old persisted arrays and deletes projects by key', async () => {
    const legacyProject = {
      id: 'legacy-project',
      system_id64: 123,
      system_name: 'Workspace System',
      project_name: 'Legacy project',
      build_plan_placements: [placement],
      selected_body_assignments: { 0: 'body1' },
      declared_roles: undefined,
      target_archetype: 'refinery_industrial',
      notes: '',
      status: 'validated',
      objective: undefined,
      start_approach: undefined,
      created_from: undefined,
      created_at: '2026-05-01T00:00:00.000Z',
      updated_at: '2026-05-01T00:00:00.000Z',
      archived_at: null,
    };
    localStorage.setItem('ed_colony_projects_v1', JSON.stringify({
      state: { projects: [legacyProject] },
      version: 1,
    }));

    await useColonyProjectStore.persist.rehydrate();

    expect(useColonyProjectStore.getState().projects['legacy-project'].project_name).toBe('Legacy project');
    expect(useColonyProjectStore.getState().projects['legacy-project'].declared_roles).toEqual([]);
    expect(useColonyProjectStore.getState().projects['legacy-project'].objective).toBeNull();
    expect(useColonyProjectStore.getState().projects['legacy-project'].start_approach).toBeNull();
    expect(useColonyProjectStore.getState().projects['legacy-project'].created_from).toBeNull();
    expect(useColonyProjectStore.getState().projects['legacy-project'].status).toBe('draft');

    useColonyProjectStore.getState().deleteProject('legacy-project');
    expect(useColonyProjectStore.getState().projects['legacy-project']).toBeUndefined();
  });
});
