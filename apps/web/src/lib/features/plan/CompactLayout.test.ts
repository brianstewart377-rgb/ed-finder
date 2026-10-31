import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import BuildOrder from './BuildOrder.svelte';
import SystemPane from './SystemPane.svelte';
import { compactPlanFixture } from './__fixtures__/compact-plan';
import { resolvePlanLocations } from './locations';
import { PRIMARY_PORT_PROTECTION } from './model';

type Fixture = ReturnType<typeof compactPlanFixture>;

function renderSystem(fixture: Fixture) {
  return render(SystemPane, {
    ...fixture,
    selectedBody: null,
    stale: false,
    onselectbody: vi.fn(),
    onselectsite: vi.fn(),
    onslot: vi.fn(),
    onadd: vi.fn(),
  });
}

function renderOrder(fixture: Fixture) {
  return render(BuildOrder, {
    model: fixture.model,
    facilities: fixture.facilities,
    locations: resolvePlanLocations(fixture.bodies),
    systemName: fixture.systemName,
    evaluation: fixture.evaluation,
    stale: false,
    selectedBody: null,
    selectedSite: null,
    filter: 'All',
    onfilter: vi.fn(),
    onwhy: vi.fn(),
    onmove: vi.fn(),
    onupdate: vi.fn(),
    onremove: vi.fn(),
  });
}

afterEach(cleanup);

describe('compact planner layout', () => {
  it('keeps 40 bodies, two belts and 80 sites in compact body rows and two-line closed steps', () => {
    const fixture = compactPlanFixture();
    const system = renderSystem(fixture);
    const bodyRows = system.container.querySelectorAll('.compact-body-row');
    expect(bodyRows).toHaveLength(42);
    for (const row of bodyRows) {
      expect(row.querySelectorAll('.body-name')).toHaveLength(1);
      expect(row.querySelectorAll('.body-features')).toHaveLength(1);
      expect(row.querySelectorAll('.slot-box').length).toBeGreaterThan(0);
      expect(row.lastElementChild).toHaveClass('add-build');
      expect(row.querySelector('p, h3, br')).toBeNull();
    }
    for (const body of fixture.bodies.bodies) {
      const row = system.container.querySelector(
        `[data-plan-body="${body.body_id}"] > .compact-body-row`,
      )!;
      expect(row.querySelectorAll('.slot-box')).toHaveLength(2);
      const tiles = row.parentElement!.querySelector('.plan-tiles')!;
      expect(row.contains(tiles)).toBe(false);
      expect(tiles.querySelectorAll('.plan-tile')).toHaveLength(2);
    }
    expect(system.container.querySelectorAll('.plan-tile')).toHaveLength(80);

    const order = renderOrder(fixture);
    const steps = order.container.querySelectorAll('.build-step');
    expect(steps).toHaveLength(80);
    for (const [index, step] of [...steps].entries()) {
      expect(step).toHaveClass('compact-step');
      expect(step.children).toHaveLength(2);
      expect(step.children[0]).toHaveClass('step-title');
      expect(step.children[1]).toHaveClass('step-detail-row');
      expect(step.children[0].querySelector('h3')).toHaveTextContent(
        fixture.model.sites[index].name,
      );
      expect(
        step.children[0].querySelector('.evaluation-value'),
      ).toBeInTheDocument();
      const detailRow = step.children[1];
      expect(
        [...detailRow.querySelectorAll('.step-actions button')].map((control) =>
          control.getAttribute('aria-label'),
        ),
      ).toEqual(
        ['Move up', 'Move down', 'Why?'].map(
          (action) => `${action} ${fixture.model.sites[index].name}`,
        ),
      );
      expect(detailRow.querySelector('summary')).toHaveAttribute(
        'aria-label',
        `Edit ${fixture.model.sites[index].name}`,
      );
      expect(step.querySelector('.step-edit')).not.toHaveAttribute('open');
    }
  }, 15_000);

  it('retains full feature names and slot names alongside short visible markers', () => {
    const fixture = compactPlanFixture(2, 4);
    const { container } = renderSystem(fixture);
    const row = container.querySelector('[data-plan-body="2"]')!;
    for (const label of [
      'Landable',
      'Rings',
      'Geological 2',
      'Biological 1',
      'Volcanism: Major Silicate Vapour Geysers',
      'Atmosphere: Hot thick Argon-rich',
      'Terraformable: Candidate for terraforming',
    ]) {
      const marker = within(row as HTMLElement).getByTitle(label);
      expect(marker).toHaveAttribute('aria-label', label);
      expect(marker).toHaveAccessibleName(label);
      expect(marker).toHaveClass('body-feature');
      expect(marker.textContent!.trim()).not.toBe('');
      expect(marker.textContent!.length).toBeLessThan(label.length);
    }
    for (const label of ['Metal Rich', 'Rocky', 'Pristine']) {
      for (const marker of screen.getAllByTitle(label)) {
        expect(marker).toHaveAttribute('aria-label', label);
        expect(marker).toHaveAccessibleName(label);
      }
    }
    expect(
      screen.getByRole('button', {
        name: 'Orbital slots on Compact Test System A: 2 used, unknown total',
      }),
    ).toHaveTextContent('2/?');
    expect(
      screen.getByRole('button', {
        name: 'Surface slots on Compact Test System A: not available',
      }),
    ).toBeDisabled();
  });

  it('uses SVG status and result icons and keeps Primary Port protection inside the edit disclosure', async () => {
    const fixture = compactPlanFixture(2, 4);
    const system = renderSystem(fixture);
    for (const site of fixture.model.sites) {
      const tile = within(system.container).getByRole('button', {
        name: new RegExp(
          `^Step ${fixture.model.sites.indexOf(site) + 1}: ${site.status},`,
        ),
      });
      expect(tile.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
    }
    const order = renderOrder(fixture);
    const resultWords = ['OK', 'Blocked', 'Needs info', 'OK'];
    for (const [index, step] of [
      ...order.container.querySelectorAll('.build-step'),
    ].entries()) {
      expect(step.querySelector('.step-state svg')).toHaveAttribute(
        'aria-hidden',
        'true',
      );
      expect(step.querySelector('.step-state')).toHaveTextContent(
        fixture.model.sites[index].status,
      );
      expect(step.querySelector('.evaluation-value svg')).toHaveAttribute(
        'aria-hidden',
        'true',
      );
      expect(step.querySelector('.evaluation-value')).toHaveTextContent(
        resultWords[index],
      );
    }
    const primary = order.container.querySelector('.build-step')!;
    const protection = within(primary as HTMLElement).getByText(
      PRIMARY_PORT_PROTECTION,
    );
    const disclosure = primary.querySelector('details')!;
    expect(disclosure.contains(protection)).toBe(true);
    expect(protection).not.toBeVisible();
    for (const direction of ['up', 'down']) {
      const control = within(primary as HTMLElement).getByRole('button', {
        name: `Move ${direction} Colony site 1`,
      });
      expect(control).toBeDisabled();
      expect(control).toHaveAttribute('title', PRIMARY_PORT_PROTECTION);
    }
    await fireEvent.click(screen.getByLabelText('Edit Colony site 1'));
    expect(disclosure).toHaveAttribute('open');
    expect(protection).toBeVisible();
  });
});
