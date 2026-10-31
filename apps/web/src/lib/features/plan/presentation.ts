import type { PlanStepV1 } from '$lib/api';

export const resultLabel: Record<PlanStepV1['result'], string> = {
  OK: 'OK',
  BLOCKED: 'Blocked',
  NEEDS_INFO: 'Needs info',
  COUNTED: 'Counted',
  IGNORED: 'Ignored',
};
