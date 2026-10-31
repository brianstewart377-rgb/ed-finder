import type { PlanStepV1 } from '$lib/api';
import type { PlannerSite } from './model';

export const resultLabel: Record<PlanStepV1['result'], string> = {
  OK: 'OK',
  BLOCKED: 'Blocked',
  NEEDS_INFO: 'Needs info',
  COUNTED: 'Counted',
  IGNORED: 'Ignored',
};
export const resultIcon: Record<PlanStepV1['result'], string> = {
  OK: '✓',
  BLOCKED: '✕',
  NEEDS_INFO: '?',
  COUNTED: '●',
  IGNORED: '–',
};
export const statusIcon: Record<PlannerSite['status'], string> = {
  complete: '●',
  building: '◐',
  planned: '○',
  demolished: '✕',
};
