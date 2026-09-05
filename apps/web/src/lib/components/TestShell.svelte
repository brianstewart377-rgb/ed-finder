<script lang="ts">
  import { QueryClientProvider } from '@tanstack/svelte-query';
  import { queryClient } from '$lib/api/query';
  import { providePersistenceContext } from '$lib/persistence/context';
  import Page from '../../routes/+page.svelte';
  import AppShell from './AppShell.svelte';
  providePersistenceContext();
</script>

<QueryClientProvider client={queryClient}
  ><AppShell><Page /></AppShell></QueryClientProvider
>
