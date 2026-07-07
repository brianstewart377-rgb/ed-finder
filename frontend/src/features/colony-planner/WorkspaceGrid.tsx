import type { SystemDetail } from '@/types/api';
import { WholeSystemColonyPlanner } from './WholeSystemColonyPlanner';

export function WorkspaceGrid({ system }: { system: SystemDetail }) {
  return <WholeSystemColonyPlanner system={system} />;
}
