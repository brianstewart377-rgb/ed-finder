<script lang="ts">
  import {
    setQueryClientContext,
    type QueryClient,
  } from '@tanstack/svelte-query';
  import { onMount, untrack } from 'svelte';
  import type { Vec3Ly } from './contracts';
  import { createGalaxyStarQuery } from './galaxy-star-query.svelte';
  import type { GalaxyStarViewport } from './galaxy-star-stream';

  let { client, viewport, focus } = $props<{
    client: QueryClient;
    viewport: GalaxyStarViewport | null;
    focus: Vec3Ly;
  }>();
  // The same context and mount lifecycle as QueryClientProvider, so this host
  // can exercise a query hook without adding a second wrapper component.
  const queryClient = untrack(() => client);
  setQueryClientContext(queryClient);
  onMount(() => {
    queryClient.mount();
    return () => queryClient.unmount();
  });
  const query = createGalaxyStarQuery(
    () => viewport,
    () => focus,
  );
</script>

<output
  data-testid="catalogue-packet"
  data-pending={query.isPending}
  data-fetching={query.isFetching}
  data-error={query.isError}
  >{query.data ? JSON.stringify(query.data) : ''}</output
>
