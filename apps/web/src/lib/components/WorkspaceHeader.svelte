<script lang="ts">
  import { resolve } from '$app/paths';
  import { page } from '$app/state';

  const links = [
    { href: '/explore', label: 'Explore' },
    { href: '/inspect', label: 'Inspect' },
    { href: '/plan', label: 'Plan' },
    { href: '/review', label: 'Review' },
  ] as const;
</script>

<header class="workspace-header">
  <a class="brand" href={resolve('/')} aria-label="ED-Finder V3 home"
    ><span>ED</span>Finder <b>V3</b></a
  >
  <nav aria-label="Product journey">
    {#each links as link (link.href)}
      <a
        href={resolve(link.href)}
        aria-current={page.url.pathname === link.href ? 'page' : undefined}
        >{link.label}</a
      >
    {/each}
  </nav>
</header>
