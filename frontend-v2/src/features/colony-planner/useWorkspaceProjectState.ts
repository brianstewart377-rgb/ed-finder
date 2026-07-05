import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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

export function useWorkspaceProjectState(
  system: SystemDetail,
  planSnapshot: TopologyPlanSnapshot,
  initialProjectId: string | null = null,
) {
  const projectRecord = useColonyProjectStore((state) => state.projects);
  const saveProject = useColonyProjectStore((state) => state.saveProject);
  const renameProject = useColonyProjectStore((state) => state.renameProject);
  const duplicateProject = useColonyProjectStore((state) => state.duplicateProject);
  const archiveProject = useColonyProjectStore((state) => state.archiveProject);
  const deleteProject = useColonyProjectStore((state) => state.deleteProject);

  const projects = useMemo(() => Object.values(projectRecord), [projectRecord]);
  const systemProjects = useMemo(() => activeProjectsForSystem(projects, system.id64), [projects, system.id64]);
  const initialProject = systemProjects.find((project) => project.id === initialProjectId) ?? null;
  const [activeProjectId, setActiveProjectId] = useState<string | null>(() => initialProject?.id ?? null);
  const [pendingProjectId, setPendingProjectId] = useState<string>(() => initialProject?.id ?? '');
  const [projectName, setProjectName] = useState(() => initialProject?.project_name ?? `${system.name || 'Colony'} project`);
  const [projectNotes, setProjectNotes] = useState(() => initialProject?.notes ?? '');
  const [declaredRoles, setDeclaredRoles] = useState<DeclaredColonyRole[]>(() => normaliseDeclaredRoles(initialProject?.declared_roles));
  const [confirmArchive, setConfirmArchive] = useState(false);
  const hasMountedProjectSync = useRef(false);
  const suppressAutoProjectSelect = useRef(false);

  const activeProject = systemProjects.find((project) => project.id === activeProjectId) ?? null;

  useEffect(() => {
    if (!initialProjectId) return;
    const targetProject = systemProjects.find((project) => project.id === initialProjectId) ?? null;
    if (!targetProject) return;
    if (activeProjectId === targetProject.id) return;
    suppressAutoProjectSelect.current = false;
    setActiveProjectId(targetProject.id);
    setPendingProjectId(targetProject.id);
  }, [activeProjectId, initialProjectId, systemProjects]);

  useEffect(() => {
    if (activeProjectId && systemProjects.some((project) => project.id === activeProjectId)) {
      suppressAutoProjectSelect.current = false;
      return;
    }
    if (!activeProjectId) return;
    setActiveProjectId(null);
  }, [activeProjectId, systemProjects]);

  useEffect(() => {
    if (!hasMountedProjectSync.current) {
      hasMountedProjectSync.current = true;
      return;
    }
    const nextPendingProjectId = activeProjectId ?? '';
    const nextProjectName = activeProject?.project_name ?? `${system.name || 'Colony'} project`;
    const nextProjectNotes = activeProject?.notes ?? '';
    const nextDeclaredRoles = normaliseDeclaredRoles(activeProject?.declared_roles);

    setPendingProjectId((current) => (current === nextPendingProjectId ? current : nextPendingProjectId));
    setProjectName((current) => (current === nextProjectName ? current : nextProjectName));
    setProjectNotes((current) => (current === nextProjectNotes ? current : nextProjectNotes));
    setDeclaredRoles((current) => (
      JSON.stringify(current) === JSON.stringify(nextDeclaredRoles) ? current : nextDeclaredRoles
    ));
    setConfirmArchive((current) => (current ? false : current));
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
      status: activeProject?.status ?? 'draft',
    });
    setActiveProjectId(saved.id);
    suppressAutoProjectSelect.current = false;
  }, [activeProject?.id, activeProject?.status, declaredRoles, planSnapshot.placements, planSnapshot.targetArchetype, projectName, projectNotes, saveProject, system.id64, system.name]);

  const handleRenameProject = useCallback(() => {
    if (!activeProject) return;
    renameProject(activeProject.id, projectName);
  }, [activeProject, projectName, renameProject]);

  const handleDuplicateProject = useCallback(() => {
    if (!activeProject) return;
    const duplicate = duplicateProject(activeProject.id);
    if (duplicate) {
      suppressAutoProjectSelect.current = false;
      setActiveProjectId(duplicate.id);
    }
  }, [activeProject, duplicateProject]);

  const handleArchiveProject = useCallback(() => {
    if (!activeProject) return;
    archiveProject(activeProject.id);
    setConfirmArchive(false);
    setActiveProjectId(null);
  }, [activeProject, archiveProject]);

  const handleDeleteActiveProject = useCallback(() => {
    if (!activeProject) return false;
    deleteProject(activeProject.id);
    setConfirmArchive(false);
    suppressAutoProjectSelect.current = true;
    setActiveProjectId(null);
    setPendingProjectId('');
    setProjectName(`${system.name || 'Colony'} project`);
    setProjectNotes('');
    setDeclaredRoles([]);
    return true;
  }, [activeProject, deleteProject, system.name]);

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
    loadProject: () => {
      suppressAutoProjectSelect.current = false;
      setActiveProjectId(pendingProjectId || null);
    },
    saveProject: handleSaveProject,
    renameProject: handleRenameProject,
    duplicateProject: handleDuplicateProject,
    archiveProject: handleArchiveProject,
    deleteActiveProject: handleDeleteActiveProject,
  };
}
