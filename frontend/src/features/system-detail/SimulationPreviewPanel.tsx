import type { RecommendedBuildPlan, SimulateBuildRequest, SystemDetail } from '@/types/api';
import { SimulationPreview } from './SimulationPreview';
import type { TopologyPlanSnapshot, TopologySelection } from '@/features/colony-planner/ColonyTopologyRail';
import type { DeclaredColonyRole } from '@/features/colony-planner/colonyRoles';
import type { PlannerWorkspaceCommand, ReviewDrawer } from '@/features/colony-planner/workspaceUtils';
import type { SimulationWorkspaceMode } from './simulation-preview/WorkspaceModeTabs';

export function SimulationPreviewPanel({
  system,
  selectedPlan,
  onPlanSnapshotChange,
  topologySelection,
  initialRequest,
  declaredRoles = [],
  workspaceCommand,
  lastHandledWorkspaceCommandToken,
  onWorkspaceCommandHandled,
  workspaceDrawer,
  onWorkspaceDrawerChange,
  initialMode,
}: {
  system: SystemDetail;
  selectedPlan: RecommendedBuildPlan | null;
  onPlanSnapshotChange?: (snapshot: TopologyPlanSnapshot) => void;
  topologySelection?: TopologySelection;
  initialRequest?: SimulateBuildRequest | null;
  declaredRoles?: DeclaredColonyRole[];
  workspaceCommand?: PlannerWorkspaceCommand | null;
  lastHandledWorkspaceCommandToken?: number;
  onWorkspaceCommandHandled?: (token: number) => void;
  workspaceDrawer?: ReviewDrawer;
  onWorkspaceDrawerChange?: (drawer: ReviewDrawer) => void;
  initialMode?: SimulationWorkspaceMode;
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
      lastHandledWorkspaceCommandToken={lastHandledWorkspaceCommandToken}
      onWorkspaceCommandHandled={onWorkspaceCommandHandled}
      workspaceDrawer={workspaceDrawer}
      onWorkspaceDrawerChange={onWorkspaceDrawerChange}
      initialMode={initialMode}
    />
  );
}
