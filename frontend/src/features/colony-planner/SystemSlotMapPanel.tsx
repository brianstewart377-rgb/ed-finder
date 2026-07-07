import type { SystemDetail } from '@/types/api';
import {
  ColonyTopologyRail,
  type TopologyPlanSnapshot,
  type TopologySelection,
} from './ColonyTopologyRail';

export function SystemSlotMapPanel({
  system,
  snapshot,
  selection,
  onSelect,
}: {
  system: SystemDetail;
  snapshot: TopologyPlanSnapshot;
  selection: TopologySelection;
  onSelect: (selection: TopologySelection) => void;
}) {
  return (
    <ColonyTopologyRail
      system={system}
      snapshot={snapshot}
      selection={selection}
      onSelect={onSelect}
    />
  );
}
