<script lang="ts">
  import { resolve } from '$app/paths';
  import {
    ArrowUpRight,
    Compass,
    Map,
    Search,
    ClipboardCheck,
  } from '@lucide/svelte';
  import BootstrapStatus from '$lib/components/BootstrapStatus.svelte';
  import WorkspaceHeader from '$lib/components/WorkspaceHeader.svelte';

  const tools = [
    {
      href: '/explore',
      label: 'Explore',
      detail: 'Search the catalogue and discover systems in the galaxy map.',
      icon: Compass,
    },
    {
      href: '/inspect',
      label: 'Inspect',
      detail: 'Take a closer look at a system, its stars and its worlds.',
      icon: Search,
    },
  ] as const;
</script>

<svelte:head>
  <title>ED-Finder — Find your place among the stars</title>
  <meta
    name="description"
    content="Explore the Elite Dangerous galaxy. Find systems, inspect their worlds, and choose where to go next."
  />
</svelte:head>

<WorkspaceHeader />
<main class="home-page">
  <section class="hero home-hero">
    <div class="hero-copy">
      <p class="eyebrow">Your next destination starts here</p>
      <h1>Search the galaxy.<br /><span>Find your future.</span></h1>
      <p class="lede">
        Find your place among the stars. Explore systems, inspect their worlds,
        and decide where to go next.
      </p>
      <div class="hero-actions">
        <a class="primary-button" href={resolve('/explore')}
          >Explore the galaxy <ArrowUpRight size={19} aria-hidden="true" /></a
        >
        <a class="quiet-button" href={resolve('/inspect')}
          >Inspect a system <Search size={17} aria-hidden="true" /></a
        >
      </div>
      <p class="hero-note">
        Explore freely. Sign in with Frontier when you need your commander
        account.
      </p>
    </div>
    <div class="galaxy-motif" aria-hidden="true">
      <div class="orbital orbital-outer"></div>
      <div class="orbital orbital-middle"></div>
      <div class="orbital orbital-inner"></div>
      <span class="orbital-star star-one"></span>
      <span class="orbital-star star-two"></span>
      <span class="orbital-star star-three"></span>
      <Compass class="galaxy-compass" size={110} strokeWidth={0.65} />
      <span class="galaxy-caption">CHART YOUR OWN COURSE</span>
    </div>
  </section>

  <section class="home-tools" aria-labelledby="tools-heading">
    <div class="home-section-heading">
      <div>
        <p class="eyebrow">Choose your next step</p>
        <h2 id="tools-heading">A galaxy of possibilities.</h2>
      </div>
      <span>Built for commanders.</span>
    </div>
    <div class="tool-grid">
      {#each tools as tool (tool.href)}
        <a class="tool-card" href={resolve(tool.href)}>
          <span class="tool-icon"
            ><tool.icon size={25} strokeWidth={1.5} aria-hidden="true" /></span
          >
          <div>
            <h3>{tool.label}</h3>
            <p>{tool.detail}</p>
          </div>
          <ArrowUpRight class="tool-arrow" size={20} aria-hidden="true" />
        </a>
      {/each}
    </div>
    <div class="upcoming-tools">
      <p>
        <Map size={18} aria-hidden="true" /><strong>Colony planning</strong
        ><span>Coming later</span>
      </p>
      <p>
        <ClipboardCheck size={18} aria-hidden="true" /><strong
          >Review & export</strong
        ><span>Coming later</span>
      </p>
    </div>
  </section>
  <BootstrapStatus />
</main>
<footer class="site-footer">
  <span><strong>ED:FINDER</strong> · Your Elite Dangerous companion.</span><span
    >Explore. Discover. Make it yours.</span
  >
</footer>
