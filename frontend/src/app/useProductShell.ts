import { useCallback, useEffect, useState } from 'react';
import { type ColonyProjectObjective, type ColonyProjectStartApproach, defaultDraftProjectName } from '@/features/colony-planner/plannerDraftContext';
import { useColonyProjectStore } from '@/features/colony-planner/colonyProjectStore';
import { useSystemDetail } from '@/features/system-detail/useSystemDetail';
import { archetypeFromEconomy } from '@/features/system-detail/simulation-preview/utils/placementHelpers';
import { writeSelectedOperatorSourceRun } from '@/features/operator/operatorSelection';
import type { UseWatchlist } from '@/features/watchlist/useWatchlist';
import type { HashRoute } from '@/hooks/useHashRoute';
import { systemStatusLabel } from '@/lib/format';
import type { SemanticStatusTone } from '@/components/SemanticStatusBadge';
import type { SystemDetail } from '@/types/api';
import { persistShellContextSystemId, readPersistedShellContextSystemId } from '@/app/shellContextStorage';
import { type SavedSystemActionState, type SavedSystemNoticeState, savedSystemFailureDetail } from '@/app/savedSystems';

export interface ShellSelectedSystem {
  id64: number;
  name: string | null;
  loading: boolean;
  evidenceLabel: string;
  evidenceTone: SemanticStatusTone;
  evidenceSummary: string;
}

interface UseProductShellOptions {
  route: HashRoute['route'];
  selectedSystemId: number | null;
  plannerSystemId: number | null;
  plannerProjectId: string | null;
  plannerMode: HashRoute['plannerMode'];
  navigate: HashRoute['navigate'];
  openSystem: HashRoute['openSystem'];
  openColonyPlanner: HashRoute['openColonyPlanner'];
  closeSystem: HashRoute['closeSystem'];
  watchlist: UseWatchlist;
}

export function useProductShell({
  route,
  selectedSystemId,
  plannerSystemId,
  plannerProjectId,
  plannerMode,
  navigate,
  openSystem,
  openColonyPlanner,
  closeSystem,
  watchlist,
}: UseProductShellOptions) {
  const saveProject = useColonyProjectStore((state) => state.saveProject);
  const [detailFocus, setDetailFocus] = useState<'colony-planner' | null>(null);
  const [savedSystemActionState, setSavedSystemActionState] = useState<Record<number, SavedSystemActionState>>({});
  const [savedSystemNotice, setSavedSystemNotice] = useState<SavedSystemNoticeState | null>(null);
  const [shellContextSystemId, setShellContextSystemId] = useState<number | null>(() => readPersistedShellContextSystemId());
  const routeSystemId = plannerSystemId ?? selectedSystemId;
  const shellSystem = useSystemDetail(shellContextSystemId);

  useEffect(() => {
    if (routeSystemId != null) {
      setShellContextSystemId(routeSystemId);
    }
  }, [routeSystemId]);

  useEffect(() => {
    persistShellContextSystemId(shellContextSystemId);
  }, [shellContextSystemId]);

  const shellSelectedSystem = shellContextSystemId != null
    ? buildShellSelectedSystem(shellContextSystemId, shellSystem.data, shellSystem.loading)
    : null;

  const openSystemDetail = useCallback((id64: number, options?: { focus?: 'colony-planner'; hostRoute?: HashRoute['route'] }) => {
    setDetailFocus(options?.focus ?? null);
    setShellContextSystemId(id64);
    openSystem(id64, { hostRoute: options?.hostRoute });
  }, [openSystem]);

  const openColonyPlannerWorkspace = useCallback((id64: number) => {
    const systemId64 = Number(id64);
    if (!Number.isFinite(systemId64) || systemId64 <= 0) return;
    setDetailFocus(null);
    setShellContextSystemId(systemId64);
    openColonyPlanner(systemId64);
  }, [openColonyPlanner]);

  const openShellContextInPlan = useCallback(() => {
    if (shellContextSystemId == null) return;
    setDetailFocus(null);
    openColonyPlanner(shellContextSystemId, {
      mode: route === 'colony-planner' ? plannerMode : 'build-plan',
      projectId: route === 'colony-planner' ? plannerProjectId : null,
    });
  }, [openColonyPlanner, plannerMode, plannerProjectId, route, shellContextSystemId]);

  const closeSystemDetail = useCallback(() => {
    setDetailFocus(null);
    closeSystem();
  }, [closeSystem]);

  const openOperatorDashboard = useCallback((sourceRunKey?: string) => {
    writeSelectedOperatorSourceRun(sourceRunKey ?? null);
    navigate('operator');
  }, [navigate]);

  const toggleSavedSystem = useCallback(async (
    id64: number,
    hint: {
      name?: string | null;
      x?: number | null;
      y?: number | null;
      z?: number | null;
      population?: number | null;
      is_colonised?: boolean;
      developmentScore?: number | null;
      economy_suggestion?: string | null;
      primary_archetype?: string | null;
      secondary_archetype?: string | null;
      buildability_score?: number | null;
      purity_score?: number | null;
    },
  ) => {
    if (savedSystemActionState[id64] && savedSystemActionState[id64] !== 'idle') return;
    const saved = watchlist.has(id64);
    const actionState: SavedSystemActionState = saved ? 'removing' : 'saving';
    const name = hint.name?.trim() || `System ${id64}`;

    setSavedSystemActionState((current) => ({ ...current, [id64]: actionState }));
    try {
      if (saved) {
        await watchlist.remove(id64);
        setSavedSystemNotice({
          tone: 'success',
          message: 'Removed from saved',
          detail: `${name} was removed from My Work saved systems.`,
        });
        return;
      }
      await watchlist.add(id64, {
        name,
        x: hint.x ?? null,
        y: hint.y ?? null,
        z: hint.z ?? null,
        population: hint.population ?? null,
        is_colonised: hint.is_colonised ?? false,
        economy_suggestion: hint.economy_suggestion ?? null,
        archetype_score: hint.developmentScore ?? null,
        primary_archetype: hint.primary_archetype ?? null,
        secondary_archetype: hint.secondary_archetype ?? null,
        buildability_score: hint.buildability_score ?? null,
        purity_score: hint.purity_score ?? null,
      });
      setSavedSystemNotice({
        tone: 'success',
        message: 'Saved to My Work',
        detail: `${name} is available in saved systems.`,
        actionLabel: 'Open My Work',
      });
    } catch (error) {
      setSavedSystemNotice({
        tone: 'error',
        message: saved ? 'Could not remove saved system' : 'Could not save system',
        detail: savedSystemFailureDetail(error, saved),
      });
    } finally {
      setSavedSystemActionState((current) => {
        const next = { ...current };
        delete next[id64];
        return next;
      });
    }
  }, [savedSystemActionState, watchlist]);

  const startPlanFromSystemDetail = useCallback((
    system: SystemDetail,
    planStart: {
      objective: ColonyProjectObjective;
      startApproach: ColonyProjectStartApproach;
    },
  ) => {
    const targetArchetype = system.primary_archetype
      ?? archetypeFromEconomy(system.primary_economy)
      ?? 'refinery_industrial';
    const saved = saveProject(null, {
      system_id64: system.id64,
      system_name: system.name || 'Unknown system',
      project_name: defaultDraftProjectName(system.name || 'Unknown system', planStart.objective),
      build_plan_placements: [],
      target_archetype: targetArchetype,
      notes: '',
      status: 'draft',
      objective: planStart.objective,
      start_approach: planStart.startApproach,
      created_from: 'system_detail',
    });
    setDetailFocus(null);
    setShellContextSystemId(system.id64);
    openColonyPlanner(system.id64, { projectId: saved.id });
  }, [openColonyPlanner, saveProject]);

  return {
    detailFocus,
    savedSystemActionState,
    savedSystemNotice,
    setSavedSystemNotice,
    shellContextSystemId,
    shellSystem,
    shellSelectedSystem,
    openSystemDetail,
    openColonyPlannerWorkspace,
    openShellContextInPlan,
    closeSystemDetail,
    openOperatorDashboard,
    toggleSavedSystem,
    startPlanFromSystemDetail,
  };
}

function buildShellSelectedSystem(
  id64: number,
  system: SystemDetail | null,
  loading: boolean,
): ShellSelectedSystem {
  if (loading) {
    return {
      id64,
      name: null,
      loading: true,
      evidenceLabel: 'Refreshing context',
      evidenceTone: 'loading',
      evidenceSummary: 'Refreshing the selected-system evidence posture for the current player flow.',
    };
  }

  if (!system) {
    return {
      id64,
      name: null,
      loading: false,
      evidenceLabel: 'Selected context',
      evidenceTone: 'unknown',
      evidenceSummary: 'This system remains selected across Explore, Inspect, Plan, and Review until you choose another one.',
    };
  }

  const status = systemStatusLabel(system);
  const confidence = typeof system.archetype_confidence === 'number' ? Math.round(system.archetype_confidence * 100) : null;
  const primaryContext = system.primary_archetype ?? system.primary_economy ?? 'system context';

  if (status === 'Colonised') {
    return {
      id64,
      name: system.name ?? null,
      loading: false,
      evidenceLabel: 'Observed colony state',
      evidenceTone: 'observed',
      evidenceSummary: `${primaryContext} with inhabited or colonised evidence in view. Planner changes remain separate from observed status.`,
    };
  }

  if (status === 'Colonising') {
    return {
      id64,
      name: system.name ?? null,
      loading: false,
      evidenceLabel: 'Needs current review',
      evidenceTone: 'needs_review',
      evidenceSummary: `Colonisation activity is already in motion here. Inspect current evidence before changing or continuing a plan for ${system.name ?? 'this system'}.`,
    };
  }

  return {
    id64,
    name: system.name ?? null,
    loading: false,
    evidenceLabel: confidence != null && confidence < 60 ? 'Candidate needs review' : 'Available candidate',
    evidenceTone: confidence != null && confidence < 60 ? 'needs_review' : 'available',
    evidenceSummary: confidence != null
      ? `${primaryContext} remains a planning candidate with ${confidence}% archetype confidence. Canonical planner truth is still created in Plan, not by this evidence summary.`
      : `${primaryContext} remains a planning candidate. Canonical planner truth is still created in Plan, not by this evidence summary.`,
  };
}
