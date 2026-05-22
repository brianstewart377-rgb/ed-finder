import { useCallback, useEffect, useMemo, useState } from 'react';
import type { SystemDetail } from '@/types/api';
import { sameBodyId } from '@/features/system-detail/simulation-preview/bodyIdUtils';
import type { TopologyPlanSnapshot } from './ColonyTopologyRail';
import {
  addDeclaredRole,
  normaliseDeclaredRoles,
  removeDeclaredRole,
  type DeclaredColonyRole,
  type DeclaredColonyRoleId,
} from './colonyRoles';
import {
  activeProjectsForSystem,
  projectMatchesSnapshot,
  useColonyProjectStore,
} from './colonyProjectStore';
import { projectRequestFromProject } from './workspaceUtils';

export function useWorkspaceProjectState(system: SystemDetail, planSnapshot: TopologyPlanSnapshot) {
  const projects = useColonyProjectStore((state) => state.projects);
  const saveProject = useColonyProjectStore((state) => state.saveProject);
  const renameProject = useColonyProjectStore((state) => state.renameProject);
  const duplicateProject = useColonyProjectStore((state) => state.duplicateProject);
  const archiveProject = useColonyProjectStore((state) => state.archiveProject);

  const systemProjects = useMemo(() => activeProjectsForSystem(projects, system.id64), [projects, system.id64]);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(() => systemProjects[0]?.id ?? null);
  const [pendingProjectId, setPendingProjectId] = useState<string>('');
  const [projectName, setProjectName] = useState(`${system.name || 'Colony'} project`);
  const [projectNotes, setProjectNotes] = useState('');
  const [declaredRoles, setDeclaredRoles] = useState<DeclaredColonyRole[]>([]);
  const [confirmArchive, setConfirmArchive] = useState(false);

  const activeProject = systemProjects.find((project) => project.id === activeProjectId) ?? null;

  useEffect(() => {
    if (activeProjectId && systemProjects.some((project) => project.id === activeProjectId)) return;
    const next = systemProjects[0] ?? null;
    setActiveProjectId(next?.id ?? null);
  }, [activeProjectId, systemProjects]);

  useEffect(() => {
    setPendingProjectId(activeProjectId ?? '');
    setProjectName(activeProject?.project_name ?? `${system.name || 'Colony'} project`);
    setProjectNotes(activeProject?.notes ?? '');
    setDeclaredRoles(normaliseDeclaredRoles(activeProject?.declared_roles));
    setConfirmArchive(false);
  }, [activeProject, activeProjectId, system.name]);

  const unsavedChanges = !projectMatchesSnapshot(
    activeProject,
    planSnapshot.placements,
    planSnapshot.targetArchetype,
    projectNotes,
    projectName,
    declaredRoles,
  );

  const projectRequest = useMemo(() => projectRequestFromProject(activeProject), [activeProject]);

  const handleSaveProject = useCallback(() => {
    const saved = saveProject(activeProject?.id ?? null, {
      system_id64: system.id64,
      system_name: system.name || 'Unknown system',
      project_name: projectName,
      build_plan_placements: planSnapshot.placements,
      declared_roles: declaredRoles,
      target_archetype: planSnapshot.targetArchetype,
      notes: projectNotes,
      status: 'draft',
    });
    setActiveProjectId(saved.id);
  }, [activeProject?.id, declaredRoles, planSnapshot.placements, planSnapshot.targetArchetype, projectName, projectNotes, saveProject, system.id64, system.name]);

  const handleRenameProject = useCallback(() => {
    if (!activeProject) return;
    renameProject(activeProject.id, projectName);
  }, [activeProject, projectName, renameProject]);

  const handleDuplicateProject = useCallback(() => {
    if (!activeProject) return;
    const duplicate = duplicateProject(activeProject.id);
    if (duplicate) setActiveProjectId(duplicate.id);
  }, [activeProject, duplicateProject]);

  const handleArchiveProject = useCallback(() => {
    if (!activeProject) return;
    archiveProject(activeProject.id);
    setConfirmArchive(false);
    setActiveProjectId(null);
  }, [activeProject, archiveProject]);

  const handleAddDeclaredRole = useCallback((bodyId: string, roleId: DeclaredColonyRoleId) => {
    const body = (system.bodies ?? []).find((candidate) => sameBodyId(candidate.id, bodyId));
    if (!body) return;
    setDeclaredRoles((current) => addDeclaredRole(current, body, roleId));
  }, [system.bodies]);

  const handleRemoveDeclaredRole = useCallback((bodyId: string, roleId: DeclaredColonyRoleId) => {
    setDeclaredRoles((current) => removeDeclaredRole(current, bodyId, roleId));
  }, []);

  return {
    projects: systemProjects,
    activeProject,
    pendingProjectId,
    projectName,
    projectNotes,
    declaredRoles,
    confirmArchive,
    projectRequest,
    unsavedChanges,
    setPendingProjectId,
    setProjectName,
    setProjectNotes,
    addDeclaredRole: handleAddDeclaredRole,
    removeDeclaredRole: handleRemoveDeclaredRole,
    setConfirmArchive,
    loadProject: () => setActiveProjectId(pendingProjectId || null),
    saveProject: handleSaveProject,
    renameProject: handleRenameProject,
    duplicateProject: handleDuplicateProject,
    archiveProject: handleArchiveProject,
  };
}
