<script lang="ts">
  import { page } from '$app/state';
  import { resolve } from '$app/paths';
</script>

<svelte:head
  ><title
    >{page.status === 404 ? 'Not found' : 'Application error'} — ED-Finder</title
  ></svelte:head
>
<main class="placeholder" data-testid="application-error">
  <p class="eyebrow">{page.status}</p>
  <h1>{page.status === 404 ? 'Route not found' : 'Something went wrong'}</h1>
  <p>
    {page.error?.message ??
      'The requested application surface could not be loaded.'}
  </p>
  <a href={resolve('/')}>Return to Finder</a>
</main>
