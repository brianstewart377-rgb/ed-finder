<script lang="ts">
  let { data } = $props();
</script>

<svelte:head><title>System {data.id64} — ED-Finder</title></svelte:head>
<main class="placeholder" data-testid="system-detail-page">
  <p class="eyebrow">Inspect</p>
  <h1>System Detail</h1>
  <p>System <code>{data.id64}</code></p>
  <p>
    This cold-entry feature body has not been ported yet. It shares the future
    content seam with the overlay.
  </p>
</main>
