<script lang="ts">
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import SystemDetail from '$lib/components/SystemDetail.svelte';
  import WorkspaceHeader from '$lib/components/WorkspaceHeader.svelte';
  import { parseId64, type Id64 } from '$lib/domain/id64';

  const rawSystem = $derived(page.url.searchParams.get('system'));
  const systemId = $derived.by((): Id64 | null => {
    if (!rawSystem) return null;
    try {
      return parseId64(rawSystem);
    } catch {
      return null;
    }
  });
</script>

<svelte:head><title>Inspect — ED-Finder V3</title></svelte:head>
<WorkspaceHeader />
<main class="inspect-page product-page">
  {#if systemId}
    <SystemDetail id64={systemId} autofocusHeading />
    <nav class="detail-actions" aria-label="System actions">
      <a class="secondary-button" href={resolve('/explore')}>Back to Explore</a>
      <a class="secondary-button" href={resolve(`/explore?system=${systemId}`)}
        >Open in Explore</a
      >
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
