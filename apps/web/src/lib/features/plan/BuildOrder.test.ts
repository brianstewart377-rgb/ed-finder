import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import BuildOrder from './BuildOrder.svelte';
import { compactPlanFixture } from './__fixtures__/compact-plan';
import { resolvePlanLocations } from './locations';

function facilityFixture() {
  const fixture = compactPlanFixture(2, 1);
  fixture.model.sites[0].status = 'planned';
  fixture.model.sites[0].body_ref = '2';
  const [port, installation] = fixture.facilities;
  fixture.facilities = [
    {
      ...port,
      id: 'surface-port',
      name: 'Surface Port',
      allowed_location: 'surface',
    },
    port,
    {
      ...port,
      id: 'surface-outpost',
      name: 'Surface Outpost',
      allowed_location: 'surface',
    },
    {
      ...port,
      id: 'ringed-port',
      name: 'Asteroid Base',
      allowed_location: 'orbital_ringed',
    },
    { ...installation, allowed_location: 'orbital' },
    {
      ...installation,
      id: 'surface-installation',
      name: 'Surface Installation',
      allowed_location: 'surface',
    },
  ];
  return fixture;
}

function renderOrder(fixture = facilityFixture(), onupdate = vi.fn()) {
  return render(BuildOrder, {
    model: fixture.model,
    facilities: fixture.facilities,
    locations: resolvePlanLocations(fixture.bodies),
    systemName: fixture.systemName,
    evaluation: null,
    stale: false,
    selectedBody: null,
    selectedSite: null,
    filter: 'All',
    onfilter: vi.fn(),
    onwhy: vi.fn(),
    onmove: vi.fn(),
    onupdate,
    onremove: vi.fn(),
  });
}

function optionValues(container: HTMLElement) {
  return within(container)
    .queryAllByRole('option')
    .map((option) => option.getAttribute('value'));
}

afterEach(cleanup);

describe('build order facility editing', () => {
  it('offers only ports of both slot kinds for a planned Primary Port on a landable body, preserving order within each group', async () => {
    renderOrder();
    await fireEvent.click(screen.getByLabelText('Edit Colony site 1'));
    const select = screen.getByRole('combobox', {
      name: 'Facility for step 1',
    });
    expect(select).toBeEnabled();
    expect(select).toHaveValue('primary-port');
    expect(
      within(select)
        .getAllByRole('group')
        .map((group) => group.getAttribute('label')),
    ).toEqual(['Orbital', 'Surface']);
    expect(
      optionValues(within(select).getByRole('group', { name: 'Orbital' })),
    ).toEqual(['primary-port', 'ringed-port']);
    expect(
      optionValues(within(select).getByRole('group', { name: 'Surface' })),
    ).toEqual(['surface-port', 'surface-outpost']);
  });

  it('offers only orbital ports on a non-landable body', async () => {
    const fixture = facilityFixture();
    fixture.bodies.bodies[1].is_landable = false;
    renderOrder(fixture);
    await fireEvent.click(screen.getByLabelText('Edit Colony site 1'));
    const select = screen.getByRole('combobox', {
      name: 'Facility for step 1',
    });
    expect(optionValues(select)).toEqual(['primary-port', 'ringed-port']);
  });

  it('still requires rings for an orbital_ringed port', async () => {
    const fixture = facilityFixture();
    fixture.bodies.bodies[1].has_rings = false;
    renderOrder(fixture);
    await fireEvent.click(screen.getByLabelText('Edit Colony site 1'));
    expect(
      optionValues(
        screen.getByRole('combobox', { name: 'Facility for step 1' }),
      ),
    ).toEqual(['primary-port', 'surface-port', 'surface-outpost']);
  });

  it('offers every facility to Unplaced sites, restricted to ports for the primary', async () => {
    const fixture = facilityFixture();
    fixture.model.sites[0].body_ref = null;
    fixture.model.sites.push({
      ...fixture.model.sites[0],
      site_id: 'site-2',
      name: 'Colony site 2',
      facility_id: 'installation',
    });
    renderOrder(fixture);
    await fireEvent.click(screen.getByLabelText('Edit Colony site 1'));
    await fireEvent.click(screen.getByLabelText('Edit Colony site 2'));
    expect(
      optionValues(
        screen.getByRole('combobox', { name: 'Facility for step 1' }),
      ),
    ).toEqual([
      'primary-port',
      'ringed-port',
      'surface-port',
      'surface-outpost',
    ]);
    expect(
      optionValues(
        screen.getByRole('combobox', { name: 'Facility for step 2' }),
      ),
    ).toEqual([
      'primary-port',
      'ringed-port',
      'installation',
      'surface-port',
      'surface-outpost',
      'surface-installation',
    ]);
  });

  it.each([
    { facility_id: 'surface-port', name: 'Surface Port' },
    { facility_id: 'unknown-port', name: 'unknown-port' },
  ])(
    'keeps the disabled invalid-current-value option for $facility_id',
    async ({ facility_id, name }) => {
      const fixture = facilityFixture();
      fixture.model.sites[0].facility_id = facility_id;
      fixture.model.sites[0].slot_kind = 'surface';
      fixture.bodies.bodies[1].is_landable = false;
      renderOrder(fixture);
      await fireEvent.click(screen.getByLabelText('Edit Colony site 1'));
      const select = screen.getByRole('combobox', {
        name: 'Facility for step 1',
      });
      expect(select).toHaveValue(facility_id);
      expect(
        within(select).getByRole('option', {
          name: `${name} — choose a valid facility`,
        }),
      ).toBeDisabled();
      expect(optionValues(select)).toEqual([
        facility_id,
        'primary-port',
        'ringed-port',
      ]);
    },
  );

  it.each([
    { initial: 'orbital', chosen: 'surface-port', slot_kind: 'surface' },
    { initial: 'surface', chosen: 'primary-port', slot_kind: 'orbital' },
  ] as const)(
    'switches a planned Primary Port from $initial to $slot_kind with one update',
    async ({ initial, chosen, slot_kind }) => {
      const fixture = facilityFixture();
      fixture.model.sites[0].slot_kind = initial;
      fixture.model.sites[0].facility_id =
        initial === 'surface' ? 'surface-port' : 'primary-port';
      const onupdate = vi.fn();
      renderOrder(fixture, onupdate);
      await fireEvent.click(screen.getByLabelText('Edit Colony site 1'));
      await fireEvent.change(
        screen.getByRole('combobox', { name: 'Facility for step 1' }),
        { target: { value: chosen } },
      );
      expect(onupdate).toHaveBeenCalledExactlyOnceWith('site-1', {
        facility_id: chosen,
        slot_kind,
      });
    },
  );

  it.each(['building', 'complete'] as const)(
    'keeps the Facility select disabled for a placed %s Primary Port',
    async (status) => {
      const fixture = facilityFixture();
      fixture.model.sites[0].status = status;
      renderOrder(fixture);
      await fireEvent.click(screen.getByLabelText('Edit Colony site 1'));
      expect(
        screen.getByRole('combobox', { name: 'Facility for step 1' }),
      ).toBeDisabled();
    },
  );
});
