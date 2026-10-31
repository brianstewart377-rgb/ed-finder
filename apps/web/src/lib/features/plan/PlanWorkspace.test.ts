import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/svelte';
import { tick } from 'svelte';
import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  evaluateV3Plan,
  getV3PlanCatalogue,
  listV3PlanBodies,
  getPlanSystem,
  type PlanBodiesV1,
  type PlanEvaluationV1,
  type PlanFacilityV1,
} from '$lib/api';
import { queryClient } from '$lib/api/query';
import { v3System } from '$lib/api/v3-system-fixtures';
import { colonyProjects } from '$lib/persistence/stores';
import { PERSISTENCE_KEYS } from '$lib/persistence/storage';
import {
  emptyPlan,
  exportPlan,
  plannerToRecord,
  type PlannerSite,
} from './model';
import PlanWorkspaceTestHost from './PlanWorkspaceTestHost.svelte';

vi.mock('$lib/api/client', async (loadOriginal) => ({
  ...(await loadOriginal<typeof import('$lib/api/client')>()),
  evaluateV3Plan: vi.fn(),
  getV3PlanCatalogue: vi.fn(),
  listV3PlanBodies: vi.fn(),
  getPlanSystem: vi.fn(),
}));

const bodyData: PlanBodiesV1 = {
  system_id64: '42',
  generation_id: 'test',
  publication_sequence: '1',
  belts: [],
  bodies: [
    {
      body_id: '1',
      name: 'Test System A',
      direct_parent_body_id: null,
      body_type: 'star',
      is_main_star: true,
      is_landable: false,
      radius_km: 400000,
      surface_gravity_g: null,
      surface_temperature_k: null,
      atmosphere: null,
      terraforming_state: null,
      volcanism: null,
      distance_from_arrival_ls: 0,
      has_rings: false,
      geological_signals: 0,
      biological_signals: 0,
      signals_complete: null,
      lifecycle_state: 'active',
    },
  ],
};
const port: PlanFacilityV1 = {
  id: 'primary-port',
  name: 'Primary Outpost',
  category: 'port',
  tier: 1,
  allowed_location: 'orbital',
  economy: null,
  is_port: true,
  escalating_port_tier: null,
  yellow_cp_cost: 0,
  green_cp_cost: 0,
  yellow_cp_generated: 0,
  green_cp_generated: 0,
  prerequisites: [],
  rule_ids: [],
};
const catalogue = { rulebook_release: 'test', facilities: [port] };
const system = v3System({ id64: '42', name: 'Test System' });

function evaluated(t2: number, blocked = 0): PlanEvaluationV1 {
  return {
    system_id64: '42',
    rulebook_release: 'test',
    now: { t2, t3: 0 },
    after_plan: { t2, t3: 0 },
    next_port_cost: { t2: 3, t3: 6 },
    steps: [],
    plan_checks: [],
    summary: { OK: 0, BLOCKED: blocked, NEEDS_INFO: 0, COUNTED: 0, IGNORED: 0 },
    explanations: {},
  };
}

function importedSite(name = 'Imported port'): PlannerSite {
  return {
    schema: 'cpe_site_v1',
    site_id: 'imported-port',
    facility_id: port.id,
    body_ref: '1',
    slot_kind: 'orbital',
    status: 'planned',
    name,
  };
}

function seedPrimary() {
  const record = plannerToRecord({
    ...emptyPlan('42'),
    sites: [importedSite('Primary port')],
  });
  colonyProjects.set({
    version: 3,
    state: { projects: { [record.id]: record } },
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((yes) => {
    resolve = yes;
  });
  return { promise, resolve };
}

async function advance(ms: number) {
  await vi.advanceTimersByTimeAsync(ms);
  await tick();
}

async function editOrbitalSlots() {
  await fireEvent.click(
    screen.getByRole('button', { name: /Orbital slots on Test System A:/ }),
  );
  await fireEvent.click(
    screen.getByRole('button', { name: 'Increase orbital slots' }),
  );
  await fireEvent.click(screen.getByRole('button', { name: 'Done' }));
}

async function upload(text: string) {
  const file = new File([text], 'plan.json', { type: 'application/json' });
  Object.defineProperty(file, 'text', { value: async () => text });
  await fireEvent.change(screen.getByLabelText('Import plan file'), {
    target: { files: [file] },
  });
  await advance(0);
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.resetAllMocks();
  localStorage.clear();
  colonyProjects.hydrate();
  queryClient.clear();
  vi.mocked(getV3PlanCatalogue).mockResolvedValue(catalogue);
  vi.mocked(listV3PlanBodies).mockResolvedValue(bodyData);
  vi.mocked(getPlanSystem).mockResolvedValue(system);
  vi.mocked(evaluateV3Plan).mockResolvedValue(evaluated(17));
  queryClient.setQueryData(['ed-finder', 'plan-catalogue'], catalogue);
  queryClient.setQueryData(['ed-finder', 'plan-bodies', '42'], bodyData);
  queryClient.setQueryData(['ed-finder', 'plan-system', '42'], system);
});

afterEach(() => {
  cleanup();
  queryClient.clear();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe('planner workspace evaluation and browser state', () => {
  it('does not send an empty plan to the evaluation endpoint', async () => {
    render(PlanWorkspaceTestHost);
    await advance(1000);
    expect(evaluateV3Plan).not.toHaveBeenCalled();
    await editOrbitalSlots();
    await advance(1000);
    expect(evaluateV3Plan).not.toHaveBeenCalled();
    expect(
      screen.getByRole('complementary', { name: 'Summary' }),
    ).toHaveAttribute('aria-busy', 'false');
  });

  it('loads the catalogue once and reuses it when the planner remounts', async () => {
    queryClient.removeQueries({ queryKey: ['ed-finder', 'plan-catalogue'] });
    const first = render(PlanWorkspaceTestHost);
    await advance(0);
    expect(getV3PlanCatalogue).toHaveBeenCalledOnce();
    first.unmount();
    render(PlanWorkspaceTestHost);
    await advance(0);
    expect(getV3PlanCatalogue).toHaveBeenCalledOnce();
  });

  it('debounces edits for 250 ms and evaluates the latest slot count', async () => {
    seedPrimary();
    render(PlanWorkspaceTestHost);
    await advance(250);
    expect(evaluateV3Plan).toHaveBeenCalledOnce();
    vi.mocked(evaluateV3Plan).mockClear();

    await editOrbitalSlots();
    await advance(200);
    expect(evaluateV3Plan).not.toHaveBeenCalled();
    await editOrbitalSlots();
    await advance(249);
    expect(evaluateV3Plan).not.toHaveBeenCalled();
    await advance(1);
    expect(evaluateV3Plan).toHaveBeenCalledOnce();
    expect(
      vi.mocked(evaluateV3Plan).mock.calls[0][0].bodies?.[0],
    ).toMatchObject({
      body_ref: '1',
      orbital_slots: 2,
    });
  });

  it('ignores an earlier response even if it arrives after the current evaluation', async () => {
    seedPrimary();
    const oldRequest = deferred<PlanEvaluationV1>();
    const currentRequest = deferred<PlanEvaluationV1>();
    vi.mocked(evaluateV3Plan)
      .mockImplementationOnce(() => oldRequest.promise)
      .mockImplementationOnce(() => currentRequest.promise);
    render(PlanWorkspaceTestHost);
    await advance(250);
    await editOrbitalSlots();
    await advance(250);
    expect(vi.mocked(evaluateV3Plan).mock.calls[0][1]?.aborted).toBe(true);

    currentRequest.resolve(evaluated(23));
    await advance(0);
    const summary = screen.getByRole('complementary', { name: 'Summary' });
    expect(within(summary).getByText('23')).toBeInTheDocument();
    oldRequest.resolve(evaluated(999));
    await advance(0);
    expect(within(summary).getByText('23')).toBeInTheDocument();
    expect(within(summary).queryByText('999')).not.toBeInTheDocument();
  });

  it('announces blocked steps and keeps the last good evaluation greyed after a 400', async () => {
    seedPrimary();
    vi.mocked(evaluateV3Plan).mockResolvedValueOnce(evaluated(17, 2));
    render(PlanWorkspaceTestHost);
    await advance(250);
    expect(
      screen.getByText('2 blocked steps. 0 steps need information.'),
    ).toHaveAttribute('aria-live', 'polite');
    vi.mocked(evaluateV3Plan).mockRejectedValueOnce(
      new ApiError(400, '/api/v1/plan/evaluate', {
        error: 'plan_invalid',
        issues: [
          {
            code: 'INVALID_PRIMARY',
            site_id: null,
            message: 'The first build must be a port.',
          },
        ],
      }),
    );
    await editOrbitalSlots();
    await advance(250);
    const summary = screen.getByRole('complementary', { name: 'Summary' });
    expect(within(summary).getByRole('alert')).toHaveTextContent(
      'The first build must be a port.',
    );
    expect(within(summary).getByText('17').closest('.stale')).not.toBeNull();
    expect(
      within(summary).getByText(/Last good evaluation/),
    ).toBeInTheDocument();
  });

  it('keeps the last evaluation greyed when the final planned site is removed', async () => {
    seedPrimary();
    render(PlanWorkspaceTestHost);
    await advance(250);
    expect(evaluateV3Plan).toHaveBeenCalledOnce();
    vi.mocked(evaluateV3Plan).mockClear();
    await fireEvent.click(screen.getByLabelText('Edit Primary port'));
    await fireEvent.click(
      screen.getByRole('button', { name: 'Remove Primary port' }),
    );
    await advance(1000);
    expect(evaluateV3Plan).not.toHaveBeenCalled();
    const summary = screen.getByRole('complementary', { name: 'Summary' });
    expect(within(summary).getByText('17').closest('.stale')).not.toBeNull();
    expect(summary).toHaveAttribute('aria-busy', 'false');
  });

  it.each([false, true])(
    'moves the third site in storage, DOM and evaluation after opening Why: %s',
    async (openWhy) => {
      const sites: PlannerSite[] = [
        { ...importedSite('Primary port'), site_id: 'primary' },
        { ...importedSite('Second build'), site_id: 'second' },
        { ...importedSite('Third build'), site_id: 'third' },
      ];
      const record = plannerToRecord({
        ...emptyPlan('42'),
        sites,
      });
      vi.mocked(evaluateV3Plan).mockResolvedValue({
        ...evaluated(17, 1),
        steps: sites.map((site) => ({
          site_id: site.site_id,
          facility_id: site.facility_id,
          status: site.status,
          view: 'after_plan',
          result: site.site_id === 'second' ? 'BLOCKED' : 'OK',
          counted_port_number: null,
          cost_t2: 3,
          cost_t3: 0,
          reward_t2: 1,
          reward_t3: 0,
          t2_before: 0,
          t3_before: 0,
          t2_after: 0,
          t3_after: 0,
          reasons: site.site_id === 'second' ? ['INSUFFICIENT_T2'] : [],
          rule_ids: [],
          payers: site.site_id === 'second' ? [port.id] : [],
        })),
      });
      colonyProjects.set({
        version: 3,
        state: { projects: { [record.id]: record } },
      });
      render(PlanWorkspaceTestHost);
      await advance(250);
      if (openWhy) {
        const why = screen.getByRole('button', { name: 'Why? Second build' });
        why.focus();
        await fireEvent.click(why);
        expect(
          screen.getByRole('dialog', { name: 'Step 2: Second build' }),
        ).toHaveFocus();
        await fireEvent.keyDown(window, { key: 'Escape' });
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        expect(why).toHaveFocus();
      }
      const move = screen.getByRole('button', { name: 'Move up Third build' });
      expect(move).toBeEnabled();
      await fireEvent.click(move);
      expect(
        get(colonyProjects).value.state.projects[
          record.id
        ].build_plan_placements.map((site) => site.site_id),
      ).toEqual(['primary', 'third', 'second']);
      const order = screen.getByRole('region', { name: 'Build order' });
      expect(
        within(order)
          .getAllByRole('heading', { level: 3 })
          .map((heading) => heading.textContent),
      ).toEqual(['Primary port', 'Third build', 'Second build']);
      const stored = JSON.parse(
        localStorage.getItem(PERSISTENCE_KEYS.colonyProjects)!,
      );
      expect(
        stored.state.projects[record.id].build_plan_placements.map(
          (site: PlannerSite) => site.site_id,
        ),
      ).toEqual(['primary', 'third', 'second']);
      await advance(250);
      expect(
        vi
          .mocked(evaluateV3Plan)
          .mock.calls.at(-1)?.[0]
          .sites.map((site) => site.site_id),
      ).toEqual(['primary', 'third', 'second']);
    },
  );

  it('creates one browser project on the first edit and restores it after remount', async () => {
    const first = render(PlanWorkspaceTestHost);
    await advance(250);
    expect(localStorage.getItem(PERSISTENCE_KEYS.colonyProjects)).toBeNull();
    await editOrbitalSlots();
    const entries = Object.values(get(colonyProjects).value.state.projects);
    expect(entries).toHaveLength(1);
    expect(entries[0].id).toMatch(/^colony-42-/);
    expect(entries[0].selected_body_assignments.cpe_slots_v1).toEqual({
      '1': { orbital_slots: 1, surface_slots: null },
    });
    expect(entries[0].build_plan_placements).toEqual([]);
    expect(
      localStorage.getItem(PERSISTENCE_KEYS.colonyProjects),
    ).not.toBeNull();

    first.unmount();
    colonyProjects.hydrate();
    render(PlanWorkspaceTestHost);
    expect(
      screen.getByRole('button', {
        name: 'Orbital slots on Test System A: 0 used, 1 total',
      }),
    ).toBeInTheDocument();
    await editOrbitalSlots();
    expect(Object.keys(get(colonyProjects).value.state.projects)).toEqual([
      entries[0].id,
    ]);
  });

  it('confirms replacement before importing and preserves older placements and assignments', async () => {
    const record = plannerToRecord(emptyPlan('42'));
    record.build_plan_placements = [{ facility_template_id: 'old-v2' }];
    record.selected_body_assignments.old_assignment = { retained: true };
    colonyProjects.set({
      version: 3,
      state: { projects: { [record.id]: record } },
    });
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(PlanWorkspaceTestHost);
    const text = exportPlan({
      ...emptyPlan('42'),
      sites: [importedSite()],
      slots: { '1': { orbital_slots: 5, surface_slots: null } },
    });
    await upload(text);
    expect(confirm).toHaveBeenCalledOnce();
    expect(
      get(colonyProjects).value.state.projects[record.id].build_plan_placements,
    ).toHaveLength(1);

    confirm.mockReturnValue(true);
    await upload(text);
    const updated = get(colonyProjects).value.state.projects[record.id];
    expect(updated.build_plan_placements).toEqual([
      { facility_template_id: 'old-v2' },
      importedSite(),
    ]);
    expect(updated.selected_body_assignments).toEqual({
      old_assignment: { retained: true },
      cpe_slots_v1: { '1': { orbital_slots: 5, surface_slots: null } },
    });
  });

  it('requires separate cross-system and replacement confirmations', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false);
    render(PlanWorkspaceTestHost);
    const text = exportPlan({ ...emptyPlan('43'), sites: [importedSite()] });
    await upload(text);
    expect(confirm).toHaveBeenCalledOnce();
    expect(confirm).toHaveBeenLastCalledWith(
      expect.stringContaining('system 43'),
    );
    expect(Object.keys(get(colonyProjects).value.state.projects)).toEqual([]);
    confirm.mockReturnValueOnce(true).mockReturnValueOnce(true);
    await upload(text);
    expect(confirm).toHaveBeenCalledTimes(3);
    expect(
      Object.values(get(colonyProjects).value.state.projects)[0].system_id64,
    ).toBe('42');
  });
});
