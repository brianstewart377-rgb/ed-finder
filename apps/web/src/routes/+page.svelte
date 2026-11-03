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
      detail: 'Find your next system.',
      icon: Compass,
    },
    {
      href: '/inspect',
      label: 'Inspect',
      detail: 'See a system in detail.',
      icon: Search,
    },
    {
      href: '/plan',
      label: 'Plan',
      detail: 'Lay out your next colony.',
      icon: Map,
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
      <Compass
        class="galaxy-compass"
        size={110}
        strokeWidth={0.65}
        aria-hidden="true"
      />
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
          <div class="tool-copy">
            <h3>{tool.label}</h3>
            <p>{tool.detail}</p>
          </div>
          <ArrowUpRight class="tool-arrow" size={20} aria-hidden="true" />
        </a>
      {/each}
    </div>
    <div class="upcoming-tools">
      <p>
        <ClipboardCheck size={18} aria-hidden="true" /><strong
          >Review & export</strong
        ><a href={resolve('/plan')}>Available in Plan</a>
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

<style>
  .home-page,
  .site-footer {
    width: min(80rem, calc(100% - 3rem));
  }

  .home-hero {
    display: grid;
    grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr);
    align-items: center;
    gap: 2rem;
    max-width: none;
    padding-block: clamp(3rem, 5vw, 4rem);
  }

  .hero-copy {
    min-width: 0;
  }

  .eyebrow {
    margin: 0;
    color: var(--accent);
    font-family: var(--font-hud);
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    line-height: 1.5;
    text-transform: uppercase;
  }

  .home-hero h1 {
    margin: 1rem 0 1.5rem;
    font-family: var(--font-hud);
    font-size: clamp(2.5rem, 4.5vw, 4rem);
    font-weight: 600;
    line-height: 1.08;
    letter-spacing: 0.06em;
  }

  .home-hero h1 span {
    color: var(--accent);
  }

  .lede {
    max-width: 48ch;
    margin: 0;
    color: var(--text-muted);
    font-size: 1rem;
    line-height: 1.65;
  }

  .hero-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    margin-top: 2rem;
  }

  .hero-actions a {
    min-height: 3rem;
    padding-inline: 1.25rem;
    font-size: 0.875rem;
  }

  .hero-note {
    max-width: 54ch;
    margin: 1rem 0 0;
    color: var(--text-muted);
    font-size: 0.8125rem;
    line-height: 1.5;
  }

  /* An ambient compass illustration, with no catalogue positions or labels. */
  .galaxy-motif {
    position: relative;
    display: grid;
    place-items: center;
    justify-self: center;
    width: min(100%, 22rem);
    aspect-ratio: 1;
    pointer-events: none;
    background: radial-gradient(
      circle,
      color-mix(in srgb, var(--accent) 11%, transparent),
      transparent 65%
    );
  }

  .orbital {
    position: absolute;
    border: 1px solid var(--line);
    border-radius: var(--radius-pill);
  }

  .orbital-outer {
    inset: 4%;
  }

  .orbital-middle {
    inset: 17%;
    border-color: color-mix(in srgb, var(--accent) 32%, transparent);
  }

  .orbital-inner {
    inset: 31%;
  }

  .galaxy-motif :global(.galaxy-compass) {
    color: var(--accent-hi);
    filter: drop-shadow(
      0 0 20px color-mix(in srgb, var(--accent) 20%, transparent)
    );
  }

  .orbital-star {
    position: absolute;
    width: 6px;
    height: 6px;
    border-radius: var(--radius-pill);
    background: var(--text);
    box-shadow: 0 0 15px color-mix(in srgb, var(--text) 33%, transparent);
  }

  .star-one {
    top: 18%;
    left: 18%;
  }

  .star-two {
    top: 60%;
    right: 18%;
    background: var(--accent);
  }

  .star-three {
    top: 33%;
    right: 41%;
    width: 4px;
    height: 4px;
  }

  .galaxy-caption {
    position: absolute;
    bottom: 0;
    color: var(--text-muted);
    font-family: var(--font-hud);
    font-size: 0.75rem;
    letter-spacing: 0.12em;
  }

  .home-section-heading {
    display: flex;
    justify-content: space-between;
    align-items: end;
    gap: 1rem;
    margin-bottom: 1.5rem;
  }

  .home-section-heading h2 {
    margin: 0.5rem 0 0;
    font-size: clamp(1.5rem, 3vw, 2rem);
    line-height: 1.2;
  }

  .home-section-heading > span {
    color: var(--text-muted);
    font-size: 0.8125rem;
  }

  .tool-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 1rem;
  }

  .tool-card {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-content: start;
    align-items: center;
    gap: 1rem;
    padding: 1.5rem;
    text-decoration: none;
  }

  .tool-card:focus-visible {
    outline: 2px solid var(--focus);
    outline-offset: 3px;
  }

  .tool-icon {
    display: grid;
    place-items: center;
    width: 3rem;
    height: 3rem;
    border: 1px solid var(--line-strong);
    border-radius: var(--radius);
    background: var(--panel-gloss), var(--panel-sunken);
    color: var(--accent);
  }

  .tool-copy {
    grid-column: 1 / -1;
    grid-row: 2;
  }

  .tool-card h3 {
    margin: 0 0 0.5rem;
    font-family: var(--font-hud);
    font-size: 1.25rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    line-height: 1.2;
    text-transform: uppercase;
  }

  .tool-card p {
    margin: 0;
    color: var(--text-muted);
    font-size: 0.875rem;
    line-height: 1.5;
  }

  .tool-card :global(.tool-arrow) {
    grid-column: 2;
    grid-row: 1;
    color: var(--neon-hi);
  }

  .upcoming-tools {
    padding-block: 1.5rem;
  }

  .upcoming-tools p {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5rem 0.75rem;
    margin: 0;
    color: var(--text-muted);
    font-size: 0.8125rem;
    line-height: 1.5;
  }

  .upcoming-tools strong {
    color: var(--text);
    font-weight: 600;
  }

  .upcoming-tools a {
    color: var(--neon-hi);
    text-underline-offset: 0.2em;
  }

  .home-page :global(.status-panel) {
    margin: 0 0 2rem;
    padding: 1rem 1.5rem;
    gap: 1rem;
  }

  .home-page :global(.connection-label) {
    margin: 0;
    color: var(--text-muted);
    font-size: 0.875rem;
  }

  .home-page :global(.status-panel dl) {
    margin: 0;
    gap: 2rem;
  }

  .home-page :global(.status-panel dt) {
    color: var(--text-muted);
    font-size: 0.75rem;
    letter-spacing: 0.06em;
  }

  .home-page :global(.status-panel dd) {
    font-size: 0.875rem;
  }

  .site-footer {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: 1rem;
    padding-block: 1.5rem 2rem;
    color: var(--text-muted);
    font-size: 0.75rem;
  }

  .site-footer strong {
    color: var(--text);
    letter-spacing: 0.06em;
  }

  @media (max-width: 900px) {
    .home-hero,
    .tool-grid {
      grid-template-columns: minmax(0, 1fr);
    }

    .galaxy-motif {
      display: none;
    }

    .tool-card {
      grid-template-columns: auto minmax(0, 1fr) auto;
    }

    .tool-copy {
      grid-column: 2;
      grid-row: 1;
    }

    .tool-card :global(.tool-arrow) {
      grid-column: 3;
    }
  }

  @media (max-width: 600px) {
    .home-page,
    .site-footer {
      width: calc(100% - 2rem);
    }

    .home-hero {
      padding-block: 2rem 3rem;
    }

    .hero-actions {
      flex-direction: column;
      align-items: stretch;
      margin-top: 1.5rem;
    }

    .home-section-heading > span {
      display: none;
    }

    .tool-card {
      gap: 1rem;
      padding: 1rem;
    }

    .home-page :global(.status-panel) {
      align-items: flex-start;
      flex-direction: column;
      padding: 1rem;
    }

    .home-page :global(.status-panel dl) {
      flex-wrap: wrap;
      gap: 1rem 2rem;
    }
  }
</style>
