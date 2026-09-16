<script lang="ts">
  import { onMount } from 'svelte';
  import { QueryClientProvider } from '@tanstack/svelte-query';
  import AppShell from '$lib/components/AppShell.svelte';
  import { queryClient } from '$lib/api/query';
  import { providePersistenceContext } from '$lib/persistence/context';
  import '../app.css';

  let { children } = $props();
  providePersistenceContext();

  // A lazily-imported chunk can fail to load — most often right after a deploy,
  // when an already-open tab requests a hashed chunk name the new build no longer
  // serves (and intermittently under some browsers). Vite emits `vite:preloadError`
  // for this; recover by reloading onto the current build. Guarded to a single
  // attempt via sessionStorage so a genuinely missing chunk cannot reload-loop.
  onMount(() => {
    const RELOAD_FLAG = 'edfinder:preload-error-reloaded';
    // Reaching onMount means the app loaded successfully, so clear any prior guard.
    sessionStorage.removeItem(RELOAD_FLAG);
    const onPreloadError = (event: Event) => {
      event.preventDefault();
      if (sessionStorage.getItem(RELOAD_FLAG)) return;
      sessionStorage.setItem(RELOAD_FLAG, '1');
      location.reload();
    };
    window.addEventListener('vite:preloadError', onPreloadError);
    return () =>
      window.removeEventListener('vite:preloadError', onPreloadError);
  });
</script>

<QueryClientProvider client={queryClient}>
  <AppShell>{@render children()}</AppShell>
</QueryClientProvider>
