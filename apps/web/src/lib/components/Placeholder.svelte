<script lang="ts">
  let { title, detail = 'This product surface has not been ported yet.' } =
    $props<{ title: string; detail?: string }>();
</script>

<svelte:head><title>{title} — ED-Finder</title></svelte:head>
<main class="placeholder">
  <p class="eyebrow">Migration placeholder</p>
  <h1>{title}</h1>
  <p>{detail}</p>
</main>
