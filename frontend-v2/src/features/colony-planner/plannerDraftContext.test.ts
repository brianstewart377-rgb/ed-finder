import { describe, expect, it } from 'vitest';
import {
  defaultDraftProjectName,
  objectiveLabel,
  plannerNextActionCopy,
  startApproachLabel,
} from './plannerDraftContext';

describe('destination-first corridor planner intent', () => {
  it('keeps the selected target explicit and never frames it as a replaceable recommendation', () => {
    expect(objectiveLabel('destination_first_corridor')).toBe('Destination-first corridor');
    expect(startApproachLabel('destination_first_corridor')).toBe('Destination-first');
    expect(defaultDraftProjectName('Blu Thua JS-J D9-1', 'destination_first_corridor'))
      .toBe('Blu Thua JS-J D9-1 - Corridor expedition');
    expect(plannerNextActionCopy('destination_first_corridor')).toContain('Destination locked');
    expect(plannerNextActionCopy('destination_first_corridor')).toContain('do not substitute another target');
    expect(plannerNextActionCopy('destination_first_corridor')).toContain('Route search has not yet checked intermediate systems');
  });
});
