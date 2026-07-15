import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

export type ExpansionPlanStatus = 'planning' | 'in_progress' | 'established';

export interface ExpansionPlanSlot {
  slot_index:              number;
  label:                   string;
  economies:               string[];
  system_id64:             number;
  system_name:             string;
  scores:                  Record<string, number>;
  distance_from_anchor_ly: number | null;
  colony_project_id:       string | null;
}

export interface ExpansionPlan {
  id:                  string;
  plan_name:           string;
  anchor_system_id64:  number;
  anchor_system_name:  string;
  galaxy_region:       string | null;
  slots:                ExpansionPlanSlot[];
  notes:                string;
  created_from:         'cluster_search';
  created_at:           string;
  updated_at:           string;
  archived_at:          string | null;
}

export interface ExpansionPlanSlotInput {
  slot_index:              number;
  label:                   string;
  economies:               string[];
  system_id64:             number;
  system_name:             string;
  scores:                  Record<string, number>;
  distance_from_anchor_ly: number | null;
}

export interface ExpansionPlanInput {
  plan_name?:          string;
  anchor_system_id64:  number;
  anchor_system_name:  string;
  galaxy_region:        string | null;
  slots:                ExpansionPlanSlotInput[];
  notes?:               string;
}

interface ExpansionPlanState {
  plans: Record<string, ExpansionPlan>;
  createPlan:      (input: ExpansionPlanInput) => ExpansionPlan;
  renamePlan:      (planId: string, name: string) => void;
  updateSlotSystem: (planId: string, slotIndex: number, system: {
    system_id64: number; system_name: string;
    scores: Record<string, number>; distance_from_anchor_ly: number | null;
  }) => void;
  linkSlotProject: (planId: string, slotIndex: number, colonyProjectId: string | null) => void;
  archivePlan:     (planId: string) => void;
  deletePlan:      (planId: string) => void;
}

const STORAGE_KEY = 'ed_expansion_plans_v1';
const SKIP_PERSIST_HYDRATION = import.meta.env.MODE === 'test';

export const useExpansionPlanStore = create<ExpansionPlanState>()(
  persist(
    (set, get) => ({
      plans: {},

      createPlan: (input) => {
        const now = new Date().toISOString();
        const id = createPlanId(input.anchor_system_id64);
        const plan: ExpansionPlan = {
          id,
          plan_name: (input.plan_name?.trim()) || `${input.anchor_system_name} Expansion`,
          anchor_system_id64: input.anchor_system_id64,
          anchor_system_name: input.anchor_system_name,
          galaxy_region: input.galaxy_region,
          slots: input.slots.map((s) => ({ ...s, colony_project_id: null })),
          notes: input.notes ?? '',
          created_from: 'cluster_search',
          created_at: now,
          updated_at: now,
          archived_at: null,
        };
        set((state) => ({ plans: { ...state.plans, [id]: plan } }));
        return plan;
      },

      renamePlan: (planId, name) => {
        const trimmed = name.trim();
        if (!trimmed) return;
        const plan = get().plans[planId];
        if (!plan) return;
        set((state) => ({
          plans: {
            ...state.plans,
            [planId]: { ...plan, plan_name: trimmed, updated_at: new Date().toISOString() },
          },
        }));
      },

      updateSlotSystem: (planId, slotIndex, system) => {
        const plan = get().plans[planId];
        if (!plan) return;
        const slots = plan.slots.map((s) =>
          s.slot_index === slotIndex
            ? { ...s, ...system, colony_project_id: null }  // reset link on swap
            : s
        );
        set((state) => ({
          plans: {
            ...state.plans,
            [planId]: { ...plan, slots, updated_at: new Date().toISOString() },
          },
        }));
      },

      linkSlotProject: (planId, slotIndex, colonyProjectId) => {
        const plan = get().plans[planId];
        if (!plan) return;
        const slots = plan.slots.map((s) =>
          s.slot_index === slotIndex ? { ...s, colony_project_id: colonyProjectId } : s
        );
        set((state) => ({
          plans: {
            ...state.plans,
            [planId]: { ...plan, slots, updated_at: new Date().toISOString() },
          },
        }));
      },

      archivePlan: (planId) => {
        const plan = get().plans[planId];
        if (!plan) return;
        set((state) => ({
          plans: {
            ...state.plans,
            [planId]: { ...plan, archived_at: new Date().toISOString(), updated_at: new Date().toISOString() },
          },
        }));
      },

      deletePlan: (planId) => {
        set((state) => {
          const plans = { ...state.plans };
          delete plans[planId];
          return { plans };
        });
      },
    }),
    {
      name: STORAGE_KEY,
      storage: createJSONStorage(() => localStorage),
      skipHydration: SKIP_PERSIST_HYDRATION,
      version: 1,
      merge: (persistedState, currentState) => ({
        ...currentState,
        ...(persistedState as Partial<ExpansionPlanState> | undefined),
      }),
    },
  ),
);

export function rehydrateExpansionPlanStore(): Promise<void> {
  return Promise.resolve(useExpansionPlanStore.persist.rehydrate());
}

export function activePlansForSystem(plans: ExpansionPlan[], systemId64: number) {
  return plans.filter(
    (plan) => !plan.archived_at && plan.slots.some((s) => s.system_id64 === systemId64)
  );
}

export function planForColonyProject(plans: ExpansionPlan[], colonyProjectId: string) {
  for (const plan of plans) {
    if (plan.archived_at) continue;
    const slot = plan.slots.find((s) => s.colony_project_id === colonyProjectId);
    if (slot) return { plan, slot };
  }
  return null;
}

function createPlanId(anchorId64: number) {
  const random = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `expansion-${anchorId64}-${random}`;
}
