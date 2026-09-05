<script lang="ts">
  import { page } from '$app/state';
  import Placeholder from '$lib/components/Placeholder.svelte';
  const names = {
    watchlist: 'Saved systems',
    pinned: 'Pinned systems',
    colony: 'Colony projects',
  };
  const title = $derived(names[page.params.alias as keyof typeof names]);
</script>

<Placeholder
  {title}
  detail="This My Work alias is retained, but its feature UI has not been ported yet."
/>
