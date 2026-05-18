import type { RecommendedBuildPlan, SystemDetail } from '@/types/api';
import { SimulationPreview } from './SimulationPreview';
import type { TopologyPlanSnapshot } from '@/features/colony-planner/ColonyTopologyRail';

export function SimulationPreviewPanel({
  system,
  selectedPlan,
  onPlanSnapshotChange,
}: {
  system: SystemDetail;
  selectedPlan: RecommendedBuildPlan | null;
  onPlanSnapshotChange?: (snapshot: TopologyPlanSnapshot) => void;
}) {
  return (
    <SimulationPreview
      system={system}
      initialRequest={selectedPlan?.simulation_request ?? null}
      initialPlanLabel={selectedPlan?.label ?? null}
      initialAssumptions={selectedPlan?.assumptions ?? []}
      onPlanSnapshotChange={onPlanSnapshotChange}
    />
  );
}
