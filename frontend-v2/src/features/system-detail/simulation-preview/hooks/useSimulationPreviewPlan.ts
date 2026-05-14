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
import { preferredTemplate, resequence } from '../utils/placementHelpers';

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
  const [placements, setPlacements] = useState<SimulateBuildPlacement[]>([]);
  const [startMode, setStartMode] = useState<StartMode>('recommended');
  const [autoLoadedRecommendation, setAutoLoadedRecommendation] = useState(false);
  const [optimiserCandidateOriginLabel, setOptimiserCandidateOriginLabel] = useState<string | null>(null);
  const [optimiserCandidateWasEdited, setOptimiserCandidateWasEdited] = useState(false);
  const [planReplacementVersion, setPlanReplacementVersion] = useState(0);

  const clearOptimiserOrigin = () => {
    setOptimiserCandidateOriginLabel(null);
    setOptimiserCandidateWasEdited(false);
  };

  const markOptimiserCandidateEdited = () => {
    if (optimiserCandidateOriginLabel) {
      setOptimiserCandidateWasEdited(true);
    }
  };

  useEffect(() => {
    if (!initialRequest) return;
    setTargetArchetype(initialRequest.target_archetype);
    setPlacements(resequence(initialRequest.placements));
    setStartMode('edit_recommended');
    clearOptimiserOrigin();
    setAutoLoadedRecommendation(true);
    setPlanReplacementVersion((current) => current + 1);
  }, [initialRequest]);

  useEffect(() => {
    if (!hasRecommendedBuild || autoLoadedRecommendation) return;
    if (placements.length > 0 || startMode === 'blank_advanced') return;
    setTargetArchetype(suggestedArchetype);
    setPlacements(recommendedPlacements);
    setStartMode('recommended');
    clearOptimiserOrigin();
    setAutoLoadedRecommendation(true);
    setPlanReplacementVersion((current) => current + 1);
  }, [
    autoLoadedRecommendation,
    hasRecommendedBuild,
    placements.length,
    recommendedPlacements,
    startMode,
    suggestedArchetype,
  ]);

  const loadRecommendedPlan = (mode: StartMode) => {
    if (!hasRecommendedBuild) return;
    setStartMode(mode);
    setTargetArchetype(suggestedArchetype);
    setPlacements(recommendedPlacements);
    clearOptimiserOrigin();
    setPlanReplacementVersion((current) => current + 1);
  };

  const loadOptimiserCandidateIntoPreview = (candidate: OptimiserCandidate) => {
    const candidatePlacements = candidatePlacementsToPreviewPlacements(candidate.placements);
    setTargetArchetype(candidate.target_archetype);
    setPlacements(resequence(candidatePlacements));
    setStartMode('optimiser_candidate');
    setAutoLoadedRecommendation(true);
    setOptimiserCandidateOriginLabel(candidate.label);
    setOptimiserCandidateWasEdited(false);
    setPlanReplacementVersion((current) => current + 1);
  };

  const startBlankAdvanced = () => {
    setStartMode('blank_advanced');
    clearOptimiserOrigin();
    setAutoLoadedRecommendation(true);
    setPlacements([]);
    setPlanReplacementVersion((current) => current + 1);
  };

  const addPlacement = () => {
    const firstTemplate = preferredTemplate(templates);
    if (!firstTemplate) return;
    markOptimiserCandidateEdited();
    if (placements.length === 0 && startMode !== 'blank_advanced') {
      setStartMode('edit_recommended');
    }
    setPlacements((current) => [
      ...current,
      {
        facility_template_id: firstTemplate.id,
        local_body_id: bodies[0]?.id != null ? String(bodies[0].id) : null,
        is_primary_port: current.length === 0 && firstTemplate.is_port,
        build_order: current.length + 1,
      },
    ]);
  };

  const updatePlacement = (index: number, patch: Partial<SimulateBuildPlacement>) => {
    markOptimiserCandidateEdited();
    if (startMode === 'recommended') {
      setStartMode('edit_recommended');
    }
    setPlacements((current) => current.map((item, i) => {
      if (i !== index) {
        return patch.is_primary_port ? { ...item, is_primary_port: false } : item;
      }
      return { ...item, ...patch };
    }));
  };

  const removePlacement = (index: number) => {
    markOptimiserCandidateEdited();
    if (startMode === 'recommended') {
      setStartMode('edit_recommended');
    }
    setPlacements((current) => resequence(current.filter((_, i) => i !== index)));
  };

  const movePlacement = (index: number, direction: -1 | 1) => {
    markOptimiserCandidateEdited();
    if (startMode === 'recommended') {
      setStartMode('edit_recommended');
    }
    setPlacements((current) => {
      const nextIndex = index + direction;
      if (nextIndex < 0 || nextIndex >= current.length) return current;
      const copy = [...current];
      [copy[index], copy[nextIndex]] = [copy[nextIndex], copy[index]];
      return resequence(copy);
    });
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
