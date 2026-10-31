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
  recordToPlanner,
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
const nonPort: PlanFacilityV1 = {
  ...port,
  id: 'installation',
  name: 'Installation',
  category: 'installation',
  is_port: false,
};
const catalogue = { rulebook_release: 'test', facilities: [port, nonPort] };
const system = v3System({ id64: '42', name: 'Test System' });
const BUILD_ORDER_KEY = 'ed-finder.plan.buildOrderOpen';

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

function blockedPrimary(): PlanEvaluationV1 {
  return {
    ...evaluated(17, 1),
    steps: [
      {
        site_id: 'imported-port',
        facility_id: port.id,
        status: 'planned',
        view: 'after_plan',
        result: 'BLOCKED',
        counted_port_number: 1,
        cost_t2: 3,
        cost_t3: 0,
        reward_t2: 0,
        reward_t3: 0,
        t2_before: 0,
        t3_before: 0,
        t2_after: 0,
        t3_after: 0,
        reasons: ['INSUFFICIENT_T2'],
        rule_ids: [],
        payers: [],
      },
    ],
  };
}

function mockWidth(wide: boolean) {
  const media = Object.assign(new EventTarget(), {
    matches: wide,
    media: '(min-width: 1400px)',
  });
  const matchMedia = vi.fn().mockReturnValue(media);
  vi.stubGlobal('matchMedia', matchMedia);
  return { media, matchMedia };
}

function buildOrderToggle() {
  return screen.getByRole('button', { name: /^Build order \(/ });
}

async function openBuildOrder() {
  await fireEvent.click(buildOrderToggle());
  await tick();
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

function seedPrimary(patch: Partial<PlannerSite> = {}) {
  const record = plannerToRecord({
    ...emptyPlan('42'),
    sites: [{ ...importedSite('Primary port'), ...patch }],
  });
  colonyProjects.set({
    version: 3,
    state: { projects: { [record.id]: record } },
  });
  return record;
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
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('build order panel', () => {
  it.each(['bodies', 'catalogue'] as const)(
    'disables the toggle while %s are loading and enables it when the pane is available',
    async (resource) => {
      const bodyRequest = deferred<PlanBodiesV1>();
      const catalogueRequest = deferred<typeof catalogue>();
      if (resource === 'bodies') {
        queryClient.removeQueries({
          queryKey: ['ed-finder', 'plan-bodies', '42'],
        });
        vi.mocked(listV3PlanBodies).mockReturnValue(bodyRequest.promise);
      } else {
        queryClient.removeQueries({
          queryKey: ['ed-finder', 'plan-catalogue'],
        });
        vi.mocked(getV3PlanCatalogue).mockReturnValue(catalogueRequest.promise);
      }
      render(PlanWorkspaceTestHost);
      await advance(0);
      expect(buildOrderToggle()).toBeDisabled();
      expect(buildOrderToggle()).toHaveAttribute('aria-expanded', 'false');
      expect(screen.getByRole('status')).toHaveTextContent(
        'Loading planner catalogue and system bodies',
      );
      expect(screen.queryByRole('region', { name: 'Build order' })).toBeNull();

      bodyRequest.resolve(bodyData);
      catalogueRequest.resolve(catalogue);
      await advance(0);
      expect(buildOrderToggle()).toBeEnabled();
      await openBuildOrder();
      expect(buildOrderToggle()).toHaveAttribute('aria-expanded', 'true');
      expect(
        screen.getByRole('heading', { name: 'Build order' }),
      ).toHaveFocus();
    },
  );

  it.each(['bodies', 'catalogue'] as const)(
    'keeps the toggle disabled when %s fail and no Build order pane is available',
    async (resource) => {
      if (resource === 'bodies') {
        queryClient.removeQueries({
          queryKey: ['ed-finder', 'plan-bodies', '42'],
        });
        vi.mocked(listV3PlanBodies).mockRejectedValue(new Error('Unavailable'));
      } else {
        queryClient.removeQueries({
          queryKey: ['ed-finder', 'plan-catalogue'],
        });
        vi.mocked(getV3PlanCatalogue).mockRejectedValue(
          new Error('Unavailable'),
        );
      }
      render(PlanWorkspaceTestHost);
      await advance(0);
      expect(screen.getByRole('alert')).toHaveTextContent(
        'The catalogue or system bodies could not be loaded.',
      );
      expect(buildOrderToggle()).toBeDisabled();
      expect(buildOrderToggle()).toHaveAttribute('aria-expanded', 'false');
      expect(screen.queryByRole('region', { name: 'Build order' })).toBeNull();
      expect(document.getElementById('plan-build-order')).toBeNull();
    },
  );

  it('shows the site and blocked counts and announces opening and closing with focus restored', async () => {
    seedPrimary();
    vi.mocked(evaluateV3Plan).mockResolvedValue(blockedPrimary());
    render(PlanWorkspaceTestHost);
    expect(buildOrderToggle()).toHaveAccessibleName('Build order (1)');
    await advance(250);
    const toggle = buildOrderToggle();
    expect(toggle).toHaveAccessibleName('Build order (1) · 1 blocked');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    const order = document.getElementById(
      toggle.getAttribute('aria-controls')!,
    )!;
    expect(order).toHaveAttribute('hidden');
    expect(screen.queryByRole('region', { name: 'Build order' })).toBeNull();

    toggle.focus();
    await openBuildOrder();
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(order).not.toHaveAttribute('hidden');
    const heading = within(order).getByRole('heading', { name: 'Build order' });
    expect(heading).toHaveAttribute('tabindex', '-1');
    expect(heading).toHaveFocus();
    expect(screen.getByText('Build order opened')).toHaveAttribute(
      'aria-live',
      'polite',
    );

    await fireEvent.click(within(order).getByRole('button', { name: 'Close' }));
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(order).toHaveAttribute('hidden');
    expect(toggle).toHaveFocus();
    expect(screen.getByText('Build order closed')).toHaveAttribute(
      'aria-live',
      'polite',
    );
  });

  it('closes from the header toggle and handles an empty order count', async () => {
    render(PlanWorkspaceTestHost);
    expect(buildOrderToggle()).toHaveAccessibleName('Build order (0)');
    await openBuildOrder();
    await fireEvent.click(buildOrderToggle());
    expect(buildOrderToggle()).toHaveAttribute('aria-expanded', 'false');
    expect(buildOrderToggle()).toHaveFocus();
    expect(screen.getByText('Build order closed')).toHaveAttribute(
      'aria-live',
      'polite',
    );
  });

  it('closes on Escape within the pane and returns focus to the toggle', async () => {
    seedPrimary();
    render(PlanWorkspaceTestHost);
    await openBuildOrder();
    const order = screen.getByRole('region', { name: 'Build order' });
    await fireEvent.keyDown(
      within(order).getByRole('heading', { name: 'Build order' }),
      { key: 'Escape' },
    );
    expect(order).toHaveAttribute('hidden');
    expect(buildOrderToggle()).toHaveAttribute('aria-expanded', 'false');
    expect(buildOrderToggle()).toHaveFocus();
    expect(screen.getByText('Build order closed')).toHaveAttribute(
      'aria-live',
      'polite',
    );
  });

  it('lets the Why drawer handle Escape without closing the Build order pane', async () => {
    seedPrimary();
    vi.mocked(evaluateV3Plan).mockResolvedValue(blockedPrimary());
    render(PlanWorkspaceTestHost);
    await advance(250);
    await openBuildOrder();
    const order = screen.getByRole('region', { name: 'Build order' });
    const why = within(order).getByRole('button', {
      name: 'Why? Primary port',
    });
    why.focus();
    await fireEvent.click(why);
    expect(screen.getByRole('dialog')).toHaveFocus();

    // Even a pane-originated event belongs to the drawer while it is open.
    await fireEvent.keyDown(why, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(order).not.toHaveAttribute('hidden');
    expect(buildOrderToggle()).toHaveAttribute('aria-expanded', 'true');
    expect(why).toHaveFocus();

    await fireEvent.keyDown(why, { key: 'Escape' });
    expect(order).toHaveAttribute('hidden');
    expect(buildOrderToggle()).toHaveFocus();
  });

  it('restores the viewer preference on remount and remembers closing', async () => {
    const first = render(PlanWorkspaceTestHost);
    await openBuildOrder();
    expect(localStorage.getItem(BUILD_ORDER_KEY)).toBe('true');
    first.unmount();

    const second = render(PlanWorkspaceTestHost);
    await tick();
    expect(buildOrderToggle()).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('region', { name: 'Build order' })).toBeVisible();
    await fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(localStorage.getItem(BUILD_ORDER_KEY)).toBe('false');
    second.unmount();

    render(PlanWorkspaceTestHost);
    await tick();
    expect(buildOrderToggle()).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('region', { name: 'Build order' })).toBeNull();
  });

  it('falls back to closed when localStorage throws and remains usable when saving throws', async () => {
    localStorage.setItem(BUILD_ORDER_KEY, 'true');
    const getItem = vi
      .spyOn(Storage.prototype, 'getItem')
      .mockImplementation(() => {
        throw new Error('Storage unavailable');
      });
    const setItem = vi
      .spyOn(Storage.prototype, 'setItem')
      .mockImplementation(() => {
        throw new Error('Storage unavailable');
      });
    render(PlanWorkspaceTestHost);
    await tick();
    expect(getItem).toHaveBeenCalledWith(BUILD_ORDER_KEY);
    expect(buildOrderToggle()).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByRole('region', { name: 'System' })).toBeVisible();
    await openBuildOrder();
    expect(setItem).toHaveBeenCalledWith(BUILD_ORDER_KEY, 'true');
    expect(buildOrderToggle()).toHaveAttribute('aria-expanded', 'true');
    await fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(setItem).toHaveBeenCalledWith(BUILD_ORDER_KEY, 'false');
    expect(buildOrderToggle()).toHaveAttribute('aria-expanded', 'false');
  });

  it.each(['narrow', 'missing'] as const)(
    'replaces System with Build order when matchMedia is %s and keeps Summary visible',
    async (mode) => {
      if (mode === 'narrow') mockWidth(false);
      else vi.stubGlobal('matchMedia', undefined);
      render(PlanWorkspaceTestHost);
      const systemPane = screen.getByRole('region', { name: 'System' });
      const order = document.getElementById(
        buildOrderToggle().getAttribute('aria-controls')!,
      )!;
      const summary = screen.getByRole('complementary', { name: 'Summary' });
      expect(systemPane).not.toHaveAttribute('hidden');
      expect(order).toHaveAttribute('hidden');
      expect(summary).toBeVisible();

      await openBuildOrder();
      expect(systemPane).toHaveAttribute('hidden');
      expect(screen.queryByRole('region', { name: 'System' })).toBeNull();
      expect(order).not.toHaveAttribute('hidden');
      expect(summary).toBeVisible();

      await fireEvent.click(
        within(order).getByRole('button', { name: 'Close' }),
      );
      expect(systemPane).not.toHaveAttribute('hidden');
      expect(order).toHaveAttribute('hidden');
      expect(summary).toBeVisible();
    },
  );

  it('keeps System and Build order visible together at the wide breakpoint', async () => {
    const { matchMedia } = mockWidth(true);
    render(PlanWorkspaceTestHost);
    await openBuildOrder();
    expect(matchMedia).toHaveBeenCalledWith('(min-width: 1400px)');
    for (const name of ['System', 'Build order']) {
      const pane = screen.getByRole('region', { name });
      expect(pane).not.toHaveAttribute('hidden');
      expect(pane).toBeVisible();
    }
    expect(
      screen.getByRole('complementary', { name: 'Summary' }),
    ).toBeVisible();
  });

  it('moves focus out of System when resizing an open panel below the wide breakpoint', async () => {
    const { media } = mockWidth(true);
    render(PlanWorkspaceTestHost);
    await openBuildOrder();
    const systemPane = screen.getByRole('region', { name: 'System' });
    within(systemPane).getByRole('button', { name: 'Names and types' }).focus();
    const order = screen.getByRole('region', { name: 'Build order' });

    media.matches = false;
    media.dispatchEvent(Object.assign(new Event('change'), { matches: false }));
    await advance(0);
    expect(systemPane).toHaveAttribute('hidden');
    expect(
      within(order).getByRole('heading', { name: 'Build order' }),
    ).toHaveFocus();
    expect(order).not.toHaveAttribute('hidden');

    media.matches = true;
    media.dispatchEvent(Object.assign(new Event('change'), { matches: true }));
    await advance(0);
    expect(systemPane).not.toHaveAttribute('hidden');
    expect(order).not.toHaveAttribute('hidden');
    expect(
      within(order).getByRole('heading', { name: 'Build order' }),
    ).toHaveFocus();
  });

  it('removes the System slot editor and its keyboard trap when resizing narrow, retaining saved slot counts', async () => {
    const { media } = mockWidth(true);
    render(PlanWorkspaceTestHost);
    await openBuildOrder();
    await fireEvent.click(
      screen.getByRole('button', {
        name: 'Orbital slots on Test System A: 0 used, unknown total',
      }),
    );
    const editor = screen.getByRole('dialog', {
      name: 'Orbital slots on Test System A',
    });
    await fireEvent.click(
      within(editor).getByRole('button', { name: 'Increase orbital slots' }),
    );
    editor.focus();

    media.matches = false;
    media.dispatchEvent(Object.assign(new Event('change'), { matches: false }));
    await advance(0);
    expect(editor).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog', { hidden: true })).toBeNull();
    const heading = screen.getByRole('heading', { name: 'Build order' });
    expect(heading).toHaveFocus();
    const tab = new KeyboardEvent('keydown', {
      key: 'Tab',
      bubbles: true,
      cancelable: true,
    });
    heading.dispatchEvent(tab);
    expect(tab.defaultPrevented).toBe(false);
    expect(heading).toHaveFocus();

    media.matches = true;
    media.dispatchEvent(Object.assign(new Event('change'), { matches: true }));
    await advance(0);
    const slots = screen.getByRole('button', {
      name: 'Orbital slots on Test System A: 0 used, 1 total',
    });
    expect(slots).toHaveAttribute('aria-expanded', 'false');
    expect(slots).toHaveTextContent('0/1');
    expect(screen.queryByRole('dialog', { hidden: true })).toBeNull();
  });

  it.each(['Close', 'Escape'] as const)(
    'returns focus to Build order when %s closes Why after resizing hides the System chip',
    async (action) => {
      const { media } = mockWidth(true);
      seedPrimary();
      vi.mocked(evaluateV3Plan).mockResolvedValue(blockedPrimary());
      render(PlanWorkspaceTestHost);
      await advance(250);
      await openBuildOrder();
      const systemPane = screen.getByRole('region', { name: 'System' });
      const chip = within(systemPane).getByRole('button', { name: /^Step 1,/ });
      chip.focus();
      await fireEvent.click(chip);
      const drawer = screen.getByRole('dialog', {
        name: 'Step 1: Primary port',
      });
      expect(drawer).toHaveFocus();

      media.matches = false;
      media.dispatchEvent(
        Object.assign(new Event('change'), { matches: false }),
      );
      await advance(0);
      expect(systemPane).toHaveAttribute('hidden');
      expect(drawer).toHaveFocus();
      if (action === 'Close') {
        await fireEvent.click(
          within(drawer).getByRole('button', { name: 'Close why panel' }),
        );
      } else {
        await fireEvent.keyDown(drawer, { key: 'Escape' });
      }
      await advance(0);

      expect(screen.queryByRole('dialog')).toBeNull();
      expect(buildOrderToggle()).toHaveAttribute('aria-expanded', 'true');
      const order = screen.getByRole('region', { name: 'Build order' });
      expect(
        within(order).getByRole('heading', { name: 'Build order' }),
      ).toHaveFocus();
      expect(chip).not.toHaveFocus();
    },
  );

  it('opens a closed panel from a Summary step link and focuses the selected step', async () => {
    seedPrimary();
    vi.mocked(evaluateV3Plan).mockResolvedValue(blockedPrimary());
    render(PlanWorkspaceTestHost);
    await advance(250);
    expect(buildOrderToggle()).toHaveAttribute('aria-expanded', 'false');
    const step = document.getElementById('plan-step-imported-port')!;
    const scrollIntoView = vi.fn();
    Object.defineProperty(step, 'scrollIntoView', { value: scrollIntoView });
    await fireEvent.click(
      screen.getByRole('button', { name: 'First blocked step: Primary port' }),
    );
    const order = screen.getByRole('region', { name: 'Build order' });
    expect(order).toContainElement(step);
    expect(buildOrderToggle()).toHaveAttribute('aria-expanded', 'true');
    expect(step).toHaveFocus();
    expect(step).toHaveClass('selected');
    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'nearest' });
    expect(screen.getByText('Build order opened')).toHaveAttribute(
      'aria-live',
      'polite',
    );
  });

  it('reveals and focuses the System body from Summary while Build order replaces it', async () => {
    mockWidth(false);
    seedPrimary();
    render(PlanWorkspaceTestHost);
    await openBuildOrder();
    await fireEvent.click(
      screen.getByRole('button', {
        name: '1 body has builds with unknown slot counts',
      }),
    );
    const systemPane = screen.getByRole('region', { name: 'System' });
    expect(buildOrderToggle()).toHaveAttribute('aria-expanded', 'false');
    const body = systemPane.querySelector('[data-plan-body="1"]')!;
    expect(body).toHaveClass('selected');
    expect(body.querySelector('.body-name')).toHaveFocus();
  });

  it('keeps the selected body and step highlighted when the wide panel opens', async () => {
    mockWidth(true);
    seedPrimary();
    vi.mocked(evaluateV3Plan).mockResolvedValue(blockedPrimary());
    render(PlanWorkspaceTestHost);
    await advance(250);
    const body = screen
      .getByRole('region', { name: 'System' })
      .querySelector('[data-plan-body="1"]')!;
    await fireEvent.click(body.querySelector('.body-name')!);
    const chip = within(body as HTMLElement).getByRole('button', {
      name: /^Step 1,/,
    });
    expect(chip).toHaveAccessibleName(/Primary Port/);
    expect(within(chip).getByText('★')).toHaveAttribute('aria-hidden', 'true');
    expect(chip.querySelector('.tile-number')).toHaveTextContent(/^★\s*1$/);
    chip.focus();
    await fireEvent.click(chip);
    expect(
      screen.getByRole('dialog', { name: 'Step 1: Primary port' }),
    ).toHaveFocus();
    await fireEvent.keyDown(window, { key: 'Escape' });
    expect(chip).toHaveFocus();
    await openBuildOrder();
    expect(body).toHaveClass('selected');
    const step = screen
      .getByRole('region', { name: 'Build order' })
      .querySelector('[data-plan-site="imported-port"]')!;
    expect(step).toHaveClass('selected');
  });
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

  it('moves a planned installation between orbital and surface slots and updates capacity highlights', async () => {
    mockWidth(true);
    const landableBodies: PlanBodiesV1 = {
      ...bodyData,
      bodies: [
        ...bodyData.bodies,
        {
          ...bodyData.bodies[0],
          body_id: '2',
          name: 'Test System A 1',
          direct_parent_body_id: '1',
          body_type: 'planet',
          is_main_star: false,
          is_landable: true,
        },
      ],
    };
    const surfaceInstallation: PlanFacilityV1 = {
      ...nonPort,
      id: 'surface-installation',
      name: 'Surface Installation',
      allowed_location: 'surface',
    };
    const switchCatalogue = {
      ...catalogue,
      facilities: [...catalogue.facilities, surfaceInstallation],
    };
    vi.mocked(listV3PlanBodies).mockResolvedValue(landableBodies);
    vi.mocked(getV3PlanCatalogue).mockResolvedValue(switchCatalogue);
    queryClient.setQueryData(
      ['ed-finder', 'plan-bodies', '42'],
      landableBodies,
    );
    queryClient.setQueryData(['ed-finder', 'plan-catalogue'], switchCatalogue);
    const record = plannerToRecord({
      ...emptyPlan('42'),
      sites: [
        importedSite('Primary port'),
        {
          ...importedSite('Second build'),
          site_id: 'second',
          facility_id: nonPort.id,
          body_ref: '2',
        },
      ],
      slots: { '2': { orbital_slots: 0, surface_slots: 0 } },
    });
    colonyProjects.set({
      version: 3,
      state: { projects: { [record.id]: record } },
    });
    render(PlanWorkspaceTestHost);
    const systemPane = within(screen.getByRole('region', { name: 'System' }));
    const orbital = systemPane.getByRole('button', {
      name: 'Orbital slots on Test System A 1: 1 used, 0 total, over capacity',
    });
    const surface = systemPane.getByRole('button', {
      name: 'Surface slots on Test System A 1: 0 used, 0 total',
    });
    expect(orbital).toHaveTextContent('1/0');
    expect(orbital).toHaveClass('over-capacity');
    expect(surface).toHaveTextContent('0/0');
    expect(surface).not.toHaveClass('over-capacity');

    await openBuildOrder();
    await fireEvent.click(screen.getByLabelText('Edit Second build'));
    const facility = screen.getByRole('combobox', {
      name: 'Facility for step 2',
    });
    await fireEvent.change(facility, {
      target: { value: surfaceInstallation.id },
    });
    expect(facility).toHaveValue(surfaceInstallation.id);
    expect(
      recordToPlanner(get(colonyProjects).value.state.projects[record.id])
        .sites[1],
    ).toMatchObject({
      facility_id: surfaceInstallation.id,
      slot_kind: 'surface',
      body_ref: '2',
    });
    expect(orbital).toHaveAccessibleName(
      'Orbital slots on Test System A 1: 0 used, 0 total',
    );
    expect(orbital).toHaveTextContent('0/0');
    expect(orbital).not.toHaveClass('over-capacity');
    expect(surface).toHaveAccessibleName(
      'Surface slots on Test System A 1: 1 used, 0 total, over capacity',
    );
    expect(surface).toHaveTextContent('1/0');
    expect(surface).toHaveClass('over-capacity');

    await fireEvent.change(facility, { target: { value: nonPort.id } });
    expect(facility).toHaveValue(nonPort.id);
    expect(orbital).toHaveAccessibleName(
      'Orbital slots on Test System A 1: 1 used, 0 total, over capacity',
    );
    expect(orbital).toHaveTextContent('1/0');
    expect(orbital).toHaveClass('over-capacity');
    expect(surface).toHaveAccessibleName(
      'Surface slots on Test System A 1: 0 used, 0 total',
    );
    expect(surface).toHaveTextContent('0/0');
    expect(surface).not.toHaveClass('over-capacity');
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

  it('shows the blocked count only for a current evaluation of a non-empty plan', async () => {
    seedPrimary();
    vi.mocked(evaluateV3Plan).mockResolvedValue(blockedPrimary());
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(PlanWorkspaceTestHost);
    await advance(250);
    expect(buildOrderToggle()).toHaveAccessibleName(
      'Build order (1) · 1 blocked',
    );
    await fireEvent.click(screen.getByRole('button', { name: 'Abandon plan' }));
    await advance(1000);
    // The greyed last evaluation stays in the Summary, but the header must not
    // present its blocked count as current, least of all for an empty plan.
    expect(buildOrderToggle()).toHaveAccessibleName('Build order (0)');
  });

  it('keeps the last evaluation greyed when the plan is abandoned', async () => {
    seedPrimary();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(PlanWorkspaceTestHost);
    await advance(250);
    expect(evaluateV3Plan).toHaveBeenCalledOnce();
    vi.mocked(evaluateV3Plan).mockClear();
    await fireEvent.click(screen.getByRole('button', { name: 'Abandon plan' }));
    await advance(1000);
    expect(evaluateV3Plan).not.toHaveBeenCalled();
    const summary = screen.getByRole('complementary', { name: 'Summary' });
    expect(within(summary).getByText('17').closest('.stale')).not.toBeNull();
    expect(summary).toHaveAttribute('aria-busy', 'false');
  });

  it.each([
    { status: 'planned', body_ref: '1' },
    { status: 'planned', body_ref: null },
    { status: 'building', body_ref: '1' },
    { status: 'building', body_ref: null },
    { status: 'complete', body_ref: null },
  ] as const)(
    'abandons a $status primary at $body_ref with confirmation, keeps slots and announces',
    async (primary) => {
      const slots = { '1': { orbital_slots: 5, surface_slots: null } };
      const record = plannerToRecord({
        ...emptyPlan('42'),
        slots,
        sites: [
          { ...importedSite('Primary port'), ...primary },
          {
            ...importedSite('Completed installation'),
            site_id: 'installation',
            facility_id: nonPort.id,
            status: 'complete',
          },
        ],
      });
      colonyProjects.set({
        version: 3,
        state: { projects: { [record.id]: record } },
      });
      const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
      render(PlanWorkspaceTestHost);
      await openBuildOrder();
      const abandon = screen.getByRole('button', { name: 'Abandon plan' });
      expect(abandon).toBeEnabled();
      await fireEvent.click(abandon);
      await advance(1000);
      expect(confirm).toHaveBeenCalledExactlyOnceWith(
        'Abandon this plan? All 2 sites for Test System will be removed, as if the claim were cancelled. Slot counts are kept.',
      );
      const updated = get(colonyProjects).value.state.projects[record.id];
      expect(recordToPlanner(updated)).toEqual({
        system_id64: '42',
        sites: [],
        slots,
      });
      const stored = JSON.parse(
        localStorage.getItem(PERSISTENCE_KEYS.colonyProjects)!,
      );
      expect(stored.state.projects[record.id]).toEqual(updated);
      expect(
        within(
          screen.getByRole('region', { name: 'Build order' }),
        ).queryAllByRole('heading', { level: 3 }),
      ).toHaveLength(0);
      expect(screen.getByText('Plan abandoned.')).toHaveAttribute(
        'aria-live',
        'polite',
      );
      expect(abandon).toBeDisabled();
      expect(evaluateV3Plan).not.toHaveBeenCalled();
    },
  );

  it('keeps the plan and storage unchanged when abandonment is cancelled', async () => {
    const record = seedPrimary();
    const stored = localStorage.getItem(PERSISTENCE_KEYS.colonyProjects);
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(PlanWorkspaceTestHost);
    await fireEvent.click(screen.getByRole('button', { name: 'Abandon plan' }));
    expect(confirm).toHaveBeenCalledExactlyOnceWith(
      'Abandon this plan? All 1 sites for Test System will be removed, as if the claim were cancelled. Slot counts are kept.',
    );
    expect(get(colonyProjects).value.state.projects[record.id]).toEqual(record);
    expect(localStorage.getItem(PERSISTENCE_KEYS.colonyProjects)).toBe(stored);
    expect(screen.queryByText('Plan abandoned.')).not.toBeInTheDocument();
  });

  it('disables abandonment for a complete and placed primary with its protection title', async () => {
    const record = seedPrimary({ status: 'complete' });
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(PlanWorkspaceTestHost);
    const abandon = screen.getByRole('button', { name: 'Abandon plan' });
    expect(abandon).toBeDisabled();
    expect(abandon).toHaveAttribute(
      'title',
      'A completed Primary Port can never be removed (RB-0008).',
    );
    await fireEvent.click(abandon);
    expect(confirm).not.toHaveBeenCalled();
    expect(get(colonyProjects).value.state.projects[record.id]).toEqual(record);
  });

  it('disables abandonment when the plan has no sites', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(PlanWorkspaceTestHost);
    const abandon = screen.getByRole('button', { name: 'Abandon plan' });
    expect(abandon).toBeDisabled();
    await fireEvent.click(abandon);
    expect(confirm).not.toHaveBeenCalled();
    expect(localStorage.getItem(PERSISTENCE_KEYS.colonyProjects)).toBeNull();
  });

  it('keeps the abandonment announcement when an earlier evaluation arrives', async () => {
    seedPrimary();
    const pendingEvaluation = deferred<PlanEvaluationV1>();
    vi.mocked(evaluateV3Plan).mockReturnValue(pendingEvaluation.promise);
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(PlanWorkspaceTestHost);
    await advance(250);
    await fireEvent.click(screen.getByRole('button', { name: 'Abandon plan' }));
    expect(vi.mocked(evaluateV3Plan).mock.calls[0][1]?.aborted).toBe(true);
    pendingEvaluation.resolve(evaluated(17, 2));
    await advance(0);
    expect(screen.getByText('Plan abandoned.')).toHaveAttribute(
      'aria-live',
      'polite',
    );
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
      await openBuildOrder();
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
    expect(confirm).toHaveBeenLastCalledWith(
      expect.stringContaining(
        'A completed Primary Port without a location here will stay editable until you give it one.',
      ),
    );
    expect(Object.keys(get(colonyProjects).value.state.projects)).toEqual([]);
    confirm.mockReturnValueOnce(true).mockReturnValueOnce(true);
    await upload(text);
    expect(confirm).toHaveBeenCalledTimes(3);
    expect(
      Object.values(get(colonyProjects).value.state.projects)[0].system_id64,
    ).toBe('42');
  });

  it.each(['42', '43'])(
    'refuses an imported non-port primary from system %s before any confirmation',
    async (systemId) => {
      const record = seedPrimary();
      const stored = localStorage.getItem(PERSISTENCE_KEYS.colonyProjects);
      const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
      render(PlanWorkspaceTestHost);
      await upload(
        exportPlan({
          ...emptyPlan(systemId),
          sites: [
            {
              ...importedSite('Completed installation'),
              facility_id: nonPort.id,
              status: 'complete',
            },
          ],
        }),
      );
      expect(screen.getByRole('alert')).toHaveTextContent(
        "This plan's first site is not a port, so it cannot be the Primary Port.",
      );
      expect(confirm).not.toHaveBeenCalled();
      expect(get(colonyProjects).value.state.projects[record.id]).toEqual(
        record,
      );
      expect(localStorage.getItem(PERSISTENCE_KEYS.colonyProjects)).toBe(
        stored,
      );
    },
  );

  it('lets an imported completed primary gain a missing location, then protects it', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(PlanWorkspaceTestHost);
    await upload(
      exportPlan({
        ...emptyPlan('43'),
        sites: [{ ...importedSite(), body_ref: '99', status: 'complete' }],
      }),
    );
    await openBuildOrder();
    await fireEvent.click(screen.getByLabelText('Edit Imported port'));
    const body = screen.getByLabelText('Body for step 1');
    const status = screen.getByLabelText('Status for step 1');
    expect(body).toBeEnabled();
    expect(body).toHaveValue('');
    expect(status).toBeEnabled();
    expect(status).toHaveValue('complete');
    await fireEvent.change(body, { target: { value: '1' } });
    expect(
      Object.values(get(colonyProjects).value.state.projects)[0]
        .build_plan_placements[0],
    ).toMatchObject({ body_ref: '1', status: 'complete' });
    expect(body).toBeDisabled();
    expect(status).toBeDisabled();
    expect(
      screen.queryByRole('button', { name: 'Remove Imported port' }),
    ).not.toBeInTheDocument();
  });
});
