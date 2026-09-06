<script lang="ts">
  import { QueryClientProvider } from '@tanstack/svelte-query';
  import { queryClient } from '$lib/api/query';
  import type { Id64 } from '$lib/domain/id64';
  import SystemDetail from './SystemDetail.svelte';

  let { id64 } = $props<{ id64: Id64 }>();
</script>

<QueryClientProvider client={queryClient}
  ><SystemDetail {id64} /></QueryClientProvider
>
