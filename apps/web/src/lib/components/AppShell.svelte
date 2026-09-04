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
  let overlayId = $derived.by((): Id64 | null => {
    const raw = page.url.searchParams.get('system');
    if (!raw || page.url.pathname.startsWith('/system/')) return null;
    try {
      return parseId64(raw);
    } catch {
      return null;
    }
  });
  let routeSelection = $derived.by((): Id64 | null => {
    if (!page.url.pathname.startsWith('/system/')) return null;
    try {
      return parseId64(
        page.url.pathname.slice('/system/'.length).split('/')[0],
      );
    } catch {
      return null;
    }
  });
  $effect(() => {
    const establishedSelection = overlayId ?? routeSelection;
    if (establishedSelection)
      persistence.selectedSystem.set(establishedSelection);
  });
  onMount(() => {
    hydrateApplicationStores();
    const normaliseLegacyHash = () =>
      applyLegacyHash(
        location,
        // eslint-disable-next-line svelte/no-navigation-without-resolve -- validated compatibility URL
        (url) => void goto(url, { replaceState: true }),
      );
    normaliseLegacyHash();
    window.addEventListener('hashchange', normaliseLegacyHash);
    void auth.bootstrap();
    return () => window.removeEventListener('hashchange', normaliseLegacyHash);
  });
</script>

<a class="skip-link" href="#main-content">Skip to main content</a>
<header class="site-header">
  <a class="brand" href={resolve('/')} aria-label="ED-Finder home"
    ><span>ED</span>Finder</a
  >
  <nav aria-label="Primary navigation">
    <a href={resolve('/')}>Finder</a><a href={resolve('/explore')}>Explore</a><a
      href={resolve('/my-work')}>My Work</a
    ><a href={resolve('/compare')}>Compare</a><a
      href={resolve('/colony-planner')}>Plan</a
    ><a href={resolve('/review')}>Review / Export</a>
  </nav>
  <div class="account" aria-live="polite" aria-label="Account status">
    {#if $auth.error}<span role="alert">Account unavailable</span>{/if}
    {#if $auth.loading}Account…{:else if $auth.authenticated}<span
        data-testid="frontier-account-name"
        >{$auth.user?.commander_name
          ? `CMDR ${$auth.user.commander_name}`
          : 'Frontier account'}</span
      >{#if $auth.user?.is_owner}<a
          href={resolve('/admin')}
          data-testid="owner-open-ops">Ops</a
        >{/if}<button
        type="button"
        data-testid="frontier-sign-out"
        onclick={() => void auth.signOut()}>Sign out</button
      >{:else}<button
        type="button"
        data-testid="frontier-sign-in"
        onclick={auth.signIn}>Sign in</button
      >{/if}
  </div>
</header>
{#if $selectedSystem.hydrated && $selectedSystem.value}<aside
    class="context-chip"
    data-testid="selected-system-context"
  >
    Selected system <strong>{$selectedSystem.value}</strong><a
      href={resolve(`/colony-planner/system/${$selectedSystem.value}`)}
      >Open plan</a
    >
  </aside>{/if}
<div id="main-content" tabindex="-1">{@render children()}</div>
<footer>
  <details>
    <summary>Data, community &amp; intellectual property attribution</summary>
    <p>
      ED-Finder uses data from the Elite Dangerous community. Elite Dangerous is
      © Frontier Developments plc. ED-Finder is a non-commercial fan project and
      is not endorsed by Frontier Developments.
    </p>
  </details>
</footer>
{#if overlayId}<SystemOverlay id64={overlayId} />{/if}
