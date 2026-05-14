import { useEffect, useState } from 'react';
import type {
  FacilityTemplate,
  OptimiserCandidate,
  SimulateBuildPlacement,
  SimulateBuildRequest,
  SystemBody,
} from '@/types/api';
import { candidatePlacementsToPreviewPlacements } from '../optimiser';
import type { StartMode } from '../types';
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
  addPlacement: () => void;
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

  const origin = useOptimiserCandidateOrigin();
  const placementEditor = usePlacementEditor({
    templates,
    bodies,
    startMode,
    setStartMode,
    onManualEdit: origin.markOptimiserCandidateEdited,
  });

  const signalPlanReplacement = () => {
    setPlanReplacementVersion((current) => current + 1);
  };

  useEffect(() => {
    if (!initialRequest) return;
    setTargetArchetype(initialRequest.target_archetype);
    placementEditor.replacePlacements(initialRequest.placements);
    setStartMode('edit_recommended');
    origin.clearOptimiserCandidateOrigin();
    setAutoLoadedRecommendation(true);
    signalPlanReplacement();
  }, [initialRequest]);

  useEffect(() => {
    if (!hasRecommendedBuild || autoLoadedRecommendation) return;
    if (placementEditor.placements.length > 0 || startMode === 'blank_advanced') return;
    setTargetArchetype(suggestedArchetype);
    placementEditor.replacePlacements(recommendedPlacements);
    setStartMode('recommended');
    origin.clearOptimiserCandidateOrigin();
    setAutoLoadedRecommendation(true);
    signalPlanReplacement();
  }, [
    autoLoadedRecommendation,
    hasRecommendedBuild,
    placementEditor.placements.length,
    recommendedPlacements,
    startMode,
    suggestedArchetype,
  ]);

  const loadRecommendedPlan = (mode: StartMode) => {
    if (!hasRecommendedBuild) return;
    setStartMode(mode);
    setTargetArchetype(suggestedArchetype);
    placementEditor.replacePlacements(recommendedPlacements);
    origin.clearOptimiserCandidateOrigin();
    signalPlanReplacement();
  };

  const loadOptimiserCandidateIntoPreview = (candidate: OptimiserCandidate) => {
    const candidatePlacements = candidatePlacementsToPreviewPlacements(candidate.placements);
    setTargetArchetype(candidate.target_archetype);
    placementEditor.replacePlacements(candidatePlacements);
    setStartMode('optimiser_candidate');
    setAutoLoadedRecommendation(true);
    origin.setLoadedOptimiserCandidate(candidate.label);
    signalPlanReplacement();
  };

  const startBlankAdvanced = () => {
    setStartMode('blank_advanced');
    origin.clearOptimiserCandidateOrigin();
    setAutoLoadedRecommendation(true);
    placementEditor.clearPlacements();
    signalPlanReplacement();
  };

  return {
    targetArchetype,
    setTargetArchetype,
    placements: placementEditor.placements,
    startMode,
    autoLoadedRecommendation,
    optimiserCandidateOriginLabel: origin.optimiserCandidateOriginLabel,
    optimiserCandidateWasEdited: origin.optimiserCandidateWasEdited,
    loadRecommendedPlan,
    loadOptimiserCandidateIntoPreview,
    startBlankAdvanced,
    addPlacement: placementEditor.addPlacement,
    updatePlacement: placementEditor.updatePlacement,
    removePlacement: placementEditor.removePlacement,
    movePlacement: placementEditor.movePlacement,
    planReplacementVersion,
  };
}
