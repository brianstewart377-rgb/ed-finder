import { useEffect, useMemo, useRef, useState } from 'react';
import type {
  FacilityTemplate,
  OptimiserCandidate,
  SimulateBuildPlacement,
  SimulateBuildRequest,
  SystemBody,
} from '@/types/api';
import { candidatePlacementsToPreviewPlacements } from '../optimiser';
import type { StartMode } from '../types';
import { resequence } from '../utils/placementHelpers';
import { useOptimiserCandidateOrigin } from './useOptimiserCandidateOrigin';
import { usePlacementEditor } from './usePlacementEditor';

export interface UseSimulationPreviewPlanOptions {
  initialRequest?: SimulateBuildRequest | null;
  templates: FacilityTemplate[];
  bodies: SystemBody[];
  recommendedPlacements: SimulateBuildPlacement[];
  hasRecommendedBuild: boolean;
  suggestedArchetype: string;
}

export interface UseSimulationPreviewPlanResult {
  targetArchetype: string;
  setTargetArchetype: (value: string) => void;
  placements: SimulateBuildPlacement[];
  startMode: StartMode;
  autoLoadedRecommendation: boolean;
  optimiserCandidateOriginLabel: string | null;
  optimiserCandidateWasEdited: boolean;
  loadRecommendedPlan: (mode: StartMode) => void;
  loadOptimiserCandidateIntoPreview: (candidate: OptimiserCandidate) => void;
  startBlankAdvanced: () => void;
  addPlacement: (options?: { bodyId?: string | null; templateId?: string | null }) => void;
  updatePlacement: (index: number, patch: Partial<SimulateBuildPlacement>) => void;
  removePlacement: (index: number) => void;
  movePlacement: (index: number, direction: -1 | 1) => void;
  planReplacementVersion: number;
}

export function useSimulationPreviewPlan({
  initialRequest,
  templates,
  bodies,
  recommendedPlacements,
  hasRecommendedBuild,
  suggestedArchetype,
}: UseSimulationPreviewPlanOptions): UseSimulationPreviewPlanResult {
  const [targetArchetype, setTargetArchetype] = useState('refinery_industrial');
  const [startMode, setStartMode] = useState<StartMode>('recommended');
  const [autoLoadedRecommendation, setAutoLoadedRecommendation] = useState(false);
  const [planReplacementVersion, setPlanReplacementVersion] = useState(0);
  const lastLoadedInitialRequestFingerprintRef = useRef<string | null>(null);

  const origin = useOptimiserCandidateOrigin();
  const placementEditor = usePlacementEditor({
    templates,
    bodies,
    startMode,
    setStartMode,
    onManualEdit: origin.markOptimiserCandidateEdited,
  });
  const placements = placementEditor.placements;
  const replacePlacements = placementEditor.replacePlacements;
  const clearPlacements = placementEditor.clearPlacements;
  const addPlacement = placementEditor.addPlacement;
  const updatePlacement = placementEditor.updatePlacement;
  const removePlacement = placementEditor.removePlacement;
  const movePlacement = placementEditor.movePlacement;
  const clearOptimiserCandidateOrigin = origin.clearOptimiserCandidateOrigin;
  const setLoadedOptimiserCandidate = origin.setLoadedOptimiserCandidate;
  const optimiserCandidateOriginLabel = origin.optimiserCandidateOriginLabel;
  const optimiserCandidateWasEdited = origin.optimiserCandidateWasEdited;

  const signalPlanReplacement = () => {
    setPlanReplacementVersion((current) => current + 1);
  };
  const initialRequestFingerprint = useMemo(
    () => simulationRequestFingerprint(initialRequest),
    [initialRequest],
  );

  useEffect(() => {
    if (!initialRequest || !initialRequestFingerprint) return;
    if (lastLoadedInitialRequestFingerprintRef.current === initialRequestFingerprint) return;
    lastLoadedInitialRequestFingerprintRef.current = initialRequestFingerprint;
    setTargetArchetype(initialRequest.target_archetype);
    replacePlacements(initialRequest.placements);
    setStartMode('edit_recommended');
    clearOptimiserCandidateOrigin();
    setAutoLoadedRecommendation(true);
    signalPlanReplacement();
  }, [
    clearOptimiserCandidateOrigin,
    initialRequest,
    initialRequestFingerprint,
    replacePlacements,
  ]);

  useEffect(() => {
    if (!hasRecommendedBuild || autoLoadedRecommendation) return;
    if (placements.length > 0 || startMode === 'blank_advanced') return;
    setTargetArchetype(suggestedArchetype);
    replacePlacements(recommendedPlacements);
    setStartMode('recommended');
    clearOptimiserCandidateOrigin();
    setAutoLoadedRecommendation(true);
    signalPlanReplacement();
  }, [
    autoLoadedRecommendation,
    clearOptimiserCandidateOrigin,
    hasRecommendedBuild,
    placements.length,
    replacePlacements,
    recommendedPlacements,
    startMode,
    suggestedArchetype,
  ]);

  const loadRecommendedPlan = (mode: StartMode) => {
    if (!hasRecommendedBuild) return;
    setStartMode(mode);
    setTargetArchetype(suggestedArchetype);
    replacePlacements(recommendedPlacements);
    clearOptimiserCandidateOrigin();
    signalPlanReplacement();
  };

  const loadOptimiserCandidateIntoPreview = (candidate: OptimiserCandidate) => {
    const candidatePlacements = candidatePlacementsToPreviewPlacements(candidate.placements);
    setTargetArchetype(candidate.target_archetype);
    replacePlacements(candidatePlacements);
    setStartMode('optimiser_candidate');
    setAutoLoadedRecommendation(true);
    setLoadedOptimiserCandidate(candidate.label);
    signalPlanReplacement();
  };

  const startBlankAdvanced = () => {
    setStartMode('blank_advanced');
    clearOptimiserCandidateOrigin();
    setAutoLoadedRecommendation(true);
    clearPlacements();
    signalPlanReplacement();
  };

  return {
    targetArchetype,
    setTargetArchetype,
    placements,
    startMode,
    autoLoadedRecommendation,
    optimiserCandidateOriginLabel,
    optimiserCandidateWasEdited,
    loadRecommendedPlan,
    loadOptimiserCandidateIntoPreview,
    startBlankAdvanced,
    addPlacement,
    updatePlacement,
    removePlacement,
    movePlacement,
    planReplacementVersion,
  };
}

function simulationRequestFingerprint(request?: SimulateBuildRequest | null): string | null {
  if (!request) return null;
  return JSON.stringify({
    system_id64: request.system_id64,
    target_archetype: request.target_archetype,
    placements: resequence(request.placements).map((placement) => ({
      facility_template_id: placement.facility_template_id,
      local_body_id: placement.local_body_id ?? null,
      is_primary_port: Boolean(placement.is_primary_port),
      build_order: placement.build_order,
    })),
  });
}
