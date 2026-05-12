import type { RecommendedBuildPlan, SystemDetail } from '@/types/api';
import { SimulationPreview } from './SimulationPreview';

export function SimulationPreviewPanel({
  system,
  selectedPlan,
}: {
  system: SystemDetail;
  selectedPlan: RecommendedBuildPlan | null;
}) {
  return (
    <SimulationPreview
      system={system}
      initialRequest={selectedPlan?.simulation_request ?? null}
      initialPlanLabel={selectedPlan?.label ?? null}
      initialAssumptions={selectedPlan?.assumptions ?? []}
    />
  );
}
