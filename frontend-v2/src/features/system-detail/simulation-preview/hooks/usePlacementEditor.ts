import { useState, type Dispatch, type SetStateAction } from 'react';
import type { FacilityTemplate, SimulateBuildPlacement, SystemBody } from '@/types/api';
import type { StartMode } from '../types';
import { preferredTemplate, resequence } from '../utils/placementHelpers';

export interface UsePlacementEditorOptions {
  templates: FacilityTemplate[];
  bodies: SystemBody[];
  startMode: StartMode;
  setStartMode: (mode: StartMode) => void;
  onManualEdit: () => void;
}

export interface UsePlacementEditorResult {
  placements: SimulateBuildPlacement[];
  setPlacements: Dispatch<SetStateAction<SimulateBuildPlacement[]>>;
  replacePlacements: (nextPlacements: SimulateBuildPlacement[]) => void;
  clearPlacements: () => void;
  addPlacement: () => void;
  updatePlacement: (index: number, patch: Partial<SimulateBuildPlacement>) => void;
  removePlacement: (index: number) => void;
  movePlacement: (index: number, direction: -1 | 1) => void;
}

export function usePlacementEditor({
  templates,
  bodies,
  startMode,
  setStartMode,
  onManualEdit,
}: UsePlacementEditorOptions): UsePlacementEditorResult {
  const [placements, setPlacements] = useState<SimulateBuildPlacement[]>([]);

  const replacePlacements = (nextPlacements: SimulateBuildPlacement[]) => {
    setPlacements(resequence(nextPlacements));
  };

  const clearPlacements = () => {
    setPlacements([]);
  };

  const addPlacement = () => {
    const firstTemplate = preferredTemplate(templates);
    if (!firstTemplate) return;
    onManualEdit();
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
    onManualEdit();
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
    onManualEdit();
    if (startMode === 'recommended') {
      setStartMode('edit_recommended');
    }
    setPlacements((current) => resequence(current.filter((_, i) => i !== index)));
  };

  const movePlacement = (index: number, direction: -1 | 1) => {
    onManualEdit();
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
    placements,
    setPlacements,
    replacePlacements,
    clearPlacements,
    addPlacement,
    updatePlacement,
    removePlacement,
    movePlacement,
  };
}
