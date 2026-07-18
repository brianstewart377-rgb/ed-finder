import { beforeEach, describe, expect, it } from 'vitest';
import {
  activePlansForSystem,
  planForColonyProject,
  useExpansionPlanStore,
} from './expansionPlanStore';

const input = {
  anchor_system_id64: 42,
  anchor_system_name: 'Test Anchor',
  galaxy_region: 'Inner Orion Spur',
  slots: [{
    slot_index: 0,
    label: 'Refinery',
    economies: ['Refinery'],
    system_id64: 84,
    system_name: 'First Target',
    scores: { refinery: 80 },
    distance_from_anchor_ly: 12,
  }],
};

describe('expansionPlanStore', () => {
  beforeEach(() => {
    localStorage.clear();
    useExpansionPlanStore.setState({ plans: {} });
  });

  it('creates, renames, and archives a plan', () => {
    const plan = useExpansionPlanStore.getState().createPlan(input);
    expect(plan.plan_name).toBe('Test Anchor Expansion');
    expect(plan.slots[0].colony_project_id).toBeNull();

    useExpansionPlanStore.getState().renamePlan(plan.id, '  Refinery Loop  ');
    expect(useExpansionPlanStore.getState().plans[plan.id].plan_name).toBe('Refinery Loop');

    useExpansionPlanStore.getState().archivePlan(plan.id);
    expect(useExpansionPlanStore.getState().plans[plan.id].archived_at).not.toBeNull();
    expect(activePlansForSystem(Object.values(useExpansionPlanStore.getState().plans), 84)).toEqual([]);
  });

  it('updates slot systems and clears stale project links', () => {
    const plan = useExpansionPlanStore.getState().createPlan(input);
    useExpansionPlanStore.getState().linkSlotProject(plan.id, 0, 'project-1');
    expect(planForColonyProject(Object.values(useExpansionPlanStore.getState().plans), 'project-1')?.plan.id).toBe(plan.id);

    useExpansionPlanStore.getState().updateSlotSystem(plan.id, 0, {
      system_id64: 126,
      system_name: 'Replacement Target',
      scores: { refinery: 92 },
      distance_from_anchor_ly: 18,
    });

    const updated = useExpansionPlanStore.getState().plans[plan.id];
    expect(updated.slots[0]).toMatchObject({
      system_id64: 126,
      system_name: 'Replacement Target',
      colony_project_id: null,
    });
    expect(planForColonyProject([updated], 'project-1')).toBeNull();
  });

  it('deletes a plan without affecting other plans', () => {
    const first = useExpansionPlanStore.getState().createPlan(input);
    const second = useExpansionPlanStore.getState().createPlan({
      ...input,
      anchor_system_id64: 43,
      anchor_system_name: 'Second Anchor',
    });

    useExpansionPlanStore.getState().deletePlan(first.id);

    expect(useExpansionPlanStore.getState().plans[first.id]).toBeUndefined();
    expect(useExpansionPlanStore.getState().plans[second.id]).toBeDefined();
  });
});
