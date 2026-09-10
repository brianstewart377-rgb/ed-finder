<script lang="ts">
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { onMount } from 'svelte';
  import { auth } from '$lib/auth/auth';
  import { parseId64, type Id64 } from '$lib/domain/id64';
  import { usePersistenceContext } from '$lib/persistence/context';
  import { hydrateApplicationStores } from '$lib/persistence/stores';
  import { applyLegacyHash } from '$lib/routing/legacy-hash';
  import SystemOverlay from './SystemOverlay.svelte';

  let { children } = $props<{ children: import('svelte').Snippet }>();
  const persistence = usePersistenceContext();
  const { selectedSystem } = persistence;
  let persistenceReady = $state(false);
  let lastUrlSelection: Id64 | null = null;

  let urlSelection = $derived.by((): Id64 | null => {
    const raw = page.url.searchParams.get('system');
    if (!raw) return null;
    try {
      return parseId64(raw);
    } catch {
      return null;
    }
  });

  // Inspect is the canonical detail route. The modal lifecycle is retained
  // only as an Explore-context affordance, never as a competing route model.
  let overlayId = $derived(
    page.url.pathname === '/explore' ? urlSelection : null,
  );

  function establishUrlSelection(): void {
    if (!urlSelection) {
      lastUrlSelection = null;
      return;
    }
    if (urlSelection === lastUrlSelection) return;
    selectedSystem.set(urlSelection);
    lastUrlSelection = urlSelection;
  }

  $effect(() => {
    if (persistenceReady) establishUrlSelection();
  });

  onMount(() => {
    hydrateApplicationStores();
    establishUrlSelection();
    persistenceReady = true;

    const normaliseLegacyHash = () =>
      applyLegacyHash(location, (url) => {
        // eslint-disable-next-line svelte/no-navigation-without-resolve -- compatibility destination is closed and validated
        void goto(url, { replaceState: true });
      });
    normaliseLegacyHash();
    window.addEventListener('hashchange', normaliseLegacyHash);
    void auth.bootstrap();

    return () => window.removeEventListener('hashchange', normaliseLegacyHash);
  });
</script>

<a class="skip-link" href="#main-content">Skip to main content</a>
{#if persistenceReady && $selectedSystem.hydrated && $selectedSystem.value}
  <aside class="context-chip" data-testid="selected-system-context">
    Selected system <strong>{$selectedSystem.value}</strong>
    <a href={resolve(`/inspect?system=${$selectedSystem.value}`)}>Inspect</a>
    <a href={resolve(`/plan?system=${$selectedSystem.value}`)}>Open plan</a>
  </aside>
{/if}
<div id="main-content" tabindex="-1">{@render children()}</div>
{#if overlayId}<SystemOverlay id64={overlayId} />{/if}
