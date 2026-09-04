<script lang="ts">
  import { Compass, Map, Search, ClipboardCheck } from '@lucide/svelte';
  import BootstrapStatus from '$lib/components/BootstrapStatus.svelte';

  const steps = [
    { href: '/explore', label: 'Explore', detail: 'Future discovery workspace', icon: Compass },
    { href: '/inspect', label: 'Inspect', detail: 'Future system detail', icon: Search },
    { href: '/plan', label: 'Plan', detail: 'Future colony planning', icon: Map },
    { href: '/review', label: 'Review / Export', detail: 'Future evidence workflow', icon: ClipboardCheck }
  ];
</script>

<svelte:head><title>ED-Finder V3</title><meta name="description" content="ED-Finder V3 application foundation" /></svelte:head>

<header class="site-header">
  <a class="brand" href="/" aria-label="ED-Finder V3 home"><span>ED</span>Finder <b>V3</b></a>
  <nav aria-label="Product journey">
    {#each steps as step}<a href={step.href}>{step.label}</a>{/each}
  </nav>
</header>
<main>
  <section class="hero">
    <p class="eyebrow">New application foundation</p>
    <h1>Find your place<br />among the stars.</h1>
    <p class="lede">ED-Finder V3 is taking shape. This shell establishes the journey while existing tools remain in the reference application during migration.</p>
  </section>
  <section aria-labelledby="journey-title">
    <p class="eyebrow">Product journey</p><h2 id="journey-title">Explore to evidence</h2>
    <div class="journey">
      {#each steps as step, index}
        <a href={step.href}><span class="number">0{index + 1}</span><step.icon aria-hidden="true" size={24} /><strong>{step.label}</strong><small>{step.detail}</small></a>
      {/each}
    </div>
  </section>
  <BootstrapStatus />
</main>
<footer>Foundation only — product features have not yet been ported.</footer>
