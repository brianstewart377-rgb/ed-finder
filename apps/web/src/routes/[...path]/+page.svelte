<script lang="ts">
  import { page } from '$app/state';
  import Finder from '$lib/components/Finder.svelte';
  import OwnerAccessGate from '$lib/components/OwnerAccessGate.svelte';
  import { routeFromPath } from '$lib/routing';
  import { persistentState } from '$lib/stores/persistence.svelte';
  const parsed = $derived(routeFromPath(page.url.pathname));
  const titles: Record<string, string> = {
    'my-work': 'My Work',
    compare: 'Compare',
    map: 'Map',
    'search-tuning': 'Development Tuning',
    fc: 'Fleet Carrier Planner',
    'colony-planner': 'Colony Planner',
    admin: 'Admin',
    operator: 'Operator',
  };
</script>

<svelte:head
  ><title
    >{parsed.route === 'finder' ? 'System Finder' : titles[parsed.route]} — ED-Finder</title
  ></svelte:head
>{#if parsed.route === 'finder'}<Finder
  />{:else if parsed.route === 'my-work'}<section>
    <h1>My Work</h1>
    <p>Saved systems, pins and colony projects.</p>
    {#if parsed.alias}<p data-testid="my-work-alias">
        Showing {parsed.alias} compatibility view.
      </p>{/if}
    <h2>Pinned systems</h2>
    {#if persistentState.pins.length}<ul>
        {#each persistentState.pins as pin (pin.id64)}<li>
            <a href={`/finder/system/${pin.id64}`}>{pin.name}</a>
          </li>{/each}
      </ul>{:else}<p>No pinned systems yet.</p>{/if}
  </section>{:else if parsed.route === 'admin' || parsed.route === 'operator'}<OwnerAccessGate
    ><section data-testid={`${parsed.route}-workspace`}>
      <h1>{titles[parsed.route]}</h1>
      <p>Authenticated owner workspace.</p>
    </section></OwnerAccessGate
  >{:else}<section>
    <h1>{titles[parsed.route]}</h1>
    <p>
      This workspace remains available at its stable direct URL while its
      feature implementation moves to Svelte.
    </p>
  </section>{/if}
