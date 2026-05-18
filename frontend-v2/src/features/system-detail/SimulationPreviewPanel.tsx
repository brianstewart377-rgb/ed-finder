import type { RecommendedBuildPlan, SimulateBuildRequest, SystemDetail } from '@/types/api';
import { SimulationPreview } from './SimulationPreview';
import type { TopologyPlanSnapshot, TopologySelection } from '@/features/colony-planner/ColonyTopologyRail';

export function SimulationPreviewPanel({
  system,
  selectedPlan,
  onPlanSnapshotChange,
  topologySelection,
  initialRequest,
}: {
  system: SystemDetail;
  selectedPlan: RecommendedBuildPlan | null;
  onPlanSnapshotChange?: (snapshot: TopologyPlanSnapshot) => void;
  topologySelection?: TopologySelection;
  initialRequest?: SimulateBuildRequest | null;
}) {
  return (
    <SimulationPreview
      system={system}
      initialRequest={initialRequest ?? selectedPlan?.simulation_request ?? null}
      initialPlanLabel={selectedPlan?.label ?? null}
      initialAssumptions={selectedPlan?.assumptions ?? []}
      onPlanSnapshotChange={onPlanSnapshotChange}
      topologySelection={topologySelection}
    />
  );
}
