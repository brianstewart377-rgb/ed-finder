<script lang="ts">
  import { QueryClient, QueryClientProvider } from '@tanstack/svelte-query';
  import Page from '../../routes/+page.svelte';
  import AppShell from './AppShell.svelte';
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
</script>

<QueryClientProvider {client}><AppShell><Page /></AppShell></QueryClientProvider
>
