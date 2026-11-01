import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { PlanEvaluationV1, PlanFacilityV1, PlanRequestV1 } from '$lib/api';
import FacilityPicker from './FacilityPicker.svelte';
import { compactPlanFixture } from './__fixtures__/compact-plan';
import { resolvePlanLocations } from './locations';
import { evaluatePlanPreview } from './preview';

vi.mock('./preview', () => ({ evaluatePlanPreview: vi.fn() }));

function facility(
  id: string,
  name: string,
  fields: Partial<PlanFacilityV1> = {},
): PlanFacilityV1 {
  return {
    id,
    name,
    category: 'installation',
    tier: 1,
    allowed_location: 'orbital',
    economy: null,
    is_port: false,
    escalating_port_tier: null,
    // Deliberately unlike the server response: these must never become previews.
    yellow_cp_cost: 99,
    green_cp_cost: 99,
    yellow_cp_generated: 99,
    green_cp_generated: 99,
    prerequisites: [],
    rule_ids: [],
    ...fields,
  };
}

const port = { category: 'port', is_port: true };
// Intentionally interleaved and out of display order, like the catalogue.
const facilities = [
  facility('orbis_t3', 'Orbis', { ...port, tier: 3 }),
  facility('surface-hub', 'Outpost Hub', {
    category: 'hub',
    allowed_location: 'surface',
    tier: 2,
  }),
  facility('surface-outpost', 'Outpost Civilian', {
    ...port,
    allowed_location: 'surface',
  }),
  facility('ocellus_station', 'Ocellus', { ...port, tier: 3 }),
  facility('installation-t1', 'Mining Outpost', { category: 'extraction' }),
  facility('surface_settlement_agriculture', 'Agricultural Settlement', {
    category: 'agriculture',
    allowed_location: 'surface',
  }),
  facility('asteroid_base', 'Asteroid Base', {
    ...port,
    tier: 2,
    allowed_location: 'ringed_orbital',
  }),
  facility('outpost-b', 'Scientific Outpost', port),
  facility('dodecahedron_t3', 'Dodecahedron', { ...port, tier: 3 }),
  facility('planetary_port', 'Port', {
    ...port,
    tier: 3,
    allowed_location: 'surface',
  }),
  facility('installation-t2', 'Research Installation', {
    tier: 2,
    prerequisites: [['installation-t1']],
  }),
  facility('coriolis_station', 'Coriolis', { ...port, tier: 2 }),
  facility('outpost-a', 'Commercial Outpost', port),
];

function pickerProps(withPrimary = false) {
  const fixture = compactPlanFixture(2, withPrimary ? 1 : 0);
  fixture.bodies.bodies[1].has_rings = false;
  return {
    bodies: fixture.bodies,
    model: fixture.model,
    facilities,
    location: resolvePlanLocations(fixture.bodies).find(
      (location) => location.body_ref === '2',
    )!,
    onadd: vi.fn(),
    onclose: vi.fn(),
  };
}

function evaluation(request: PlanRequestV1): PlanEvaluationV1 {
  return {
    ...compactPlanFixture(2, 0).evaluation,
    steps: request.sites.map((site) => ({
      site_id: site.site_id,
      facility_id: site.facility_id,
      status: site.status,
      view: 'after_plan',
      result: 'OK',
      counted_port_number: null,
      cost_t2: 0,
      cost_t3: 7,
      reward_t2: 1,
      reward_t3: 0,
      t2_before: 0,
      t3_before: 0,
      t2_after: 1,
      t3_after: 0,
      reasons: [],
      rule_ids: [],
      payers: [],
    })),
  };
}

function facilityButtons() {
  return Array.from(
    document.querySelectorAll<HTMLButtonElement>('button[data-facility-id]'),
  );
}

async function advance(ms = 250) {
  await tick();
  await vi.advanceTimersByTimeAsync(ms);
  await tick();
}

function mockIntersections() {
  const observers: {
    targets: Set<Element>;
    root: Element | Document | null;
    notify: (targets: Element[], visible?: boolean) => void;
  }[] = [];
  vi.stubGlobal(
    'IntersectionObserver',
    class {
      targets = new Set<Element>();
      root: Element | Document | null;
      constructor(
        private callback: IntersectionObserverCallback,
        options: IntersectionObserverInit = {},
      ) {
        this.root = options.root ?? null;
        observers.push(this);
      }
      observe(target: Element) {
        this.targets.add(target);
      }
      unobserve(target: Element) {
        this.targets.delete(target);
      }
      disconnect() {
        this.targets.clear();
      }
      notify(targets: Element[], visible = true) {
        this.callback(
          targets.map(
            (target) =>
              ({
                target,
                isIntersecting: visible,
                intersectionRatio: visible ? 1 : 0,
              }) as IntersectionObserverEntry,
          ),
          this as unknown as IntersectionObserver,
        );
      }
    },
  );
  return () => observers.findLast((observer) => observer.targets.size > 0)!;
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal('IntersectionObserver', undefined);
  vi.mocked(evaluatePlanPreview).mockReset();
  vi.mocked(evaluatePlanPreview).mockImplementation(async (request) =>
    evaluation(request),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('Facility picker tabs and list', () => {
  it('defaults an empty landable plan to Orbital and lists all four starports in Raven order without pages', () => {
    render(FacilityPicker, pickerProps());
    expect(screen.getByRole('tab', { name: 'Orbital' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(
      facilityButtons()
        .slice(0, 4)
        .map((button) => button.dataset.facilityId),
    ).toEqual([
      'coriolis_station',
      'dodecahedron_t3',
      'ocellus_station',
      'orbis_t3',
    ]);
    expect(facilityButtons()).toHaveLength(8);
    expect(
      screen.queryByRole('button', {
        name: /Previous facilities|More facilities|Next facilities/i,
      }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText('Asteroid Base')).not.toBeInTheDocument();
    expect(screen.queryByText('Requires: None')).not.toBeInTheDocument();
    expect(screen.getByText('Requires: Mining Outpost')).toBeInTheDocument();
    const installation = document.querySelector<HTMLButtonElement>(
      '[data-facility-id="installation-t2"]',
    )!;
    expect(installation).toBeDisabled();
    expect(installation).toHaveAccessibleName('Research Installation');
    expect(installation).toHaveAccessibleDescription(
      'T2 Choose a Primary Port first Requires: Mining Outpost',
    );
    expect(installation.closest('li')).toHaveTextContent(
      'Choose a Primary Port first',
    );
  });

  it('inserts Asteroid Base between Coriolis and Dodecahedron only at ringed locations', async () => {
    const props = pickerProps();
    const { rerender } = render(FacilityPicker, props);
    await rerender({
      ...props,
      location: { ...props.location, has_rings: true },
    });
    expect(
      facilityButtons()
        .slice(0, 5)
        .map((button) => button.dataset.facilityId),
    ).toEqual([
      'coriolis_station',
      'asteroid_base',
      'dodecahedron_t3',
      'ocellus_station',
      'orbis_t3',
    ]);
    await rerender(props);
    expect(screen.queryByText('Asteroid Base')).not.toBeInTheDocument();
  });

  it('disables Surface with an explanation on non-landable locations and skips it with arrow keys', async () => {
    const props = pickerProps(true);
    render(FacilityPicker, {
      ...props,
      location: { ...props.location, is_landable: false },
    });
    const orbital = screen.getByRole('tab', { name: 'Orbital' });
    const surface = screen.getByRole('tab', { name: 'Surface' });
    const both = screen.getByRole('tab', { name: 'Both' });
    expect(orbital).toHaveAttribute('aria-selected', 'true');
    expect(surface).toBeDisabled();
    expect(surface.getAttribute('title')).toMatch(/landable/i);
    orbital.focus();
    await fireEvent.keyDown(orbital, { key: 'ArrowRight' });
    expect(both).toHaveFocus();
    expect(both).toHaveAttribute('aria-selected', 'true');
    await fireEvent.keyDown(both, { key: 'ArrowLeft' });
    expect(orbital).toHaveFocus();
    expect(orbital).toHaveAttribute('tabindex', '0');
    expect(both).toHaveAttribute('tabindex', '-1');
  });

  it('defaults an established landable plan to Both, ordered by section, tier and name', () => {
    render(FacilityPicker, pickerProps(true));
    expect(screen.getByRole('tab', { name: 'Both' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(
      screen
        .getAllByRole('heading', { level: 4 })
        .map((heading) => heading.textContent),
    ).toEqual([
      'Orbital starports',
      'Orbital outposts',
      'Orbital installations',
      'Surface ports',
      'Surface settlements',
      'Surface hubs',
    ]);
    expect(
      facilityButtons().map((button) => button.dataset.facilityId),
    ).toEqual([
      'coriolis_station',
      'dodecahedron_t3',
      'ocellus_station',
      'orbis_t3',
      'outpost-a',
      'outpost-b',
      'installation-t2',
      'installation-t1',
      'planetary_port',
      'surface-outpost',
      'surface_settlement_agriculture',
      'surface-hub',
    ]);
  });

  it('filters search within the selected tab and hides empty sections', async () => {
    render(FacilityPicker, pickerProps(true));
    await fireEvent.click(screen.getByRole('tab', { name: 'Orbital' }));
    await fireEvent.input(
      screen.getByRole('searchbox', { name: 'Find a facility' }),
      { target: { value: 'Outpost' } },
    );
    expect(
      facilityButtons().map((button) => button.dataset.facilityId),
    ).toEqual(['outpost-a', 'outpost-b', 'installation-t1']);
    expect(
      screen.queryByRole('heading', { name: 'Orbital starports' }),
    ).not.toBeInTheDocument();
    await fireEvent.click(screen.getByRole('tab', { name: 'Surface' }));
    expect(
      facilityButtons().map((button) => button.dataset.facilityId),
    ).toEqual(['surface-outpost', 'surface-hub']);
    await fireEvent.input(screen.getByRole('searchbox'), {
      target: { value: 'Coriolis' },
    });
    expect(facilityButtons()).toHaveLength(0);
    expect(screen.getByText('No matching facilities.')).toBeInTheDocument();
    await fireEvent.click(screen.getByRole('tab', { name: 'Orbital' }));
    expect(
      facilityButtons().map((button) => button.dataset.facilityId),
    ).toEqual(['coriolis_station']);
  });

  it('keeps the 300-site limit alert and disables every facility without preview requests', async () => {
    const props = pickerProps(true);
    props.model.sites = Array.from({ length: 300 }, (_, index) => ({
      ...props.model.sites[0],
      site_id: `site-${index}`,
    }));
    render(FacilityPicker, props);
    expect(screen.getByRole('alert')).toHaveTextContent(
      'A plan can contain at most 300 sites.',
    );
    for (const button of facilityButtons()) expect(button).toBeDisabled();
    await advance();
    expect(evaluatePlanPreview).not.toHaveBeenCalled();
  });
});

describe('Facility picker server previews', () => {
  it('falls back to only the first six rows without IntersectionObserver and displays server costs', async () => {
    render(FacilityPicker, pickerProps(true));
    expect(screen.getAllByText('Evaluating CP…')).toHaveLength(12);
    await advance(249);
    expect(evaluatePlanPreview).not.toHaveBeenCalled();
    await advance(1);
    expect(
      vi
        .mocked(evaluatePlanPreview)
        .mock.calls.map(([request]) => request.sites.at(-1)?.facility_id),
    ).toEqual(
      facilityButtons()
        .slice(0, 6)
        .map((button) => button.dataset.facilityId),
    );
    expect(screen.getAllByText('-7 T3 · +1 T2')).toHaveLength(6);
    expect(facilityButtons()[0]).toHaveAccessibleName('Coriolis');
    expect(facilityButtons()[0]).toHaveAccessibleDescription(
      'T2 -7 T3 · +1 T2',
    );
    expect(screen.queryByText(/99 T[23]/)).not.toBeInTheDocument();
  });

  it('requests only intersecting rows and keeps at most six requests in flight while draining the visible queue', async () => {
    const currentObserver = mockIntersections();
    let active = 0;
    let peak = 0;
    const finish: (() => void)[] = [];
    vi.mocked(evaluatePlanPreview).mockImplementation(
      (request, signal) =>
        new Promise((resolve, reject) => {
          active += 1;
          peak = Math.max(peak, active);
          let settled = false;
          function settle(aborted: boolean) {
            if (settled) return;
            settled = true;
            active -= 1;
            if (aborted) reject(new DOMException('Aborted', 'AbortError'));
            else resolve(evaluation(request));
          }
          signal.addEventListener('abort', () => settle(true), { once: true });
          finish.push(() => settle(false));
        }),
    );
    render(FacilityPicker, pickerProps(true));
    await advance();
    expect(evaluatePlanPreview).not.toHaveBeenCalled();
    const observer = currentObserver();
    expect(observer.root).toBe(screen.getByRole('tabpanel'));
    const targets = [...observer.targets];
    expect(targets).toHaveLength(12);
    observer.notify(targets.slice(0, 2));
    await advance();
    expect(evaluatePlanPreview).toHaveBeenCalledTimes(2);
    observer.notify(targets.slice(2));
    await advance();
    expect(active).toBe(6);
    expect(evaluatePlanPreview).toHaveBeenCalledTimes(6);
    finish[0]();
    await advance(0);
    expect(evaluatePlanPreview).toHaveBeenCalledTimes(7);
    expect(active).toBe(6);
    // Once rows leave the list's viewport, queued requests must not start.
    observer.notify(targets, false);
    for (const complete of finish) complete();
    await advance();
    expect(evaluatePlanPreview).toHaveBeenCalledTimes(7);
    expect(peak).toBe(6);
  });

  it.each(['search', 'tab', 'plan', 'location'] as const)(
    'cancels previews when %s changes and ignores a late result',
    async (change) => {
      const props = pickerProps(true);
      const pending: {
        request: PlanRequestV1;
        signal: AbortSignal;
        resolve: (value: PlanEvaluationV1) => void;
      }[] = [];
      vi.mocked(evaluatePlanPreview).mockImplementation(
        (request, signal) =>
          new Promise((resolve) => pending.push({ request, signal, resolve })),
      );
      const { rerender } = render(FacilityPicker, props);
      await advance();
      expect(pending).toHaveLength(6);
      const previous = [...pending];
      if (change === 'search')
        await fireEvent.input(screen.getByRole('searchbox'), {
          target: { value: 'Outpost' },
        });
      else if (change === 'tab')
        await fireEvent.click(screen.getByRole('tab', { name: 'Surface' }));
      else if (change === 'plan')
        await rerender({
          ...props,
          model: {
            ...props.model,
            slots: { '2': { orbital_slots: 5, surface_slots: 5 } },
          },
        });
      else
        await rerender({
          ...props,
          location: { ...props.location, body_ref: '1' },
        });
      for (const request of previous) expect(request.signal.aborted).toBe(true);
      await advance();
      expect(pending).toHaveLength(6);
      previous[0].resolve(evaluation(previous[0].request));
      await advance(0);
      expect(pending).toHaveLength(7);
      for (const request of previous)
        request.resolve(evaluation(request.request));
      await advance(0);
      expect(screen.queryByText('-7 T3 · +1 T2')).not.toBeInTheDocument();
      await advance();
      expect(pending.length).toBeGreaterThan(previous.length);
    },
  );

  it('shows preview failures without disabling eligible facilities', async () => {
    vi.mocked(evaluatePlanPreview).mockRejectedValue(new Error('Unavailable'));
    render(FacilityPicker, pickerProps());
    await advance();
    expect(
      screen.getAllByText('CP preview unavailable').length,
    ).toBeGreaterThan(0);
    expect(screen.getByRole('status')).toHaveTextContent(
      'Cost previews are temporarily unavailable.',
    );
    expect(
      within(facilityButtons()[0].closest('li')!).getByRole('button'),
    ).toBeEnabled();
    expect(
      document.querySelector('[data-facility-id="installation-t2"]'),
    ).toBeDisabled();
  });
});
