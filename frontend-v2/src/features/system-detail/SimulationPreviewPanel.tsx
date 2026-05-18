import type { RecommendedBuildPlan, SimulateBuildRequest, SystemDetail } from '@/types/api';
import { SimulationPreview } from './SimulationPreview';
import type { TopologyPlanSnapshot, TopologySelection } from '@/features/colony-planner/ColonyTopologyRail';
import type { ReviewDrawer } from '@/features/colony-planner/workspaceUtils';

export function SimulationPreviewPanel({
  system,
  selectedPlan,
  onPlanSnapshotChange,
  topologySelection,
  initialRequest,
  workspaceDrawer,
  onWorkspaceDrawerChange,
  showWorkspaceDrawerControls,
}: {
  system: SystemDetail;
  selectedPlan: RecommendedBuildPlan | null;
  onPlanSnapshotChange?: (snapshot: TopologyPlanSnapshot) => void;
  topologySelection?: TopologySelection;
  initialRequest?: SimulateBuildRequest | null;
  workspaceDrawer?: ReviewDrawer;
  onWorkspaceDrawerChange?: (drawer: ReviewDrawer) => void;
  showWorkspaceDrawerControls?: boolean;
}) {
  return (
    <SimulationPreview
      system={system}
      initialRequest={initialRequest ?? selectedPlan?.simulation_request ?? null}
      initialPlanLabel={selectedPlan?.label ?? null}
      initialAssumptions={selectedPlan?.assumptions ?? []}
      onPlanSnapshotChange={onPlanSnapshotChange}
      topologySelection={topologySelection}
      workspaceDrawer={workspaceDrawer}
      onWorkspaceDrawerChange={onWorkspaceDrawerChange}
      showWorkspaceDrawerControls={showWorkspaceDrawerControls}
    />
  );
}
