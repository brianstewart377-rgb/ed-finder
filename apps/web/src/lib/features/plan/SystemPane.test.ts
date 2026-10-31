import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import SystemPane from './SystemPane.svelte';
import { compactPlanFixture } from './__fixtures__/compact-plan';

function siteGroupsFixture() {
  const fixture = compactPlanFixture(2, 3);
  for (const site of fixture.model.sites) site.body_ref = '2';
  fixture.model.sites[1].slot_kind = 'surface';
  fixture.model.sites[2].slot_kind = 'orbital';
  return fixture;
}

function renderSystem(fixture = siteGroupsFixture(), onselectsite = vi.fn()) {
  return render(SystemPane, {
    ...fixture,
    selectedBody: null,
    stale: false,
    onselectbody: vi.fn(),
    onselectsite,
    onslot: vi.fn(),
    onadd: vi.fn(),
  });
}

function siteButton(step: number) {
  return screen.getByRole('button', { name: new RegExp(`^Step ${step},`) });
}

afterEach(cleanup);

describe('System pane site groups', () => {
  it('shows two orbital sites before one surface site in named lists beneath the body row', () => {
    const { container } = renderSystem();
    const body = container.querySelector<HTMLElement>('[data-plan-body="2"]')!;
    const orbital = within(body).getByRole('list', {
      name: 'Orbital sites on A 1',
    });
    const surface = within(body).getByRole('list', {
      name: 'Surface sites on A 1',
    });
    expect(within(body).getAllByRole('list')).toEqual([orbital, surface]);
    expect(within(orbital).getAllByRole('listitem')).toHaveLength(2);
    expect(within(surface).getAllByRole('listitem')).toHaveLength(1);
    expect(within(orbital).getAllByRole('button')).toEqual([
      siteButton(1),
      siteButton(3),
    ]);
    expect(within(surface).getAllByRole('button')).toEqual([siteButton(2)]);
    expect(body.firstElementChild).toHaveClass('compact-body-row');
    for (const [name, list] of [
      ['Orbital', orbital],
      ['Surface', surface],
    ] as const) {
      const group = list.parentElement!;
      const heading = within(group).getByRole('heading', { name });
      expect(group.children[0]).toBe(heading);
      expect(group.children[1]).toBe(list);
      expect(heading.querySelector('svg')).toHaveAttribute(
        'aria-hidden',
        'true',
      );
      expect(heading.querySelector('svg')).toHaveAttribute(
        'focusable',
        'false',
      );
    }
    expect(surface.parentElement).toHaveClass('surface');
    expect(orbital.parentElement).not.toHaveClass('surface');
  });

  it('renders only the surface group for a body with no orbital sites', () => {
    const fixture = siteGroupsFixture();
    for (const site of fixture.model.sites) site.slot_kind = 'surface';
    renderSystem(fixture);

    expect(screen.queryByRole('heading', { name: 'Orbital' })).toBeNull();
    expect(screen.queryByRole('list', { name: /Orbital sites/ })).toBeNull();
    const surface = screen.getByRole('list', { name: 'Surface sites on A 1' });
    expect(within(surface).getAllByRole('listitem')).toHaveLength(3);
    expect(screen.getByRole('heading', { name: 'Surface' })).toBeVisible();
  });

  it('does not add empty site groups beneath a body with no sites', () => {
    const { container } = renderSystem();
    const body = container.querySelector<HTMLElement>('[data-plan-body="1"]')!;
    expect(within(body).queryByRole('list')).toBeNull();
    expect(within(body).queryByRole('heading')).toBeNull();
  });

  it('places the full station name before its muted facility type and tier', () => {
    const fixture = siteGroupsFixture();
    const name = 'Deep Space Communications and Exploration Anchorage';
    fixture.model.sites[2].name = name;
    fixture.facilities[1].name = 'Communication Installation';
    renderSystem(fixture);

    const button = siteButton(3);
    const label = button.querySelector('.tile-label')!;
    expect(label.children).toHaveLength(2);
    expect(label.children[0]).toHaveClass('site-name');
    expect(label.children[0].tagName).toBe('STRONG');
    expect(label.children[0]).toHaveTextContent(name);
    expect(label.children[1]).toHaveClass('site-type');
    expect(label.children[1]).toHaveTextContent('Communication Installation');
    expect(label.children[1]).toHaveAttribute(
      'title',
      'Communication Installation',
    );
    expect(label.nextElementSibling).toHaveClass('plan-chip');
    expect(label.nextElementSibling).toHaveTextContent('T2');
    const fullLabel = `Step 3, planned, ${name}, Communication Installation, orbital, Needs info`;
    expect(button).toHaveAccessibleName(fullLabel);
    expect(button).toHaveAttribute('title', fullLabel);
  });

  it('uses the facility type once in the name position when the station has no name', () => {
    const fixture = siteGroupsFixture();
    fixture.model.sites[1].name = '';
    renderSystem(fixture);

    const button = siteButton(2);
    expect(button.querySelector('.site-name')).toHaveTextContent(
      'Research Installation',
    );
    expect(button.querySelector('.site-type')).toBeNull();
    expect(within(button).getAllByText('Research Installation')).toHaveLength(
      1,
    );
    expect(button).toHaveAccessibleName(
      'Step 2, building, Research Installation, surface',
    );
    expect(button).toHaveAttribute(
      'title',
      'Step 2, building, Research Installation, surface',
    );
  });

  it('switches to Types only without repeating types, and restores station names', async () => {
    const fixture = siteGroupsFixture();
    renderSystem(fixture);
    const toggle = screen.getByRole('button', { name: 'Names and types' });
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
    await fireEvent.click(toggle);

    expect(toggle).toHaveAccessibleName('Types only');
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
    for (const [index, site] of fixture.model.sites.entries()) {
      const button = siteButton(index + 1);
      const facility = fixture.facilities.find(
        (entry) => entry.id === site.facility_id,
      )!;
      expect(button.querySelector('.site-name')).toHaveTextContent(
        facility.name,
      );
      expect(button.querySelector('.site-type')).toBeNull();
      expect(screen.queryByText(site.name)).toBeNull();
      expect(button.getAttribute('aria-label')).not.toContain(site.name);
      expect(button.getAttribute('title')).not.toContain(site.name);
    }
    expect(siteButton(1)).toHaveAccessibleName(
      'Step 1, Primary Port, complete, Primary Outpost, orbital',
    );
    await fireEvent.click(toggle);
    expect(toggle).toHaveAccessibleName('Names and types');
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
    for (const site of fixture.model.sites) {
      expect(screen.getByText(site.name)).toBeVisible();
    }
  });

  it('starts the primary accessible name with its step and Primary Port, and retains Why selection', async () => {
    const onselectsite = vi.fn();
    renderSystem(siteGroupsFixture(), onselectsite);
    const button = siteButton(1);
    const fullLabel =
      'Step 1, Primary Port, complete, Colony site 1, Primary Outpost, orbital';
    expect(button).toHaveAccessibleName(fullLabel);
    expect(button).toHaveAttribute('title', fullLabel);
    expect(button.querySelector('.tile-number')).toHaveTextContent(/^★\s*1$/);
    expect(within(button).getByText('★')).toHaveAttribute(
      'aria-hidden',
      'true',
    );
    expect(button.querySelectorAll('svg')).toHaveLength(1);
    expect(siteButton(3).querySelectorAll('svg')).toHaveLength(2);

    await fireEvent.click(button);
    expect(onselectsite).toHaveBeenCalledExactlyOnceWith('site-1');
  });

  it('groups null and unresolved Unplaced locations by slot kind in the same order', () => {
    const fixture = siteGroupsFixture();
    fixture.model.sites[0].body_ref = null;
    fixture.model.sites[1].body_ref = 'unknown-body';
    fixture.model.sites[2].body_ref = null;
    renderSystem(fixture);

    expect(screen.getByRole('heading', { name: 'Unplaced' })).toBeVisible();
    const orbital = screen.getByRole('list', {
      name: 'Orbital sites in Unplaced',
    });
    const surface = screen.getByRole('list', {
      name: 'Surface sites in Unplaced',
    });
    expect(screen.getAllByRole('list', { name: /sites in Unplaced$/ })).toEqual(
      [orbital, surface],
    );
    expect(within(orbital).getAllByRole('listitem')).toHaveLength(2);
    expect(within(surface).getAllByRole('listitem')).toHaveLength(1);
    expect(within(orbital).getAllByRole('button')).toEqual([
      siteButton(1),
      siteButton(3),
    ]);
    expect(within(surface).getAllByRole('button')).toEqual([siteButton(2)]);
    expect(surface.parentElement).toHaveClass('surface');
    expect(screen.queryByRole('list', { name: /sites on / })).toBeNull();
  });
});
