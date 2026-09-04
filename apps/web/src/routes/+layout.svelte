<script lang="ts">
  import { QueryClient, QueryClientProvider } from '@tanstack/svelte-query';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { legacyHashPath } from '$lib/routing';
  import { persistentState } from '$lib/stores/persistence.svelte';
  import { authState } from '$lib/stores/auth.svelte';
  import AccountControls from '$lib/components/AccountControls.svelte';
  import '../app.css';
  let { children } = $props();
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: 1, staleTime: 30000 } },
  });
  const nav = [
    ['/finder', 'Finder'],
    ['/my-work', 'My Work'],
    ['/compare', 'Compare'],
    ['/map', 'Map'],
    ['/colony-planner', 'Colony Planner'],
    ['/fc', 'Fleet Carrier'],
  ];
  onMount(() => {
    persistentState.hydrate();
    void authState.refresh();
    const target = legacyHashPath(location.hash);
    if (target) {
      history.replaceState(null, '', target);
      void goto(target, { replaceState: true });
    }
  });
</script>

<svelte:head
  ><meta
    name="description"
    content="Find, save and plan Elite Dangerous systems"
  /></svelte:head
><QueryClientProvider client={queryClient}
  ><a class="skip-link" href="#app-content">Skip to main content</a>
  <header class="site-header" data-testid="app-shell">
    <a class="brand" href="/finder" aria-label="ED-Finder home"
      ><span>ED</span>Finder</a
    >
    <nav aria-label="Primary navigation">
      {#each nav as item (item[0])}<a
          href={item[0]}
          aria-current={page.url.pathname.startsWith(item[0])
            ? 'page'
            : undefined}>{item[1]}</a
        >{/each}
    </nav>
    <AccountControls />
  </header>
  <main id="app-content" tabindex="-1">{@render children()}</main>
  <footer>
    <nav aria-label="Footer navigation">
      <a href="/search-tuning">Development Tuning</a><a href="/admin">Admin</a
      ><a href="/operator">Operator</a>
    </nav>
    <p>ED-Finder · Galaxy exploration and colony planning</p>
  </footer></QueryClientProvider
>
