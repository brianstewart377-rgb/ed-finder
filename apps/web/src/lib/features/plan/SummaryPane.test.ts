import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, expect, it, vi } from 'vitest';
import SummaryPane from './SummaryPane.svelte';
import { compactPlanFixture } from './__fixtures__/compact-plan';
import { resolvePlanLocations } from './locations';

afterEach(cleanup);

it('uses a retired former belt cluster alias to find known slot totals', async () => {
  const fixture = compactPlanFixture(2, 1);
  const belt = fixture.bodies.belts[0];
  fixture.bodies.bodies.push(
    {
      ...fixture.bodies.bodies[0],
      body_id: 'old-cluster',
      name: `${belt.name} Cluster 1`,
      body_type: 'belt cluster',
      lifecycle_state: 'RETIRED',
    },
    {
      ...fixture.bodies.bodies[0],
      body_id: 'current-cluster',
      name: `${belt.name} Cluster 2`,
      body_type: 'belt cluster',
    },
  );
  fixture.model.sites[0].body_ref = 'current-cluster';
  fixture.model.slots = {
    'old-cluster': { orbital_slots: 2, surface_slots: null },
  };
  const { rerender } = render(SummaryPane, {
    model: fixture.model,
    bodies: fixture.bodies,
    facilities: fixture.facilities,
    locations: resolvePlanLocations(fixture.bodies),
    evaluation: null,
    view: 'now',
    error: '',
    pending: false,
    stale: false,
    onstep: vi.fn(),
    onbody: vi.fn(),
    onwhy: vi.fn(),
  });
  expect(
    screen.queryByRole('button', { name: /unknown slot counts/ }),
  ).not.toBeInTheDocument();
  expect(screen.getByText('No items need attention.')).toBeVisible();

  await rerender({ model: { ...fixture.model, slots: {} } });
  expect(
    screen.getByRole('button', {
      name: '1 body has builds with unknown slot counts',
    }),
  ).toBeVisible();
});
