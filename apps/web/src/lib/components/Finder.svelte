<script lang="ts">
  import {
    autocomplete,
    localSearch,
    clusterSearch,
    getWatchlist,
    addWatchlist,
    removeWatchlist,
    ApiError,
    type SearchHit,
  } from '$lib/api/client';
  import { persistentState } from '$lib/stores/persistence.svelte';
  let mode = $state<'system' | 'region'>('system'),
    refName = $state('Sol'),
    coords = $state({ x: 0, y: 0, z: 0 }),
    query = $state(''),
    hits = $state<
      Array<{ id64: string; name: string; x: number; y: number; z: number }>
    >([]),
    active = $state(-1),
    timer: ReturnType<typeof setTimeout> | undefined,
    loading = $state(false),
    error = $state(''),
    results = $state<SearchHit[]>([]),
    watchlist = $state<string[]>([]);
  $effect(() => {
    getWatchlist(persistentState.syncKey)
      .then((x) => (watchlist = x.watchlist.map((e) => String(e.system_id64))))
      .catch(() => {});
  });
  function typeahead() {
    clearTimeout(timer);
    active = -1;
    if (query.trim().length < 2) {
      hits = [];
      return;
    }
    timer = setTimeout(async () => {
      try {
        hits = (await autocomplete(query.trim())).results;
      } catch {
        hits = [];
      }
    }, 200);
  }
  function pick(hit: (typeof hits)[number]) {
    refName = hit.name;
    query = hit.name;
    coords = { x: hit.x, y: hit.y, z: hit.z };
    hits = [];
  }
  function keydown(e: KeyboardEvent) {
    if (!hits.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      active = (active + 1) % hits.length;
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      active = (active - 1 + hits.length) % hits.length;
    } else if (e.key === 'Enter' && active >= 0) {
      e.preventDefault();
      pick(hits[active]);
    } else if (e.key === 'Escape') hits = [];
  }
  async function search() {
    loading = true;
    error = '';
    try {
      const data = await localSearch({
        reference_coords: coords,
        filters: {
          distance: { min: 0, max: 200 },
          population: { comparison: 'equal', value: 0 },
        },
        size: 50,
        from: 0,
        sort_by: 'development',
        galaxy_wide: false,
        min_development_score: 0,
      });
      results = data.results;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }
  async function regions() {
    loading = true;
    error = '';
    try {
      await clusterSearch({
        slots: [{ economies: ['Industrial'] }],
        limit: 20,
        reference_coords: coords,
      });
      results = [];
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }
  async function toggleWatch(id64: string) {
    const had = watchlist.includes(id64);
    watchlist = had
      ? watchlist.filter((x) => x !== id64)
      : [id64, ...watchlist];
    try {
      if (had) await removeWatchlist(persistentState.syncKey, id64);
      else await addWatchlist(persistentState.syncKey, id64);
    } catch (e) {
      if (!(had && e instanceof ApiError && e.status === 404))
        watchlist = had
          ? [id64, ...watchlist]
          : watchlist.filter((x) => x !== id64);
      error = e instanceof Error ? e.message : String(e);
    }
  }
</script>

<section class="finder">
  <header data-testid="finder-page-heading">
    <h1>System <em>Finder</em></h1>
    <p>
      {mode === 'system'
        ? 'Find promising systems. Save them for later or inspect them before starting a plan.'
        : 'Find regions where the economies your colony needs cluster within 500 LY.'}
    </p>
    <div data-testid="finder-mode-toggle">
      <button data-active={mode === 'system'} onclick={() => (mode = 'system')}
        >Systems</button
      ><button data-active={mode === 'region'} onclick={() => (mode = 'region')}
        >Regions</button
      >
    </div>
  </header>
  {#if mode === 'system'}<form
      data-testid="search-form"
      onsubmit={(e) => {
        e.preventDefault();
        search();
      }}
    >
      <label
        >Origin system<input
          aria-label="Origin system"
          role="combobox"
          aria-expanded={hits.length > 0}
          aria-controls="reference-options"
          bind:value={query}
          oninput={typeahead}
          onkeydown={keydown}
          placeholder={refName}
        /></label
      >{#if hits.length}<ul id="reference-options" role="listbox">
          {#each hits as hit, i (hit.id64)}<li
              role="option"
              aria-selected={active === i}
            >
              <button
                type="button"
                onmousedown={(e) => e.preventDefault()}
                onclick={() => pick(hit)}>{hit.name}</button
              >
            </li>{/each}
        </ul>{/if}<button data-testid="search-submit" disabled={loading}
        >{loading ? 'Scanning…' : 'Run search'}</button
      >
    </form>
    <section data-testid="results-panel" aria-live="polite">
      {#if error}<p role="alert">Search failed: {error}</p>{:else if loading}<p>
          Scanning systems…
        </p>{:else if !results.length}<h2>Ready to search</h2>
        <p>Adjust the filters, then run a search.</p>{:else}<h2>
          {results.length} matches
        </h2>
        <ul class="results">
          {#each results as system (system.id64)}<li
              class="result-card"
              data-testid="result-card"
            >
              <h3>{system.name}</h3>
              <p>ID64 {system.id64}</p>
              <a href={`/finder/system/${system.id64}`}>Inspect</a><button
                data-testid="pin-system"
                aria-pressed={persistentState.pins.some(
                  (p) => String(p.id64) === system.id64,
                )}
                onclick={() =>
                  persistentState.togglePin({
                    id64: system.id64,
                    name: system.name,
                  })}>Pin</button
              ><button
                data-testid="watchlist-system"
                aria-pressed={watchlist.includes(system.id64)}
                onclick={() => toggleWatch(system.id64)}
                >{watchlist.includes(system.id64)
                  ? 'Remove from saved'
                  : 'Save to My Work'}</button
              >
            </li>{/each}
        </ul>{/if}
    </section>
  {:else}<form
      onsubmit={(e) => {
        e.preventDefault();
        regions();
      }}
    >
      <label
        >Required economy<select
          ><option>Industrial</option><option>High Tech</option></select
        ></label
      ><button disabled={loading}>Search regions</button>
    </form>
    <section data-testid="cluster-results-panel">
      <h2>Find region clusters</h2>
    </section>{/if}
</section>
