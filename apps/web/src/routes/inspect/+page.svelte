<script lang="ts">
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import SystemDetail from '$lib/components/SystemDetail.svelte';
  import WorkspaceHeader from '$lib/components/WorkspaceHeader.svelte';
  import { FINDER_F4_ENABLED } from '$lib/config';
  import { parseId64, type Id64 } from '$lib/domain/id64';
  import { navigateWithAnchor } from '$lib/features/explore/navigation';

  const rawSystem = $derived(page.url.searchParams.get('system'));
  const systemId = $derived.by((): Id64 | null => {
    if (!rawSystem) return null;
    try {
      return parseId64(rawSystem);
    } catch {
      return null;
    }
  });
  const backHref = $derived(exploreHref(false));
  const openHref = $derived(exploreHref(true));

  function exploreHref(selectSystem: boolean): string {
    if (!FINDER_F4_ENABLED) {
      return selectSystem && systemId
        ? resolve(`/explore?system=${systemId}`)
        : resolve('/explore');
    }
    const params = new URLSearchParams(page.url.searchParams.get('from') ?? '');
    if (selectSystem && systemId) {
      // Replace prior selections, including every duplicate in the source query.
      params.delete('selected');
      params.delete('system');
      params.set('selected', systemId);
      params.set('system', systemId);
    }
    const query = params.toString();
    return `${resolve('/explore')}${query ? `?${query}` : ''}`;
  }

  function followExplore(event: MouseEvent, destination: string): void {
    if (
      !FINDER_F4_ENABLED ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    )
      return;
    event.preventDefault();
    void navigateWithAnchor(destination);
  }
</script>

<svelte:head><title>Inspect — ED-Finder V3</title></svelte:head>
<WorkspaceHeader />
<main class="inspect-page product-page">
  {#if systemId}
    <SystemDetail id64={systemId} autofocusHeading />
    <nav class="detail-actions" aria-label="System actions">
      <!-- eslint-disable svelte/no-navigation-without-resolve -- exploreHref resolves the Explore route -->
      <a
        class="secondary-button"
        href={backHref}
        onclick={(event) => followExplore(event, backHref)}>Back to Explore</a
      >
      <a
        class="secondary-button"
        href={openHref}
        onclick={(event) => followExplore(event, openHref)}>Open in Explore</a
      >
      <!-- eslint-enable svelte/no-navigation-without-resolve -->
      <a class="primary-button" href={resolve(`/plan?system=${systemId}`)}
        >Continue to Plan</a
      >
    </nav>
  {:else}
    <section
      class="system-detail invalid"
      data-invalid-system={rawSystem ?? ''}
    >
      <p class="eyebrow">Inspect</p>
      <h1>Choose a valid system</h1>
      <p class="state-copy" role="alert">
        {#if rawSystem}
          <code>{rawSystem}</code> is not a canonical unsigned 64-bit system identifier.
        {:else}
          Inspect opens a system by its exact ID64. Start in Explore to choose
          one.
        {/if}
      </p>
      <a class="primary-button" href={resolve('/explore')}>Explore systems</a>
    </section>
  {/if}
</main>
