<script lang="ts">
  import { resolve } from '$app/paths';
  import type { Id64 } from '$lib/domain/id64';
  import { usePersistenceContext } from '$lib/persistence/context';
  import { buildCompareRows, compareCsv, COMPARE_MAX } from './compare-metrics';

  let { onOpenDetail } = $props<{ onOpenDetail?: (id64: Id64) => void }>();
  const { compare } = usePersistenceContext();
  const entries = $derived($compare.value);
  const rows = $derived(buildCompareRows(entries));
  const componentId = $props.id();
  const headingId = `${componentId}-compare-title`;

  function remove(id64: Id64): void {
    compare.set(entries.filter((entry) => entry.id64 !== id64));
  }

  function clear(): void {
    if (window.confirm(`Clear all ${entries.length} systems from comparison?`))
      compare.set([]);
  }

  function exportCsv(): void {
    const blob = new Blob([compareCsv(entries)], {
      type: 'text/csv;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `ed-compare-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }
</script>

<section class="compare-panel" aria-labelledby={headingId}>
  <header class="compare-heading">
    <div>
      <h2 id={headingId}>Compare systems</h2>
      <p>Up to {COMPARE_MAX} candidates side by side.</p>
    </div>
    <span class="compare-count" aria-live="polite"
      >{entries.length} / {COMPARE_MAX} systems</span
    >
    {#if entries.length > 0}
      <div class="compare-actions">
        <button type="button" class="secondary-button" onclick={exportCsv}
          >Export CSV</button
        >
        <button type="button" class="secondary-button" onclick={clear}
          >Clear comparison</button
        >
      </div>
    {/if}
  </header>

  {#if $compare.diagnostic}
    <p role="alert">
      Your comparison could not be saved or restored in this browser. Changes
      may not survive a reload.
    </p>
  {/if}

  {#if entries.length === 0}
    <div class="compare-empty">
      <h3>No systems added</h3>
      <p>
        Choose Compare on at least two systems in Finder, Watchlist or Pinned to
        see their attributes side by side.
      </p>
    </div>
  {:else}
    {#if entries.length === 1}
      <p role="status">
        Add one more system to compare your candidates side by side.
      </p>
    {/if}
    <!-- svelte-ignore a11y_no_noninteractive_tabindex (Keyboard users need to scroll the wide comparison table.) -->
    <div
      class="compare-scroll"
      role="region"
      aria-label="Comparison metrics"
      tabindex="0"
    >
      <table>
        <caption>System comparison</caption>
        <thead>
          <tr>
            <th scope="col">Metric</th>
            {#each entries as entry (entry.id64)}
              <th scope="col">
                {#if onOpenDetail}
                  <button
                    type="button"
                    class="system-name"
                    onclick={() => onOpenDetail?.(entry.id64)}
                    >{entry.name}</button
                  >
                {:else}
                  <a
                    class="system-name"
                    href={resolve(`/inspect?system=${entry.id64}`)}
                    >{entry.name}</a
                  >
                {/if}
                <button
                  type="button"
                  class="remove-system"
                  aria-label={`Remove ${entry.name} from comparison`}
                  onclick={() => remove(entry.id64)}>Remove</button
                >
              </th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each rows as row (row.label)}
            <tr>
              <th scope="row">{row.label}</th>
              {#each row.cells as cell, index (entries[index].id64)}
                <td class:best={cell.best}>
                  {cell.display}
                  {#if cell.best}<span class="best-value">Best value</span>{/if}
                </td>
              {/each}
            </tr>
          {/each}
          <tr>
            <th scope="row">Links</th>
            {#each entries as entry (entry.id64)}
              <td class="external-links">
                <a
                  href={`https://spansh.co.uk/system/${entry.id64}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={`${entry.name} on Spansh`}>Spansh ↗</a
                >
                <a
                  href={`https://inara.cz/starsystem/?search=${encodeURIComponent(entry.name)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={`${entry.name} on Inara`}>Inara ↗</a
                >
              </td>
            {/each}
          </tr>
        </tbody>
      </table>
    </div>
    <p class="compare-note">
      Best values are labelled where at least two known values differ. Shorter
      distances are better; higher scores and counts are better.
    </p>
  {/if}
  <p class="compare-note">
    Saved in this browser. Values and search reference distances reflect when
    each system was added.
  </p>
</section>

<style>
  .compare-panel {
    min-width: 0;
    border: 1px solid var(--line);
    border-radius: 0.75rem;
    background: var(--color-panel);
    padding: 1.1rem;
  }
  .compare-heading {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 1rem;
    margin-bottom: 1rem;
  }
  .compare-heading h2 {
    margin: 0;
    font-size: 1.2rem;
  }
  .compare-heading p {
    margin: 0.4rem 0 0;
    color: var(--muted);
  }
  .compare-count {
    margin-left: auto;
    font-variant-numeric: tabular-nums;
  }
  .compare-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }
  .compare-empty {
    padding: 1.5rem 0;
  }
  .compare-empty h3 {
    margin-top: 0;
  }
  .compare-empty p,
  .compare-note {
    color: var(--muted);
    line-height: 1.6;
  }
  .compare-note {
    font-size: 0.82rem;
    margin-bottom: 0;
  }
  .compare-scroll {
    max-width: 100%;
    overflow-x: auto;
    border: 1px solid var(--line);
    border-radius: 0.4rem;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.875rem;
  }
  caption {
    padding: 0.7rem;
    text-align: left;
    color: var(--muted);
  }
  th,
  td {
    padding: 0.8rem;
    text-align: left;
    border-top: 1px solid var(--line);
    vertical-align: top;
  }
  thead th {
    min-width: 12rem;
    background: var(--panel-raised);
  }
  th:first-child {
    position: sticky;
    left: 0;
    background: var(--color-panel);
    z-index: 1;
    min-width: 10rem;
  }
  tbody th {
    font-weight: 500;
  }
  .system-name,
  .remove-system {
    background: transparent;
    border: 0;
    color: inherit;
    font: inherit;
    cursor: pointer;
    text-align: left;
    padding: 0;
    text-decoration: underline;
    text-underline-offset: 0.2em;
  }
  .system-name {
    font-weight: 700;
  }
  .remove-system {
    display: block;
    color: var(--muted);
    font-size: 0.8rem;
    margin-top: 0.7rem;
  }
  .best {
    font-weight: 700;
  }
  .best-value {
    display: block;
    width: fit-content;
    margin-top: 0.4rem;
    border: 1px solid currentColor;
    border-radius: 0.2rem;
    padding: 0.15rem 0.35rem;
    font-size: 0.7rem;
  }
  .external-links a {
    display: inline-block;
    margin: 0 0.7rem 0.3rem 0;
  }
</style>
