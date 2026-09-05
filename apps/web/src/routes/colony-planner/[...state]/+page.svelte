<script lang="ts">
  import Placeholder from '$lib/components/Placeholder.svelte';
  let { data } = $props();
  const detail = $derived(
    data.system
      ? `System ${data.system}${data.project ? ` · project ${data.project}` : ''}${data.mode ? ` · ${data.mode}` : ''}. Planner features have not been ported yet.`
      : 'Colony Planner has not been ported yet.',
  );
</script>

<Placeholder title="Colony Planner" {detail} />
