import type { FacilityTemplate, RecommendedBuildPlan, SimulateBuildPlacement, SystemDetail } from '@/types/api';
import { SimulationPreview } from './SimulationPreview';

export function SimulationPreviewPanel({
  system,
  selectedPlan,
  onPlanContextChange,
}: {
  system: SystemDetail;
  selectedPlan: RecommendedBuildPlan | null;
  onPlanContextChange?: (context: {
    placements: SimulateBuildPlacement[];
    templates: FacilityTemplate[];
  }) => void;
}) {
  return (
    <SimulationPreview
      system={system}
      initialRequest={selectedPlan?.simulation_request ?? null}
      initialPlanLabel={selectedPlan?.label ?? null}
      initialAssumptions={selectedPlan?.assumptions ?? []}
      onPlanContextChange={onPlanContextChange}
    />
  );
}
