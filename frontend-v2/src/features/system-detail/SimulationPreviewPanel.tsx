import type { RecommendedBuildPlan, SimulateBuildRequest, SystemDetail } from '@/types/api';
import { SimulationPreview } from './SimulationPreview';
import type { TopologyPlanSnapshot, TopologySelection } from '@/features/colony-planner/ColonyTopologyRail';
import type { DeclaredColonyRole } from '@/features/colony-planner/colonyRoles';
import type { ReviewDrawer } from '@/features/colony-planner/workspaceUtils';

export function SimulationPreviewPanel({
  system,
  selectedPlan,
  onPlanSnapshotChange,
  topologySelection,
  initialRequest,
  declaredRoles = [],
  workspaceDrawer,
  onWorkspaceDrawerChange,
}: {
  system: SystemDetail;
  selectedPlan: RecommendedBuildPlan | null;
  onPlanSnapshotChange?: (snapshot: TopologyPlanSnapshot) => void;
  topologySelection?: TopologySelection;
  initialRequest?: SimulateBuildRequest | null;
  declaredRoles?: DeclaredColonyRole[];
  workspaceDrawer?: ReviewDrawer;
  onWorkspaceDrawerChange?: (drawer: ReviewDrawer) => void;
}) {
  return (
    <SimulationPreview
      system={system}
      initialRequest={initialRequest ?? selectedPlan?.simulation_request ?? null}
      initialPlanLabel={selectedPlan?.label ?? null}
      initialAssumptions={selectedPlan?.assumptions ?? []}
      onPlanSnapshotChange={onPlanSnapshotChange}
      topologySelection={topologySelection}
      declaredRoles={declaredRoles}
      workspaceDrawer={workspaceDrawer}
      onWorkspaceDrawerChange={onWorkspaceDrawerChange}
    />
  );
}
