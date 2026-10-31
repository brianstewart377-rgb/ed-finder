<script lang="ts">
  import { QueryClientProvider } from '@tanstack/svelte-query';
  import { queryClient } from '$lib/api/query';
  import { parseId64 } from '$lib/domain/id64';
  import PlanWorkspace from './PlanWorkspace.svelte';
</script>

<QueryClientProvider client={queryClient}>
  <PlanWorkspace systemId={parseId64('42')} />
</QueryClientProvider>
