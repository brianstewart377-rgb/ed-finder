import { useMemo } from 'react';
import type { SimulationWorkspaceMode } from '@/features/system-detail/simulation-preview/WorkspaceModeTabs';
import { SimulationPreviewPanel } from '@/features/system-detail/SimulationPreviewPanel';
import type { SimulateBuildRequest, SystemDetail } from '@/types/api';
import type { DeclaredColonyRole } from './colonyRoles';
import type { TopologyPlanSnapshot, TopologySelection } from './ColonyTopologyRail';
import type { PlannerWorkspaceCommand } from './workspaceUtils';

export function AdvancedPlannerDrawer({
  open,
  initialMode,
  system,
  snapshot,
  selection,
  declaredRoles,
  workspaceCommand,
  lastHandledWorkspaceCommandToken,
  onOpenChange,
  onPlanSnapshotChange,
  onWorkspaceCommandHandled,
}: {
  open: boolean;
  initialMode: SimulationWorkspaceMode;
  system: SystemDetail;
  snapshot: TopologyPlanSnapshot;
  selection: TopologySelection;
  declaredRoles: DeclaredColonyRole[];
  workspaceCommand: PlannerWorkspaceCommand | null;
  lastHandledWorkspaceCommandToken: number;
  onOpenChange: (open: boolean) => void;
  onPlanSnapshotChange: (snapshot: TopologyPlanSnapshot) => void;
  onWorkspaceCommandHandled: (token: number) => void;
}) {
  const initialRequest = useMemo<SimulateBuildRequest>(() => ({
    system_id64: system.id64,
    target_archetype: snapshot.targetArchetype,
    placements: snapshot.placements,
  }), [snapshot.placements, snapshot.targetArchetype, system.id64]);

  return (
    <section className="mt-3 rounded-chunk-lg border border-border/55 bg-bg2/35" data-testid="advanced-planner-drawer">
      <button
        type="button"
        data-testid="advanced-workspace-toggle"
        onClick={() => onOpenChange(!open)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left"
      >
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-silver-dk">Advanced Planner</div>
          <p className="mt-0.5 font-mono text-[10px] text-silver-dk">
            Suggested Builds, Preview, and list editor remain explicit tools.
          </p>
        </div>
        <span className="rounded border border-border/60 bg-bg3/45 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-silver">
          {open ? 'Hide' : 'Open'}
        </span>
      </button>
      {open && (
        <div className="border-t border-border/60 px-2 pb-2 pt-2" data-testid="advanced-planner-content">
          <SimulationPreviewPanel
            system={system}
            selectedPlan={null}
            initialMode={initialMode}
            onPlanSnapshotChange={onPlanSnapshotChange}
            topologySelection={selection}
            initialRequest={initialRequest}
            declaredRoles={declaredRoles}
            workspaceCommand={workspaceCommand}
            lastHandledWorkspaceCommandToken={lastHandledWorkspaceCommandToken}
            onWorkspaceCommandHandled={onWorkspaceCommandHandled}
          />
        </div>
      )}
    </section>
  );
}
