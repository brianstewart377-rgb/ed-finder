<script lang="ts">
  import { QueryClientProvider } from '@tanstack/svelte-query';
  import { queryClient } from '$lib/api/query';
  import { providePersistenceContext } from '$lib/persistence/context';
  import ExploreWorkspace from './ExploreWorkspace.svelte';

  providePersistenceContext();
</script>

<QueryClientProvider client={queryClient}
  ><ExploreWorkspace /></QueryClientProvider
>
