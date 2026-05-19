import type { RecommendedBuildPlan, SimulateBuildRequest, SystemDetail } from '@/types/api';
import { SimulationPreview } from './SimulationPreview';
import type { TopologyPlanSnapshot, TopologySelection } from '@/features/colony-planner/ColonyTopologyRail';
import type { DeclaredColonyRole } from '@/features/colony-planner/colonyRoles';
import type { PlannerWorkspaceCommand, ReviewDrawer } from '@/features/colony-planner/workspaceUtils';

export function SimulationPreviewPanel({
  system,
  selectedPlan,
  onPlanSnapshotChange,
  topologySelection,
  initialRequest,
  declaredRoles = [],
  workspaceCommand,
  workspaceDrawer,
  onWorkspaceDrawerChange,
}: {
  system: SystemDetail;
  selectedPlan: RecommendedBuildPlan | null;
  onPlanSnapshotChange?: (snapshot: TopologyPlanSnapshot) => void;
  topologySelection?: TopologySelection;
  initialRequest?: SimulateBuildRequest | null;
  declaredRoles?: DeclaredColonyRole[];
  workspaceCommand?: PlannerWorkspaceCommand | null;
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
      workspaceCommand={workspaceCommand}
      workspaceDrawer={workspaceDrawer}
      onWorkspaceDrawerChange={onWorkspaceDrawerChange}
    />
  );
}
