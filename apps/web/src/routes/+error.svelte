<script lang="ts">
  import { page } from '$app/state';
</script>

<svelte:head><title>Something went wrong — ED-Finder</title></svelte:head>
<section class="error-page" role="alert">
  <h1>{page.status === 404 ? 'Page not found' : 'Something went wrong'}</h1>
  <p>{page.error?.message ?? 'The requested view could not be loaded.'}</p>
  <a href="/finder">Return to Finder</a>
</section>
